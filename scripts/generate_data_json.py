#!/usr/bin/env python3
"""
Generate pre-built JSON data files for client-side JS injection.

Outputs to site/data/:
  - calendar.json      — all 3021 calendar events indexed by MM-DD
  - latest-news.json   — latest site announcements (bluesru/announcements/)
  - artists/{slug}.json — per-artist album+review list

Run from /Users/fedor/bluesru/
"""

import json
import re
import yaml
from pathlib import Path
from datetime import datetime

import os
ARC = Path(__file__).resolve().parent.parent
_ws = Path(os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
DATA = ARC / "data"
EXTRACTED = DATA  # canonical; DATA is the consolidated data dir
SITE = Path(os.environ.get('BLUESRU_SITE', str(_ws / 'bluesru-site')))
OUT = SITE / "data"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "artists").mkdir(exist_ok=True)


def read_yaml_frontmatter(path):
    """Parse YAML frontmatter + body from a markdown file."""
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---', 3)
    if end < 0:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end+4:].strip()
    fm = {}
    for line in fm_text.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            fm[k.strip()] = v.strip().strip("'\"")
    return fm, body


# ─── 1. calendar.json ──────────────────────────────────────────────────────

def generate_calendar():
    # New structure: single calendar.yaml with event_type already stored
    cal_yaml = EXTRACTED / "calendar.yaml"
    # Fallback: old events/ directory
    events_dir = EXTRACTED / "blues-data" / "events"

    by_day = {}  # "MM-DD" → list of events

    if cal_yaml.exists():
        events = yaml.safe_load(cal_yaml.read_text(encoding='utf-8')) or []
        for ev in events:
            date_str = ev.get('date') or ''
            month_day = ev.get('month_day') or (date_str[5:10] if len(str(date_str)) >= 10 else '')
            if not month_day or len(month_day) != 5:
                continue
            picture = ev.get('picture') or ''
            event = {
                "id": ev.get('id', ''),
                "title": ev.get('title', ''),
                "year": str(ev.get('year', '')),
                "picture": picture,
                "type": ev.get('event_type', ''),
                "text": ev.get('text', ''),
            }
            by_day.setdefault(month_day, []).append(event)
    elif events_dir.exists():
        for fpath in sorted(events_dir.glob("*.md")):
            fm, body = read_yaml_frontmatter(fpath)
            date_str = str(fm.get('date', ''))
            if not date_str or len(date_str) < 10:
                continue
            mm_dd = date_str[5:10]
            picture = fm.get('picture', '') or ''
            if picture in ('null', 'None', 'none'):
                picture = ''
            body_lc = body.lower()
            if re.search(r'родил[асьи]', body_lc):
                ev_type = 'born'
            elif re.search(r'скончал[сяь]|умер|умерл[аи]|погиб', body_lc):
                ev_type = 'died'
            else:
                ev_type = ''
            event = {
                "id": fm.get('id', ''),
                "title": fm.get('title', ''),
                "year": date_str[:4],
                "picture": picture,
                "type": ev_type,
                "text": body,
            }
            by_day.setdefault(mm_dd, []).append(event)

    out_path = OUT / "calendar.json"
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(by_day, f, ensure_ascii=False, indent=2)
    print(f"calendar.json: {len(by_day)} days, {sum(len(v) for v in by_day.values())} events")


# ─── 2. latest-news.json ───────────────────────────────────────────────────

_ATB_RE = re.compile(
    r'\bATB\b|atb_|/[Aa]tb/|Весь\s+[Ээ]тот\s+[Бб]люз|All\s+That\s+Blues',
    re.IGNORECASE)


def _is_atb_announcement(body):
    return bool(_ATB_RE.search(body))


def generate_latest_news(count=5):
    """
    Site announcements from bluesru/announcements/. These are the 'Новости blues.ru'
    that will continue to be updated. NOT blues-data/news/ (archive).
    ATB (radio show) announcements are excluded — they have their own block on the homepage.
    """
    # New structure: announcements/YYYY/{date}-{slug}.md
    ann_dir = EXTRACTED / "announcements"
    if not ann_dir.exists():
        ann_dir = EXTRACTED / "bluesru" / "announcements"  # fallback old path
    items = []
    atb_filtered = 0

    for fpath in sorted(ann_dir.rglob("*.md")):
        fm, body = read_yaml_frontmatter(fpath)
        if _is_atb_announcement(body):
            atb_filtered += 1
            continue
        date_str = fm.get('date', '')
        items.append({
            "id": fm.get('id', ''),
            "date": str(date_str)[:10] if date_str else '',
            "text": body,
        })

    items.sort(key=lambda x: (str(x['date'])[:10] if x['date'] else '0000',
                               int(x['id']) if str(x['id']).isdigit() else 0), reverse=True)

    out = {"items": items[:count], "total": len(items)}
    out_path = OUT / "latest-news.json"
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"latest-news.json: {len(items)} non-ATB items (filtered {atb_filtered} ATB), showing {min(count, len(items))}")


# ─── 3. per-artist JSON files ──────────────────────────────────────────────

def load_reviews_by_album_id():
    """Build album_id → review slug mapping from embedded reviews in album YAMLs."""
    mapping = {}
    albums_dir = EXTRACTED / "albums"
    if not albums_dir.exists():
        albums_dir = EXTRACTED / "blues-data" / "albums"
    for fpath in albums_dir.glob("*/*.yaml"):
        album = yaml.safe_load(fpath.read_text(encoding='utf-8')) or {}
        album_id = str(album.get('id', ''))
        if not album_id:
            continue
        reviews = album.get('reviews', [])
        if reviews:
            # slug = review-{first_review_id} for compat
            first_id = reviews[0].get('id', '')
            mapping[album_id] = f"review-{first_id}" if first_id else fpath.stem
    return mapping


def load_albums_by_artist_id():
    """Build artist_id → list of album dicts."""
    albums_dir = EXTRACTED / "albums"
    if not albums_dir.exists():
        albums_dir = EXTRACTED / "blues-data" / "albums"
    by_artist = {}
    for fpath in sorted(albums_dir.glob("*/*.yaml")):
        album = yaml.safe_load(fpath.read_text(encoding='utf-8')) or {}
        artist_id = str(album.get('artist_id', ''))
        if not artist_id:
            continue
        entry = {
            "id": str(album.get('id', '')),
            "title": album.get('title', ''),
            "year": str(album.get('year', '')),
            "label": album.get('label', ''),
            "artist": album.get('artist', ''),
            "asin": album.get('asin', ''),
            "slug": fpath.stem,
        }
        by_artist.setdefault(artist_id, []).append(entry)
    return by_artist


def load_artists():
    """Load all artists from artists.yaml."""
    path = EXTRACTED / "artists.yaml"
    if not path.exists():
        path = EXTRACTED / "blues-data" / "artists.yaml"
    with path.open(encoding='utf-8') as f:
        return yaml.safe_load(f) or []


def generate_artist_jsons():
    artists = load_artists()
    reviews_map = load_reviews_by_album_id()
    albums_map = load_albums_by_artist_id()

    generated = 0
    for artist in artists:
        artist_id = str(artist.get('id', ''))
        slug = artist.get('slug', '')
        if not slug or not artist_id:
            continue

        albums = albums_map.get(artist_id, [])
        # Add review_slug to each album
        for album in albums:
            album['review_slug'] = reviews_map.get(str(album['id']), '')

        # Sort albums by year desc
        def year_key(a):
            try: return -int(a.get('year', 0) or 0)
            except: return 0
        albums.sort(key=year_key)

        if not albums:
            continue  # skip artists with no albums

        data = {
            "artist_id": artist_id,
            "name": artist.get('name', ''),
            "albums": albums,
        }
        out_path = OUT / "artists" / f"{slug}.json"
        with out_path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        generated += 1

    print(f"artist JSONs: {generated} files in {OUT}/artists/")


# ─── 4. latest-blues-news.json — headers for homepage ─────────────────────

def generate_latest_blues_news(count=5):
    """
    Recent blues-data news item headers for homepage display.
    Only title + date + url — no body text.
    """
    news_dir = EXTRACTED / "news"
    if not news_dir.exists():
        news_dir = EXTRACTED / "blues-data" / "news"
    items = []

    for fpath in sorted(news_dir.rglob("*.md")):
        fm, _ = read_yaml_frontmatter(fpath)
        date_str = str(fm.get('date', ''))[:10]
        if not date_str or len(date_str) < 10:
            continue
        title = fm.get('title', '').strip()
        if not title:
            continue
        nid = fm.get('id', '')
        url = f'/news/{date_str[:4]}/{date_str[5:7]}/{date_str[8:10]}/story{nid}/'
        items.append({
            "id": str(nid),
            "title": title,
            "date": date_str,
            "url": url,
        })

    # Sort by date desc, then id desc
    items.sort(key=lambda x: (x['date'], int(x['id']) if str(x['id']).isdigit() else 0), reverse=True)

    out = {"items": items[:count]}
    out_path = OUT / "latest-blues-news.json"
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"latest-blues-news.json: {len(items)} total, showing {min(count, len(items))}")


# ─── main ──────────────────────────────────────────────────────────────────

def main():
    print("Generating data JSON files...")
    generate_calendar()
    generate_latest_news(count=8)
    generate_latest_blues_news(count=8)
    generate_artist_jsons()
    print("Done.")


if __name__ == '__main__':
    main()
