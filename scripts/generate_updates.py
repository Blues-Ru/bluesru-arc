#!/usr/bin/env python3
"""Generate /updates/ section from announcements."""
import re
import sys
import yaml
from collections import defaultdict, OrderedDict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import (
    ANNOUNCE_DIR,
    FOOTER,
    JINJA_ENV,
    RE_FM,
    SITE,
)
from render_utils import format_news_body_simple


def generate_updates() -> None:
    print("Generating updates pages...")
    if not ANNOUNCE_DIR.exists():
        print("  ANNOUNCE_DIR not found, skipping updates")
        return

    items: list[tuple[dict, str]] = []
    for p in sorted(ANNOUNCE_DIR.rglob('*.md')):
        m = RE_FM.match(p.read_text(encoding='utf-8'))
        if m:
            meta = yaml.safe_load(m.group(1))
            body = m.group(2).strip()
            items.append((meta, body))

    items.sort(key=lambda x: str(x[0].get('date', '0000')), reverse=True)

    tmpl = JINJA_ENV.get_template('updates_list.html.j2')

    def fmt_date(date_str: str) -> str:
        try:
            return datetime.strptime(str(date_str)[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
        except Exception:
            return str(date_str) if date_str else ''

    def make_item(meta: dict, body: str) -> dict:
        date_str = str(meta.get('date', ''))
        return {
            'id':           str(meta.get('id', '')),
            'date_display': fmt_date(date_str),
            'date_str':     date_str,
            'body':         format_news_body_simple(body),
        }

    all_items = [make_item(meta, body) for meta, body in items]

    by_year: dict[str, list] = defaultdict(list)
    for item in all_items:
        year = item['date_str'][:4] if item['date_str'] else ''
        if year:
            by_year[year].append(item)
    year_list = sorted(by_year.keys(), reverse=True)

    def year_nav_html(current: str, prev_y: str | None, next_y: str | None) -> str:
        parts = []
        if next_y:
            parts.append(f'← <a href="/updates/{next_y}/">{next_y}</a>')
        parts.append(f'<b>{current}</b>')
        if prev_y:
            parts.append(f'<a href="/updates/{prev_y}/">{prev_y}</a> →')
        return ' | '.join(parts)

    # /updates/ — most recent 15 items
    dst = SITE / 'updates' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    recent = all_items[:15]
    recent_by_year: OrderedDict = OrderedDict()
    for item in recent:
        y = item['date_str'][:4] if item['date_str'] else ''
        if y not in recent_by_year:
            recent_by_year[y] = []
        recent_by_year[y].append(item)
    recent_year_blocks = [{'year': y, 'entries': entries}
                          for y, entries in recent_by_year.items()]
    oldest_shown = list(recent_by_year.keys())[-1] if recent_by_year else None
    more_years_html = (f'<a href="/updates/{oldest_shown}/">{oldest_shown}</a> →'
                       if oldest_shown else '')

    dst.write_text(tmpl.render(
        page_title='Обновления Blues.Ru',
        current_year=None,
        nav_links=None,
        year_blocks=recent_year_blocks,
        more_years=more_years_html,
        year_list=year_list,
        footer=FOOTER,
        canonical_url='https://blues.ru/updates/',
    ), encoding='utf-8')

    # /updates/YYYY/ — per-year pages
    for i, year in enumerate(year_list):
        prev_y = year_list[i + 1] if i + 1 < len(year_list) else None
        next_y = year_list[i - 1] if i > 0 else None
        nav = year_nav_html(year, prev_y, next_y)

        dst_year = SITE / 'updates' / year / 'index.html'
        dst_year.parent.mkdir(parents=True, exist_ok=True)
        dst_year.write_text(tmpl.render(
            page_title=f'Обновления Blues.Ru: {year}',
            current_year=year,
            nav_links=nav,
            year_blocks=[{'year': year, 'entries': by_year[year]}],
            more_years=None,
            year_list=year_list,
            footer=FOOTER,
        ), encoding='utf-8')

    print(f"  Updates: {len(all_items)} items, {len(year_list)} year pages")


if __name__ == '__main__':
    generate_updates()
