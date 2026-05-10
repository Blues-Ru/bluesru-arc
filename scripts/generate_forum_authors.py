#!/usr/bin/env python3
"""
Generate forum author pages at /forum/{slug}/.

For authors with >= 3 non-deleted posts:
  - Top 10 most engaging topics (by unique participant count)
  - Full activity history: posts by year/month with links to bookmarks

Also builds an author slug index used by generate_forum.py to link names.
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
    """
    Generate a URL slug from an author name.
    Prefers the Latin nickname in parentheses if present.
    Falls back to transliterated full name.
    """
    # Extract nickname: "Name (nickname)"
    m = re.search(r'\(([^)]+)\)', name)
    if m:
        nick = m.group(1).strip()
        # Use nickname if it's mostly Latin
        latin_ratio = sum(1 for c in nick if c.isascii() and c.isalpha()) / max(len(nick), 1)
        if latin_ratio >= 0.7:
            nick_slug = re.sub(r'[^a-z0-9]+', '-', nick.lower()).strip('-')
            if nick_slug:
                return nick_slug

    # Strip nickname part, transliterate
    base = re.sub(r'\s*\([^)]*\)', '', name).strip()
    translit = _transliterate(base)
    slug = re.sub(r'[^a-z0-9]+', '-', translit.lower()).strip('-')
    return slug or 'author'


# ── Post tree traversal ────────────────────────────────────────────────────

def _iter_posts(posts):
    """Yield (post_id, poster, date, subject, deleted) recursively."""
    for p in posts:
        pid = p.get('id')
        if pid in SPAM_IDS:
            continue
        yield p
        yield from _iter_posts(p.get('replies', []))


def _count_participants(posts) -> set:
    participants = set()
    for p in _iter_posts(posts):
        if not p.get('deleted'):
            poster = (p.get('poster') or '').strip()
            if poster:
                participants.add(poster)
    return participants


# ── Build author index ─────────────────────────────────────────────────────

def build_author_index():
    """
    Scan all topic YAMLs. Return:
      - authors: {name → AuthorData}
      - slug_to_name: {slug → name}  (for linking in forum posts)
    """
    # Per-author: list of (topic_id, topic_title, date_str, post_id, topic_slug)
    author_posts = collections.defaultdict(list)
    # Per-topic: set of participants + post_count + topic_meta
    topic_meta = {}  # topic_id → {title, slug, first_post, post_count, participants}

    topic_files = sorted(glob.glob(
        str(TOPICS_DIR / '**' / '*.yaml'), recursive=True
    ))

    print(f'  Scanning {len(topic_files)} topic files…')
    for fpath in topic_files:
        with open(fpath, encoding='utf-8') as f:
            t = yaml.safe_load(f)
        tid = t.get('topic_id')
        if not tid:
            continue
        tslug = f'topic{tid}'
        ttitle = t.get('title', '')
        posts_list = t.get('posts', [])

        participants = _count_participants(posts_list)
        topic_meta[tid] = {
            'title': ttitle,
            'slug': tslug,
            'first_post': str(t.get('first_post', '') or ''),
            'post_count': t.get('post_count', 0),
            'participants': participants,
            'participant_count': len(participants),
        }

        for p in _iter_posts(posts_list):
            if p.get('deleted'):
                continue
            poster = (p.get('poster') or '').strip()
            if not poster:
                continue
            date_str = str(p.get('date', '') or '')
            author_posts[poster].append({
                'topic_id': tid,
                'topic_title': ttitle,
                'topic_slug': tslug,
                'date': date_str,
                'post_id': p.get('id'),
                'subject': p.get('subject', '') or '',
            })

    # Filter to authors with >= MIN_POSTS
    qualified = {
        name: posts
        for name, posts in author_posts.items()
        if len(posts) >= MIN_POSTS
    }
    print(f'  Qualified authors (>= {MIN_POSTS} posts): {len(qualified)}')

    # Build slug → name mapping (handle collisions by appending count)
    slug_map = {}  # slug → name (first assigned)
    name_to_slug = {}
    for name in sorted(qualified.keys(), key=lambda n: -len(author_posts[n])):
        s = author_slug(name)
        if s not in slug_map:
            slug_map[s] = name
            name_to_slug[name] = s
        else:
            # Collision: append number
            i = 2
            while f'{s}-{i}' in slug_map:
                i += 1
            slug_map[f'{s}-{i}'] = name
            name_to_slug[name] = f'{s}-{i}'

    return qualified, topic_meta, name_to_slug, slug_map


# ── Page generation ────────────────────────────────────────────────────────

def _month_name_ru(month: int) -> str:
    months = ['', 'янв', 'фев', 'мар', 'апр', 'май', 'июн',
              'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
    return months[month] if 1 <= month <= 12 else ''


def generate_author_page(name: str, posts: list, slug: str, topic_meta: dict):
    """Generate /forum/{slug}/index.html for one author."""
    dst_dir = SITE / 'forum' / slug
    dst_dir.mkdir(parents=True, exist_ok=True)

    # Find unique topics this author posted in
    topic_ids_posted = set(p['topic_id'] for p in posts)

    # Top 10 topics by participant count (most engaging)
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
        })
    topic_scores.sort(key=lambda x: (-x['participant_count'], -x['post_count']))
    top_topics = topic_scores[:10]

    # Author's own post count per topic
    posts_per_topic = collections.Counter(p['topic_id'] for p in posts)

    # Activity by year → month → [(date, topic_id, topic_title, topic_slug, post_id)]
    by_year_month = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in posts:
        date_str = p.get('date', '') or ''
        try:
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
            by_year_month[dt.year][dt.month].append(p)
        except (ValueError, TypeError):
            by_year_month[0][0].append(p)

    # Summary stats
    total_posts = len(posts)
    total_topics = len(topic_ids_posted)
    first_post_date = min((p['date'] for p in posts if p.get('date')), default='')
    last_post_date = max((p['date'] for p in posts if p.get('date')), default='')

    # Render years in reverse chronological order
    activity = []
    for year in sorted(by_year_month.keys(), reverse=True):
        months = []
        for month in sorted(by_year_month[year].keys()):
            month_posts = sorted(by_year_month[year][month], key=lambda p: p.get('date', ''))
            # Deduplicate topics within month
            seen_topics = {}
            topic_refs = []
            for p in month_posts:
                tid = p['topic_id']
                if tid not in seen_topics:
                    seen_topics[tid] = p
                    topic_refs.append({
                        'topic_title': html_mod.escape(p['topic_title'][:60]),
                        'topic_slug': p['topic_slug'],
                        'post_id': p['post_id'],
                        'date': p['date'][:10] if p.get('date') else '',
                    })
            months.append({
                'month': month,
                'month_name': _month_name_ru(month),
                'post_count': len(month_posts),
                'topic_count': len(seen_topics),
                'topics': topic_refs,
            })
        year_total = sum(m['post_count'] for m in months)
        activity.append({
            'year': year,
            'post_count': year_total,
            'topic_count': sum(m['topic_count'] for m in months),
            'months': months,
        })

    # Build top_topics with author's own post count
    for t in top_topics:
        t['author_posts'] = posts_per_topic.get(t['topic_id'], 0)
        # Format first_post date
        fp = t.get('first_post', '')
        if fp and len(fp) >= 10:
            try:
                dt = datetime.strptime(fp[:10], '%Y-%m-%d')
                t['first_post_fmt'] = dt.strftime('%d.%m.%Y')
            except ValueError:
                t['first_post_fmt'] = fp[:10]
        else:
            t['first_post_fmt'] = fp

    tmpl = JINJA_ENV.get_template('forum_author.html.j2')
    out = tmpl.render(
        author_name=html_mod.escape(name),
        author_slug=slug,
        total_posts=total_posts,
        total_topics=total_topics,
        first_post_date=first_post_date[:10] if first_post_date else '',
        last_post_date=last_post_date[:10] if last_post_date else '',
        top_topics=top_topics,
        activity=activity,
    )
    (dst_dir / 'index.html').write_text(out, encoding='utf-8')


# ── Slug index persistence ─────────────────────────────────────────────────

AUTHOR_SLUGS_JSON = DATA / 'forum' / 'author-slugs.json'


def save_author_slugs(name_to_slug: dict):
    """Write name→slug mapping for use by forum post renderer."""
    AUTHOR_SLUGS_JSON.write_text(
        json.dumps(name_to_slug, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f'  Author slugs saved: {AUTHOR_SLUGS_JSON}')


def load_author_slugs() -> dict:
    """Load name→slug mapping (returns {} if not yet built)."""
    if not AUTHOR_SLUGS_JSON.exists():
        return {}
    return json.loads(AUTHOR_SLUGS_JSON.read_text(encoding='utf-8'))


# ── Main ──────────────────────────────────────────────────────────────────

def generate_forum_authors():
    print('Generating forum author pages…')
    qualified, topic_meta, name_to_slug, slug_map = build_author_index()

    save_author_slugs(name_to_slug)

    count = 0
    for name, posts in qualified.items():
        slug = name_to_slug[name]
        generate_author_page(name, posts, slug, topic_meta)
        count += 1

    print(f'  Generated {count} author pages')
    return name_to_slug


if __name__ == '__main__':
    generate_forum_authors()
