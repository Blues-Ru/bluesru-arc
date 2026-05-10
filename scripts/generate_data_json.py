#!/usr/bin/env python3
"""
Generate pre-built JSON data files for client-side JS injection.

Outputs to site/data/:
  - calendar.json — all calendar events indexed by MM-DD (used by calendar.js)
"""

import json
import re
import sys
import yaml
from pathlib import Path
from datetime import datetime

import os
_scripts = Path(__file__).resolve().parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from generate_shared import fix_all_caps_name, process_calendar_text

ARC = Path(__file__).resolve().parent.parent
_site_default = str(ARC / 'bluesru-site') if os.environ.get('CF_PAGES') else str(ARC.parent / 'bluesru-site')
DATA = ARC / "data"
EXTRACTED = DATA  # canonical; DATA is the consolidated data dir
SITE = Path(os.environ.get('BLUESRU_SITE', _site_default))
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
            slug = ev.get('artist_slug', '') or ''
            title = ev.get('title', '') or ''
            text = ev.get('text', '') or ''
            display_title = fix_all_caps_name(title) if title else title
            if slug:
                text = process_calendar_text(text, slug, title)
            event = {
                "id": ev.get('id', ''),
                "title": display_title,
                "year": str(ev.get('year', '')),
                "picture": picture,
                "type": ev.get('event_type', ''),
                "text": text,
                "slug": slug,
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

    # Write per-day files: data/calendar/MM-DD.json
    cal_dir = OUT / "calendar"
    cal_dir.mkdir(exist_ok=True)
    for mmdd, events in by_day.items():
        day_path = cal_dir / f"{mmdd}.json"
        with day_path.open('w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    print(f"calendar/: {len(by_day)} day files, {sum(len(v) for v in by_day.values())} events")


# ─── 2. redirects.json ─────────────────────────────────────────────────────

def generate_redirects():
    """Generate data/redirects.json for middleware-side redirect handling.

    CF Pages _redirects doesn't support query-string matching and has a 2000
    static / 100 dynamic rule limit. This JSON is fetched by _middleware.js
    to handle aspx and legacy-directory redirects at the edge.
    """
    import re
    albums_dir = DATA / "albums"
    artists_yaml = DATA / "artists.yaml"

    # album id → /artist/{artist-slug}/{album-slug}/
    albums = {}
    if albums_dir.exists():
        for p in sorted(albums_dir.glob("*/*.yaml")):
            a = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            aid = a.get("id")
            album_slug = a.get("slug", "")
            if not aid or not album_slug:
                continue
            # Determine artist slug
            artist_id = str(a.get("artist_id", ""))
            a_slug = "various-musicians"
            # (artist slug resolved below after loading artists)
            albums[str(aid)] = {"album_slug": album_slug, "artist_id": artist_id}

    # artist id → slug, legacy_dir
    artists_raw = yaml.safe_load(artists_yaml.read_text(encoding="utf-8")) if artists_yaml.exists() else []
    artist_by_id = {}
    for a in (artists_raw or []):
        slug = a.get("slug", "")
        aid = str(a.get("id", ""))
        lp = (a.get("legacy_path") or "").strip("/")
        parts = lp.split("/")
        legacy_dir = parts[-1] if parts and parts[-1] else ""
        if "." in legacy_dir or legacy_dir.startswith("www."):
            legacy_dir = ""
        artist_by_id[aid] = {"slug": slug, "legacy_dir": legacy_dir}

    # Build album redirect map
    album_redirects = {}
    for album_id, info in albums.items():
        artist_id = info["artist_id"]
        album_slug = info["album_slug"]
        art = artist_by_id.get(artist_id, {})
        a_slug = art.get("slug") or "various-musicians"
        # Strip artist prefix from album slug
        if a_slug not in ("various-musicians",) and album_slug.startswith(a_slug + "-"):
            album_slug = album_slug[len(a_slug) + 1:]
        album_redirects[album_id] = f"/artist/{a_slug}/{album_slug}/"

    # Build artist redirect map
    artist_redirects = {}
    for aid, info in artist_by_id.items():
        slug = info.get("slug") or info.get("legacy_dir")
        if slug:
            artist_redirects[aid] = f"/artist/{slug}/"

    # Build bluesmen dir map: old legacy_dir → new slug URL prefix
    bluesmen_dirs = {}
    for aid, info in artist_by_id.items():
        slug = info.get("slug", "")
        legacy_dir = info.get("legacy_dir", "")
        if legacy_dir and slug:
            bluesmen_dirs[legacy_dir] = f"/artist/{slug}"

    # Extra bluesmen dir mappings not covered by legacy_path (loaded from data file)
    extra_file = DATA / "bluesmen-extra-redirects.yaml"
    if extra_file.exists():
        extra = yaml.safe_load(extra_file.read_text(encoding="utf-8")) or {}
        for old_dir, slug in extra.items():
            bluesmen_dirs[old_dir] = f"/artist/{slug}"

    # Bluesnews subdir → photo gallery map (loaded from data file)
    bluesnews_file = DATA / "bluesnews-redirects.yaml"
    bluesnews_dirs = {}
    if bluesnews_file.exists():
        bluesnews_dirs = yaml.safe_load(bluesnews_file.read_text(encoding="utf-8")) or {}

    manifest = {
        "albums": album_redirects,
        "artists": artist_redirects,
        "bluesmen": bluesmen_dirs,
        "bluesnews": bluesnews_dirs,
    }

    out_path = OUT / "redirects.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"redirects.json: {len(album_redirects)} albums, {len(artist_redirects)} artists, "
          f"{len(bluesmen_dirs)} bluesmen dirs, {len(bluesnews_dirs)} bluesnews dirs")


# ─── main ──────────────────────────────────────────────────────────────────

def main():
    print("Generating data JSON files...")
    generate_calendar()
    generate_redirects()
    print("Done.")


if __name__ == '__main__':
    main()
