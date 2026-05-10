"""
Artist page building utilities.

Functions for constructing artist resource links, album lists, ATB links,
and processing artist HTML directory trees.
"""

from __future__ import annotations

import html as html_mod
import re
import shutil
from pathlib import Path
from typing import Any

from models import Album, ArtistLink, CalendarEvent
from render_utils import cover_url_for_asin, star_rating_html


# ── URL helpers ────────────────────────────────────────────────────────────────

def strip_artist_prefix(artist_slug: str, album_slug: str) -> str:
    """
    Remove redundant artist prefix from album slug.
    'albert-collins-cold-snap' → 'cold-snap' (given artist_slug='albert-collins').
    """
    if (artist_slug
            and artist_slug != 'various-musicians'
            and album_slug.startswith(artist_slug + '-')):
        return album_slug[len(artist_slug) + 1:]
    return album_slug


# ── Subpage scanning ───────────────────────────────────────────────────────────

_SUBPAGE_PATTERNS = [
    ('tabs.html',   'Ноты',   'tabs'),
    ('lyrics.html', 'Тексты', 'lyrics'),
    ('photos.html', 'Фото',   'photos'),
    ('press.html',  'Пресса', 'press'),
]
_INTERVIEW_GLOBS = ['*interv*.html', 'interview.html', '*_int.html', '*_interview.html']
_ARTICLE_GLOBS   = ['article.html', '*article*.html', '*_article.html']
_ARTICLE_EXCLUDE = {'allman-brothers'}
_SERIES_RE = re.compile(r'^(.+?)-0*(\d+)\.html?$', re.IGNORECASE)


def scan_artist_subpages(artist_dir: Path, artist_slug: str) -> list[dict]:
    """
    Scan content/artist/{slug}/ for sub-pages and return resource dicts:
        {'type': str, 'url': str, 'label': str}
    """
    if not artist_dir or not artist_dir.exists():
        return []

    resources: list[dict] = []
    found: set[str] = set()
    base = f'/artist/{artist_slug}'

    for filename, label, rtype in _SUBPAGE_PATTERNS:
        if rtype in found:
            continue
        f = artist_dir / filename
        if f.exists():
            resources.append({'type': rtype, 'url': f'{base}/{filename}', 'label': label})
            found.add(rtype)
        elif rtype == 'tabs' and (artist_dir / 'tabs').is_dir():
            resources.append({'type': rtype, 'url': f'{base}/tabs/', 'label': label})
            found.add(rtype)

    if 'interview' not in found:
        for glob_pat in _INTERVIEW_GLOBS:
            matches = sorted(artist_dir.glob(glob_pat))
            if matches:
                fname = matches[0].name
                resources.append({'type': 'interview', 'url': f'{base}/{fname}', 'label': 'Интервью'})
                found.add('interview')
                break

    if 'article' not in found and artist_slug not in _ARTICLE_EXCLUDE:
        for glob_pat in _ARTICLE_GLOBS:
            matches = sorted(artist_dir.glob(glob_pat))
            if matches:
                fname = matches[0].name
                resources.append({'type': 'article', 'url': f'{base}/{fname}', 'label': 'Статья'})
                found.add('article')
                break

    if 'series' not in found:
        series_groups: dict[str, list] = {}
        for f in artist_dir.iterdir():
            if f.suffix.lower() not in ('.html', '.htm'):
                continue
            m = _SERIES_RE.match(f.name)
            if not m:
                continue
            prefix = m.group(1)
            num    = int(m.group(2))
            series_groups.setdefault(prefix, []).append((num, f.name))
        for prefix, entries in series_groups.items():
            if len(entries) < 2:
                continue
            entries.sort()
            first = entries[0][1]
            resources.append({'type': 'article', 'url': f'{base}/{first}', 'label': 'Статья'})
            found.add('article')
            found.add('series')
            break

    return resources


# ── ATB links ─────────────────────────────────────────────────────────────────

def atb_links_html(atb_episodes: list[dict]) -> str:
    """Render ATB episode links block for artist pages."""
    if not atb_episodes:
        return ''
    lines: list[str] = []
    for ep in sorted(atb_episodes, key=lambda e: e.get('date', ''), reverse=True):
        label    = html_mod.escape(ep['summary'])
        url      = ep['page_url']
        date     = ep.get('date', '')
        date_str = (f'<small style="color:#777">{html_mod.escape(date)}</small> '
                    if date else '')
        lines.append(f'{date_str}<a href="{url}">{label}</a>')
    return '<b>Весь этот блюз:</b><br>' + '<br>'.join(lines)


# ── Resource links ─────────────────────────────────────────────────────────────

_RTYPE_MAP = {
    'Тексты': 'lyrics', 'Ноты': 'tabs', 'Интервью': 'interview',
    'Статья': 'article', 'Фото': 'photo', 'Пресса': 'press',
}


def collect_artist_links(
    slug: str,
    artist_id: str,
    src_dir: Path | None,
    galleries_by_slug: dict[str, list[dict]],
    resources_by_artist: dict[str, list[dict]],
    calendar_by_slug: dict[str, list],
    has_album_list: bool = False,
    artist_streaming_ids: Any = None,           # ArtistStreamingIds | None
    streaming_url_templates: dict | None = None,
    streaming_labels: dict | None = None,
) -> list[ArtistLink]:
    """
    Build structured resource links for an artist.
    Returns list of ArtistLink objects.
    """
    from streaming import ARTIST_URL_TEMPLATES, PLATFORM_LABELS
    streaming_url_templates = streaming_url_templates or ARTIST_URL_TEMPLATES
    streaming_labels        = streaming_labels or PLATFORM_LABELS

    links: list[ArtistLink] = []
    seen: set[str] = set()

    # 1. Auto-detected sub-pages
    auto = scan_artist_subpages(src_dir, slug) if (src_dir and slug) else []
    auto_types = {r['type'] for r in auto}
    for r in auto:
        links.append(ArtistLink(type=r['type'], url=r['url'], title=r['label'], external=False))
        seen.add(r['url'])

    # 2. Photo galleries
    for g in sorted(galleries_by_slug.get(slug, []), key=lambda g: g.get('date', '')):
        links.append(ArtistLink(type='photo', url=g['url'],
                                title=g.get('title') or 'Фото', external=False))
        seen.add(g['url'])

    # 3. Manual resources from artists.yaml
    for r in resources_by_artist.get(str(artist_id), []):
        rtype = r.get('type_short', '') or ''
        url   = r.get('url', '') or ''
        if not url or r.get('type_id') == 1:
            continue
        if '.aspx' in url.lower():
            continue
        url = re.sub(r'^https?://(?:www\.)?blues\.ru', '', url, flags=re.IGNORECASE)
        if url.startswith('/bluesmen/') and slug:
            url = f'/artist/{slug}' + re.sub(r'^/bluesmen/[^/]+', '', url)
        elif url.startswith('/artist/') and slug:
            url = f'/artist/{slug}' + re.sub(r'^/artist/[^/]+', '', url)
        if re.match(r'^/[Aa][Tt][Bb]/.*\.mp3$', url):
            continue
        if url.rstrip('/') == f'/artist/{slug}':
            continue
        if '#' in url and url.split('#')[0].rstrip('/') == f'/artist/{slug}':
            continue
        mapped = _RTYPE_MAP.get(rtype, '')
        if mapped and mapped in auto_types:
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(ArtistLink(type=mapped or rtype.lower() or 'link',
                                url=url, title=rtype or url, external=False))

    # 4. Album reviews section
    if has_album_list and slug:
        links.append(ArtistLink(type='review', url=f'/artist/{slug}/#review',
                                title='Обзоры', external=False))

    # 5. Streaming platforms
    if artist_streaming_ids:
        for platform, tmpl in streaming_url_templates.items():
            val = getattr(artist_streaming_ids, f'{platform}_id', None)
            if val:
                links.append(ArtistLink(
                    type='streaming', platform=platform,
                    url=tmpl.format(val),
                    title=streaming_labels.get(platform, platform),
                    external=True))

    # 6. Calendar
    if slug and calendar_by_slug.get(slug):
        links.append(ArtistLink(type='calendar', url=f'/artist/{slug}/#calendar',
                                title='Календарь', external=False))

    return links


def format_artist_links(links: list[ArtistLink], types: set[str] | None = None) -> str:
    """Format ArtistLink list as ' | '-separated HTML anchors."""
    parts: list[str] = []
    for r in links:
        if types is not None and r.type not in types:
            continue
        target = ' target="_blank"' if r.external else ''
        parts.append(f'<a href="{r.url}"{target}>{html_mod.escape(r.title)}</a>')
    return ' | '.join(parts)


# ── Album list HTML ────────────────────────────────────────────────────────────

def build_album_list_html(
    artist_slug: str,
    artist_id: str,
    albums_by_artist: dict[str, list[dict]],
) -> str:
    """Build the album review list HTML block for an artist page."""
    albums = albums_by_artist.get(str(artist_id), [])
    if not albums:
        return ''

    def _year_key(a: dict) -> int:
        try:
            return -int(a.get('year', 0) or 0)
        except (TypeError, ValueError):
            return 0

    albums = sorted(albums, key=_year_key)

    THUMB = 80
    PLACEHOLDER = (
        f'<div style="width:{THUMB}px;height:{THUMB}px;background:#e8e8e8;'
        f'border:1px solid #ccc;display:flex;align-items:center;'
        f'justify-content:center;font-size:2em;color:#bbb">♪</div>'
    )

    parts = [
        '<a name="review" id="review"></a>\n',
        '<h2>Обзоры</h2>\n',
    ]

    for a in albums:
        asin       = a.get('asin', '')
        album_slug = a.get('slug', '')
        url_seg    = strip_artist_prefix(artist_slug, album_slug) if album_slug else ''
        if url_seg:
            href = f'/artist/{artist_slug}/{url_seg}/'
        elif a.get('review_slug'):
            href = f'/review/{a["review_slug"]}/'
        else:
            href = ''

        title = html_mod.escape(a.get('title', '') or a.get('artist', '') or '')
        year  = str(a.get('year', '') or '')

        if asin:
            img = (f'<img src="{cover_url_for_asin(asin)}" width="{THUMB}" height="{THUMB}" '
                   f'alt="" border="0" style="display:block;object-fit:cover">')
        else:
            img = PLACEHOLDER
        cover_block = f'<a href="{href}">{img}</a>' if href else img

        title_html = (f'<a href="{href}" style="font-size:1.05em;font-weight:bold">{title}</a>'
                      if href else f'<span style="font-size:1.05em;font-weight:bold">{title}</span>')

        rev_parts: list[str] = []
        for rv in a.get('reviews', []):
            author = html_mod.escape(rv.get('author', '') or '')
            stars  = star_rating_html(rv.get('mark'))
            rev_parts.append(f'{stars}{author}')
        reviewers_html = (
            f'<div style="font-size:0.85em;color:#555;margin-top:2px">'
            f'{"<br>".join(rev_parts)}</div>'
        ) if rev_parts else ''

        parts.append(
            f'<div style="display:flex;align-items:flex-start;gap:10px;'
            f'padding:6px 0;border-bottom:1px solid #eee">\n'
            f'  <div style="flex-shrink:0">{cover_block}</div>\n'
            f'  <div style="flex-shrink:0;width:42px;color:#888;font-size:0.9em;padding-top:6px">'
            f'{html_mod.escape(year)}</div>\n'
            f'  <div style="flex:1;padding-top:6px">{title_html}{reviewers_html}</div>\n'
            f'</div>\n'
        )

    return ''.join(parts)


# ── Artist directory processing ────────────────────────────────────────────────

def find_main_htm(src_dir: Path) -> Path | None:
    """Find the primary HTML file in an artist source directory."""
    dir_name   = src_dir.name
    skip_sfx   = ['_lyr', '_tab', '_lyric', '_lyrics', '_tabs']
    index_names = ('index.htm', 'index.html')
    htm_files  = [
        f for f in sorted(src_dir.iterdir())
        if f.suffix.lower() in ('.htm', '.html')
        and f.name.lower() not in ('default.htm', 'default.html')
        and not any(f.stem.lower().endswith(s) for s in skip_sfx)
    ]
    if not htm_files:
        return None
    for f in htm_files:
        if f.name.lower() in index_names:
            return f
    dir_lower = dir_name.lower()
    for f in htm_files:
        if f.stem.lower() == dir_lower:
            return f
    return htm_files[0]


def process_artist_dir(
    artist: dict,
    src_dir: Path,
    src_root: Path,
    site_dir: Path,
    skip_extensions: set[str],
    process_html_fn: Any,
    artist_resources: list | None = None,
    artist_albums_html: str | None = None,
    artist_atb_html: str | None = None,
    artist_resource_links_html: str | None = None,
    artist_calendar_html: str | None = None,
) -> None:
    """
    Copy an artist's source directory to the output site, processing HTML files.
    ``process_html_fn`` is called for each HTML file with signature:
        (content, src_dir, src_root, **kwargs) -> str
    """
    slug     = artist.get('slug', '')
    url_dir  = slug or src_dir.name
    dst_dir  = site_dir / 'artist' / url_dir
    dst_dir.mkdir(parents=True, exist_ok=True)

    main_htm = find_main_htm(src_dir)

    for src_path in sorted(src_dir.rglob('*')):
        if not src_path.is_file():
            continue
        ext = src_path.suffix.lower()
        if ext in skip_extensions:
            continue
        if src_path.name.lower() in {'config.xml'}:
            continue

        rel   = src_path.relative_to(src_dir)
        parts = rel.parts
        out_name      = normalize_filename(src_path.name)
        is_main_rename = (len(parts) == 1 and main_htm and src_path == main_htm)
        if is_main_rename:
            out_name = 'index.html'

        if len(parts) > 1:
            dst_path = dst_dir / Path(*parts[:-1]) / out_name
        else:
            dst_path = dst_dir / out_name
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if ext in ('.htm', '.html'):
            from html_utils import read_file
            content = read_file(src_path)
            if content:
                is_main = main_htm and src_path == main_htm
                content = process_html_fn(
                    content, src_path.parent, src_root,
                    artist_slug=slug if is_main else None,
                    artist_name=artist.get('name', '') if is_main else None,
                    artist_legacy_dir=url_dir if is_main else None,
                    artist_resources=artist_resources if is_main else None,
                    artist_albums_html=artist_albums_html if is_main else None,
                    artist_atb_html=artist_atb_html if is_main else None,
                    artist_resource_links_html=artist_resource_links_html if is_main else None,
                    artist_calendar_html=artist_calendar_html if is_main else None,
                )
                dst_path.write_text(content, encoding='utf-8')

                if is_main_rename and src_path.name.lower() not in (
                        'default.htm', 'default.html', 'index.htm', 'index.html'):
                    orig_dst = dst_dir / normalize_filename(src_path.name)
                    if orig_dst != dst_path:
                        orig_dst.write_text(content, encoding='utf-8')
                        if orig_dst.suffix == '.html':
                            orig_dst.with_suffix('.htm').write_text(content, encoding='utf-8')

                if dst_path.suffix == '.html' and dst_path.name != 'index.html':
                    htm_alias = dst_path.with_suffix('.htm')
                    if htm_alias != dst_path:
                        htm_alias.write_text(content, encoding='utf-8')

                raw_fname = src_path.name
                if '_' in raw_fname or (raw_fname != raw_fname.lower() and '.' in raw_fname):
                    norm_name = raw_fname.replace('_', '-').lower()
                    if norm_name.endswith('.htm'):
                        norm_name = norm_name[:-4] + '.html'
                    norm_path = dst_path.parent / norm_name
                    if norm_path != dst_path and norm_name != 'index.html':
                        norm_path.write_text(content, encoding='utf-8')
            continue

        shutil.copy2(src_path, dst_path)


def normalize_filename(name: str) -> str:
    """Map legacy index names to index.html."""
    if name.lower() in ('default.htm', 'default.html', 'index.htm'):
        return 'index.html'
    return name
