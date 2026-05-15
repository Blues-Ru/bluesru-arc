"""
Typed Pydantic models for all Blues.Ru data types.

These models are the source of truth for what fields each data entity has.
They validate YAML-loaded data and provide type safety throughout generators.

Usage:
    artist = Artist.model_validate(raw_dict)
    album  = Album.model_validate(raw_dict)
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, model_validator


# ── Leaf models ────────────────────────────────────────────────────────────────

class ArtistResource(BaseModel):
    """A single resource link associated with an artist (from artists.yaml)."""
    type: str = 'link'
    url: str = ''
    name: Optional[str] = None


class AlbumReview(BaseModel):
    """A single critic review embedded in an album YAML."""
    id: Optional[int] = None
    author: str = ''
    mark: Optional[int] = None           # 0–20 integer; displayed as 0–10 stars
    date: Optional[str] = None
    text: str = ''


# ── Artist ─────────────────────────────────────────────────────────────────────

class Artist(BaseModel):
    """One row from data/artists.yaml."""
    id: int
    slug: str
    name: str
    sort_name: Optional[str] = None
    legacy_path: Optional[str] = None    # original /bluesmen/Dir_Name/ path
    amg_id: Optional[str] = None
    spotify_id: Optional[str] = None
    apple_music_id: Optional[str] = None
    deezer_id: Optional[str] = None
    ytmusic_id: Optional[str] = None
    discogs_id: Optional[str] = None
    resources: list[ArtistResource] = Field(default_factory=list)

    @property
    def effective_sort_name(self) -> str:
        return self.sort_name or self.name

    @property
    def sort_letter(self) -> str:
        name = self.effective_sort_name
        return name[0].upper() if name else '#'

    @property
    def display_letter(self) -> str:
        return self.name[0].upper() if self.name else '#'

    @property
    def legacy_dir(self) -> str:
        """Last path segment of legacy_path, e.g. 'Albert_Collins'."""
        lp = (self.legacy_path or '').strip('/')
        parts = lp.split('/')
        last = parts[-1] if parts else ''
        if '.' in last or last.startswith('www.'):
            return ''
        return last


# ── Album ──────────────────────────────────────────────────────────────────────

class Album(BaseModel):
    """One file from data/albums/{artist-slug}/{slug}.yaml."""
    id: int
    slug: str
    artist_id: Optional[int] = None
    artist_slug: Optional[str] = None
    artist: Optional[str] = ''
    title: Optional[str] = ''
    year: Optional[int] = None
    label: Optional[str] = None
    asin: Optional[str] = None
    amg_id: Optional[str] = None
    apple_music_id: Optional[str] = None
    spotify_id: Optional[str] = None
    deezer_id: Optional[str] = None
    ytmusic_id: Optional[str] = None
    youtube_video_id: Optional[str] = None
    youtube_playlist_id: Optional[str] = None
    discogs_master_id: Optional[str] = None
    reviews: list[AlbumReview] = Field(default_factory=list)

    @property
    def year_str(self) -> str:
        return str(self.year) if self.year else ''


# ── Calendar ───────────────────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    """One entry from data/calendar.yaml."""
    date: str = ''
    year: Optional[str | int] = None   # stored as int in YAML, used as str
    month_day: Optional[str] = None
    event_type: Optional[str] = None
    title: Optional[str] = None
    text: str = ''
    picture: Optional[str] = None
    artist_slug: Optional[str] = None


# ── ATB ────────────────────────────────────────────────────────────────────────

class ATBEpisode(BaseModel):
    """One entry from data/atb/episodes.yaml."""
    slug: str
    date: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    artists_tags: list[Any] = Field(default_factory=list)
    filename: Optional[str] = None
    parts: list[Any] = Field(default_factory=list)


# ── Gallery ────────────────────────────────────────────────────────────────────

class GalleryPhoto(BaseModel):
    file: str
    caption: Optional[str] = None
    thumb: Optional[str] = None


class GalleryMeta(BaseModel):
    """
    Metadata for one photo gallery (from data/galleries/*.yaml or index.yaml).
    """
    slug: str = ''
    title: Optional[str] = None
    clean_title: Optional[str] = None
    canonical_date: Optional[str] = None
    path: Optional[str] = None           # source dir within bluesnews/
    type: Optional[str] = None           # 'lightroom', 'mts', 'custom'
    photo_count: int = 0
    photos: list[Any] = Field(default_factory=list)
    artists_tags: list[str] = Field(default_factory=list)
    exclude: bool = False
    description: Optional[str] = None
    extra_text: Optional[str] = None
    source_articles: list[Any] = Field(default_factory=list)

    @property
    def display_title(self) -> str:
        return self.clean_title or self.title or self.slug


# ── News ───────────────────────────────────────────────────────────────────────

class NewsItem(BaseModel):
    """
    Parsed from data/news/YYYY/MM/DD/{slug}.md front-matter.
    The body text is kept separate (not a model field) because it's rendered
    markdown/HTML and can be large.
    """
    id: Optional[int] = None
    slug: Optional[str] = None
    title: str = ''
    date: Optional[str] = None
    author: Optional[str] = None
    source: Optional[str] = None


# ── Forum ──────────────────────────────────────────────────────────────────────

class ForumPost(BaseModel):
    """Recursive post node from a topic YAML file."""
    id: Optional[int] = None
    poster: str = ''
    date: Optional[str] = None
    subject: str = ''
    text: str = ''
    deleted: bool = False
    replies: list[ForumPost] = Field(default_factory=list)

    model_config = {'arbitrary_types_allowed': True}

ForumPost.model_rebuild()  # required for self-referencing model


class ForumTopicMeta(BaseModel):
    """Lightweight topic descriptor used in forum index (from topics-index.yaml)."""
    topic_id: int
    slug: str
    title: str = ''
    first_post: Optional[str] = None
    last_post: Optional[str] = None
    post_count: int = 0
    _path: Optional[Any] = None          # runtime Path, not serialised

    model_config = {'arbitrary_types_allowed': True, 'populate_by_name': True}

    @classmethod
    def from_dict(cls, d: dict, path: Any = None) -> ForumTopicMeta:
        m = cls.model_validate(d)
        object.__setattr__(m, '_path', path)
        return m


class ForumTopic(BaseModel):
    """Full topic data loaded from a per-topic YAML file."""
    topic_id: Optional[int] = None
    slug: str = ''
    title: str = ''
    posts: list[ForumPost] = Field(default_factory=list)


# ── Links ──────────────────────────────────────────────────────────────────────

class LinkSite(BaseModel):
    """One external site entry from data/links.yaml."""
    id: str = ''
    name: str = ''
    url: str = ''
    description: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    status: str = 'unknown'


class LinkCategory(BaseModel):
    """One category node from data/links.yaml."""
    id: str
    name: str
    parent_id: Optional[str] = None


# ── Streaming ──────────────────────────────────────────────────────────────────

class ArtistStreamingIds(BaseModel):
    """Streaming IDs for an artist. All fields are optional."""
    spotify_id: Optional[str] = None
    apple_music_id: Optional[str] = None
    deezer_id: Optional[str] = None
    discogs_id: Optional[str] = None

    def is_empty(self) -> bool:
        return not any([self.spotify_id, self.apple_music_id, self.deezer_id,
                        self.discogs_id])


class AlbumStreamingIds(BaseModel):
    """Streaming IDs for an album. All fields are optional."""
    spotify_id: Optional[str] = None
    apple_music_id: Optional[str] = None
    deezer_id: Optional[str] = None
    ytmusic_id: Optional[str] = None
    youtube_video_id: Optional[str] = None
    youtube_playlist_id: Optional[str] = None
    discogs_master_id: Optional[str] = None

    def is_empty(self) -> bool:
        return not any([
            self.spotify_id, self.apple_music_id, self.deezer_id,
            self.ytmusic_id, self.youtube_video_id, self.youtube_playlist_id,
            self.discogs_master_id,
        ])


# ── Artist link (rich version for templates) ───────────────────────────────────

class ArtistLink(BaseModel):
    """
    A structured resource link for an artist page nav block.
    Produced by collect_artist_links(); consumed by format_artist_links().
    """
    type: str                   # 'interview', 'article', 'photo', 'streaming', 'calendar', etc.
    url: str
    title: str
    external: bool = False
    platform: Optional[str] = None   # for type='streaming': 'spotify', 'apple_music', etc.
