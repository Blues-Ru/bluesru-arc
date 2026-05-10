"""
Gallery path/URL computation utilities.

All functions are pure (take raw data, return strings/tuples).
"""

from __future__ import annotations

import re
from pathlib import Path


def gallery_year(path: str) -> int | None:
    """Extract a 4-digit year from a gallery path string."""
    top = path.split('/')[0].lstrip('_')
    m = re.search(r'((?:19|20)\d\d)', top)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    m = re.match(r'^(\d\d)[^0-9]', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    m = re.match(r'^(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    return None


def gallery_canonical_url(data: dict, gpath: str) -> tuple[str, str]:
    """
    Compute (canonical_rel_path, year_str) for a gallery.

    ``canonical_rel_path`` is e.g. ``photo/2005/2005-06-12-notodden``.
    ``year_str`` is e.g. ``'2005'`` or ``'misc'``.
    """
    canonical_date = data.get('canonical_date') or ''
    gallery_slug = data.get('slug') or re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')

    m = re.match(r'^(\d{4})', str(canonical_date))
    if m:
        year_str = m.group(1)
    else:
        year = gallery_year(gpath)
        year_str = str(year) if year else 'misc'

    cd = str(canonical_date)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', cd):
        date_prefix = cd
    elif re.match(r'^\d{4}-\d{2}$', cd):
        date_prefix = cd
    elif re.match(r'^\d{4}$', cd):
        date_prefix = cd
    else:
        date_prefix = year_str

    clean_slug = gallery_slug
    clean_slug = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', clean_slug).rstrip('-')
    clean_slug = re.sub(r'-\d{4}-\d{2}$', '', clean_slug).rstrip('-')
    clean_slug = re.sub(r'-\d{4}$', '', clean_slug).rstrip('-')
    if not clean_slug:
        clean_slug = gallery_slug

    if gallery_slug.startswith(date_prefix):
        dir_name = gallery_slug
    else:
        dir_name = f'{date_prefix}-{clean_slug}'

    return f'photo/{year_str}/{dir_name}', year_str


def write_gallery_redirects(arc_dir: Path, redirects: list[tuple[str, str]]) -> None:
    """Write gallery old→new URL redirects into _redirects, inside markers."""
    redirects_file = arc_dir / '_redirects'
    if not redirects_file.exists():
        return
    content = redirects_file.read_text(encoding='utf-8')
    marker_start = '# BEGIN gallery-redirects'
    marker_end   = '# END gallery-redirects'
    if marker_start in content:
        start = content.index(marker_start)
        end   = content.index(marker_end) + len(marker_end)
        content = content[:start].rstrip() + '\n' + content[end:].lstrip('\n')
    lines = [marker_start]
    for old, new in redirects:
        lines.append(f'{old.replace(" ", "%20")}  {new}  301')
    lines.append(marker_end)
    content = content.rstrip('\n') + '\n\n' + '\n'.join(lines) + '\n'
    redirects_file.write_text(content, encoding='utf-8')
