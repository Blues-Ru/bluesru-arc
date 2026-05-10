#!/usr/bin/env python3
"""
Generate forum author pages and the authors index.

For each author with >= 3 posts:
  /forum/{slug}/  — author page (top-10 topics + activity history)

/forum/authors/   — index with top-50 + JS search over all authors

Terminology (non-intersecting):
  Темы    = topics the author STARTED (first poster)
  Ответы  = posts the author made in OTHER people's topics
  Авторы  = unique participants in topics the author started (excl. self)

Ranking = Авторы + Ответы / 5
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

MIN_POSTS = 3

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


# ── Build full author data ─────────────────────────────────────────────────

def build_author_data():
    """
    Scan all topic YAMLs. Return:
      - all_authors: dict name → AuthorRecord
      - name_to_slug: dict name → slug (only for authors with page)
      - slug_map: dict slug → name

    AuthorRecord has:
      posts_list: list of post dicts (for page generation)
      topics_started: int
      replies: int
      participants_in_started: set of names
      topic_meta: dict of {topic_id → {title, slug, participants, ...}}
    """
    topic_files = sorted(glob.glob(
        str(TOPICS_DIR / '**' / '*.yaml'), recursive=True
    ))
    print(f'  Scanning {len(topic_files)} topic files…')

    # Per-topic metadata (participants, first_poster)
    topic_meta = {}  # topic_id → dict

    # Per-author accumulators
    author_posts_list = collections.defaultdict(list)  # name → list of post records
    author_topics_started = collections.defaultdict(set)  # name → set of topic_ids started
    author_replies_tids = collections.defaultdict(set)   # name → set of topic_ids replied in (NOT started)
    # For each topic started by X: participants (excluding X)
    started_topic_participants = collections.defaultdict(lambda: collections.defaultdict(set))
    # name → {topic_id → set of participants}

    for fpath in topic_files:
        with open(fpath, encoding='utf-8') as f:
            t = yaml.safe_load(f)
        tid = t.get('topic_id')
        if not tid:
            continue
        tslug = f'topic{tid}'
        ttitle = t.get('title', '')
        posts_list = t.get('posts', [])

        # First poster
        first_poster = ''
        for p in _iter_posts(posts_list):
            if not p.get('deleted'):
                raw = (p.get('poster') or '').strip()
                if raw:
                    first_poster = raw
                    break

        # Collect all participants
        participants = set()
        all_topic_posts = []
        for p in _iter_posts(posts_list):
            if p.get('deleted'):
                continue
            poster = (p.get('poster') or '').strip()
            if poster:
                participants.add(poster)
            all_topic_posts.append(p)

        topic_meta[tid] = {
            'title': ttitle,
            'slug': tslug,
            'first_post': str(t.get('first_post', '') or ''),
            'post_count': t.get('post_count', 0),
            'participants': participants,
            'participant_count': len(participants),
            'first_poster': first_poster,
        }

        # Record per-author data
        for p in all_topic_posts:
            poster = (p.get('poster') or '').strip()
            if not poster:
                continue
            date_str = str(p.get('date', '') or '')
            author_posts_list[poster].append({
                'topic_id': tid,
                'topic_title': ttitle,
                'topic_slug': tslug,
                'date': date_str,
                'post_id': p.get('id'),
                'subject': p.get('subject', '') or '',
                'is_start': poster == first_poster and p.get('id') == all_topic_posts[0].get('id'),
            })

        if first_poster:
            author_topics_started[first_poster].add(tid)
            others = participants - {first_poster}
            started_topic_participants[first_poster][tid] = others

        for poster in participants:
            if poster != first_poster:
                author_replies_tids[poster].add(tid)

    # Build AuthorRecord per name
    all_authors = {}
    all_names = set(author_posts_list.keys())

    for name in all_names:
        posts = author_posts_list[name]
        topics_started_ids = author_topics_started.get(name, set())
        replies_ids = author_replies_tids.get(name, set())

        # Count: Темы = unique topics started, Ответы = posts in non-started topics
        t_count = len(topics_started_ids)
        r_posts = sum(1 for p in posts if p['topic_id'] not in topics_started_ids)
        r_count = r_posts  # number of reply posts

        # Авторы = unique participants across started topics (excluding self)
        participants_set = set()
        for tid_s in topics_started_ids:
            participants_set.update(started_topic_participants[name].get(tid_s, set()))
        av_count = len(participants_set)

        rank = av_count + r_count / 5.0

        has_page = len(posts) >= MIN_POSTS

        # Topic links for authors without page
        topic_links = []
        if not has_page:
            seen = {}
            for p in sorted(posts, key=lambda x: x.get('date', ''), reverse=True):
                tid = p['topic_id']
                if tid not in seen:
                    seen[tid] = {'id': tid, 'title': p['topic_title'][:60]}
                    topic_links.append(seen[tid])

        all_authors[name] = {
            'name': name,
            'slug': None,
            'topics': t_count,
            'replies': r_count,
            'participants': av_count,
            'rank': rank,
            'total_posts': len(posts),
            'has_page': has_page,
            'topic_links': topic_links,
            'posts_list': posts,
            'topics_started_ids': topics_started_ids,
            'topic_meta': topic_meta,
        }

    # Assign slugs to page authors, handle collisions
    slug_map = {}
    name_to_slug = {}
    page_authors = sorted(
        (a for a in all_authors.values() if a['has_page']),
        key=lambda a: -a['rank']
    )
    for rec in page_authors:
        name = rec['name']
        s = author_slug(name)
        if s not in slug_map:
            slug_map[s] = name
        else:
            i = 2
            while f'{s}-{i}' in slug_map:
                i += 1
            s = f'{s}-{i}'
            slug_map[s] = name
        rec['slug'] = s
        all_authors[name]['slug'] = s
        name_to_slug[name] = s

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

    # Top 10 topics by participant count
    topic_ids_posted = set(p['topic_id'] for p in posts)
    topic_scores = []
    for tid in topic_ids_posted:
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
            'is_started': tid in topics_started_ids,
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

    # Activity by year → month
    by_year_month = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in posts:
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
        r_year = 0
        for month in sorted(by_year_month[year].keys()):
            month_posts = sorted(by_year_month[year][month], key=lambda p: p.get('date', ''))
            t_month = sum(1 for p in month_posts if p['topic_id'] in topics_started_ids)
            r_month = len(month_posts) - t_month
            t_year += t_month
            r_year += r_month
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
                        'is_start': p['topic_id'] in topics_started_ids,
                    })
            months.append({
                'month': month,
                'month_name': _month_name_ru(month),
                'topics_count': t_month,
                'replies_count': r_month,
                'topic_refs': topic_refs,
            })
        activity.append({
            'year': year,
            'topics_count': t_year,
            'replies_count': r_year,
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
        rank=rec['rank'],
        top_topics=top_topics,
        activity=activity,
    )
    (dst_dir / 'index.html').write_text(out, encoding='utf-8')


def generate_authors_index(all_authors: dict, name_to_slug: dict):
    """Generate /forum/authors/index.html with top-50 + JS search."""
    # Build ranked list of all authors
    ranked = sorted(
        all_authors.values(),
        key=lambda a: -a['rank']
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
            'rank': round(rec['rank'], 1),
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
