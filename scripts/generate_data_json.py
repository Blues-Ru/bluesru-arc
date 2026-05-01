#!/usr/bin/env python3
"""
Generate pre-built JSON data files for client-side JS injection.

Outputs to site/data/:
  - calendar.json — all calendar events indexed by MM-DD (used by calendar.js)
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
        if legacy_dir and slug and legacy_dir.lower().replace("-", "_") != slug.lower().replace("-", "_"):
            bluesmen_dirs[legacy_dir] = f"/artist/{slug}"
        elif legacy_dir and slug:
            bluesmen_dirs[legacy_dir] = f"/artist/{slug}"

    # Hardcoded extra bluesmen dir mappings not covered by legacy_path
    extra = {
        "Johnny_Winter": "johnny-winter",
        "Larry_McCray": "larry-mccray",
        "Lazy_Bill_Lucas": "lazy-bill-lucas",
        "Little_Richard": "little-richard",
        "Luther_Allison": "luther-allison",
        "Scott_Henderson": "scott-henderson",
    }
    for old_dir, slug in extra.items():
        bluesmen_dirs[old_dir] = f"/artist/{slug}"

    # Bluesnews subdir → photo gallery map (from generate_redirects.py)
    bluesnews_dirs = {
        "/bluesnews/_13/13_02_16_Pardo": "/photo/2013/2013-02-16-pardo/",
        "/bluesnews/_13/13_02_26_Rusinov_Oleinikova": "/photo/2013/2013-02-26-rusinov-oleinikova/",
        "/bluesnews/_13/13_06_02_Hugh_Laurie": "/photo/2013/2013-06-02-hugh-laurie-moscow/",
        "/bluesnews/_13/13_10_19_Arsen": "/photo/2013/2013-10-19-arsen/",
        "/bluesnews/_13/13_10_19_Jimmy_Burns": "/photo/2013/2013-10-19-jimmy-burns/",
        "/bluesnews/_13/13_11_08_Mishouris": "/photo/2013/2013-11-08-mishouris/",
        "/bluesnews/_13/13_11_29_Joakim Tinderholt": "/photo/2013/2013-11-29-joakim-tinderholt/",
        "/bluesnews/_14/14_03_10_Mishouris_Seals": "/photo/2014/2014-03-10-mishouris-seals/",
        "/bluesnews/_14/14_04_19_Lisikova": "/photo/2014/2014-04-19-lisikova/",
        "/bluesnews/_14/14_04_25_BB": "/photo/2014/2014-04-25-bb/",
        "/bluesnews/_14/14_05_09_danny_giles": "/photo/2014/2014-05-09-danny-giles/",
        "/bluesnews/_15/15_10_07_Dzagnidze": "/photo/2015/2015-10-07-dzagnidze/",
        "/bluesnews/_15/15_10_30_KW2": "/photo/2015/2015-10-30-kw2/",
        "/bluesnews/_15/15_11_21_Old_Fassion": "/photo/2015/2015-11-21-old-fassion/",
        "/bluesnews/_15/16_09_30_SOBO": "/photo/2016/2016-09-30-sobo/",
        "/bluesnews/_16/16_06_10_Eddie Shaw": "/photo/2016/2016-06-10-eddie-shaw/",
        "/bluesnews/_16/16_06_10_Jam": "/photo/2016/2016-06-10-jam/",
        "/bluesnews/_16/16_06_10_Lil_Ed": "/photo/2016/2016-06-10-lil-ed-williams-siegel/",
        "/bluesnews/_16/16_06_10_TC_TC": "/photo/2016/2016-06-10-tc-tc/",
        "/bluesnews/_16/16_06_12_Clearwater": "/photo/2016/2016-06-12-clearwater/",
        "/bluesnews/_16/16_06_12_Migration": "/photo/2016/2016-06-12-migration/",
        "/bluesnews/_16/16_07_07RWIP": "/photo/2016/2016-07-07-raphael-wressnig-igor-prado/",
        "/bluesnews/_16/16_07_07_Raphael Wressnig Igor Prado": "/photo/2016/2016-07-07-raphael-wressnig-igor-prado/",
        "/bluesnews/_16/16_11_02_ Giles_Robson": "/photo/2016/2016-11-02-giles-robson/",
        "/bluesnews/_16/16_11_05_Kozh_Jhuk": "/photo/2016/2016-11-05-kozh-jhuk/",
        "/bluesnews/_16/16_12_10_Smith": "/photo/2016/2016-12-10-jc-smith/",
        "/bluesnews/_16/19_06_11_Weskey": "/photo/2019/2019-06-11-weskey/",
        "/bluesnews/_17/17_01_21_Tomi_Leino": "/photo/2017/2017-01-21-tomi-leino/",
        "/bluesnews/_17/17_01_28_Chino": "/photo/2017/2017-01-28-chino-swingslide/",
        "/bluesnews/_17/17_06_03_Shanna_Waterstown": "/photo/2017/2017-06-03-shanna-waterstown/",
        "/bluesnews/_17/17_10_23_Tarasov": "/photo/2017/2017-10-23-tarasov/",
        "/bluesnews/_17/17_10_25_Ash": "/photo/2017/2017-10-25-frank-ash/",
        "/bluesnews/_17/17_10_28_JCSmith": "/photo/2017/2017-10-28-jcsmith/",
        "/bluesnews/_17/17_11_13_ChrisRea": "/photo/2017/2017-11-13-chris-rea-moscow/",
        "/bluesnews/_17/17_11_30_Kaverkin": "/photo/2017/2017-11-30-kaverkin/",
        "/bluesnews/_17/17_11_30_folkline": "/photo/2017/2017-11-30-folkline/",
        "/bluesnews/_17/Iv_Sh": "/photo/2017/2017-iv-sh/",
        "/bluesnews/_17/Waterstown_Delta": "/photo/2017/2017-waterstown-delta/",
        "/bluesnews/_18/18_01_27_Harris": "/photo/2018/2018-01-27-harris/",
        "/bluesnews/_18/18_02_24_Shanna": "/photo/2018/2018-02-24-shanna/",
        "/bluesnews/_18/18_03_24_Guy_Davis": "/photo/2018/2018-03-24-guy-davis/",
        "/bluesnews/_18/18_11_11_Mark_Hummel": "/photo/2018/2018-11-11-mark-hummel/",
        "/bluesnews/_18/19_01_22_Shinel": "/photo/2019/2019-01-22-shinel/",
        "/bluesnews/_19/19_01_31_JJThames": "/photo/2019/2019-01-31-jjthames/",
        "/bluesnews/_19/19_03_04_Nekrasov_I": "/photo/2019/2019-03-04-nekrasov-i/",
        "/bluesnews/_19/19_04_28_Kolosova": "/photo/2019/2019-04-28-kolosova/",
        "/bluesnews/_19/19_11_10_Crosseyedcats": "/photo/2019/2019-11-10-crosseyedcats/",
        "/bluesnews/_19/2019-11-24_Juk_Kozh": "/photo/2019/2019-11-24-juk-kozh/",
        "/bluesnews/_19/Arkh19_Guitar": "/photo/2019/2019-arkh19-guitar/",
        "/bluesnews/_22": "/photo/2022/2022-11-23-neighbours/",
    }

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
