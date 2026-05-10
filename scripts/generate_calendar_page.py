#!/usr/bin/env python3
"""
Generate static calendar pages.

Outputs:
  - site/calendar/index.html  — today/yesterday/tomorrow (JS-driven)
  - site/calendar/YYYY/index.html — all events for year YYYY (static)

Run from /Users/fedor/bluesru/
"""

import re
import sys
import os
import yaml
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from jinja2 import Environment, FileSystemLoader

_scripts = Path(__file__).resolve().parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from generate_shared import link_artist_in_text
ARC = Path(__file__).resolve().parent.parent
_site_default = str(ARC / 'bluesru-site') if os.environ.get('CF_PAGES') else str(ARC.parent / 'bluesru-site')
DATA = ARC / "data"
CALENDAR_YAML = DATA / "calendar.yaml"
EVENTS_DIR = DATA / "blues-data" / "events"  # fallback for old structure
DST = Path(os.environ.get('BLUESRU_SITE', _site_default)) / "calendar"


def read_yaml_frontmatter(path):
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


FOOTER = (ARC / "includes" / "footer.inc").read_text(encoding='utf-8').strip()

GA_SNIPPET = '''\
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8HDC1W9R3E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-8HDC1W9R3E');
</script>'''

_jinja_env = Environment(loader=FileSystemLoader(str(ARC / 'templates')), autoescape=False)


def generate_calendar_index(all_years, index_nav):
    tmpl = _jinja_env.get_template('calendar_index.html.j2')
    html = tmpl.render(ga_snippet=GA_SNIPPET, footer=FOOTER, all_years=all_years,
                       year_nav=index_nav)
    DST.mkdir(parents=True, exist_ok=True)
    (DST / 'index.html').write_text(html, encoding='utf-8')
    print("  calendar/index.html written")


def generate_year_pages():
    """Generate /calendar/YYYY/index.html for each year with events."""
    by_year = defaultdict(list)

    if CALENDAR_YAML.exists():
        events = yaml.safe_load(CALENDAR_YAML.read_text(encoding='utf-8')) or []
        for ev in events:
            date_str = str(ev.get('date', ''))
            if not date_str or len(date_str) < 10:
                continue
            year = date_str[:4]
            if not year.isdigit():
                continue
            picture = ev.get('picture', '') or ''
            by_year[year].append({
                'date': date_str,
                'title': ev.get('title', ''),
                'picture': picture,
                'text': ev.get('text', ''),
                'artist_slug': ev.get('artist_slug', '') or '',
            })
    elif EVENTS_DIR.exists():
        for fpath in sorted(EVENTS_DIR.glob("*.md")):
            fm, body = read_yaml_frontmatter(fpath)
            date_str = fm.get('date', '')
            if not date_str or len(date_str) < 10 or date_str.startswith('null'):
                continue
            year = date_str[:4]
            if not year.isdigit():
                continue
            picture = fm.get('picture', '') or ''
            if picture in ('null', 'None', 'none'):
                picture = ''
            by_year[year].append({
                'date': date_str,
                'title': fm.get('title', ''),
                'picture': picture,
                'text': body,
            })

    all_years = sorted(by_year.keys())

    # Build year navigation: decade shortcuts for other decades,
    # individual years expanded for the current decade.
    # current_year=None → all decades as shortcuts (used for index page).
    def year_nav(current_year, all_years):
        years_set = set(int(y) for y in all_years)
        decades = sorted(set((y // 10) * 10 for y in years_set))
        current_int = int(current_year) if current_year else None
        current_decade = (current_int // 10) * 10 if current_int else None

        parts = []
        for decade in decades:
            if decade == current_decade:
                for y in range(decade, decade + 10):
                    if y == current_int:
                        parts.append(f'<b>{y}</b>')
                    elif y in years_set:
                        parts.append(f'<a href="/calendar/{y}/">{y}</a>')
            else:
                first = next((y for y in range(decade, decade + 10) if y in years_set), decade)
                label = str(decade)[:-1] + 'x'
                parts.append(f'<a href="/calendar/{first}/">{label}</a>')
        return ' | '.join(parts)

    count = 0
    for year, events in by_year.items():
        events_sorted = sorted(events, key=lambda e: e['date'])
        year_int = int(year)

        current_year = datetime.now().year
        for ev in events_sorted:
            date_str = ev['date']
            ev['day_month'] = f'{date_str[8:10]}.{date_str[5:7]}'
            ev['years_ago'] = current_year - year_int
            slug = ev.get('artist_slug', '')
            title = ev.get('title', '')
            if slug and title:
                ev['text'] = link_artist_in_text(ev.get('text', ''), title, slug)

        nav = year_nav(year, all_years)
        tmpl = _jinja_env.get_template('calendar_year.html.j2')
        html = tmpl.render(
            ga_snippet=GA_SNIPPET,
            footer=FOOTER,
            year=year,
            year_nav=nav,
            events=events_sorted,
        )

        dst_dir = DST / year
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / 'index.html').write_text(html, encoding='utf-8')
        count += 1

    index_nav = year_nav(None, all_years)
    print(f"  calendar year pages: {count} years")
    return all_years, index_nav


def main():
    print("Generating calendar pages...")
    all_years, index_nav = generate_year_pages()
    generate_calendar_index(all_years, index_nav)


if __name__ == '__main__':
    main()
