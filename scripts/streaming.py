"""
Streaming platform link generation.

All platform URL templates and labels live here.  Functions produce HTML
strings or structured dicts ready for templates.
"""

from __future__ import annotations

from models import ArtistStreamingIds, AlbumStreamingIds

# ── URL templates ──────────────────────────────────────────────────────────────
ALBUM_URL_TEMPLATES: dict[str, str] = {
    'apple_music':      'https://geo.music.apple.com/album/{}',
    'spotify':          'https://open.spotify.com/album/{}',
    'deezer':           'https://www.deezer.com/album/{}',
    'ytmusic':          'https://music.youtube.com/browse/{}',
    'youtube_video':    'https://www.youtube.com/watch?v={}',
    'youtube_playlist': 'https://www.youtube.com/playlist?list={}',
}

ARTIST_URL_TEMPLATES: dict[str, str] = {
    'apple_music': 'https://geo.music.apple.com/artist/{}',
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

# Named browser windows — one per service so repeated clicks reuse the same tab
PLATFORM_TARGETS: dict[str, str] = {
    'apple_music':      'bluesru-apple',
    'spotify':          'bluesru-spotify',
    'deezer':           'bluesru-deezer',
    'ytmusic':          'bluesru-ytmusic',
    'youtube_video':    'bluesru-youtube',
    'youtube_playlist': 'bluesru-youtube',
}

# ── Service logo SVGs (36×36) ──────────────────────────────────────────────────
_ICONS: dict[str, str] = {
    'spotify': (
        '<svg viewBox="0 0 36 36" width="36" height="36" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="18" cy="18" r="18" fill="#1DB954"/>'
        '<path d="M9 15q9-4 18 0" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>'
        '<path d="M9.5 20.5q8-3.5 17 0" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>'
        '<path d="M11 25.5q6.5-2.5 14 0" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"/>'
        '</svg>'
    ),
    'apple_music': (
        '<svg viewBox="0 0 36 36" width="36" height="36" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="36" height="36" rx="8" fill="#FA2D48"/>'
        '<path d="M14 26v-13l11-3v12" fill="none" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/>'
        '<circle cx="12" cy="26" r="3" fill="#fff"/>'
        '<circle cx="23" cy="23" r="3" fill="#fff"/>'
        '</svg>'
    ),
    'deezer': (
        '<svg viewBox="0 0 36 36" width="36" height="36" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="36" height="36" rx="7" fill="#A238FF"/>'
        '<rect x="5"  y="22" width="5" height="9"  rx="2" fill="#fff"/>'
        '<rect x="12" y="17" width="5" height="14" rx="2" fill="#fff"/>'
        '<rect x="19" y="12" width="5" height="19" rx="2" fill="#fff"/>'
        '<rect x="26" y="7"  width="5" height="24" rx="2" fill="#fff"/>'
        '</svg>'
    ),
    'ytmusic': (
        '<svg viewBox="0 0 36 36" width="36" height="36" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="18" cy="18" r="18" fill="#FF0000"/>'
        '<circle cx="18" cy="18" r="12" fill="#fff"/>'
        '<polygon points="14,12 27,18 14,24" fill="#FF0000"/>'
        '<circle cx="18" cy="18" r="4.5" fill="#FF0000"/>'
        '</svg>'
    ),
    'youtube': (
        '<svg viewBox="0 0 36 36" width="36" height="36" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="36" height="36" rx="8" fill="#FF0000"/>'
        '<polygon points="13,10 28,18 13,26" fill="#fff"/>'
        '</svg>'
    ),
}

# Map platform key → icon key
_PLATFORM_ICON: dict[str, str] = {
    'apple_music':      'apple_music',
    'spotify':          'spotify',
    'deezer':           'deezer',
    'ytmusic':          'ytmusic',
    'youtube_video':    'youtube',
    'youtube_playlist': 'youtube',
}


def _icon_link(url: str, platform: str, label: str) -> str:
    icon = _ICONS.get(_PLATFORM_ICON.get(platform, ''), '')
    if not icon:
        return ''
    target = PLATFORM_TARGETS.get(platform, '_blank')
    return (f'<a href="{url}" target="{target}" rel="noopener"'
            f' class="stream-icon" title="{label}">{icon}</a>')


def _plain_link(url: str, label: str, platform: str) -> str:
    target = PLATFORM_TARGETS.get(platform, '_blank')
    return f'<a href="{url}" target="{target}" rel="noopener">{label}</a>'


# ── Text links (for "Альбом на:" row and resource nav) ─────────────────────────

def artist_streaming_links_html(ids: ArtistStreamingIds | None) -> str:
    """Return plain text links for artist streaming platforms."""
    if ids is None or ids.is_empty():
        return ''
    parts: list[str] = []
    for platform, tmpl in ARTIST_URL_TEMPLATES.items():
        value = getattr(ids, f'{platform}_id', None)
        if value:
            parts.append(_plain_link(tmpl.format(value), PLATFORM_LABELS[platform], platform))
    return ' | '.join(parts)


def album_streaming_links_html(ids: AlbumStreamingIds | None) -> str:
    """Return plain text links for album streaming platforms."""
    if ids is None or ids.is_empty():
        return ''
    parts: list[str] = []
    seen_labels: set[str] = set()
    for platform, tmpl in ALBUM_URL_TEMPLATES.items():
        value = getattr(ids, f'{platform}_id', None)
        if not value:
            continue
        label = PLATFORM_LABELS[platform]
        if label in seen_labels:
            continue
        seen_labels.add(label)
        parts.append(_plain_link(tmpl.format(value), label, platform))
    return ' | '.join(parts)


def streaming_links_html(slug: str, kind: str, store) -> str:
    """Convenience wrapper: looks up streaming IDs from ``store`` and returns HTML.
    ``kind`` is 'artist' or 'album'."""
    if kind == 'artist':
        return artist_streaming_links_html(store.artist_streaming().get(slug))
    return album_streaming_links_html(store.album_streaming().get(slug))


# ── Icon row ───────────────────────────────────────────────────────────────────

def album_stream_icons_html(ids: AlbumStreamingIds | None) -> str:
    """Return a row of service logo icon links for an album."""
    if ids is None or ids.is_empty():
        return ''
    parts: list[str] = []
    seen_labels: set[str] = set()
    for platform, tmpl in ALBUM_URL_TEMPLATES.items():
        value = getattr(ids, f'{platform}_id', None)
        if not value:
            continue
        label = PLATFORM_LABELS[platform]
        if label in seen_labels:
            continue
        seen_labels.add(label)
        link = _icon_link(tmpl.format(value), platform, label)
        if link:
            parts.append(link)
    if not parts:
        return ''
    return '<div class="stream-icons">' + ''.join(parts) + '</div>\n'


def artist_stream_icons_html(ids: ArtistStreamingIds | None) -> str:
    """Return a row of service logo icon links for an artist."""
    if ids is None or ids.is_empty():
        return ''
    parts: list[str] = []
    for platform, tmpl in ARTIST_URL_TEMPLATES.items():
        value = getattr(ids, f'{platform}_id', None)
        if value:
            link = _icon_link(tmpl.format(value), platform, PLATFORM_LABELS[platform])
            if link:
                parts.append(link)
    if not parts:
        return ''
    return '<div class="stream-icons">' + ''.join(parts) + '</div>\n'


def stream_icons_html(slug: str, kind: str, store) -> str:
    """Convenience wrapper for icon row."""
    if kind == 'artist':
        return artist_stream_icons_html(store.artist_streaming().get(slug))
    return album_stream_icons_html(store.album_streaming().get(slug))
