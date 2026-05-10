"""
Shared HTML rendering helpers: star ratings, review body formatting,
news body formatting, cover URLs, and cover image helpers.
"""

from __future__ import annotations

import re
from pathlib import Path

# Cover images live under bluesru-arc/covers/{asin}.jpg
_COVERS = Path(__file__).resolve().parent.parent / 'covers'


def cover_url_for_asin(asin: str | None) -> str:
    """Return a local /covers/{asin}.jpg path, falling back to Amazon CDN."""
    if not asin:
        return ''
    local = _COVERS / f'{asin}.jpg'
    if local.exists():
        return f'/covers/{asin}.jpg'
    return f'https://images-na.ssl-images-amazon.com/images/P/{asin}.01.MZZZZZZZ.jpg'


def star_rating_html(mark: int | None, size: str = '1.4rem') -> str:
    """
    Return HTML star rating widget.
    ``mark`` is 0–20 integer; displayed as 0–5 stars (divided by 2).
    """
    if not mark:
        return ''
    n = int(mark)
    rating = n / 2.0
    full = int(rating)
    half = (n % 2) == 1
    text = f'{rating:g} из 5'

    GOLD = '#C8952C'
    HALF = '#d4ab6a'
    GRAY = '#ccc'

    parts: list[str] = []
    if full:
        parts.append(f'<span style="color:{GOLD}">{"★" * full}</span>')
    if half:
        parts.append(f'<span style="color:{HALF}">★</span>')
    empty = 5 - full - (1 if half else 0)
    if empty > 0:
        parts.append(f'<span style="color:{GRAY}">{"★" * empty}</span>')

    return f'<span class="star-rating" title="{text}">{"".join(parts)}</span> '


def format_mark_ats(mark: int | None) -> str:
    """Format a 0–20 mark as '@@@@@' style string (legacy display)."""
    if not mark:
        return ''
    n = int(mark)
    return '@' * (n // 2) + ('+' if n % 2 else '')


def format_review_body(body: str) -> str:
    """Clean up album review body HTML: strip allmusic links, ensure <p> wrapping."""
    body = body.strip()
    body = re.sub(
        r'<a\b[^>]*allmusic\.com[^>]*>(.*?)</a>', r'\1',
        body, flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(r'<img\b[^>]*image\.allmusic\.com[^>]*/?>', '',
                  body, flags=re.IGNORECASE)
    body = re.sub(r'https?://(?:www\.)?allmusic\.com/\S+', '',
                  body, flags=re.IGNORECASE)
    if not body:
        return body
    if '\n\n' not in body:
        body_lower = body.lower()
        if body_lower.startswith('<p>') and body_lower.endswith('</p>'):
            return body
        return f'<p>{body}</p>'
    parts = re.split(r'\n{2,}', body)
    result: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        pl = part.lower()
        if pl.startswith('<p>') or pl.endswith('</p>'):
            result.append(part)
        else:
            result.append(f'<p>{part}</p>')
    return '\n'.join(result)


def format_news_body(body: str) -> str:
    """Ensure news body text has proper <p> wrapping."""
    body = body.strip()
    if not body:
        return body
    body = re.sub(r'</p>\s*\n+\s*<p>', '</p><p>', body, flags=re.IGNORECASE)
    if '\n\n' in body:
        parts = re.split(r'\n{2,}', body)
        joined: list[str] = []
        for i, part in enumerate(parts):
            part = part.strip()
            if not part:
                continue
            if i > 0 and joined:
                prev = joined[-1]
                if prev.lower().rstrip().endswith('</p>') or part.lower().startswith('<p>'):
                    joined.append(part)
                else:
                    joined[-1] = prev + '</p><p>' + part
                    continue
            joined.append(part)
        body = '\n'.join(joined)
    body_lower = body.lower()
    if not (body_lower.startswith('<p>') and body_lower.rstrip().endswith('</p>')):
        body = f'<p>{body}</p>'
    return body


def format_news_body_simple(body: str) -> str:
    """Simpler <p> wrapping for news bodies (used in some templates)."""
    body = body.strip()
    if not body:
        return body
    if re.search(r'<p[\s>]', body, re.IGNORECASE):
        body = re.sub(r'</p>\s*\n+\s*<p>', '</p><p>', body, flags=re.IGNORECASE)
        return body
    if '\n\n' in body:
        parts = re.split(r'\n{2,}', body)
        return '\n'.join(f'<p>{p.strip()}</p>' for p in parts if p.strip())
    return f'<p>{body}</p>'
