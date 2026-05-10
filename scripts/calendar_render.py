"""
Calendar HTML rendering for artist pages and calendar section.

All functions are pure (take data, return HTML strings).
"""

from __future__ import annotations

import html as html_mod
import re

from models import CalendarEvent


_MONTHS_RU = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
               'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


# ── Text helpers ───────────────────────────────────────────────────────────────

def years_ago_ru(years: int) -> str:
    """Return 'N лет/год/года назад' (full form)."""
    if years <= 0:
        return ''
    n = abs(years) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        word = 'лет'
    elif n1 == 1:
        word = 'год'
    elif 2 <= n1 <= 4:
        word = 'года'
    else:
        word = 'лет'
    return f'{years}\u00a0{word} назад'


def years_ago_abbr(years: int) -> str:
    """Return 'N г. назад' or 'N л. назад' (abbreviated)."""
    if years <= 0:
        return ''
    n = abs(years) % 100
    n1 = n % 10
    abbr = 'л.' if (11 <= n <= 19 or n1 == 0 or n1 >= 5) else 'г.'
    return f'{years}\u00a0{abbr} назад'


def fix_all_caps_name(name: str) -> str:
    """Convert ALL_CAPS word segments to TitleCase. 'A.C.REED' → 'A.C.Reed'."""
    def fix_seg(s: str) -> str:
        if len(s) > 1 and s.isalpha() and s.isupper():
            return s[0] + s[1:].lower()
        return s
    return ' '.join(
        '.'.join(fix_seg(part) for part in w.split('.'))
        for w in name.split()
    )


# ── Calendar text processing ───────────────────────────────────────────────────

def process_calendar_text(text: str, slug: str, title: str | None) -> str:
    """
    Normalize calendar event text for an artist:
    - Remove /artist/{slug}/ self-links
    - Remove Cyrillic-text links to other artists
    - Fix ALL CAPS title occurrences
    - Link first occurrence of title to /artist/{slug}/#calendar
    """
    if not text or not slug:
        return text

    display_title = fix_all_caps_name(title) if title else ''

    text = re.sub(
        r'<a\s[^>]*href="[^"]*/' + re.escape(slug) + r'/?"[^>]*>([\s\S]*?)</a>',
        lambda m: m.group(1), text)

    def _strip_cyrillic_link(m: re.Match) -> str:
        anchor = m.group(1)
        if sum(1 for c in anchor if '\u0400' <= c <= '\u04FF') > 0:
            return anchor
        return m.group(0)
    text = re.sub(
        r'<a\s[^>]*href="[^"]*?/artist/[^"]*"[^>]*>([\s\S]*?)</a>',
        _strip_cyrillic_link, text)

    if not display_title:
        return text

    if display_title != title and title:
        text = text.replace(title, display_title)

    link_open = f'<a href="/artist/{slug}/#calendar">'
    pattern = re.compile(re.escape(display_title), re.IGNORECASE)
    parts = re.split(r'(<a\s[^>]*>[\s\S]*?</a>)', text, flags=re.DOTALL)
    replaced = False
    result: list[str] = []
    for part in parts:
        if replaced or part.startswith('<a '):
            result.append(part)
        else:
            m = pattern.search(part)
            if m:
                result.append(part[:m.start()] + link_open
                               + html_mod.escape(display_title) + '</a>'
                               + part[m.end():])
                replaced = True
            else:
                result.append(part)
    text = ''.join(result)

    if not replaced:
        text = text.rstrip() + f' \u2014 {link_open}{html_mod.escape(display_title)}</a>'

    return text


# ── Calendar table HTML ────────────────────────────────────────────────────────

def calendar_events_html(events: list[CalendarEvent], current_year: int = 2026) -> str:
    """Render calendar events as an HTML table block for artist pages."""
    if not events:
        return ''
    rows: list[str] = [
        '<a name="calendar" id="calendar"></a>',
        '<h2>Календарь</h2>',
        '<table style="border-collapse:collapse;width:100%;border-spacing:0">',
    ]
    for ev in events:
        date   = ev.date or ''
        year   = date[:4] if date and len(date) >= 4 else str(ev.year or '') if ev.year else ''
        md     = ev.month_day or ''
        if md and len(md) == 5:
            try:
                mo  = int(md[:2])
                day = int(md[3:5])
                day_month = f'{day} {_MONTHS_RU[mo]}' if 1 <= mo <= 12 else ''
            except (ValueError, IndexError):
                day_month = ''
        else:
            day_month = ''

        text       = ev.text or ''
        picture    = ev.picture or ''
        title      = ev.title or ''
        slug       = ev.artist_slug or ''
        years_ago  = (current_year - int(year)) if year and year.isdigit() else 0
        cal_url    = f'/calendar/{year}/' if year else '/calendar/'

        date_lines = [
            f'<a href="{cal_url}" style="color:#333;font-weight:bold;font-size:1.1em">'
            f'{html_mod.escape(year)}</a>',
        ]
        if day_month:
            date_lines.append(
                f'<span style="color:#555;font-size:0.85em">{html_mod.escape(day_month)}</span>')
        if years_ago > 0:
            date_lines.append(
                f'<span style="color:#aaa;font-size:0.8em">{years_ago_abbr(years_ago)}</span>')
        date_cell = (
            f'<td style="white-space:nowrap;vertical-align:top;padding:8px 14px 8px 0;'
            f'width:1%;line-height:1.6">' + '<br>'.join(date_lines) + '</td>')

        if slug:
            text = process_calendar_text(text, slug, title)
        img_html = ''
        if picture:
            img_html = (
                f'<img src="/calendar/images/{html_mod.escape(picture)}" border="0" '
                f'align="right" vspace="2" hspace="6" '
                f'style="max-width:140px;max-height:100px;">')
        text_cell = f'<td style="vertical-align:top;padding:8px 0">{img_html}{text}</td>'
        rows.append(f'<tr style="border-bottom:1px solid #eee">{date_cell}{text_cell}</tr>')
    rows.append('</table>')
    return '\n'.join(rows)
