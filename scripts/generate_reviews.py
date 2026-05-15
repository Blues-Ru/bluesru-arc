#!/usr/bin/env python3
"""Generate review (albumview) pages and review index."""
import re
import sys
from collections import defaultdict, OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import (
    ALBUMS_DIR,
    FOOTER,
    JINJA_ENV,
    MONTHS_RU,
    SITE,
    _strip_artist_prefix,
    load_reviews,
    load_albums,
    load_artists,
    get_review_author_slug,
)
from render_utils import cover_url_for_asin, format_mark_ats, format_review_body
from streaming import streaming_links_html, album_stream_icons_html, artist_stream_icons_html
from data import store


def generate_reviews() -> None:
    print("Generating review pages...")
    reviews, review_by_album = load_reviews()
    albums  = load_albums()
    artists = {str(a['id']): a for a in load_artists()}

    def artist_slug_for_url(artist: dict) -> str:
        if not artist:
            return 'various-musicians'
        slug = artist.get('slug', '')
        if slug:
            return slug
        lp = (artist.get('legacy_path') or '').strip('/')
        parts = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        if legacy_dir and '.' not in legacy_dir and not legacy_dir.startswith('www.'):
            return re.sub(r'[^a-z0-9]+', '-', legacy_dir.lower()).strip('-')
        return 'various-musicians'

    tmpl     = JINJA_ENV.get_template('albumview.html.j2')
    tmpl_idx = JINJA_ENV.get_template('review_index.html.j2')
    generated = 0

    by_month: dict[str, list] = defaultdict(list)

    # Group reviews by album page URL so multiple reviews render on one page
    by_url: OrderedDict = OrderedDict()
    for meta, body in reviews:
        review_slug = meta.get('slug', '')
        album_id    = str(meta.get('album_id', ''))
        album       = albums.get(album_id, {})
        artist_id   = str(album.get('artist_id', '') or meta.get('artist_id', '') or '')
        artist      = artists.get(artist_id, {})

        a_slug         = artist_slug_for_url(artist) if artist_id else 'various-musicians'
        album_slug     = album.get('slug', '') or review_slug
        url_album_slug = _strip_artist_prefix(a_slug, album_slug)
        new_url        = f'/artist/{a_slug}/{url_album_slug}/'

        mark = meta.get('mark')
        _auth = meta.get('author', '')
        _auth_slug = get_review_author_slug(_auth)
        review_data = {
            'id':          meta.get('id', ''),
            'album_title': album.get('title', '') or meta.get('album', ''),
            'year':        album.get('year', ''),
            'author':      _auth,
            'author_url':  f'/author/{_auth_slug}/' if _auth_slug else '',
            'body':        format_review_body(body),
            'mark':        mark,
            'mark_text':   format_mark_ats(mark) if mark else '',
        }

        date_str = str(meta.get('date', ''))
        if new_url not in by_url:
            by_url[new_url] = {
                'album':          album,
                'artist':         artist,
                'a_slug':         a_slug,
                'url_album_slug': url_album_slug,
                'new_url':        new_url,
                'reviews':        [],
                'date_str':       date_str,
            }
        if body:
            by_url[new_url]['reviews'].append(review_data)
        if date_str < by_url[new_url]['date_str'] or not by_url[new_url]['date_str']:
            by_url[new_url]['date_str'] = date_str

    for page in by_url.values():
        album          = page['album']
        artist         = page['artist']
        a_slug         = page['a_slug']
        url_album_slug = page['url_album_slug']
        new_url        = page['new_url']
        date_str       = page['date_str']
        alb_slug       = album.get('slug', '')

        alb_ids    = store.album_streaming().get(alb_slug)
        artist_ids = store.artist_streaming().get(a_slug)
        out = tmpl.render(
            album=album,
            cover_url=cover_url_for_asin(album.get('asin', ''), fallback=True),
            artist_name=artist.get('name') or album.get('artist') or '',
            artist_legacy_path=a_slug,
            reviews=page['reviews'],
            streaming_links=streaming_links_html(alb_slug, 'album', store),
            artist_streaming_links=streaming_links_html(a_slug, 'artist', store),
            stream_icons=album_stream_icons_html(alb_ids) or artist_stream_icons_html(artist_ids),
            footer=FOOTER,
        )
        dst = SITE / 'artist' / a_slug / url_album_slug / 'index.html'
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out, encoding='utf-8')
        generated += 1

        first_review = page['reviews'][0] if page['reviews'] else {}
        month_key = date_str[:7] if len(date_str) >= 7 else '0000-00'
        by_month[month_key].append({
            'url':         new_url,
            'artist_name': artist.get('name') or album.get('artist') or '',
            'album_title': album.get('title') or album.get('artist') or '',
            'year':        album.get('year', ''),
            'author':      first_review.get('author', ''),
            'asin':        album.get('asin', ''),
            'cover_url':   cover_url_for_asin(album.get('asin', ''), fallback=True),
            'date_str':    date_str,
            'mark':        first_review.get('mark'),
        })

    month_keys = sorted(by_month.keys(), reverse=True)

    years_months: OrderedDict = OrderedDict()
    for mk in month_keys:
        if mk == '0000-00':
            continue
        yr = mk[:4]
        years_months.setdefault(yr, []).append(mk)
    year_list = list(years_months.keys())

    def year_nav_data(current_year: str | None = None) -> list[dict]:
        return [{'year': y, 'current': y == current_year} for y in year_list]

    def months_for_year(yr: str) -> list[dict]:
        return [
            {'key': mk, 'label': MONTHS_RU[int(mk[5:7])]}
            for mk in years_months.get(yr, [])
        ]

    (SITE / 'review').mkdir(parents=True, exist_ok=True)

    current_yr    = year_list[0] if year_list else None
    curr_mkeys    = years_months.get(current_yr, [])
    index_blocks: list[dict] = []
    for mk in curr_mkeys:
        mo      = int(mk[5:7])
        entries = sorted(by_month[mk], key=lambda x: x['date_str'], reverse=True)
        index_blocks.append({'label': f'{current_yr} {MONTHS_RU[mo]}', 'key': mk, 'reviews': entries})

    (SITE / 'review' / 'index.html').write_text(tmpl_idx.render(
        current_month=None,
        current_year=current_yr,
        month_blocks=index_blocks,
        nav_links=None,
        more_html=None,
        month_list=None,
        year_nav=year_nav_data(current_yr),
        current_year_months=months_for_year(current_yr or ''),
        footer=FOOTER,
        canonical_url='https://blues.ru/review/',
    ), encoding='utf-8')

    for yi, yr in enumerate(year_list):
        yr_mkeys  = years_months[yr]
        yr_blocks = []
        for mk in yr_mkeys:
            mo      = int(mk[5:7])
            entries = sorted(by_month[mk], key=lambda x: x['date_str'], reverse=True)
            yr_blocks.append({'label': f'{yr} {MONTHS_RU[mo]}', 'key': mk, 'reviews': entries})
        dst_yr = SITE / 'review' / yr / 'index.html'
        dst_yr.parent.mkdir(parents=True, exist_ok=True)
        dst_yr.write_text(tmpl_idx.render(
            current_month=None,
            current_year=yr,
            month_blocks=yr_blocks,
            nav_links=None,
            more_html=None,
            month_list=None,
            year_nav=year_nav_data(yr),
            current_year_months=months_for_year(yr),
            footer=FOOTER,
        ), encoding='utf-8')

    # ── Per-author pages ─────────────────────────────────────────────────────
    by_author: dict[str, list] = defaultdict(list)
    for meta, body in reviews:
        author = (meta.get('author', '') or '').strip()
        if not author:
            continue
        album_id  = str(meta.get('album_id', ''))
        album     = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or meta.get('artist_id', '') or '')
        artist    = artists.get(artist_id, {})
        a_slug    = artist_slug_for_url(artist) if artist_id else 'various-musicians'
        album_slug = album.get('slug', '') or meta.get('slug', '')
        date_str   = str(meta.get('date', ''))
        by_author[author].append({
            'url':         f'/artist/{a_slug}/{_strip_artist_prefix(a_slug, album_slug)}/',
            'artist_name': artist.get('name') or album.get('artist') or '',
            'album_title': album.get('title') or meta.get('album') or '',
            'year':        album.get('year', ''),
            'asin':        album.get('asin', ''),
            'cover_url':   cover_url_for_asin(album.get('asin', ''), fallback=True),
            'date_str':    date_str,
        })

    def author_slug(name: str, idx: int) -> str:
        s = get_review_author_slug(name)
        if s:
            return s
        # Fallback for unmapped names (should not happen in production)
        latin = re.sub(r'[^a-zA-Z0-9\s_-]', '', name).strip()
        latin = re.sub(r'[\s_]+', '-', latin).strip('-').lower()
        return latin if len(latin) >= 3 else f'author-{idx + 1}'

    author_tmpl       = JINJA_ENV.get_template('review_author.html.j2')
    author_index_rows: list[dict] = []

    (SITE / 'author').mkdir(parents=True, exist_ok=True)

    for idx, (author_name, author_reviews) in enumerate(
            sorted(by_author.items(), key=lambda x: x[0].lower())):
        a_slug   = author_slug(author_name, idx)
        # Group by artist alphabetically, sort by year ascending within each artist
        from collections import defaultdict as _dd
        artist_map = _dd(list)
        for r in author_reviews:
            artist_map[r['artist_name'] or '—'].append(r)
        artist_groups = []
        for aname in sorted(artist_map.keys(), key=lambda s: s.lower()):
            items = sorted(artist_map[aname], key=lambda r: (str(r.get('year') or ''), r['album_title']))
            artist_groups.append({'artist_name': aname, 'albums': items})
        dst_auth = SITE / 'author' / a_slug / 'index.html'
        dst_auth.parent.mkdir(parents=True, exist_ok=True)
        dst_auth.write_text(author_tmpl.render(
            author=author_name,
            author_slug=a_slug,
            artist_groups=artist_groups,
            total=len(author_reviews),
            footer=FOOTER), encoding='utf-8')
        author_index_rows.append({
            'name':  author_name,
            'slug':  a_slug,
            'url':   f'/author/{a_slug}/',
            'count': len(author_reviews),
        })

    ai_tmpl = JINJA_ENV.get_template('review_author_index.html.j2')
    (SITE / 'author' / 'index.html').write_text(
        ai_tmpl.render(authors=author_index_rows, footer=FOOTER), encoding='utf-8')

    # ── Various Musicians stub page ──────────────────────────────────────────
    various_reviews: list[dict] = []
    for meta, body in reviews:
        album_id  = str(meta.get('album_id', ''))
        album     = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or meta.get('artist_id', '') or '')
        artist    = artists.get(artist_id, {})
        if artist_slug_for_url(artist) == 'various-musicians':
            album_slug = album.get('slug', '') or meta.get('slug', '')
            various_reviews.append({
                'url':         f'/artist/various-musicians/{_strip_artist_prefix("various-musicians", album_slug)}/',
                'album_title': album.get('title') or meta.get('album') or '',
                'year':        album.get('year', ''),
                'asin':        album.get('asin', ''),
                'cover_url':   cover_url_for_asin(album.get('asin', ''), fallback=True),
            })

    if various_reviews:
        v_tmpl = JINJA_ENV.get_template('various_artists.html.j2')
        dst_v  = SITE / 'artist' / 'various-musicians' / 'index.html'
        dst_v.parent.mkdir(parents=True, exist_ok=True)
        dst_v.write_text(v_tmpl.render(reviews=various_reviews, footer=FOOTER), encoding='utf-8')

    print(f"  Reviews: {generated} pages, {len(month_keys)} month indexes, {len(by_author)} author pages")


if __name__ == '__main__':
    generate_reviews()
