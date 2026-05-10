#!/usr/bin/env python3
"""
Generate forum author pages and the authors index.

Identity: person_id is the primary key. author_groups.yaml clusters multiple
person_ids (re-registrations) into one canonical author with one slug.
Posts without person_id are keyed by name string and get their own entry.

For each author with >= 3 posts:
  /forum/{slug}/  — author page (top-10 started topics + topics-by-year history)

/forum/authors/   — index sorted by Темы, top-50 shown + JS search over all

Terminology (non-intersecting):
  Темы    = topics the author STARTED (first poster)
  Ответы  = posts the author made in OTHER people's topics
  Авторы  = unique participants in topics the author started (excl. self)
"""
import sys
import re
import yaml
import json
import glob
import collections
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_shared import JINJA_ENV, SITE, ARC, DATA, TOPICS_DIR, html_mod, SPAM_IDS

MIN_TOPICS = 3  # minimum started topics to get an author page

# ── Transliteration ────────────────────────────────────────────────────────

_CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}

def _transliterate(s: str) -> str:
    out = []
    for ch in s.lower():
        out.append(_CYR.get(ch, ch))
    return ''.join(out)


def author_slug(name: str) -> str:
    m = re.search(r'\(([^)]+)\)', name)
    if m:
        nick = m.group(1).strip()
        latin_ratio = sum(1 for c in nick if c.isascii() and c.isalpha()) / max(len(nick), 1)
        if latin_ratio >= 0.7:
            nick_slug = re.sub(r'[^a-z0-9]+', '-', nick.lower()).strip('-')
            if nick_slug:
                return nick_slug

    base = re.sub(r'\s*\([^)]*\)', '', name).strip()
    translit = _transliterate(base)
    slug = re.sub(r'[^a-z0-9]+', '-', translit.lower()).strip('-')
    return slug or 'author'


# ── Post tree traversal ────────────────────────────────────────────────────

def _iter_posts(posts):
    for p in posts:
        pid = p.get('id')
        if pid in SPAM_IDS:
            continue
        yield p
        yield from _iter_posts(p.get('replies', []))


# ── Author groups (person_id clustering) ──────────────────────────────────

AUTHOR_GROUPS_YAML = DATA / 'forum' / 'author_groups.yaml'


def _load_groups():
    """
    Return:
      pid_to_key:    person_id (int) → group_key
      name_to_key:   normalized poster name (str) → group_key
      key_to_group:  group_key → {slug, canonical, pids: set}
    """
    pid_to_key = {}
    name_to_key = {}
    key_to_group = {}

    if AUTHOR_GROUPS_YAML.exists():
        groups = yaml.safe_load(AUTHOR_GROUPS_YAML.read_text(encoding='utf-8')) or []
        for g in groups:
            slug = g['slug']
            canonical = g['canonical']
            pids = {g['pid']} | set(g.get('extra_pids', []) or [])
            extra_names = g.get('names', []) or []
            key_to_group[slug] = {'slug': slug, 'canonical': canonical, 'pids': pids}
            for pid in pids:
                pid_to_key[int(pid)] = slug
            for name in extra_names:
                # Normalize same way as _norm() — collapse whitespace + space before (
                n = ' '.join(name.split())
                n = re.sub(r'(\S)\(', r'\1 (', n)
                name_to_key[n] = slug

    return pid_to_key, name_to_key, key_to_group


# ── Build full author data ─────────────────────────────────────────────────

def build_author_data():
    """
    Scan all topic YAMLs. Return:
      - all_authors: dict author_key → AuthorRecord
      - pid_name_map: dict (pid, name) → author_key  (for slug lookup)
      - name_to_slug: dict poster-name → slug (for forum post rendering)
      - slug_map: dict slug → author_key
    """
    pid_to_key, group_name_to_key, key_to_group = _load_groups()

    topic_files = sorted(glob.glob(
        str(TOPICS_DIR / '**' / '*.yaml'), recursive=True
    ))
    print(f'  Scanning {len(topic_files)} topic files…')

    topic_meta = {}  # topic_id → dict

    # Accumulators keyed by author_key (pid-based or name-based)
    ak_posts_list = collections.defaultdict(list)
    ak_topics_started = collections.defaultdict(set)
    ak_replies_tids = collections.defaultdict(set)
    # author_key → {topic_id → set of participant author_keys}
    ak_started_participants = collections.defaultdict(lambda: collections.defaultdict(set))
    # poster-name → author_key (for slug lookup after)
    name_to_ak = {}

    # pid-name counts: track how many pid posts each author made under each name
    # Used post-scan to build name_to_ak with proportional threshold (no auto-merge).
    ak_pid_name_counts = collections.defaultdict(lambda: collections.defaultdict(int))

    # Proportional threshold: keep name if ≥3 posts AND ≥5% of author's total pid posts
    _MIN_PID_ABS = 3
    _MIN_PID_FRAC = 0.05

    def _norm(name):
        """Normalize whitespace and spacing around parentheses for name matching."""
        name = ' '.join(name.split())
        name = re.sub(r'(\S)\(', r'\1 (', name)
        return name

    def _post_author_key(p):
        """Return the author_key for a post.
        Priority: person_id → inferred_person_id → explicit yaml names → name-string.
        No name inference — inferred pids must be set explicitly in source YAML.
        """
        pid = p.get('person_id') or p.get('inferred_person_id')
        if pid:
            pid = int(pid)
            if pid in pid_to_key:
                return pid_to_key[pid]
            return f'pid:{pid}'
        name = _norm((p.get('poster') or '').strip())
        if name and name in group_name_to_key:
            return group_name_to_key[name]
        return f'name:{name}' if name else None

    for fpath in topic_files:
        with open(fpath, encoding='utf-8') as f:
            t = yaml.safe_load(f)
        tid = t.get('topic_id')
        if not tid:
            continue
        tslug = f'topic{tid}'
        ttitle = t.get('title', '')
        posts_list = t.get('posts', [])

        # First non-deleted poster → author_key
        first_ak = None
        first_name = ''
        for p in _iter_posts(posts_list):
            if not p.get('deleted'):
                ak = _post_author_key(p)
                name = _norm((p.get('poster') or '').strip())
                if ak and name:
                    first_ak = ak
                    first_name = name
                    break

        # Collect all participant author_keys
        participant_aks = set()
        all_topic_posts = []
        for p in _iter_posts(posts_list):
            if p.get('deleted'):
                continue
            ak = _post_author_key(p)
            name = (p.get('poster') or '').strip()
            if ak:
                participant_aks.add(ak)
                # Count pid-based name usage for post-scan threshold filtering
                if name and (p.get('person_id') or p.get('inferred_person_id')):
                    ak_pid_name_counts[ak][_norm(name)] += 1
            all_topic_posts.append((p, ak))

        # Collect poster display names + counts for search index
        poster_name_counts = {}  # norm_name → [count, best_display_name]
        for p, _ak in all_topic_posts:
            raw = (p.get('poster') or '').strip()
            if raw:
                nname = _norm(raw)
                if nname not in poster_name_counts:
                    poster_name_counts[nname] = [0, raw]
                poster_name_counts[nname][0] += 1

        post_count_val = t.get('post_count', 0) or 0
        engagement = len(participant_aks) + post_count_val / 5.0

        topic_meta[tid] = {
            'title': ttitle,
            'slug': tslug,
            'first_post': str(t.get('first_post', '') or ''),
            'post_count': post_count_val,
            'participant_count': len(participant_aks),
            'first_poster_ak': first_ak,
            'first_poster_norm': _norm(first_name) if first_name else '',
            'poster_name_counts': poster_name_counts,
            'engagement': engagement,
        }

        # Record per-author data
        for p, ak in all_topic_posts:
            if not ak:
                continue
            name = _norm((p.get('poster') or '').strip())
            date_str = str(p.get('date', '') or '')
            ak_posts_list[ak].append({
                'topic_id': tid,
                'topic_title': ttitle,
                'topic_slug': tslug,
                'date': date_str,
                'post_id': p.get('id'),
                'subject': p.get('subject', '') or '',
                'display_name': name,
            })

        if first_ak:
            ak_topics_started[first_ak].add(tid)
            others = participant_aks - {first_ak}
            ak_started_participants[first_ak][tid] = others

        for ak in participant_aks:
            if ak != first_ak:
                ak_replies_tids[ak].add(tid)

    # Build name_to_ak for rendering links and search slug lookup.
    # Only use names that meet the proportional threshold (significant pid usage).
    # No auto-merge of name-keyed entries — attribution requires real/inferred pid
    # or explicit yaml names field. Pre-pid posts stay as name:X until reviewed.
    for ak, name_counts in ak_pid_name_counts.items():
        total = sum(name_counts.values())
        if not total:
            continue
        for nname, count in name_counts.items():
            if count >= _MIN_PID_ABS and count / total >= _MIN_PID_FRAC:
                existing = name_to_ak.get(nname)
                if existing is None or existing.startswith('name:'):
                    name_to_ak[nname] = ak
    # Explicit yaml names always take priority
    for nname, ak in group_name_to_key.items():
        existing = name_to_ak.get(nname)
        if existing is None or existing.startswith('name:'):
            name_to_ak[nname] = ak

    # Build display name per author_key: canonical from groups, or most-used name
    ak_name_counts = collections.defaultdict(lambda: collections.defaultdict(int))
    for ak, posts in ak_posts_list.items():
        for p in posts:
            ak_name_counts[ak][p['display_name']] += 1

    def _best_name(ak):
        if ak in key_to_group:
            return key_to_group[ak]['canonical']
        counts = ak_name_counts.get(ak, {})
        if not counts:
            return ak
        return max(counts, key=counts.get)

    # Build AuthorRecord per author_key
    all_authors = {}
    for ak, posts in ak_posts_list.items():
        topics_started_ids = ak_topics_started.get(ak, set())
        t_count = len(topics_started_ids)
        r_count = sum(1 for p in posts if p['topic_id'] not in topics_started_ids)

        participants_set = set()
        for tid_s in topics_started_ids:
            participants_set.update(ak_started_participants[ak].get(tid_s, set()))
        av_count = len(participants_set)

        has_page = t_count >= MIN_TOPICS

        # Topic links for authors without page (their started topics)
        topic_links = []
        if not has_page:
            seen = {}
            for p in sorted(posts, key=lambda x: x.get('date', ''), reverse=True):
                if p['topic_id'] in topics_started_ids and p['topic_id'] not in seen:
                    seen[p['topic_id']] = True
                    topic_links.append({'id': p['topic_id'], 'title': p['topic_title'][:60]})

        all_authors[ak] = {
            'ak': ak,
            'name': _best_name(ak),
            'slug': None,
            'topics': t_count,
            'replies': r_count,
            'participants': av_count,
            'total_posts': len(posts),
            'has_page': has_page,
            'topic_links': topic_links,
            'posts_list': posts,
            'topics_started_ids': topics_started_ids,
            'topic_meta': topic_meta,
        }

    # Assign slugs — groups get their canonical slug, others derived from name
    slug_map = {}

    def _assign_slug(ak, preferred_slug=None):
        s = preferred_slug or author_slug(_best_name(ak))
        if s not in slug_map:
            slug_map[s] = ak
            return s
        i = 2
        while f'{s}-{i}' in slug_map:
            i += 1
        s = f'{s}-{i}'
        slug_map[s] = ak
        return s

    # First assign grouped authors (deterministic slugs)
    for slug, grp in key_to_group.items():
        ak = slug  # group key == slug for listed groups
        if ak in all_authors:
            all_authors[ak]['slug'] = _assign_slug(ak, preferred_slug=slug)

    # Then assign all remaining page authors sorted by topics desc
    remaining = sorted(
        (a for a in all_authors.values() if a['has_page'] and a['slug'] is None),
        key=lambda a: (-a['topics'], -a['total_posts'])
    )
    for rec in remaining:
        rec['slug'] = _assign_slug(rec['ak'])

    # Build name→slug map for post rendering (all known poster names)
    name_to_slug = {}
    for name, ak in name_to_ak.items():
        if ak in all_authors and all_authors[ak]['slug']:
            name_to_slug[name] = all_authors[ak]['slug']

    return all_authors, topic_meta, name_to_slug, slug_map, name_to_ak


# ── Page generation ────────────────────────────────────────────────────────

def _month_name_ru(month: int) -> str:
    months = ['', 'янв', 'фев', 'мар', 'апр', 'май', 'июн',
              'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
    return months[month] if 1 <= month <= 12 else ''


def generate_author_page(rec: dict, slug: str):
    """Generate /forum/{slug}/index.html for one author."""
    name = rec['name']
    posts = rec['posts_list']
    topic_meta = rec['topic_meta']
    topics_started_ids = rec['topics_started_ids']

    dst_dir = SITE / 'forum' / slug
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Top 30 started topics with ≥2 replying authors (excl. topic-starter)
    topic_scores = []
    for tid in topics_started_ids:
        tm = topic_meta.get(tid)
        if not tm:
            continue
        replying_authors = tm['participant_count'] - 1  # excl. starter (for filter)
        if replying_authors < 2:
            continue
        topic_scores.append({
            'topic_id': tid,
            'title': tm['title'],
            'slug': tm['slug'],
            'first_post': tm['first_post'],
            'post_count': max(0, tm['post_count'] - 1),    # Ответы (excl. opening post)
            'participant_count': tm['participant_count'],    # Участники (incl. starter)
        })
    topic_scores.sort(key=lambda x: (-x['participant_count'], -x['post_count']))
    top_topics = topic_scores[:100]  # pass all (up to 100) for JS show-more

    # Format dates
    for t in top_topics:
        fp = t.get('first_post', '')
        if fp and len(fp) >= 10:
            try:
                dt = datetime.strptime(fp[:10], '%Y-%m-%d')
                t['first_post_fmt'] = dt.strftime('%d.%m.%Y')
                t['year'] = dt.year
            except ValueError:
                t['first_post_fmt'] = fp[:10]
                t['year'] = fp[:4]
        else:
            t['first_post_fmt'] = fp
            t['year'] = ''

    # Activity by year → month — one entry per started topic at its start date
    topic_first_post = {}
    for p in sorted(posts, key=lambda x: x.get('date', '')):
        tid = p['topic_id']
        if tid in topics_started_ids and tid not in topic_first_post:
            topic_first_post[tid] = p

    by_year_month = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in topic_first_post.values():
        date_str = p.get('date', '') or ''
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
            by_year_month[dt.year][dt.month].append(p)
        except (ValueError, TypeError):
            by_year_month[0][0].append(p)

    activity = []
    for year in sorted(by_year_month.keys(), reverse=True):
        months = []
        t_year = 0
        for month in sorted(by_year_month[year].keys()):
            month_posts = sorted(by_year_month[year][month], key=lambda p: p.get('date', ''))
            seen_topics = {}
            topic_refs = []
            for p in month_posts:
                tid = p['topic_id']
                if tid not in seen_topics:
                    seen_topics[tid] = True
                    tm_entry = topic_meta.get(tid, {})
                    topic_refs.append({
                        'topic_title': html_mod.escape(p['topic_title'][:55]),
                        'topic_slug': p['topic_slug'],
                        'post_id': p['post_id'],
                        'post_count': max(0, (tm_entry.get('post_count', 1) or 1) - 1),
                        'participant_count': tm_entry.get('participant_count', 0) or 0,
                    })
            t_month = len(topic_refs)
            t_year += t_month
            months.append({
                'month': month,
                'month_name': _month_name_ru(month),
                'topics_count': t_month,
                'topic_refs': topic_refs,
            })
        activity.append({
            'year': year,
            'topics_count': t_year,
            'months': months,
        })

    import urllib.parse
    # Build clean search query: "Имя Фамилия (nick)" → "имя фамилия nick"
    _m = re.match(r'^(.*?)\s*\(([^)]+)\)\s*$', name)
    if _m:
        _query = f'{_m.group(1).strip().lower()} {_m.group(2).strip().lower()}'
    else:
        _query = name.lower()
    author_search_url = f'/forum/authors/#q={urllib.parse.quote(_query)}'

    tmpl = JINJA_ENV.get_template('forum_author.html.j2')
    out = tmpl.render(
        author_name=html_mod.escape(name),
        author_slug=slug,
        top_topics=top_topics,
        activity=activity,
        author_search_url=author_search_url,
        topics_count=rec['topics'],
        replies_count=rec['replies'],
    )
    (dst_dir / 'index.html').write_text(out, encoding='utf-8')


def generate_authors_index(all_authors: dict, name_to_slug: dict, topic_meta: dict, name_to_ak: dict):
    """Generate /forum/authors/index.html and site/data/forum-search-index.json."""
    ranked = sorted(
        all_authors.values(),
        key=lambda a: (-a['topics'], -a['total_posts'])
    )
    registered = [r for r in ranked if r['has_page']]

    # Build ak → all known names (for alt_names in search)
    ak_to_names = collections.defaultdict(set)
    for norm_name, ak in name_to_ak.items():
        ak_to_names[ak].add(norm_name)

    # Compute date range (first/last year starting a topic) for each registered author
    for rec in registered:
        years = []
        for tid in rec.get('topics_started_ids', set()):
            tm_entry = topic_meta.get(tid)
            if tm_entry:
                fp = tm_entry.get('first_post', '')
                if fp and len(fp) >= 4:
                    try:
                        years.append(int(fp[:4]))
                    except ValueError:
                        pass
        rec['fy'] = min(years) if years else None
        rec['ty'] = max(years) if years else None

    # Build JSON for JS author search (registered authors only, with alt names)
    search_data = []
    for rec in registered:
        ak = rec['ak']
        canonical_lower = rec['name'].lower()
        alt_names = [n for n in ak_to_names.get(ak, set()) if n.lower() != canonical_lower]
        entry = {
            'name': rec['name'],
            'alt': alt_names,
            'slug': rec['slug'],
            'topics': rec['topics'],
            'replies': rec['replies'],
            'fy': rec['fy'],
            'ty': rec['ty'],
        }
        search_data.append(entry)

    tmpl = JINJA_ENV.get_template('forum_authors.html.j2')
    out = tmpl.render(
        all_authors=registered,
        search_data_json=json.dumps(search_data, ensure_ascii=False),
        total_authors=len(registered),
    )
    dst = SITE / 'forum' / 'authors'
    dst.mkdir(parents=True, exist_ok=True)
    (dst / 'index.html').write_text(out, encoding='utf-8')
    print(f'  Authors index: {len(registered)} registered authors')

    # Build forum-search-index.json for lazy-loaded topic/reply search
    topics_index = []
    for tid, tm in topic_meta.items():
        pnc = tm.get('poster_name_counts', {})
        if not pnc:
            continue
        # Starter slug comes directly from first_poster_ak (real pid or explicit yaml name).
        # No name inference — pre-pid posts have ak='name:X' and produce no starter slug.
        starter_ak = tm.get('first_poster_ak', '')
        starter_slug = ''
        if starter_ak and starter_ak in all_authors:
            starter_slug = all_authors[starter_ak].get('slug') or ''
        first_norm = tm.get('first_poster_norm', '')
        posters = sorted(
            [[dname[:50], cnt, norm == first_norm, name_to_slug.get(norm, '')]
             for norm, (cnt, dname) in pnc.items()],
            key=lambda x: -x[1]
        )
        post_count = tm.get('post_count', 0) or 0
        fp = tm.get('first_post', '')
        try:
            topic_year = int(fp[:4]) if fp and len(fp) >= 4 else None
        except ValueError:
            topic_year = None
        topics_index.append({
            'tid': tid,
            's': tm['slug'],
            't': tm['title'][:80],
            'e': round(tm.get('engagement', 0), 1),
            'n': max(0, post_count - 1),       # Ответы (excl. opening post)
            'u': tm['participant_count'],        # Участники (all incl. starter)
            'ss': starter_slug,
            'y': topic_year,
            'p': posters,
        })
    topics_index.sort(key=lambda x: -x['e'])

    idx_path = SITE / 'data' / 'forum-search-index.json'
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    idx_path.write_text(json.dumps(topics_index, ensure_ascii=False), encoding='utf-8')
    print(f'  Forum search index: {len(topics_index)} topics → forum-search-index.json')


# ── Slug index ─────────────────────────────────────────────────────────────

AUTHOR_SLUGS_JSON = DATA / 'forum' / 'author-slugs.json'


def save_author_slugs(name_to_slug: dict):
    AUTHOR_SLUGS_JSON.write_text(
        json.dumps(name_to_slug, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f'  Author slugs: {len(name_to_slug)} names → {AUTHOR_SLUGS_JSON.name}')


def load_author_slugs() -> dict:
    if not AUTHOR_SLUGS_JSON.exists():
        return {}
    return json.loads(AUTHOR_SLUGS_JSON.read_text(encoding='utf-8'))


# ── Main ──────────────────────────────────────────────────────────────────

def generate_forum_authors():
    print('Generating forum author pages…')
    all_authors, topic_meta, name_to_slug, slug_map, name_to_ak = build_author_data()

    save_author_slugs(name_to_slug)

    page_count = 0
    for name, rec in all_authors.items():
        if rec['has_page']:
            generate_author_page(rec, rec['slug'])
            page_count += 1

    generate_authors_index(all_authors, name_to_slug, topic_meta, name_to_ak)
    print(f'  Generated {page_count} author pages')
    return name_to_slug


if __name__ == '__main__':
    generate_forum_authors()
