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

    out_path = OUT / "calendar.json"
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(by_day, f, ensure_ascii=False, indent=2)
    print(f"calendar.json: {len(by_day)} days, {sum(len(v) for v in by_day.values())} events")


# ─── main ──────────────────────────────────────────────────────────────────

def main():
    print("Generating data JSON files...")
    generate_calendar()
    print("Done.")


if __name__ == '__main__':
    main()
