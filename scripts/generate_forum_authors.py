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
      pid_to_key:   person_id (int) → group_key (str, e.g. 'fedor')
      key_to_group: group_key → {slug, canonical, pids: set}
    """
    pid_to_key = {}
    key_to_group = {}

    if AUTHOR_GROUPS_YAML.exists():
        groups = yaml.safe_load(AUTHOR_GROUPS_YAML.read_text(encoding='utf-8')) or []
        for g in groups:
            slug = g['slug']
            canonical = g['canonical']
            pids = {g['pid']} | set(g.get('extra_pids', []) or [])
            key_to_group[slug] = {'slug': slug, 'canonical': canonical, 'pids': pids}
            for pid in pids:
                pid_to_key[int(pid)] = slug

    return pid_to_key, key_to_group


# ── Build full author data ─────────────────────────────────────────────────

def build_author_data():
    """
    Scan all topic YAMLs. Return:
      - all_authors: dict author_key → AuthorRecord
      - pid_name_map: dict (pid, name) → author_key  (for slug lookup)
      - name_to_slug: dict poster-name → slug (for forum post rendering)
      - slug_map: dict slug → author_key
    """
    pid_to_key, key_to_group = _load_groups()

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

    def _norm(name):
        """Normalize whitespace and spacing around parentheses for name matching."""
        name = ' '.join(name.split())
        name = re.sub(r'(\S)\(', r'\1 (', name)  # ensure space before (
        return name

    def _post_author_key(p):
        """Return the author_key for a post: pid-based if possible, else normalized name."""
        pid = p.get('person_id')
        if pid:
            pid = int(pid)
            if pid in pid_to_key:
                return pid_to_key[pid]
            return f'pid:{pid}'
        name = _norm((p.get('poster') or '').strip())
        return f'name:{name}' if name else None

    def _display_name(p, ak):
        """Best display name for an author_key."""
        if ak and ak.startswith('pid:') is False and not ak.startswith('name:'):
            # grouped: use canonical
            return key_to_group[ak]['canonical']
        pid = p.get('person_id')
        return (p.get('poster') or '').strip()

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
                if name:
                    nname = _norm(name)
                    # Prefer pid-based attribution; don't overwrite with name-based
                    existing = name_to_ak.get(nname)
                    if existing is None or existing.startswith('name:'):
                        name_to_ak[nname] = ak
            all_topic_posts.append((p, ak))

        topic_meta[tid] = {
            'title': ttitle,
            'slug': tslug,
            'first_post': str(t.get('first_post', '') or ''),
            'post_count': t.get('post_count', 0),
            'participant_count': len(participant_aks),
            'first_poster_ak': first_ak,
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

    # Merge name-keyed entries into the pid group when the name was used by that group.
    # e.g. pid=2 posted as "Федор Романенко" → name_to_ak["Федор Романенко"] = "fedor"
    # Any name:Федор Романенко posts (no pid) belong to the same person.
    for name, target_ak in list(name_to_ak.items()):
        src_ak = f'name:{name}'
        if src_ak in ak_posts_list and src_ak != target_ak:
            ak_posts_list[target_ak].extend(ak_posts_list.pop(src_ak))
            ak_topics_started[target_ak].update(ak_topics_started.pop(src_ak, set()))
            ak_replies_tids[target_ak].update(ak_replies_tids.pop(src_ak, set()))
            for tid_s, parts in ak_started_participants.pop(src_ak, {}).items():
                ak_started_participants[target_ak][tid_s].update(parts)

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

    return all_authors, topic_meta, name_to_slug, slug_map


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

    # Top 10 started topics by participant count
    topic_scores = []
    for tid in topics_started_ids:
        tm = topic_meta.get(tid)
        if not tm:
            continue
        topic_scores.append({
            'topic_id': tid,
            'title': tm['title'],
            'slug': tm['slug'],
            'first_post': tm['first_post'],
            'post_count': tm['post_count'],
            'participant_count': tm['participant_count'],
        })
    topic_scores.sort(key=lambda x: (-x['participant_count'], -x['post_count']))
    top_topics = topic_scores[:10]

    # Format dates
    for t in top_topics:
        fp = t.get('first_post', '')
        if fp and len(fp) >= 10:
            try:
                dt = datetime.strptime(fp[:10], '%Y-%m-%d')
                t['first_post_fmt'] = dt.strftime('%d.%m.%Y')
            except ValueError:
                t['first_post_fmt'] = fp[:10]
        else:
            t['first_post_fmt'] = fp

    # Activity by year → month — only started topics
    by_year_month = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in posts:
        if p['topic_id'] not in topics_started_ids:
            continue
        # Use only the first post in each started topic (the opening post)
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
                    topic_refs.append({
                        'topic_title': html_mod.escape(p['topic_title'][:55]),
                        'topic_slug': p['topic_slug'],
                        'post_id': p['post_id'],
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

    tmpl = JINJA_ENV.get_template('forum_author.html.j2')
    out = tmpl.render(
        author_name=html_mod.escape(name),
        author_slug=slug,
        total_posts=rec['total_posts'],
        topics_count=rec['topics'],
        replies_count=rec['replies'],
        participants_count=rec['participants'],
        top_topics=top_topics,
        activity=activity,
    )
    (dst_dir / 'index.html').write_text(out, encoding='utf-8')


def generate_authors_index(all_authors: dict, name_to_slug: dict):
    """Generate /forum/authors/index.html with top-50 + JS search."""
    # Sort by topics started (Темы) descending
    ranked = sorted(
        all_authors.values(),
        key=lambda a: (-a['topics'], -a['total_posts'])
    )

    # Build JSON data for JS search (all authors)
    search_data = []
    for rec in ranked:
        entry = {
            'name': rec['name'],
            'slug': rec.get('slug'),      # null if no page
            'topics': rec['topics'],
            'replies': rec['replies'],
            'participants': rec['participants'],
            'topic_links': rec['topic_links'] if not rec['has_page'] else [],
        }
        search_data.append(entry)

    top50 = ranked[:50]

    tmpl = JINJA_ENV.get_template('forum_authors.html.j2')
    out = tmpl.render(
        top50=top50,
        search_data_json=json.dumps(search_data, ensure_ascii=False),
        total_authors=len(all_authors),
    )
    dst = SITE / 'forum' / 'authors'
    dst.mkdir(parents=True, exist_ok=True)
    (dst / 'index.html').write_text(out, encoding='utf-8')
    print(f'  Authors index: {len(all_authors)} total, top-50 shown')


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
    all_authors, topic_meta, name_to_slug, slug_map = build_author_data()

    save_author_slugs(name_to_slug)

    page_count = 0
    for name, rec in all_authors.items():
        if rec['has_page']:
            generate_author_page(rec, rec['slug'])
            page_count += 1

    generate_authors_index(all_authors, name_to_slug)
    print(f'  Generated {page_count} author pages')
    return name_to_slug


if __name__ == '__main__':
    generate_forum_authors()
