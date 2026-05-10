#!/usr/bin/env python3
"""Generate artist list and artist bio pages."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from generate_shared import *
from collections import defaultdict


def _build_artist_resource_links(slug, artist_id, src_dir, galleries_by_slug, resources_by_artist):
    """
    Build the resource links string for an artist by combining:
      1. Auto-detected static sub-pages (tabs, lyrics, interview, article, photos…)
      2. Photo galleries tagged with this artist
      3. Manual resources from artists.yaml (non-overlapping unique links)
    Returns HTML string with ' | ' separators.
    """
    auto = _scan_artist_subpages(src_dir, slug) if (src_dir and slug) else []
    auto_types = {r['type'] for r in auto}

    # Gallery Фото links
    gallery_entries = galleries_by_slug.get(slug, [])
    gallery_links = []
    for g in sorted(gallery_entries, key=lambda g: g.get('date', '')):
        title = g.get('title', '') or 'Фото'
        url = g['url']
        gallery_links.append({'type': 'photos', 'url': url, 'label': html_mod.escape(title)})

    # Manual resources from artists.yaml — keep only unique non-overlapping ones
    manual = resources_by_artist.get(str(artist_id), [])
    manual_links = []
    seen_urls = {r['url'] for r in auto} | {g['url'] for g in gallery_links}
    for r in manual:
        rtype = r.get('type_short', '') or ''
        url = r.get('url', '') or ''
        if not url or r.get('type_id') == 1:
            continue
        if '.aspx' in url.lower():
            continue
        # Fix /bluesmen/ → /artist/ prefix
        url = re.sub(r'^https?://(?:www\.)?blues\.ru', '', url, flags=re.IGNORECASE)
        if url.startswith('/bluesmen/') and slug:
            rest = re.sub(r'^/bluesmen/[^/]+', '', url)
            url = f'/artist/{slug}{rest}'
        elif url.startswith('/artist/') and slug:
            rest = re.sub(r'^/artist/[^/]+', '', url)
            url = f'/artist/{slug}{rest}'
        # Skip ATB mp3 links
        if re.match(r'^/[Aa][Tt][Bb]/.*\.mp3$', url):
            continue
        # Skip self-link
        if url.rstrip('/') == f'/artist/{slug}':
            continue
        # Skip anchor-only fragments and anchors on missing files
        if '#' in url:
            path_part = url.split('#')[0]
            if path_part.rstrip('/') == f'/artist/{slug}':
                continue  # anchor on the main page — usually #photo on old bios
        # Skip if type already covered by auto-detection
        type_map = {'Тексты': 'lyrics', 'Ноты': 'tabs', 'Интервью': 'interview',
                    'Статья': 'article', 'Фото': 'photos', 'Пресса': 'press'}
        if type_map.get(rtype, '') in auto_types and type_map.get(rtype):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        manual_links.append({'type': rtype, 'url': url, 'label': rtype})

    all_links = auto + gallery_links + manual_links
    if not all_links:
        return ''

    items = [f'<a href="{r["url"]}">{r["label"]}</a>' for r in all_links]
    return ' | '.join(items)


def generate_bluesmen():
    print("Generating bluesmen pages...")
    artists = load_artists()
    tmpl = JINJA_ENV.get_template('bluesmen_list.html.j2')
    resources_by_artist = load_resources()
    atb_by_slug = _build_atb_by_slug()
    galleries_by_slug = _build_galleries_by_slug()
    calendar_by_slug = build_calendar_by_slug()

    SRC_BLUESMEN = CONTENT / 'artist'
    print(f"  Source: {SRC_BLUESMEN}")

    artist_reviews = _load_artist_reviews()
    albums = load_albums()

    reviews, review_by_album = load_reviews()
    albums_by_artist_id = {}
    for album in albums.values():
        artist_id_key = str(album.get('artist_id', '') or '')
        if not artist_id_key:
            continue
        entry = {
            'id': str(album.get('id', '')),
            'title': album.get('title', ''),
            'year': str(album.get('year', '')),
            'label': album.get('label', ''),
            'artist': album.get('artist', ''),
            'asin': album.get('asin', ''),
            'slug': album.get('slug', ''),
            'review_slug': review_by_album.get(str(album.get('id', '')), ''),
        }
        albums_by_artist_id.setdefault(artist_id_key, []).append(entry)

    by_letter = defaultdict(list)
    letters_all = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    letter_has = {l: False for l in letters_all}

    bio_count = 0
    stub_count = 0

    for a in artists:
        name = a.get('name', '')
        sort_name = a.get('sort_name', name) or name
        letter = name[0].upper() if name else '#'
        if letter not in letter_has:
            letter = '#'

        lp = (a.get('legacy_path') or '').strip('/')
        parts = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        external = '.' in legacy_dir or legacy_dir.startswith('www.')
        if external:
            legacy_dir = ''

        src_dir = SRC_BLUESMEN / legacy_dir if legacy_dir else None
        has_dir = src_dir and src_dir.exists()
        if not has_dir and legacy_dir:
            name_dir = name.replace(' ', '_') if name else ''
            name_src = SRC_BLUESMEN / name_dir if name_dir else None
            if name_src and name_src.exists():
                src_dir = name_src
                has_dir = True
                legacy_dir = name_dir
        slug = a.get('slug', '')
        if not has_dir and slug:
            slug_src = SRC_BLUESMEN / slug
            if slug_src.exists():
                src_dir = slug_src
                has_dir = True
                legacy_dir = slug

        artist_id = str(a.get('id', ''))
        has_reviews = bool(artist_reviews.get(artist_id))
        has_galleries = bool(galleries_by_slug.get(slug))

        if has_dir and slug:
            link_dir = slug
        elif has_dir:
            link_dir = legacy_dir
        elif (has_reviews or has_galleries) and slug:
            link_dir = slug
        else:
            link_dir = ''

        # Build rich resource links (auto-detected + galleries + manual)
        effective_src = src_dir if has_dir else None
        resource_links = _build_artist_resource_links(
            slug, artist_id, effective_src, galleries_by_slug, resources_by_artist
        )
        stream_html = streaming_links_html(slug, kind='artist')
        if stream_html:
            resource_links = (resource_links + ' | ' if resource_links else '') + stream_html

        row = {
            'id': artist_id,
            'name': name,
            'sort_name': sort_name,
            'letter': letter,
            'legacy_dir': link_dir,
            'external': external,
            'amg_id': a.get('amg_id', ''),
            'slug': slug,
            'secondary': False,
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
                    'id': artist_id,
                    'name': name,
                    'sort_name': sort_name,
                    'letter': sort_letter,
                    'legacy_dir': link_dir,
                    'external': external,
                    'amg_id': '',
                    'slug': slug,
                    'secondary': True,
                    'resource_links': '',
                }
                by_letter[sort_letter].append(sec_row)
                if link_dir:
                    letter_has[sort_letter] = True

        if has_dir:
            albums_html = _build_album_list_html(slug, artist_id, albums_by_artist_id) if slug else ''
            atb_html = _atb_links_html(atb_by_slug.get(slug, []))
            cal_html = calendar_events_html(calendar_by_slug.get(slug, []))
            _process_artist_dir(a, src_dir, SRC_BLUESMEN,
                                artist_resources=resources_by_artist.get(artist_id),
                                artist_albums_html=albums_html,
                                artist_atb_html=atb_html or None,
                                artist_resource_links_html=resource_links,
                                artist_calendar_html=cal_html or None)
            bio_count += 1
        elif (has_reviews or has_galleries) and slug:
            atb_html = _atb_links_html(atb_by_slug.get(slug, []))
            cal_html = calendar_events_html(calendar_by_slug.get(slug, []))
            reviews_list = artist_reviews.get(artist_id, [])
            _generate_stub_artist_page(a, reviews_list, albums,
                                       artist_atb_html=atb_html or None,
                                       artist_resource_links_html=resource_links or None,
                                       artist_calendar_html=cal_html or None)
            stub_count += 1

    # Fallback: process orphaned bio dirs
    processed_dirs = set()
    for a in artists:
        lp = (a.get('legacy_path') or '').strip('/')
        parts = lp.split('/')
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
        if not src_dir.is_dir():
            continue
        if src_dir.name in processed_dirs:
            continue
        dir_name = src_dir.name
        inferred_name = dir_name.replace('-', ' ').replace('_', ' ').title()
        letter = inferred_name[0].upper() if inferred_name else '#'
        if letter not in letter_has:
            letter = '#'
        orphan_artist = {
            'id': '',
            'slug': '',
            'name': inferred_name,
            'sort_name': inferred_name,
            'legacy_path': f'/artist/{dir_name}/',
            'amg_id': '',
        }
        _process_artist_dir(orphan_artist, src_dir, SRC_BLUESMEN)
        bio_count += 1
        orphan_count += 1
        row = {
            'id': '',
            'name': inferred_name,
            'sort_name': inferred_name,
            'letter': letter,
            'legacy_dir': dir_name,
            'external': False,
            'amg_id': '',
            'slug': '',
            'secondary': False,
            'resource_links': '',
        }
        by_letter[letter].append(row)
        if dir_name:
            letter_has[letter] = True

    if orphan_count:
        print(f"  Orphan bio dirs processed: {orphan_count}")

    various_page = SITE / 'artist' / 'various-musicians' / 'index.html'
    if various_page.exists():
        by_letter['V'].append({
            'id': '',
            'name': 'Various Musicians',
            'sort_name': 'Various Musicians',
            'letter': 'V',
            'legacy_dir': 'various-musicians',
            'external': False,
            'amg_id': '',
            'slug': 'various-musicians',
            'secondary': False,
            'resource_links': '',
        })
        letter_has['V'] = True

    letters_used = [l for l in letters_all if l in by_letter]
    for l in by_letter:
        by_letter[l].sort(key=lambda x: (x['secondary'], x['sort_name'].lower() if x['secondary'] else x['name'].lower()))

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
