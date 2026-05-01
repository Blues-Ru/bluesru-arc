#!/usr/bin/env python3
"""
Generate static calendar pages.

Outputs:
  - site/calendar/index.html  — today/yesterday/tomorrow (JS-driven)
  - site/calendar/YYYY/index.html — all events for year YYYY (static)

Run from /Users/fedor/bluesru/
"""

import re
import yaml
from pathlib import Path
from collections import defaultdict

import os
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


def generate_calendar_index():
    html = '''<!DOCTYPE html>
<html>
<head>
<title>Блюзовый календарь — Blues.Ru</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<link rel="shortcut icon" href="/images/bluesru.ico">
{GA_SNIPPET}
</head>
<body bgcolor="#FFFFFF" text="#000000" link="#0000FF" vlink="#5511CC" alink="#00BB00">

<table cellpadding="4" cellspacing="0" border="0" align="right">
<tr><td align="left">
  <a href="/"><img src="/images/bluesru100x100.gif" width="100" height="100" border="0"></a>
</td></tr>
<tr><td width="150">
</td></tr>
</table>

<h3 align="center">Блюзовый календарь: этот день в истории блюза...</h3>

<div id="blues-calendar" data-mode="full"><i>Загрузка...</i></div>

<script src="/static/js/calendar.js"></script>

<hr size="1">
<p align="center">
''' + FOOTER + '''
</p>
</body>
</html>'''

    html = html.replace('{GA_SNIPPET}', GA_SNIPPET)
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

    # Build year navigation — decades + individual years near each target
    def year_nav(current_year, all_years):
        current_int = int(current_year)
        years_set = set(int(y) for y in all_years)

        nav_years = set()
        # Decades
        for y in years_set:
            nav_years.add((y // 10) * 10)
        # Individual years within ±5 of current
        for y in range(current_int - 5, current_int + 6):
            if y in years_set:
                nav_years.add(y)
        nav_years.add(current_int)

        parts = []
        prev = None
        for y in sorted(nav_years):
            if prev is not None and y - prev > 1:
                parts.append('...')
            if y == current_int:
                parts.append(f'<b>{y}</b>')
            elif y in years_set:
                parts.append(f'<a href="/calendar/{y}/">{y}</a>')
            prev = y
        return ' | '.join(parts)

    count = 0
    for year, events in by_year.items():
        events_sorted = sorted(events, key=lambda e: e['date'])
        year_int = int(year)

        body_html = ''
        for ev in events_sorted:
            date_str = ev['date']  # YYYY-MM-DD
            dd = date_str[8:10]
            mm = date_str[5:7]
            formatted_date = f'{dd}.{mm}.{year}'

            body_html += '<p>'
            if ev['picture']:
                body_html += (f'<img src="/calendar/{ev["picture"]}" border="0"'
                              f' align="right" vspace="4" hspace="8"'
                              f' style="max-width:180px;max-height:120px;">')
            name = ev['title']
            body_html += f'<b>{formatted_date}</b> - '
            if name:
                body_html += f'<b>{name}</b> - '
            body_html += ev['text']
            if ev['picture']:
                body_html += '<br clear="both">'
            body_html += '</p>\n<hr size="1">\n'

        nav = year_nav(year, all_years)
        html = f'''<!DOCTYPE html>
<html>
<head>
<title>Блюзовый календарь - {year} год — Blues.Ru</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<link rel="shortcut icon" href="/images/bluesru.ico">
{GA_SNIPPET}
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc" alink="#00bb00">

<table cellpadding="4" cellspacing="0" border="0" align="right">
<tr><td align="left">
  <a href="/"><img src="/images/bluesru100x100.gif" width="100" height="100" border="0"></a>
</td></tr>
<tr><td width="150">
</td></tr>
</table>

<h3><a href="/calendar/">Блюзовый календарь</a>: {year_int} год</h3>
<p>{nav}</p>
{body_html}
<p align="center">
{FOOTER}
</p>
</body>
</html>'''

        dst_dir = DST / year
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / 'index.html').write_text(html, encoding='utf-8')
        count += 1

    print(f"  calendar year pages: {count} years")


def main():
    print("Generating calendar pages...")
    generate_calendar_index()
    generate_year_pages()


if __name__ == '__main__':
    main()
