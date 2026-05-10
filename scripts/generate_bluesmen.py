#!/usr/bin/env python3
"""Generate artist list and artist bio pages."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import (
    CONTENT,
    FOOTER,
    JINJA_ENV,
    SITE,
    _build_atb_by_slug,
    _build_galleries_by_slug,
    _generate_stub_artist_page,
    _load_artist_reviews,
    _process_artist_dir,
    build_calendar_by_slug,
    collect_artist_links,
    format_artist_links,
    load_albums,
    load_artists,
    load_resources,
)
from artist_utils import build_album_list_html
from calendar_render import calendar_events_html
from models import CalendarEvent


def generate_bluesmen() -> None:
    print("Generating bluesmen pages...")
    artists            = load_artists()
    tmpl               = JINJA_ENV.get_template('bluesmen_list.html.j2')
    resources_by_artist = load_resources()
    atb_by_slug        = _build_atb_by_slug()
    galleries_by_slug  = _build_galleries_by_slug()
    calendar_by_slug   = build_calendar_by_slug()

    SRC_BLUESMEN = CONTENT / 'artist'
    print(f"  Source: {SRC_BLUESMEN}")

    artist_reviews   = _load_artist_reviews()
    albums           = load_albums()
    reviews_by_album = {}  # built below while iterating albums
    albums_by_artist_id: dict[str, list] = {}
    for album in albums.values():
        artist_id_key = str(album.get('artist_id', '') or '')
        if not artist_id_key:
            continue
        entry = {
            'id':          str(album.get('id', '')),
            'title':       album.get('title', ''),
            'year':        str(album.get('year', '')),
            'label':       album.get('label', ''),
            'artist':      album.get('artist', ''),
            'asin':        album.get('asin', ''),
            'slug':        album.get('slug', ''),
            'review_slug': reviews_by_album.get(str(album.get('id', '')), ''),
            'reviews':     [{'author': rv.get('author', ''), 'mark': rv.get('mark')}
                            for rv in album.get('reviews', [])],
        }
        albums_by_artist_id.setdefault(artist_id_key, []).append(entry)

    by_letter: dict[str, list] = defaultdict(list)
    letters_all = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    letter_has  = {l: False for l in letters_all}

    bio_count  = 0
    stub_count = 0

    for a in artists:
        name      = a.get('name', '')
        sort_name = a.get('sort_name', name) or name
        letter    = name[0].upper() if name else '#'
        if letter not in letter_has:
            letter = '#'

        lp        = (a.get('legacy_path') or '').strip('/')
        parts     = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        external  = '.' in legacy_dir or legacy_dir.startswith('www.')
        if external:
            legacy_dir = ''

        src_dir  = SRC_BLUESMEN / legacy_dir if legacy_dir else None
        has_dir  = src_dir and src_dir.exists()
        if not has_dir and legacy_dir:
            name_dir = name.replace(' ', '_') if name else ''
            name_src = SRC_BLUESMEN / name_dir if name_dir else None
            if name_src and name_src.exists():
                src_dir   = name_src
                has_dir   = True
                legacy_dir = name_dir
        slug = a.get('slug', '')
        if not has_dir and slug:
            slug_src = SRC_BLUESMEN / slug
            if slug_src.exists():
                src_dir   = slug_src
                has_dir   = True
                legacy_dir = slug

        artist_id    = str(a.get('id', ''))
        has_reviews  = bool(artist_reviews.get(artist_id))
        has_galleries = bool(galleries_by_slug.get(slug))

        if has_dir and slug:
            link_dir = slug
        elif has_dir:
            link_dir = legacy_dir
        elif (has_reviews or has_galleries) and slug:
            link_dir = slug
        else:
            link_dir = ''

        effective_src  = src_dir if has_dir else None
        has_album_list = bool(albums_by_artist_id.get(artist_id))
        artist_links   = collect_artist_links(
            slug, artist_id, effective_src,
            galleries_by_slug, resources_by_artist, calendar_by_slug,
            has_album_list=has_album_list,
        )
        resource_links = format_artist_links(artist_links)

        row: dict = {
            'id':          artist_id,
            'name':        name,
            'sort_name':   sort_name,
            'letter':      letter,
            'legacy_dir':  link_dir,
            'external':    external,
            'amg_id':      a.get('amg_id', ''),
            'slug':        slug,
            'secondary':   False,
            'links':       artist_links,
            'resource_links': resource_links,
        }
        by_letter[letter].append(row)
        if link_dir:
            letter_has[letter] = True

        if sort_name != name and slug:
            sort_letter = sort_name[0].upper()
            if sort_letter not in letter_has:
                sort_letter = '#'
            if sort_letter != letter:
                sec_row = {
                    'id':          artist_id,
                    'name':        name,
                    'sort_name':   sort_name,
                    'letter':      sort_letter,
                    'legacy_dir':  link_dir,
                    'external':    external,
                    'amg_id':      '',
                    'slug':        slug,
                    'secondary':   True,
                    'resource_links': '',
                }
                by_letter[sort_letter].append(sec_row)
                if link_dir:
                    letter_has[sort_letter] = True

        if has_dir:
            albums_html = (build_album_list_html(slug, artist_id, albums_by_artist_id)
                           if slug else '')
            from artist_utils import atb_links_html
            atb_html  = atb_links_html(atb_by_slug.get(slug, []))
            cal_events = [CalendarEvent.model_validate(e)
                          for e in calendar_by_slug.get(slug, [])]
            cal_html  = calendar_events_html(cal_events)
            _process_artist_dir(a, src_dir, SRC_BLUESMEN,
                                artist_resources=resources_by_artist.get(artist_id),
                                artist_albums_html=albums_html,
                                artist_atb_html=atb_html or None,
                                artist_resource_links_html=resource_links,
                                artist_calendar_html=cal_html or None)
            bio_count += 1

        elif (has_reviews or has_galleries) and slug:
            from artist_utils import atb_links_html
            atb_html   = atb_links_html(atb_by_slug.get(slug, []))
            cal_events = [CalendarEvent.model_validate(e)
                          for e in calendar_by_slug.get(slug, [])]
            cal_html   = calendar_events_html(cal_events)
            reviews_list = artist_reviews.get(artist_id, [])
            albums_html  = (build_album_list_html(slug, artist_id, albums_by_artist_id)
                            if slug else '')
            _generate_stub_artist_page(a, reviews_list, albums,
                                       artist_atb_html=atb_html or None,
                                       artist_resource_links_html=resource_links or None,
                                       artist_calendar_html=cal_html or None,
                                       artist_albums_html=albums_html or None)
            stub_count += 1

    # Fallback: process orphaned bio dirs
    processed_dirs: set[str] = set()
    for a in artists:
        lp        = (a.get('legacy_path') or '').strip('/')
        parts     = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        if legacy_dir and '.' not in legacy_dir and not legacy_dir.startswith('www.'):
            processed_dirs.add(legacy_dir)
        slug_dir = a.get('slug', '')
        if slug_dir:
            processed_dirs.add(slug_dir)
        name = a.get('name', '')
        if name and legacy_dir and '.' not in legacy_dir:
            name_dir = name.replace(' ', '_')
            if (SRC_BLUESMEN / name_dir).exists():
                processed_dirs.add(name_dir)

    orphan_count = 0
    for src_dir in sorted(SRC_BLUESMEN.iterdir()):
        if not src_dir.is_dir() or src_dir.name in processed_dirs:
            continue
        dir_name      = src_dir.name
        inferred_name = dir_name.replace('-', ' ').replace('_', ' ').title()
        letter        = inferred_name[0].upper() if inferred_name else '#'
        if letter not in letter_has:
            letter = '#'
        orphan_artist = {
            'id': '', 'slug': '', 'name': inferred_name, 'sort_name': inferred_name,
            'legacy_path': f'/artist/{dir_name}/', 'amg_id': '',
        }
        _process_artist_dir(orphan_artist, src_dir, SRC_BLUESMEN)
        bio_count   += 1
        orphan_count += 1
        row = {
            'id': '', 'name': inferred_name, 'sort_name': inferred_name,
            'letter': letter, 'legacy_dir': dir_name, 'external': False,
            'amg_id': '', 'slug': '', 'secondary': False, 'resource_links': '',
        }
        by_letter[letter].append(row)
        if dir_name:
            letter_has[letter] = True

    if orphan_count:
        print(f"  Orphan bio dirs processed: {orphan_count}")

    various_page = SITE / 'artist' / 'various-musicians' / 'index.html'
    if various_page.exists():
        by_letter['V'].append({
            'id': '', 'name': 'Various Musicians', 'sort_name': 'Various Musicians',
            'letter': 'V', 'legacy_dir': 'various-musicians', 'external': False,
            'amg_id': '', 'slug': 'various-musicians', 'secondary': False, 'resource_links': '',
        })
        letter_has['V'] = True

    letters_used = [l for l in letters_all if l in by_letter]
    for l in by_letter:
        by_letter[l].sort(key=lambda x: (
            x['secondary'],
            x['sort_name'].lower() if x['secondary'] else x['name'].lower()
        ))

    out = tmpl.render(
        letters=letters_used,
        letter_has_artists=letter_has,
        artists_by_letter=by_letter,
    )
    dst = SITE / 'artist' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding='utf-8')
    print(f"  Bluesmen list: {len(artists)} artists, {bio_count} bio pages + {stub_count} stub pages")


if __name__ == '__main__':
    generate_bluesmen()
