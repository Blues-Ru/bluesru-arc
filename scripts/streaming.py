"""
Streaming platform link generation.

All platform URL templates and labels live here.  Functions produce HTML
strings or structured dicts ready for templates.
"""

from __future__ import annotations

from models import ArtistStreamingIds, AlbumStreamingIds

# ── URL templates ──────────────────────────────────────────────────────────────
ALBUM_URL_TEMPLATES: dict[str, str] = {
    'apple_music':      'https://music.apple.com/us/album/{}',
    'spotify':          'https://open.spotify.com/album/{}',
    'deezer':           'https://www.deezer.com/album/{}',
    'ytmusic':          'https://music.youtube.com/browse/{}',
    'youtube_video':    'https://www.youtube.com/watch?v={}',
    'youtube_playlist': 'https://www.youtube.com/playlist?list={}',
}

ARTIST_URL_TEMPLATES: dict[str, str] = {
    'apple_music': 'https://music.apple.com/us/artist/{}',
    'spotify':     'https://open.spotify.com/artist/{}',
    'deezer':      'https://www.deezer.com/artist/{}',
}

PLATFORM_LABELS: dict[str, str] = {
    'apple_music':      'Apple Music',
    'spotify':          'Spotify',
    'deezer':           'Deezer',
    'ytmusic':          'YouTube Music',
    'youtube_video':    'YouTube',
    'youtube_playlist': 'YouTube',
}


def artist_streaming_links_html(ids: ArtistStreamingIds | None) -> str:
    """Return ' | '-separated HTML anchor tags for artist streaming platforms."""
    if ids is None or ids.is_empty():
        return ''
    parts: list[str] = []
    for platform, tmpl in ARTIST_URL_TEMPLATES.items():
        value = getattr(ids, f'{platform}_id', None)
        if value:
            url = tmpl.format(value)
            label = PLATFORM_LABELS[platform]
            parts.append(f'<a href="{url}" target="_blank">{label}</a>')
    return ' | '.join(parts)


def album_streaming_links_html(ids: AlbumStreamingIds | None) -> str:
    """Return ' | '-separated HTML anchor tags for album streaming platforms."""
    if ids is None or ids.is_empty():
        return ''
    parts: list[str] = []
    for platform, tmpl in ALBUM_URL_TEMPLATES.items():
        key = f'{platform}_id'
        value = getattr(ids, key, None)
        if value:
            url = tmpl.format(value)
            label = PLATFORM_LABELS[platform]
            parts.append(f'<a href="{url}" target="_blank">{label}</a>')
    return ' | '.join(parts)


def streaming_links_html(slug: str, kind: str, store) -> str:
    """
    Convenience wrapper: looks up streaming IDs from ``store`` and returns HTML.
    ``kind`` is 'artist' or 'album'.
    """
    if kind == 'artist':
        return artist_streaming_links_html(store.artist_streaming().get(slug))
    return album_streaming_links_html(store.album_streaming().get(slug))
