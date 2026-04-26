#!/usr/bin/env python3
"""
Generate RSS feed for CD reviews (latest 50).

Output: site/review/rss.xml

Run from /Users/fedor/bluesru/
"""

import re
import yaml
import html as html_mod
from pathlib import Path
from datetime import datetime

import os
ARC = Path(__file__).resolve().parent.parent
_ws = Path(os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
SITE_DIR = Path(os.environ.get('BLUESRU_SITE', str(_ws / 'bluesru-site')))
_extracted_arc = ARC / "extracted-data"
_extracted = _extracted_arc if _extracted_arc.exists() else _ws / "extracted-data"
REVIEWS_DIR = _extracted / "blues-data" / "reviews"
ALBUMS_DIR = _extracted / "blues-data" / "albums"
OUT = SITE_DIR / "review" / "rss.xml"

SITE = "https://blues.ru"
RE_FRONTMATTER = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)', re.DOTALL)


def parse_review(path):
    text = path.read_text(encoding='utf-8')
    m = RE_FRONTMATTER.match(text)
    if not m:
        return None, None
    meta = yaml.safe_load(m.group(1))
    body = m.group(2).strip()
    return meta, body


def load_albums():
    albums = {}
    for p in ALBUMS_DIR.glob('*.yaml'):
        a = yaml.safe_load(p.read_text(encoding='utf-8'))
        if a and a.get('id'):
            albums[str(a['id'])] = a
    return albums


def rfc2822(date_str):
    try:
        dt = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
        return dt.strftime('%a, %d %b %Y 12:00:00 +0300')
    except Exception:
        return ''


def main():
    print("Generating review RSS...")
    albums = load_albums()

    reviews = []
    for rf in REVIEWS_DIR.glob('review-*.md'):
        meta, body = parse_review(rf)
        if meta and meta.get('album_id'):
            album = albums.get(str(meta['album_id']))
            reviews.append((meta, body, album))

    # Sort by id descending, take latest 50
    reviews.sort(key=lambda x: -int(x[0].get('id', 0)))
    reviews = reviews[:50]

    items = []
    for meta, body, album in reviews:
        slug = meta.get('slug', '')
        album_title = (album.get('title', '') if album else '') or meta.get('album', '')
        artist_name = (album.get('artist', '') if album else '') or meta.get('artist', '')
        author = meta.get('author', '')
        date_str = str(meta.get('date', ''))
        mark = meta.get('mark', '')

        title_parts = []
        if artist_name:
            title_parts.append(artist_name)
        if album_title:
            title_parts.append(f'"{album_title}"')
        title = ' — '.join(title_parts) or slug

        url = f'{SITE}/review/{slug}/'
        pub_date = rfc2822(date_str)

        desc_parts = []
        if body:
            plain = re.sub(r'<[^>]+>', '', body)
            desc_parts.append(plain[:300] + ('…' if len(plain) > 300 else ''))
        if mark:
            desc_parts.append(f'Оценка: {mark}/10')
        if author:
            desc_parts.append(f'Рецензент: {author}')
        description = ' '.join(desc_parts)

        item = f'''  <item>
    <title>{html_mod.escape(title)}</title>
    <link>{url}</link>
    <guid>{url}</guid>
    <description>{html_mod.escape(description)}</description>
    {f"<pubDate>{pub_date}</pubDate>" if pub_date else ""}
  </item>'''
        items.append(item)

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
<channel>
  <title>Blues.Ru — CD обзор</title>
  <link>{SITE}/review/</link>
  <description>Рецензии на блюзовые диски — Blues.Ru</description>
  <language>ru</language>
  <lastBuildDate>{rfc2822(reviews[0][0].get("date", "") if reviews else "")}</lastBuildDate>
{chr(10).join(items)}
</channel>
</rss>
'''

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(xml, encoding='utf-8')
    print(f"  review/rss.xml: {len(items)} items")


if __name__ == '__main__':
    main()
