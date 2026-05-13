#!/usr/bin/env python3
"""
Shared constants, helpers, and data loaders for all bluesru-arc generators.

Imported by generate_forum.py, generate_reviews.py, generate_news.py, etc.
Do not run directly.

Architecture note (refactored):
  This module remains the single import point for generator scripts
  (``from generate_shared import *`` keeps working).  The actual
  implementations live in focused sub-modules:
    models.py         — Pydantic data models
    data.py           — typed data loading (DataStore singleton)
    html_utils.py     — SSI, link rewriting, analytics stripping
    render_utils.py   — star ratings, review/news body formatting, cover URLs
    streaming.py      — streaming platform URLs and HTML
    forum_render.py   — forum post/topic HTML rendering
    calendar_render.py — calendar HTML rendering
    gallery_utils.py  — gallery path/URL computation
    artist_utils.py   — artist page building helpers
"""

import os
import re
import sys
import json
import shutil
import html as html_mod
import yaml
from pathlib import Path
from datetime import datetime

import jinja2

# ── New typed sub-modules ─────────────────────────────────────────────────────
from models import (
    Album, AlbumReview, AlbumStreamingIds,
    Artist, ArtistResource, ArtistStreamingIds,
    ArtistLink,
    ATBEpisode, CalendarEvent,
    ForumPost, ForumTopicMeta, ForumTopic,
    GalleryMeta,
    LinkCategory, LinkSite,
    NewsItem,
)

from render_utils import (
    cover_url_for_asin,
    star_rating_html,
    format_mark_ats,
    format_review_body,
    format_news_body,
    format_news_body_simple,
)

from gallery_utils import (
    gallery_year       as _gallery_year,
    gallery_canonical_url as _gallery_canonical_url,
    write_gallery_redirects as _write_gallery_redirects_impl,
)

from forum_render import (
    sanitize_forum_html,
    autolink_bare_urls    as _autolink_bare_urls,
    format_forum_date,
    render_post_html      as _render_post_html_impl,
    render_topic_html     as _render_topic_html_impl,
    topic_is_all_deleted  as _topic_is_all_deleted_impl,
)

from calendar_render import (
    years_ago_ru      as _years_ago_ru,
    years_ago_abbr    as _years_ago_abbr,
    fix_all_caps_name,
    process_calendar_text,
    calendar_events_html  as _calendar_events_html_impl,
)

# Private module alias kept in namespace for scripts that import it directly
_MONTHS_RU = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
               'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

from artist_utils import (
    strip_artist_prefix     as _strip_artist_prefix,
    scan_artist_subpages    as _scan_artist_subpages,
    find_main_htm           as _find_main_htm,
    collect_artist_links    as _collect_artist_links_impl,
    format_artist_links     as _format_artist_links_impl,
    build_album_list_html   as _build_album_list_html_impl,
    process_artist_dir      as _process_artist_dir_impl,
    atb_links_html          as _atb_links_html,
    normalize_filename      as _normalize_filename_artist,
)

import streaming as _streaming_mod

from html_utils import (
    read_file,
    strip_analytics,
    resolve_include         as _resolve_include_impl,
    extract_asp_variables   as _extract_asp_variables,
    RE_INCLUDE_VIRTUAL,
    RE_INCLUDE_FILE,
    RE_DYNAMIC_ASPX,
    RE_UNRESOLVED,
    SKIP_EXTENSIONS,
    load_redirect_rules     as _load_redirect_rules_impl,
    load_link_fixes         as _load_link_fixes_impl,
    make_link_rewriter,
    rewrite_gallery_img_src as _rewrite_gallery_img_src,
    normalize_filename      as _normalize_filename_html,
)


# ── Paths ──────────────────────────────────────────────────────────────────────
ARC        = Path(__file__).resolve().parent.parent
_site_default = str(ARC / 'bluesru-site') if os.environ.get('CF_PAGES') else str(ARC.parent / 'bluesru-site')
SITE       = Path(os.environ.get('BLUESRU_SITE', _site_default))
TEMPLATES  = ARC / 'templates'
INCLUDES   = ARC / 'includes'
COVERS     = ARC / 'covers'
CONTENT    = ARC / 'content'
BLUESNEWS  = CONTENT / 'bluesnews'
ATB        = CONTENT / 'atb'
BEEFHEART  = CONTENT / 'beefheart'
ETHNOTRIP  = CONTENT / 'ethnotrip'
ZAPPAZUHOI = CONTENT / 'zappazuhoi'
CAL_IMGS   = ARC / 'calendar' / 'images'

MEDIA_BASE_URL = ''

DATA              = ARC / 'data'
ARTISTS_YAML      = DATA / 'artists.yaml'
ALBUMS_DIR        = DATA / 'albums'
REVIEWS_DIR       = DATA / 'albums'
EVENTS_DIR        = DATA / 'calendar.yaml'
ANNOUNCE_DIR      = DATA / 'updates'
NEWS_DIR          = DATA / 'news'
TOPICS_DIR        = DATA / 'forum' / 'topics'
RESOURCES_YAML    = DATA / 'artists.yaml'
STREAMING_ARTISTS = DATA / 'artists.yaml'
STREAMING_ALBUMS  = DATA / 'albums'
GALLERIES_YAML    = DATA / 'galleries' / 'index.yaml'
GALLERIES_DIR     = DATA / 'galleries'
CALENDAR_YAML     = DATA / 'calendar.yaml'
ATB_EPISODES_YAML      = DATA / 'atb' / 'episodes.yaml'
ATB_TRANSCRIPTS_DIR    = DATA / 'atb' / 'transcripts'


# ── Data store (singleton from data.py) ───────────────────────────────────────
from data import store as _store


# ── Forum state (lazy-loaded, kept here for backward compat) ──────────────────

def _load_spam_ids() -> set:
    spam_yaml = DATA / 'forum' / 'spam-ids.yaml'
    if not spam_yaml.exists():
        return set()
    d = yaml.safe_load(spam_yaml.read_text(encoding='utf-8')) or {}
    return set(d.get('post_ids', []))

SPAM_IDS = _load_spam_ids()

_AUTHOR_SLUGS: dict | None = None

def _get_author_slugs() -> dict:
    global _AUTHOR_SLUGS
    if _AUTHOR_SLUGS is None:
        p = DATA / 'forum' / 'author-slugs.json'
        _AUTHOR_SLUGS = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    return _AUTHOR_SLUGS


# ── Jinja2 environment ─────────────────────────────────────────────────────────
JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES)),
    autoescape=False,
    undefined=jinja2.Undefined,
)

# ── Footer, GA, CSS ────────────────────────────────────────────────────────────
FOOTER = (INCLUDES / 'footer.inc').read_text(encoding='utf-8').strip()
DONATE = (INCLUDES / 'donate.inc').read_text(encoding='utf-8').strip()
JINJA_ENV.globals['footer'] = FOOTER
JINJA_ENV.globals['donate'] = DONATE

GA_SNIPPET = '''\
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8HDC1W9R3E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-8HDC1W9R3E');
</script>'''

SITE_CSS_TAG = (
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<link rel="stylesheet" href="/css/site.css">\n'
    '<link rel="stylesheet" href="/css/photo.css">\n'
    '<link rel="stylesheet" href="/css/responsive.css">'
)

JINJA_ENV.globals['ga_snippet'] = GA_SNIPPET
JINJA_ENV.globals['site_css_tag'] = SITE_CSS_TAG
JINJA_ENV.globals['star_rating_html'] = star_rating_html

MONTHS_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
             'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']


# ── Redirect & dead-link rules (module-level, loaded once) ────────────────────

def _load_redirect_rules() -> list:
    return _load_redirect_rules_impl(ARC / '_redirects')

def _load_link_fixes() -> dict:
    return _load_link_fixes_impl(ARC / 'data' / 'link_fixes.yaml')

_REDIRECT_RULES = _load_redirect_rules()
_LINK_FIXES     = _load_link_fixes()

# Build the link-rewriter function once from module-level state
_rewrite_links = make_link_rewriter(_REDIRECT_RULES, _LINK_FIXES)


# ── SSI resolution wrapper (uses module-level FOOTER/DONATE) ──────────────────

def resolve_include(
    vpath: str,
    source_dir: Path,
    source_root: Path,
    variables: dict | None = None,
) -> str:
    return _resolve_include_impl(vpath, source_dir, source_root,
                                  footer=FOOTER, donate=DONATE, variables=variables)


# ── Gallery state ─────────────────────────────────────────────────────────────

_gallery_yaml_map: dict | None = None

def _gallery_yaml(slug: str) -> Path | None:
    global _gallery_yaml_map
    if _gallery_yaml_map is None:
        _gallery_yaml_map = {}
        for p in GALLERIES_DIR.glob('*.yaml'):
            if p.stem != 'index':
                _gallery_yaml_map[p.stem] = p
        for p in GALLERIES_DIR.glob('*/*.yaml'):
            _gallery_yaml_map[p.stem] = p
    return _gallery_yaml_map.get(slug)


def load_all_gallery_yamls() -> list:
    seen: set = set()
    galleries: list = []

    def _add(d: dict) -> None:
        if isinstance(d, dict) and d.get('slug'):
            key = (d['slug'], str(d.get('canonical_date') or ''))
            if key not in seen:
                seen.add(key)
                galleries.append(d)

    for p in sorted(GALLERIES_DIR.glob('*.yaml')):
        if p.stem != 'index':
            _add(yaml.safe_load(p.read_text(encoding='utf-8')) or {})
    for p in sorted(GALLERIES_DIR.glob('*/*.yaml')):
        _add(yaml.safe_load(p.read_text(encoding='utf-8')) or {})

    galleries.sort(key=lambda g: (str(g.get('canonical_date') or '0000'), g.get('slug', '')))
    return galleries


# ── Streaming (delegates to streaming module + data store) ────────────────────

ALBUM_URL_TEMPLATES      = _streaming_mod.ALBUM_URL_TEMPLATES
ARTIST_URL_TEMPLATES     = _streaming_mod.ARTIST_URL_TEMPLATES
STREAMING_PLATFORM_LABELS = _streaming_mod.PLATFORM_LABELS

_STREAMING_ARTISTS: dict | None = None
_STREAMING_ALBUMS: dict | None  = None


def get_streaming_artists() -> dict:
    global _STREAMING_ARTISTS
    if _STREAMING_ARTISTS is None:
        result = {}
        for a in _store.artists():
            ids = _store.artist_streaming().get(a.slug)
            if ids:
                d = {}
                for k in ('spotify_id', 'apple_music_id', 'deezer_id'):
                    v = getattr(ids, k, None)
                    if v:
                        d[k] = v
                result[a.slug] = d
        _STREAMING_ARTISTS = result
    return _STREAMING_ARTISTS


def get_streaming_albums() -> dict:
    global _STREAMING_ALBUMS
    if _STREAMING_ALBUMS is None:
        result = {}
        for album in _store.albums_by_id().values():
            ids = _store.album_streaming().get(album.slug)
            if ids and album.slug:
                d = {}
                for k in ('spotify_id', 'apple_music_id', 'deezer_id',
                           'ytmusic_id', 'youtube_video_id', 'youtube_playlist_id'):
                    v = getattr(ids, k, None)
                    if v:
                        d[k] = v
                result[album.slug] = d
        _STREAMING_ALBUMS = result
    return _STREAMING_ALBUMS


def streaming_links_html(slug: str, kind: str = 'artist') -> str:
    return _streaming_mod.streaming_links_html(slug, kind, _store)


def stream_icons_html(slug: str, kind: str = 'artist') -> str:
    return _streaming_mod.stream_icons_html(slug, kind, _store)


# ── Data loaders (thin wrappers over data.store) ──────────────────────────────

def load_artists() -> list:
    """Return raw artist list as plain dicts (backward compat)."""
    with open(ARTISTS_YAML) as f:
        return yaml.safe_load(f)


def load_albums() -> dict:
    """Return {album_id_str: album_dict} (backward compat)."""
    albums: dict = {}
    for p in ALBUMS_DIR.glob('*/*.yaml'):
        a = yaml.safe_load(p.read_text(encoding='utf-8'))
        if a and a.get('id'):
            albums[str(a['id'])] = a
    return albums


RE_FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)', re.DOTALL)


def load_reviews() -> tuple:
    reviews: list = []
    review_by_album: dict = {}
    for p in sorted(ALBUMS_DIR.glob('*/*.yaml')):
        album = yaml.safe_load(p.read_text(encoding='utf-8'))
        if not album:
            continue
        album_id = str(album.get('id', ''))
        for rv in album.get('reviews', []):
            meta = {
                'id': rv.get('id'),
                'album_id': album.get('id'),
                'album': album.get('title', ''),
                'artist': album.get('artist', ''),
                'artist_id': album.get('artist_id'),
                'author': rv.get('author', ''),
                'mark': rv.get('mark'),
                'date': rv.get('date'),
                'slug': f"review-{rv.get('id', '')}",
            }
            body = rv.get('text', '')
            reviews.append((meta, body))
            if album_id and album_id not in review_by_album:
                review_by_album[album_id] = meta['slug']
    return reviews, review_by_album


def load_resources() -> dict:
    if not ARTISTS_YAML.exists():
        return {}
    data = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8'))
    if not data:
        return {}
    result: dict = {}
    for artist in data:
        aid = str(artist.get('id', ''))
        res = artist.get('resources', [])
        if aid and res:
            type_map = {'page': 1, 'article': 2, 'discography': 3, 'photos': 4,
                        'tabs': 5, 'lyrics': 6, 'video': 7, 'audio': 8, 'links': 9, 'interview': 10}
            type_short_map = {'page': 'Страница', 'article': 'Статья', 'discography': 'Диски',
                              'photos': 'Фото', 'tabs': 'Ноты', 'lyrics': 'Тексты',
                              'video': 'Видео', 'audio': 'Аудио', 'interview': 'Интервью',
                              'link': 'Страница', 'links': 'Ссылки', 'press': 'Пресса'}
            result[aid] = [
                {'type_id': type_map.get(r.get('type', 'link'), 0),
                 'type_short': type_short_map.get(r.get('type', 'link'), r.get('type', '')),
                 'url': r.get('url', '')}
                for r in res
            ]
    return result


# ── Forum helpers ─────────────────────────────────────────────────────────────

def _load_topics_index() -> list:
    return _store.topics_index()


def _find_topic_yaml(topic_id: int) -> Path | None:
    return _store.find_topic_yaml(topic_id)


# ── Forum rendering (wrappers that inject module-level state) ─────────────────

def render_post_html(
    post: dict,
    topic_slug: str,
    full: bool = True,
    depth: int = 0,
) -> str:
    return _render_post_html_impl(
        post, topic_slug, full=full, depth=depth,
        spam_ids=SPAM_IDS, author_slugs=_get_author_slugs())


def render_topic_html(
    topic_data: dict | None,
    topic_meta: dict,
    full: bool = False,
    forum_page: int = 1,
) -> str:
    return _render_topic_html_impl(
        topic_data, topic_meta, full=full, forum_page=forum_page,
        spam_ids=SPAM_IDS, author_slugs=_get_author_slugs())


def _topic_is_all_deleted(topic_data: dict | None) -> bool:
    return _topic_is_all_deleted_impl(topic_data, spam_ids=SPAM_IDS)


def _forum_visible_topics() -> tuple:
    topics_index = _load_topics_index()
    topics_sorted = sorted(
        topics_index,
        key=lambda t: int(t.get('topic_id', 0)),
        reverse=True,
    )
    topics_visible = []
    for tm in topics_sorted:
        tf = tm.get('_path') or _find_topic_yaml(tm['topic_id'])
        if not tf or not tf.exists():
            continue
        td = yaml.safe_load(tf.read_text())
        if not _topic_is_all_deleted(td):
            topics_visible.append(tm)
    PAGE_SIZE = 50
    topic_to_page = {
        tm['topic_id']: (i // PAGE_SIZE) + 1
        for i, tm in enumerate(topics_visible)
    }
    return topics_visible, topic_to_page


# ── Calendar (wrappers) ───────────────────────────────────────────────────────

def calendar_events_html(events: list, current_year: int = 2026) -> str:
    typed = [CalendarEvent.model_validate(e) if isinstance(e, dict) else e for e in events]
    return _calendar_events_html_impl(typed, current_year=current_year)


def build_calendar_by_slug() -> dict:
    """Return {artist_slug: [event_dict, ...]} from calendar.yaml."""
    if not CALENDAR_YAML.exists():
        return {}
    events = yaml.safe_load(CALENDAR_YAML.read_text(encoding='utf-8')) or []
    index: dict = {}
    for ev in events:
        slug = ev.get('artist_slug', '') or ''
        if not slug:
            continue
        index.setdefault(slug, []).append({
            'date': str(ev.get('date', '') or ''),
            'year': ev.get('year', ''),
            'month_day': ev.get('month_day', ''),
            'event_type': ev.get('event_type', ''),
            'title': ev.get('title', ''),
            'text': ev.get('text', ''),
            'picture': ev.get('picture', '') or '',
            'artist_slug': slug,
        })
    for slug in index:
        index[slug].sort(key=lambda e: e.get('date', ''))
    return index


# ── ATB helpers ────────────────────────────────────────────────────────────────

def _build_atb_by_slug() -> dict:
    return _store.atb_by_artist_slug()


# ── Gallery helpers ────────────────────────────────────────────────────────────

def _build_galleries_by_slug() -> dict:
    return _store.galleries_by_artist_slug()


def _write_gallery_redirects(redirects: list) -> None:
    _write_gallery_redirects_impl(ARC, redirects)


def _gallery_dir_prefixes() -> set:
    galleries = load_all_gallery_yamls()
    prefixes: set = set()
    for g in galleries:
        gtype = g.get('type', '')
        if gtype == 'custom':
            continue
        gpath = g.get('path', '')
        if not gpath:
            slug = g.get('slug', '')
            per = _gallery_yaml(slug)
            if per and per.exists():
                gpath = (yaml.safe_load(per.read_text(encoding='utf-8')) or {}).get('path', '')
        if not gpath:
            continue
        prefixes.add(f'bluesnews/{gpath}/')
        if gpath.endswith('/content'):
            prefixes.add(f'bluesnews/{gpath[:-8]}/')
    return prefixes


def _build_custom_gallery_media_map() -> dict:
    galleries = load_all_gallery_yamls()
    result: dict = {}
    for g in galleries:
        if g.get('type') != 'custom':
            continue
        yaml_slug = g.get('slug', '')
        if not yaml_slug:
            gpath_raw = g.get('path', '')
            yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath_raw.lower()).strip('-')
        per_yaml = _gallery_yaml(yaml_slug)
        if not per_yaml or not per_yaml.exists():
            continue
        data = yaml.safe_load(per_yaml.read_text(encoding='utf-8')) or {}
        gpath = data.get('path', '') or g.get('path', '')
        if not gpath:
            continue
        canonical_rel, _ = _gallery_canonical_url(data, gpath)
        prefix = f'bluesnews/{gpath}/'
        result[prefix] = f'{MEDIA_BASE_URL}/{canonical_rel}'
    return result


# ── Artist helpers (wrappers) ─────────────────────────────────────────────────

def collect_artist_links(
    slug: str,
    artist_id: str,
    src_dir: Path | None,
    galleries_by_slug: dict,
    resources_by_artist: dict,
    calendar_by_slug: dict,
    has_album_list: bool = False,
    has_atb: bool = False,
) -> list:
    artist_ids = _store.artist_streaming().get(slug)
    return _collect_artist_links_impl(
        slug, artist_id, src_dir,
        galleries_by_slug, resources_by_artist, calendar_by_slug,
        has_album_list=has_album_list,
        has_atb=has_atb,
        artist_streaming_ids=artist_ids,
    )


def format_artist_links(links: list, types: set | None = None) -> str:
    return _format_artist_links_impl(links, types=types)


def _build_album_list_html(artist_slug: str, artist_id: str, albums_by_artist: dict) -> str:
    return _build_album_list_html_impl(artist_slug, artist_id, albums_by_artist)


def _normalize_filename(name: str) -> str:
    return _normalize_filename_html(name)


# ── HTML pipeline ──────────────────────────────────────────────────────────────

def _build_resource_links(resources: list, artist_slug: str) -> str:
    """Build ' | '-separated resource link HTML from legacy resource dicts."""
    if not resources:
        return ''
    seen_urls: set = set()
    items: list = []
    for r in resources:
        url        = r.get('url', '') or ''
        type_short = r.get('type_short', '')
        name       = r.get('name', '')
        if not url or not type_short:
            continue
        if r.get('type_id') == 1:
            continue
        if '.aspx' in url.lower():
            continue
        url = re.sub(r'^https?://(?:www\.)?blues\.ru', '', url, flags=re.IGNORECASE)
        if url.startswith('/bluesmen/') and artist_slug:
            rest = re.sub(r'^/bluesmen/[^/]+', '', url)
            url = f'/artist/{artist_slug}{rest}'
        elif url.startswith('/artist/') and artist_slug:
            rest = re.sub(r'^/artist/[^/]+', '', url)
            url = f'/artist/{artist_slug}{rest}'
        if re.match(r'^/ATB/.*\.mp3$', url, re.IGNORECASE):
            continue
        if re.match(r'^/atb/?$', url, re.IGNORECASE):
            continue
        if artist_slug and url.rstrip('/') == f'/artist/{artist_slug}':
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        label = name or type_short
        items.append(f'<a href="{url}">{html_mod.escape(label)}</a>')
    if not items:
        return ''
    return ' | '.join(items)


def process_html(
    content: str,
    source_dir: Path,
    source_root: Path,
    artist_slug: str | None = None,
    artist_name: str | None = None,
    artist_legacy_dir: str | None = None,
    artist_resources: list | None = None,
    artist_albums_html: str | None = None,
    artist_atb_html: str | None = None,
    artist_resource_links_html: str | None = None,
    artist_calendar_html: str | None = None,
    artist_photo_html: str | None = None,
) -> str:
    """Main HTML processing pipeline: clean, resolve SSI, inject artist blocks, rewrite links."""
    asp_vars = _extract_asp_variables(content)
    content = strip_analytics(content)
    content = re.sub(r'charset\s*=\s*["\']?windows-1251["\']?', 'charset=utf-8',
                     content, flags=re.IGNORECASE)
    content = re.sub(r'href="http://www\.blues\.ru/default\.htm"', 'href="/"',
                     content, flags=re.IGNORECASE)
    content = re.sub(r'href="default\.html?"', 'href="./"',
                     content, flags=re.IGNORECASE)

    if artist_slug:
        nav_block = '<hr size="1">\n'
        if artist_resource_links_html is not None:
            res_links = artist_resource_links_html
        else:
            res_links = _build_resource_links(artist_resources, artist_legacy_dir)
            stream_html = streaming_links_html(artist_slug, kind='artist')
            if stream_html:
                res_links = (res_links + ' | ' if res_links else '') + stream_html
        if res_links:
            nav_block += f'<p style="font-size:1.1em">{res_links}</p>\n'
        icons_html = stream_icons_html(artist_slug, kind='artist')
        if icons_html:
            nav_block += icons_html
        if artist_photo_html:
            nav_block += f'\n{artist_photo_html}\n'
        if artist_atb_html:
            nav_block += f'<p>{artist_atb_html}</p>\n'
        if artist_calendar_html:
            nav_block += f'<p>{artist_calendar_html}</p>\n'
        album_block = f'\n{nav_block}'
        if artist_albums_html:
            album_block += artist_albums_html
        replaced = RE_DYNAMIC_ASPX.sub(album_block, content)
        if replaced == content:
            footer_pat = r'(<!--\s*#include\s+virtual\s*=\s*"/footer\.inc"\s*-->)'
            replaced2 = re.sub(footer_pat, album_block + '\n\\1', content, count=1,
                                flags=re.IGNORECASE)
            if replaced2 != content:
                content = replaced2
            else:
                content = re.sub(r'(</body>)', album_block + '\n\\1', content, count=1,
                                  flags=re.IGNORECASE)
        else:
            content = replaced
    else:
        content = RE_DYNAMIC_ASPX.sub('', content)

    if artist_slug and not re.search(
            r'<!--\s*#include\s+virtual\s*=\s*"/footer\.inc"\s*-->', content, re.IGNORECASE):
        footer_include = '<!--#include virtual="/footer.inc"-->'
        content = re.sub(r'(</body>)', footer_include + '\n\\1', content, count=1,
                          flags=re.IGNORECASE)

    content = RE_INCLUDE_VIRTUAL.sub(
        lambda m: resolve_include(m.group(1), source_dir, source_root, variables=asp_vars or None),
        content)
    content = RE_INCLUDE_FILE.sub(
        lambda m: resolve_include(m.group(1), source_dir, source_root, variables=asp_vars or None),
        content)
    content = RE_UNRESOLVED.sub('', content)
    content = _rewrite_links(content)

    if '</head>' in content.lower():
        inject = SITE_CSS_TAG + '\n' + GA_SNIPPET + '\n'
        content = re.sub(r'(</head>)', inject + '\\1', content, count=1, flags=re.IGNORECASE)
    return content


# ── Artist directory processing (wrapper) ────────────────────────────────────

def _process_artist_dir(
    artist: dict,
    src_dir: Path,
    src_root: Path,
    artist_resources: list | None = None,
    artist_albums_html: str | None = None,
    artist_atb_html: str | None = None,
    artist_resource_links_html: str | None = None,
    artist_calendar_html: str | None = None,
    artist_photo_html: str | None = None,
) -> None:
    _process_artist_dir_impl(
        artist, src_dir, src_root, SITE, SKIP_EXTENSIONS, process_html,
        artist_resources=artist_resources,
        artist_albums_html=artist_albums_html,
        artist_atb_html=artist_atb_html,
        artist_resource_links_html=artist_resource_links_html,
        artist_calendar_html=artist_calendar_html,
        artist_photo_html=artist_photo_html,
    )


# ── Stub artist page generation ───────────────────────────────────────────────

def _generate_stub_artist_page(
    artist: dict,
    reviews_list: list,
    albums: dict,
    artist_atb_html: str | None = None,
    artist_resource_links_html: str | None = None,
    artist_calendar_html: str | None = None,
    artist_albums_html: str | None = None,
    artist_photo_html: str | None = None,
) -> Path:
    slug = artist.get('slug', '')
    name = artist.get('name', '')
    amg_id = artist.get('amg_id', '')

    reviews_data = []
    for meta, body in sorted(reviews_list, key=lambda x: -int(x[0].get('id', 0))):
        album_id = str(meta.get('album_id', ''))
        album    = albums.get(album_id, {})
        mark     = meta.get('mark')
        reviews_data.append({
            'id':          meta.get('id', ''),
            'album_title': album.get('title', '') or meta.get('album', ''),
            'year':        album.get('year', ''),
            'author':      meta.get('author', ''),
            'body':        format_review_body(body),
            'mark':        mark,
            'mark_text':   format_mark_ats(mark) if mark else '',
        })

    tmpl = JINJA_ENV.get_template('albumview.html.j2')
    artist_streaming = ('' if artist_resource_links_html
                        else streaming_links_html(slug, kind='artist'))
    out = tmpl.render(
        album={'title': '', 'artist': name, 'year': '', 'label': '', 'asin': '', 'amg_id': amg_id},
        cover_url='',
        artist_name=name,
        artist_legacy_path=slug,
        reviews=[],
        streaming_links='',
        artist_streaming_links=artist_streaming,
        stream_icons=stream_icons_html(slug, kind='artist'),
        artist_atb_links=artist_atb_html or '',
        artist_resource_links=artist_resource_links_html or '',
        artist_calendar_links=artist_calendar_html or '',
        artist_album_list=artist_albums_html or '',
        artist_photo_html=artist_photo_html or '',
        footer=FOOTER,
    )
    dst = SITE / 'artist' / slug / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding='utf-8')
    return dst


# ── Artist review loader ───────────────────────────────────────────────────────

def _load_artist_reviews() -> dict:
    reviews, _ = load_reviews()
    albums = load_albums()
    by_artist: dict = {}
    for meta, body in reviews:
        album_id  = str(meta.get('album_id', ''))
        album     = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or '')
        if artist_id:
            by_artist.setdefault(artist_id, []).append((meta, body))
    return by_artist


# ── Content section copy ───────────────────────────────────────────────────────

_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'}


def _copy_section(
    src_dir: Path,
    dst_dir: Path,
    source_root: Path,
    skip_exts: set | None = None,
    skip_paths: set | None = None,
    media_gallery_map: dict | None = None,
) -> int:
    skip_exts        = (skip_exts or set()) | SKIP_EXTENSIONS
    skip_paths       = skip_paths or set()
    media_gallery_map = media_gallery_map or {}
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    home_files: set = set()
    for cfg in src_dir.rglob('config.xml'):
        try:
            import xml.etree.ElementTree as ET
            root_el = ET.parse(cfg).getroot()
            home = root_el.get('home') or (root_el.find('.//*[@home]') or ET.Element('')).get('home', '')
            if home:
                home_files.add(cfg.parent / home)
        except Exception:
            pass

    for src_path in sorted(src_dir.rglob('*')):
        if not src_path.is_file():
            continue
        if '.git' in src_path.parts:
            continue
        ext = src_path.suffix.lower()
        if ext in skip_exts:
            continue
        if skip_paths and ext in ('.htm', '.html'):
            rel_site = str(dst_dir.relative_to(SITE) / src_path.relative_to(src_dir))
            rel_site = rel_site.replace('\\', '/')
            if any(rel_site.startswith(p) for p in skip_paths):
                continue
        rel   = src_path.relative_to(src_dir)
        parts = rel.parts
        out_name = _normalize_filename(src_path.name)
        dst_path = dst_dir / (Path(*parts[:-1]) / out_name if len(parts) > 1 else Path(out_name))

        rel_site_path = str(dst_dir.relative_to(SITE) / rel).replace('\\', '/')
        media_base = None
        for prefix, mbase in media_gallery_map.items():
            if rel_site_path.startswith(prefix):
                media_base = mbase
                break

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if ext in ('.htm', '.html', '.inc'):
            content = read_file(src_path)
            if content:
                content = process_html(content, src_path.parent, source_root)
                if media_base:
                    content = _rewrite_gallery_img_src(content, media_base)
                dst_path.write_text(content, encoding='utf-8')
                if src_path in home_files and dst_path.name.lower() != 'index.html':
                    (dst_path.parent / 'index.html').write_text(content, encoding='utf-8')
                count += 1
                continue
        shutil.copy2(src_path, dst_path)
        count += 1
    return count


def _copy_dir(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)


# ── ATB helpers ────────────────────────────────────────────────────────────────

def _atb_episode_slug(ep: dict) -> str:
    if ep.get('slug'):
        return ep['slug']
    stem = ep['filename'].replace('.mp3', '').replace('.MP3', '')
    return re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')


def _parse_transcript_md(md_text: str) -> list:
    if not md_text:
        return []
    ANCHOR_RE = re.compile(r'<a id="([tm])(\d+)"></a>')
    MUSIC_RE  = re.compile(r'\*\*\[MUSIC:\s*(\d+):(\d+)\s*[–\-]\s*(\d+):(\d+)\]\*\*')
    parts = ANCHOR_RE.split(md_text)
    blocks: list = []
    i = 1
    while i + 2 < len(parts):
        kind, raw_secs, content = parts[i], parts[i + 1], parts[i + 2].strip()
        try:
            secs = int(raw_secs)
        except ValueError:
            i += 3
            continue
        if kind == 't':
            content = re.sub(r'\*\*\[\d+:\d+(?::\d+)?\]\*\*\s*', '', content).strip()
            paras = [p.strip() for p in content.split('\n\n') if p.strip()]
            if paras:
                html_t = ''.join(f'<p>{p}</p>' for p in paras)
                blocks.append({'type': 'speech', 'seconds': secs, 'text': html_t})
        elif kind == 'm':
            m = MUSIC_RE.search(content)
            if m:
                end_s = int(m.group(3)) * 60 + int(m.group(4))
                blocks.append({'type': 'music', 'seconds': secs, 'end_seconds': end_s})
        i += 3
    return blocks


def _fmt_tc(s: int) -> str:
    m, sec = divmod(int(s), 60)
    h, m   = divmod(m, 60)
    return f'{h}:{m:02d}:{sec:02d}' if h else f'{m}:{sec:02d}'


def _transcript_to_html(blocks: list, part_index: int) -> str:
    if not blocks:
        return ''
    out: list = []
    for b in blocks:
        t      = b['seconds']
        tc     = _fmt_tc(t)
        anchor = f'p{part_index}t{t}'
        if b['type'] == 'speech':
            out.append(
                f'<div class="atb-speech" id="{anchor}">'
                f'<button class="atb-tc" onclick="atbSeek({part_index},{t})">{tc}</button>'
                f'<div class="atb-speech-text">{b["text"]}</div>'
                f'</div>')
        else:
            dur = b['end_seconds'] - t
            out.append(
                f'<div class="atb-music" id="{anchor}" onclick="atbSeek({part_index},{t})" '
                f'role="button" tabindex="0">'
                f'<span class="atb-m-note">&#9835;</span>'
                f'<span class="atb-m-start">{tc}</span>'
                f'<span class="atb-m-dur">&thinsp;&middot;&thinsp;{_fmt_tc(dur)}</span>'
                f'</div>')
    return '\n'.join(out)


# ── Links page helpers ─────────────────────────────────────────────────────────

def _get_blues_cat_ids(categories: dict, root_id: str = '1') -> set:
    result = {root_id}
    changed = True
    while changed:
        changed = False
        for c in categories.values():
            if c['id'] not in result and c.get('parent_id') in result:
                result.add(c['id'])
                changed = True
    return result


def _build_links_snippet(categories: dict, sites: list) -> str:
    blues_ids    = _get_blues_cat_ids(categories)
    live_statuses = {'live', 'redirected'}
    blues_sites  = [
        s for s in sites
        if any(cid in blues_ids for cid in s.get('categories', []))
        and s.get('status', '') in live_statuses
    ]
    top_cats = [c for c in categories.values() if c.get('parent_id') == '1']
    by_cat: dict = {}
    for site in blues_sites:
        for cid in site.get('categories', []):
            if cid in blues_ids:
                by_cat.setdefault(cid, []).append(site)

    html = '<b><a href="/links/">Блюзовые ссылки</a></b>\n<ul>\n'
    for cat in sorted(top_cats, key=lambda c: c.get('name', '')):
        cat_sites = by_cat.get(cat['id'], [])
        if not cat_sites:
            continue
        html += f'<li><b>{cat["name"]}</b><ul>\n'
        for site in cat_sites[:5]:
            html += f'  <li><a href="{site["url"]}">{html_mod.escape(site["name"])}</a></li>\n'
        if len(cat_sites) > 5:
            html += f'  <li><a href="/links/"><small>ещё {len(cat_sites)-5}...</small></a></li>\n'
        html += '</ul></li>\n'
    html += f'</ul>\n<p><a href="/links/">Все ссылки &gt;&gt;</a></p>\n'
    return html


def _generate_links_page(categories: dict, sites: list) -> None:
    blues_ids    = _get_blues_cat_ids(categories)
    live_statuses = {'live', 'redirected', 'unknown'}
    blues_sites  = [
        s for s in sites
        if any(cid in blues_ids for cid in s.get('categories', []))
        and s.get('status', 'unknown') in live_statuses
    ]
    by_cat: dict = {}
    for site in blues_sites:
        for cid in site.get('categories', []):
            if cid in blues_ids:
                by_cat.setdefault(cid, []).append(site)

    top_cats   = [c for c in categories.values() if c.get('parent_id') == '1']
    child_cats: dict = {}
    for c in categories.values():
        if c.get('parent_id'):
            child_cats.setdefault(c['parent_id'], []).append(c)

    def render_cat(cat: dict, depth: int = 0) -> str:
        cid        = cat['id']
        cat_sites  = by_cat.get(cid, [])
        child_list = sorted(child_cats.get(cid, []), key=lambda c: c.get('name', ''))
        if not cat_sites and not child_list:
            return ''
        hn = f'h{"23456"[min(depth, 4)]}'
        s  = f'<{hn}>{cat["name"]}</{hn}>\n'
        if cat_sites:
            s += '<ul>\n'
            for site in sorted(cat_sites, key=lambda x: x.get('name', '')):
                desc = f' — {html_mod.escape(site["description"])}' if site.get('description') else ''
                s += f'  <li><a href="{site["url"]}">{html_mod.escape(site["name"])}</a>{desc}</li>\n'
            s += '</ul>\n'
        for child in child_list:
            s += render_cat(child, depth + 1)
        return s

    html = ('<!DOCTYPE html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>Блюзовые ссылки — Blues.Ru</title>\n'
            '<link rel="shortcut icon" href="/images/bluesru.ico">\n'
            '<link rel="stylesheet" href="/css/site.css">\n'
            '<link rel="stylesheet" href="/css/responsive.css">\n'
            + GA_SNIPPET + '\n'
            '<style>a{text-decoration:none} body{max-width:900px;margin:0 auto;padding:0 1em}</style>\n'
            '</head>\n<body bgcolor="#FFFFFF" text="#000000" link="#0000FF" vlink="#5511CC">\n'
            '<a href="/"><img src="/images/bluesru.svg" width="120" height="120" border="0" '
            'alt="Blues.Ru" style="float:right"></a>\n'
            '<p><a href="/"><b>Blues.Ru</b></a> &gt; Ссылки</p>\n'
            '<h1>Блюзовые ссылки</h1>\n'
            '<p>Ссылки на сайты о блюзе. Собраны в 2001–2009 годах; показаны работавшие на момент проверки.</p>\n')
    for cat in sorted(top_cats, key=lambda c: c.get('name', '')):
        html += render_cat(cat)
    dead_count = sum(
        1 for s in sites
        if any(cid in blues_ids for cid in s.get('categories', []))
        and s.get('status') in ('dead', 'changed')
    )
    html += f'<hr size="1">\n<p align="center">{FOOTER}</p>\n</body>\n</html>'
    out = SITE / 'links'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(html, encoding='utf-8')
    print(f'  links/index.html: {len(blues_sites)} live blues sites ({dead_count} dead filtered)')


# ── Postprocess & deploy ───────────────────────────────────────────────────────

def postprocess_dead_links() -> None:
    if not _LINK_FIXES and not _REDIRECT_RULES:
        return
    fixed = 0
    for html_file in SITE.rglob('*.html'):
        try:
            content = html_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        if 'href="/' not in content:
            continue
        new_content = _rewrite_links(content)
        if new_content != content:
            html_file.write_text(new_content, encoding='utf-8')
            fixed += 1
    print(f'  postprocess_dead_links: rewrote {fixed} files')


def copy_root_files() -> None:
    for fname in ['_redirects', '_headers', 'robots.txt']:
        src = ARC / fname
        if src.exists():
            shutil.copy2(src, SITE / fname)
    tmpl = JINJA_ENV.get_template('404.html.j2')
    (SITE / '404.html').write_text(tmpl.render(), encoding='utf-8')
    print('  Root files: _redirects, _headers, 404.html')


# ── Compatibility aliases ──────────────────────────────────────────────────────
# Keep old private names that external scripts may reference directly.
link_artist_in_text = process_calendar_text

# Export all names so 'from generate_shared import *' keeps working
__all__ = [k for k in globals() if not k.startswith('__')]
