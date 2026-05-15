"""
Typed data loading layer for Blues.Ru generators.

All YAML/JSON loading goes through this module.  Every loader returns typed
Pydantic models (see models.py) and is cached after the first call.

Usage:
    from data import store
    artists = store.artists()           # list[Artist]
    albums  = store.albums_by_id()      # dict[str, Album]
    album   = store.album_by_slug('albert-collins-cold-snap')
"""

from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Optional

from models import (
    Album, AlbumReview, AlbumStreamingIds,
    Artist, ArtistResource, ArtistStreamingIds,
    ATBEpisode, CalendarEvent,
    ForumTopicMeta, ForumPost, ForumTopic,
    GalleryMeta,
    LinkCategory, LinkSite,
    NewsItem,
)

# ── Path resolution ────────────────────────────────────────────────────────────
# data.py is in scripts/; ARC is one level up.
_ARC = Path(__file__).resolve().parent.parent
_DATA = _ARC / 'data'

ARTISTS_YAML      = _DATA / 'artists.yaml'
ALBUMS_DIR        = _DATA / 'albums'
CALENDAR_YAML     = _DATA / 'calendar.yaml'
ATB_EPISODES_YAML = _DATA / 'atb' / 'episodes.yaml'
TOPICS_DIR        = _DATA / 'forum' / 'topics'
LINKS_YAML        = _DATA / 'links.yaml'
GALLERIES_DIR     = _DATA / 'galleries'
GALLERIES_YAML    = _DATA / 'galleries' / 'index.yaml'
NEWS_DIR          = _DATA / 'news'


# ── Internal YAML helpers ──────────────────────────────────────────────────────

def _read_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def _str(v: object) -> str:
    return str(v) if v is not None else ''


# ── DataStore (singleton) ──────────────────────────────────────────────────────

class DataStore:
    """
    Lazy-loading, cached data store.  All heavy YAML parsing is deferred to
    first access; subsequent calls return the cached result instantly.

    Use the module-level ``store`` singleton rather than constructing your own.
    """

    def __init__(self) -> None:
        self._artists: Optional[list[Artist]] = None
        self._albums_by_id: Optional[dict[str, Album]] = None
        self._albums_by_slug: Optional[dict[str, Album]] = None
        self._calendar_by_slug: Optional[dict[str, list[CalendarEvent]]] = None
        self._atb_by_slug: Optional[dict[str, list[dict]]] = None
        self._atb_episodes: Optional[list[ATBEpisode]] = None
        self._spam_ids: Optional[set[int]] = None
        self._author_slugs: Optional[dict[str, str]] = None
        self._topics_index: Optional[list[dict]] = None
        self._galleries: Optional[list[GalleryMeta]] = None
        self._gallery_map: Optional[dict[str, Path]] = None
        self._links: Optional[tuple[dict[str, LinkCategory], list[LinkSite]]] = None
        self._artist_streaming: Optional[dict[str, ArtistStreamingIds]] = None
        self._album_streaming: Optional[dict[str, AlbumStreamingIds]] = None
        self._reviews_by_album_id: Optional[dict[str, list[tuple[dict, str]]]] = None
        self._resources_by_artist_id: Optional[dict[str, list[dict]]] = None

    # ── Artists ────────────────────────────────────────────────────────────────

    def artists(self) -> list[Artist]:
        if self._artists is None:
            raw = _read_yaml(ARTISTS_YAML) or []
            self._artists = [Artist.model_validate(a) for a in raw]
        return self._artists

    def artists_by_id(self) -> dict[str, Artist]:
        return {str(a.id): a for a in self.artists()}

    def artists_by_slug(self) -> dict[str, Artist]:
        return {a.slug: a for a in self.artists() if a.slug}

    # ── Albums ─────────────────────────────────────────────────────────────────

    def _load_albums(self) -> None:
        if self._albums_by_id is not None:
            return
        by_id: dict[str, Album] = {}
        by_slug: dict[str, Album] = {}
        for p in ALBUMS_DIR.glob('*/*.yaml'):
            raw = yaml.safe_load(p.read_text(encoding='utf-8'))
            if not raw or not raw.get('id'):
                continue
            album = Album.model_validate(raw)
            by_id[str(album.id)] = album
            if album.slug:
                by_slug[album.slug] = album
        self._albums_by_id = by_id
        self._albums_by_slug = by_slug

    def albums_by_id(self) -> dict[str, Album]:
        self._load_albums()
        return self._albums_by_id  # type: ignore[return-value]

    def albums_by_slug(self) -> dict[str, Album]:
        self._load_albums()
        return self._albums_by_slug  # type: ignore[return-value]

    def album_by_slug(self, slug: str) -> Optional[Album]:
        return self.albums_by_slug().get(slug)

    def albums_by_artist_id(self) -> dict[str, list[Album]]:
        result: dict[str, list[Album]] = {}
        for album in self.albums_by_id().values():
            if album.artist_id:
                result.setdefault(str(album.artist_id), []).append(album)
        return result

    # ── Reviews ────────────────────────────────────────────────────────────────

    def reviews(self) -> list[tuple[dict, str]]:
        """Return list of (meta_dict, body_text) pairs, all albums."""
        reviews: list[tuple[dict, str]] = []
        for p in sorted(ALBUMS_DIR.glob('*/*.yaml')):
            raw = yaml.safe_load(p.read_text(encoding='utf-8'))
            if not raw:
                continue
            for rv in raw.get('reviews', []):
                meta = {
                    'id': rv.get('id'),
                    'album_id': raw.get('id'),
                    'album': raw.get('title', ''),
                    'artist': raw.get('artist', ''),
                    'artist_id': raw.get('artist_id'),
                    'author': rv.get('author', ''),
                    'mark': rv.get('mark'),
                    'date': rv.get('date'),
                    'slug': f"review-{rv.get('id', '')}",
                }
                body = rv.get('text', '')
                reviews.append((meta, body))
        return reviews

    def review_by_album_id(self) -> dict[str, str]:
        """Return {album_id_str: first_review_slug} mapping."""
        result: dict[str, str] = {}
        for meta, _ in self.reviews():
            album_id = str(meta.get('album_id', ''))
            if album_id and album_id not in result:
                result[album_id] = meta['slug']
        return result

    def reviews_by_artist_id(self) -> dict[str, list[tuple[dict, str]]]:
        if self._reviews_by_album_id is None:
            albums = self.albums_by_id()
            by_artist: dict[str, list[tuple[dict, str]]] = {}
            for meta, body in self.reviews():
                album_id = str(meta.get('album_id', ''))
                album = albums.get(album_id)
                if album and album.artist_id:
                    by_artist.setdefault(str(album.artist_id), []).append((meta, body))
            self._reviews_by_album_id = by_artist  # type: ignore[assignment]
        return self._reviews_by_album_id  # type: ignore[return-value]

    # ── Resources (from artists.yaml) ─────────────────────────────────────────

    def resources_by_artist_id(self) -> dict[str, list[dict]]:
        """Return {artist_id_str: [compat_resource_dict, ...]}."""
        if self._resources_by_artist_id is not None:
            return self._resources_by_artist_id
        result: dict[str, list[dict]] = {}
        _TYPE_ID = {'page': 1, 'article': 2, 'discography': 3, 'photos': 4,
                    'tabs': 5, 'lyrics': 6, 'video': 7, 'audio': 8, 'links': 9, 'interview': 10}
        _TYPE_SHORT = {'page': 'Страница', 'article': 'Статья', 'discography': 'Диски',
                       'photos': 'Фото', 'tabs': 'Ноты', 'lyrics': 'Тексты',
                       'video': 'Видео', 'audio': 'Аудио', 'interview': 'Интервью',
                       'link': 'Страница', 'links': 'Ссылки', 'press': 'Пресса'}
        for artist in self.artists():
            aid = str(artist.id)
            if not artist.resources:
                continue
            compat = []
            for r in artist.resources:
                rtype = r.type or 'link'
                compat.append({
                    'type_id': _TYPE_ID.get(rtype, 0),
                    'type_short': _TYPE_SHORT.get(rtype, rtype),
                    'url': r.url,
                    'name': r.name or '',
                })
            result[aid] = compat
        self._resources_by_artist_id = result
        return result

    # ── Streaming ──────────────────────────────────────────────────────────────

    def artist_streaming(self) -> dict[str, ArtistStreamingIds]:
        if self._artist_streaming is None:
            result: dict[str, ArtistStreamingIds] = {}
            for a in self.artists():
                ids = ArtistStreamingIds(
                    spotify_id=a.spotify_id,
                    apple_music_id=a.apple_music_id,
                    deezer_id=a.deezer_id,
                    discogs_id=a.discogs_id,
                )
                if not ids.is_empty():
                    result[a.slug] = ids
            self._artist_streaming = result
        return self._artist_streaming

    def album_streaming(self) -> dict[str, AlbumStreamingIds]:
        if self._album_streaming is None:
            result: dict[str, AlbumStreamingIds] = {}
            for album in self.albums_by_id().values():
                ids = AlbumStreamingIds(
                    spotify_id=album.spotify_id,
                    apple_music_id=album.apple_music_id,
                    deezer_id=album.deezer_id,
                    ytmusic_id=album.ytmusic_id,
                    youtube_video_id=album.youtube_video_id,
                    youtube_playlist_id=album.youtube_playlist_id,
                    discogs_master_id=album.discogs_master_id,
                )
                if not ids.is_empty() and album.slug:
                    result[album.slug] = ids
            self._album_streaming = result
        return self._album_streaming

    # ── Calendar ───────────────────────────────────────────────────────────────

    def calendar_by_slug(self) -> dict[str, list[CalendarEvent]]:
        if self._calendar_by_slug is None:
            index: dict[str, list[CalendarEvent]] = {}
            if CALENDAR_YAML.exists():
                for raw in (_read_yaml(CALENDAR_YAML) or []):
                    ev = CalendarEvent.model_validate(raw)
                    if ev.artist_slug:
                        index.setdefault(ev.artist_slug, []).append(ev)
            for slug in index:
                index[slug].sort(key=lambda e: e.date)
            self._calendar_by_slug = index
        return self._calendar_by_slug

    # ── ATB ────────────────────────────────────────────────────────────────────

    def atb_episodes(self) -> list[ATBEpisode]:
        if self._atb_episodes is None:
            if ATB_EPISODES_YAML.exists():
                self._atb_episodes = [
                    ATBEpisode.model_validate(e)
                    for e in (_read_yaml(ATB_EPISODES_YAML) or [])
                ]
            else:
                self._atb_episodes = []
        return self._atb_episodes

    def atb_by_artist_slug(self) -> dict[str, list[dict]]:
        """Return {artist_slug: [episode_info_dict, ...]} for artist pages."""
        if self._atb_by_slug is None:
            index: dict[str, list[dict]] = {}
            for ep in self.atb_episodes():
                for tag in ep.artists_tags:
                    slug = tag.get('slug', '') if isinstance(tag, dict) else tag
                    if not slug:
                        continue
                    index.setdefault(slug, []).append({
                        'summary': ep.summary or ep.topic or ep.slug,
                        'page_url': f'/atb/{ep.slug}/',
                        'date': ep.date or '',
                    })
            self._atb_by_slug = index
        return self._atb_by_slug

    # ── Forum ──────────────────────────────────────────────────────────────────

    def spam_ids(self) -> set[int]:
        if self._spam_ids is None:
            spam_yaml = _DATA / 'forum' / 'spam-ids.yaml'
            if spam_yaml.exists():
                d = _read_yaml(spam_yaml) or {}
                self._spam_ids = set(d.get('post_ids', []))
            else:
                self._spam_ids = set()
        return self._spam_ids

    def author_slugs(self) -> dict[str, str]:
        if self._author_slugs is None:
            p = _DATA / 'forum' / 'author-slugs.json'
            if p.exists():
                self._author_slugs = json.loads(p.read_text(encoding='utf-8'))
            else:
                self._author_slugs = {}
        return self._author_slugs

    def topics_index(self) -> list[dict]:
        """Return raw topic index list (lightweight dicts for forum index generation)."""
        if self._topics_index is None:
            index_yaml = _DATA / 'forum' / 'topics-index.yaml'
            if index_yaml.exists():
                self._topics_index = _read_yaml(index_yaml) or []
            else:
                topics: list[dict] = []
                for p in TOPICS_DIR.glob('*/*.yaml'):
                    d = _read_yaml(p) or {}
                    if d.get('topic_id'):
                        topics.append({
                            'topic_id': d['topic_id'],
                            'slug': d.get('slug', f"topic-{d['topic_id']}"),
                            'title': d.get('title', ''),
                            'first_post': _str(d.get('first_post')),
                            'last_post': _str(d.get('last_post')),
                            'post_count': d.get('post_count', 0),
                            '_path': p,
                        })
                self._topics_index = topics
        return self._topics_index

    def find_topic_yaml(self, topic_id: int) -> Optional[Path]:
        for p in TOPICS_DIR.glob(f'*/*-topic-{topic_id}.yaml'):
            return p
        flat = TOPICS_DIR / f'topic-{topic_id}.yaml'
        return flat if flat.exists() else None

    # ── Galleries ──────────────────────────────────────────────────────────────

    def galleries(self) -> list[GalleryMeta]:
        if self._galleries is None:
            seen: set[tuple[str, str]] = set()
            result: list[GalleryMeta] = []

            def _add(raw: dict) -> None:
                if not isinstance(raw, dict) or not raw.get('slug'):
                    return
                key = (raw['slug'], str(raw.get('canonical_date') or ''))
                if key in seen:
                    return
                seen.add(key)
                result.append(GalleryMeta.model_validate(raw))

            for p in sorted(GALLERIES_DIR.glob('*.yaml')):
                if p.stem != 'index':
                    _add(_read_yaml(p) or {})
            for p in sorted(GALLERIES_DIR.glob('*/*.yaml')):
                _add(_read_yaml(p) or {})

            result.sort(key=lambda g: (str(g.canonical_date or '0000'), g.slug))
            self._galleries = result
        return self._galleries

    def gallery_yaml_path(self, slug: str) -> Optional[Path]:
        if self._gallery_map is None:
            self._gallery_map = {}
            for p in GALLERIES_DIR.glob('*.yaml'):
                if p.stem != 'index':
                    self._gallery_map[p.stem] = p
            for p in GALLERIES_DIR.glob('*/*.yaml'):
                self._gallery_map[p.stem] = p
        return self._gallery_map.get(slug)

    def galleries_by_artist_slug(self) -> dict[str, list[dict]]:
        """Return {artist_slug: [gallery_entry_dict, ...]} for artist pages."""
        index: dict[str, list[dict]] = {}
        if not GALLERIES_YAML.exists():
            return index
        raw_list = _read_yaml(GALLERIES_YAML) or []
        for raw in raw_list:
            tags = raw.get('artists_tags') or []
            if not tags:
                continue
            from gallery_utils import gallery_canonical_url
            slug = raw.get('slug', '')
            gpath = raw.get('path', slug)
            canonical_rel, year = gallery_canonical_url(raw, gpath)
            if not year:
                continue
            url = f'/{canonical_rel}/'

            photo_count = raw.get('photo_count', 0) or 0
            thumb_url   = ''
            per_path    = self.gallery_yaml_path(slug)
            if per_path and per_path.exists():
                per = _read_yaml(per_path) or {}
                photos = [p for p in (per.get('photos') or [])
                          if isinstance(p, dict) and p.get('file')]
                if photos:
                    first = photos[0]['file']
                    stem, _, ext = first.rpartition('.')
                    if ext.lower() in ('jpg', 'jpeg', 'png', 'webp'):
                        first = f'{stem}-400w.jpg'
                    thumb_url = f'/{canonical_rel}/{first}'
                photo_count = per.get('photo_count', photo_count) or len(photos)

            entry = {
                'slug':        slug,
                'title':       raw.get('title', ''),
                'url':         url,
                'date':        str(raw.get('canonical_date', '') or ''),
                'thumb':       thumb_url,
                'photo_count': photo_count,
            }
            for artist_slug in tags:
                index.setdefault(artist_slug, []).append(entry)
        return index

    # ── Links ──────────────────────────────────────────────────────────────────

    def links(self) -> tuple[dict[str, LinkCategory], list[LinkSite]]:
        if self._links is None:
            if not LINKS_YAML.exists():
                self._links = ({}, [])
            else:
                raw = _read_yaml(LINKS_YAML) or {}
                cats = {
                    str(c.get('id', '')): LinkCategory.model_validate(
                        {**c, 'id': str(c.get('id', '')),
                         'parent_id': str(c['parent_id']) if c.get('parent_id') else None}
                    )
                    for c in raw.get('categories', [])
                }
                sites = [
                    LinkSite.model_validate(
                        {**s, 'id': str(s.get('id', '')),
                         'categories': [str(cid) for cid in s.get('categories', [])]}
                    )
                    for s in raw.get('sites', [])
                ]
                self._links = (cats, sites)
        return self._links


# ── Module-level singleton ─────────────────────────────────────────────────────
store = DataStore()
