#!/usr/bin/env python3
"""Generate photo gallery index pages and photo master index."""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import (
    FOOTER,
    JINJA_ENV,
    MEDIA_BASE_URL,
    SITE,
    _write_gallery_redirects,
    load_all_gallery_yamls,
)
from gallery_utils import gallery_canonical_url as _gallery_canonical_url


def generate_photo_pages() -> None:
    """Generate gallery index pages from data/galleries/ YAML."""
    galleries = load_all_gallery_yamls()
    tmpl      = JINJA_ENV.get_template('gallery.html.j2')
    count     = 0
    redirects: list[tuple[str, str]] = []

    for g in galleries:
        yaml_slug = g.get('slug', '')
        if not yaml_slug:
            gpath     = g.get('path', '')
            yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')
        data  = g
        gpath = data.get('path', '') or yaml_slug

        if data.get('exclude'):
            continue

        photos = [p for p in (data.get('photos') or [])
                  if isinstance(p, dict) and p.get('file')]

        legacy_path                = gpath
        canonical_rel, year_str    = _gallery_canonical_url(data, gpath)
        gallery_media_base         = f'{MEDIA_BASE_URL}/{canonical_rel}'

        def _abs_url(rel_file: str) -> str:
            return f'{gallery_media_base}/{rel_file}'

        def _thumb_url(rel_file: str) -> str:
            stem, _, ext = rel_file.rpartition('.')
            return f'{gallery_media_base}/{stem}-400w.jpg'

        photos_with_media = [
            dict(p, file=_abs_url(p['file']), thumb=_thumb_url(p['file']))
            for p in photos if p.get('file')
        ]
        photos_json = json.dumps(
            [{'file':    _abs_url(p['file']),
              'caption': p.get('caption') or '',
              'thumb':   _thumb_url(p['file'])}
             for p in photos if p.get('file')],
            ensure_ascii=False)

        clean_title    = data.get('clean_title') or data.get('title') or legacy_path
        canonical_date = data.get('canonical_date') or data.get('date') or ''
        description    = data.get('description') or ''
        extra_text     = data.get('extra_text') or ''
        if len(extra_text) > 500:
            extra_text = ''

        html = tmpl.render(
            path=legacy_path,
            canonical_url='/' + canonical_rel + '/',
            title=clean_title,
            date=canonical_date,
            description=description,
            extra_text=extra_text if not description else '',
            photo_count=data.get('photo_count', len(photos)),
            photos=photos_with_media,
            photos_json=photos_json,
            year=year_str,
            source_articles=data.get('source_articles') or [],
            footer=FOOTER,
        )

        out_dir = SITE / canonical_rel
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'index.html').write_text(html, encoding='utf-8')
        count += 1

        old_url = f'/bluesnews/{legacy_path}/'
        new_url = f'/{canonical_rel}/'
        if old_url != new_url:
            redirects.append((old_url, new_url))

    _write_gallery_redirects(redirects)
    print(f"  galleries: {count} index pages written → site/photo/YYYY/*/index.html")
    print(f"  gallery redirects: {len(redirects)} → bluesru-arc/_redirects")


def generate_photo_index() -> None:
    """Generate /photo/index.html — master gallery index organized by year."""
    galleries = load_all_gallery_yamls()

    cards: list[dict] = []
    for g in galleries:
        if g.get('exclude'):
            continue
        yaml_slug = g.get('slug', '')
        gpath     = g.get('path', '')
        if not yaml_slug and gpath:
            yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')
        if not yaml_slug:
            continue

        data  = g
        gpath = gpath or data.get('path', yaml_slug)

        canonical_rel, year_str = _gallery_canonical_url(data, gpath)

        thumb  = ''
        photos = [p for p in (data.get('photos') or [])
                  if isinstance(p, dict) and p.get('file')]
        if photos:
            first_photo = photos[0]
            thumb = first_photo.get('file') or first_photo.get('thumb') or ''

        clean_title    = data.get('clean_title') or data.get('title') or gpath
        canonical_date = data.get('canonical_date') or data.get('date') or ''

        try:
            year_int = int(year_str) if year_str and year_str != 'misc' else None
        except ValueError:
            year_int = None

        if thumb:
            stem, _, ext = thumb.rpartition('.')
            thumb_file   = (f'{stem}-400w.jpg'
                            if ext.lower() in ('jpg', 'jpeg', 'png', 'webp') else thumb)
            abs_thumb    = '/' + canonical_rel + '/' + thumb_file
        else:
            abs_thumb = ''

        cards.append({
            'path':         gpath,
            'canonical_url': '/' + canonical_rel + '/',
            'title':        clean_title,
            'date':         canonical_date,
            'photo_count':  g.get('photo_count', 0),
            'thumb':        abs_thumb,
            'year':         year_int,
            'year_str':     year_str,
        })

    # Clean up stale gallery dirs
    yaml_valid_dirs: set[tuple] = set()
    for card in cards:
        url   = card.get('canonical_url', '')
        parts = url.strip('/').split('/')
        if len(parts) >= 3:
            yaml_valid_dirs.add((parts[1], parts[2]))
    out_dir = SITE / 'photo'
    stale_removed = 0
    if out_dir.exists():
        for year_dir in sorted(out_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for gal_dir in sorted(year_dir.iterdir()):
                if not gal_dir.is_dir():
                    continue
                key = (year_dir.name, gal_dir.name)
                if key in yaml_valid_dirs:
                    continue
                if gal_dir.name.endswith('-notodden-blues-festival'):
                    continue
                shutil.rmtree(gal_dir)
                stale_removed += 1
    if stale_removed:
        print(f"  photo index: removed {stale_removed} stale gallery dirs")

    # Include extra cards from other generators by scanning site/photo/
    yaml_urls  = {c['canonical_url'] for c in cards}
    photo_root = SITE / 'photo'
    if photo_root.exists():
        for year_dir in sorted(photo_root.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            yr_int = int(year_dir.name)
            for gal_dir in sorted(year_dir.iterdir()):
                if not gal_dir.is_dir():
                    continue
                canon_url = f'/photo/{year_dir.name}/{gal_dir.name}/'
                if canon_url in yaml_urls:
                    continue
                idx_html = gal_dir / 'index.html'
                if not idx_html.exists():
                    continue
                try:
                    html_text = idx_html.read_text(encoding='utf-8', errors='ignore')
                    m_title   = re.search(r'<h1>(.*?)</h1>', html_text)
                    m_count   = re.search(r'gallery-count">\s*(\d+)', html_text)
                    title     = re.sub(r'<[^>]+>', '', m_title.group(1)) if m_title else gal_dir.name
                    count     = int(m_count.group(1)) if m_count else 0
                    imgs      = re.findall(r'<img src="([^"]+\.jpg)"', html_text)
                    thumb     = imgs[0] if imgs else ''
                    if thumb and not thumb.startswith('/') and not thumb.startswith('http'):
                        thumb = canon_url + thumb
                except Exception:
                    title, count, thumb = gal_dir.name, 0, ''
                cards.append({
                    'path':          gal_dir.name,
                    'canonical_url': canon_url,
                    'title':         title,
                    'date':          year_dir.name,
                    'photo_count':   count,
                    'thumb':         thumb,
                    'year':          yr_int,
                    'year_str':      year_dir.name,
                })

    year_map: dict[int, list] = {}
    misc: list[dict] = []
    for card in cards:
        y = card['year']
        if y:
            year_map.setdefault(y, []).append(card)
        else:
            misc.append(card)

    years_sorted = sorted(year_map.keys(), reverse=True)
    by_year      = [(y, year_map[y]) for y in years_sorted]

    tmpl = JINJA_ENV.get_template('photo_index.html.j2')
    html = tmpl.render(
        years=years_sorted,
        by_year=by_year,
        misc_galleries=misc,
        footer=FOOTER,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'index.html').write_text(html, encoding='utf-8')
    total = len(cards)
    print(f"  photo index: {total} galleries, {len(years_sorted)} years → site/photo/index.html")


if __name__ == '__main__':
    if '--section' in sys.argv:
        section = sys.argv[sys.argv.index('--section') + 1]
        if section == 'photo-pages':
            generate_photo_pages()
        elif section == 'photo-index':
            generate_photo_index()
    else:
        generate_photo_pages()
