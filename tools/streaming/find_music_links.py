#!/usr/bin/env python3
"""
Find artist and album IDs on streaming platforms.

Populates:
  data/artists.yaml  — artist streaming IDs
  data/albums/{artist-slug}/*.yaml — album streaming IDs (per-album)

Services:
  Apple Music  — via iTunes Search API (free, no auth)
  Spotify      — via Web API (requires SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET)

Usage:
  python3 tools/streaming/find_music_links.py [--section artists|albums] [--limit N]

  Set env vars for Spotify:
    export SPOTIFY_CLIENT_ID=your_client_id
    export SPOTIFY_CLIENT_SECRET=your_client_secret

  Run from anywhere — paths are repo-relative.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
import yaml
from pathlib import Path

# macOS system Python often lacks CA certs; use unverified context
_SSL_CTX = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

ARC = Path("/bluesru-arc").resolve() if False else Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
ARTISTS_YAML = ARC / "data" / "artists.yaml"
ALBUMS_DIR = ARC / "data" / "albums"  # subdirs: {artist-slug}/*.yaml
# NOTE: IDs now stored per-album in ALBUMS_DIR/**/*.yaml (not flat streaming/albums.yaml)
# Rewrite load_albums()/save_albums() if re-running this script on new data.


# ── Utilities ─────────────────────────────────────────────────────────────────

def load_yaml(path):
    if path.exists():
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return {}

def save_yaml(path, data):
    path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False,
                               sort_keys=False), encoding='utf-8')

def http_get_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"    HTTP error: {e}", file=sys.stderr)
        return None

def clean_name(name):
    """Normalize artist/album name for comparison."""
    return re.sub(r'[^\w\s]', '', name.lower()).strip()


# ── Apple Music (iTunes Search API) ──────────────────────────────────────────

ITUNES_SEARCH = "https://itunes.apple.com/search"

def apple_search_artist(name):
    """Return (artist_id, artist_url) or (None, None)."""
    params = urllib.parse.urlencode({
        'term': name, 'entity': 'musicArtist', 'country': 'us', 'limit': 5
    })
    data = http_get_json(f"{ITUNES_SEARCH}?{params}")
    if not data:
        return None, None
    target = clean_name(name)
    for r in data.get('results', []):
        if clean_name(r.get('artistName', '')) == target:
            aid = r['artistId']
            url = re.sub(r'\?.*', '', r.get('artistLinkUrl', ''))
            return str(aid), url
    # Fuzzy: take first result if name is close
    results = data.get('results', [])
    if results:
        r = results[0]
        candidate = clean_name(r.get('artistName', ''))
        if target in candidate or candidate in target:
            aid = r['artistId']
            url = re.sub(r'\?.*', '', r.get('artistLinkUrl', ''))
            return str(aid), url
    return None, None

def apple_search_album(artist_name, album_title, year=None):
    """Return (album_id, album_url) or (None, None)."""
    query = f"{artist_name} {album_title}"
    params = urllib.parse.urlencode({
        'term': query, 'entity': 'album', 'country': 'us', 'limit': 10
    })
    data = http_get_json(f"{ITUNES_SEARCH}?{params}")
    if not data:
        return None, None
    target_album = clean_name(album_title)
    target_artist = clean_name(artist_name)
    for r in data.get('results', []):
        if (clean_name(r.get('collectionName', '')) == target_album and
                clean_name(r.get('artistName', '')) == target_artist):
            cid = r['collectionId']
            url = re.sub(r'\?.*', '', r.get('collectionViewUrl', ''))
            return str(cid), url
    # Looser match — album title only
    for r in data.get('results', []):
        if clean_name(r.get('collectionName', '')) == target_album:
            cid = r['collectionId']
            url = re.sub(r'\?.*', '', r.get('collectionViewUrl', ''))
            return str(cid), url
    return None, None


# ── Spotify ───────────────────────────────────────────────────────────────────

_spotify_token = None

def spotify_token():
    global _spotify_token
    if _spotify_token:
        return _spotify_token
    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
    if not client_id or not client_secret:
        return None
    import base64
    creds = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode()
    req = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=data,
        headers={'Authorization': f'Basic {creds}', 'Content-Type': 'application/x-www-form-urlencoded'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            r = json.loads(resp.read())
            _spotify_token = r.get('access_token')
            return _spotify_token
    except Exception as e:
        print(f"  Spotify auth failed: {e}", file=sys.stderr)
        return None

def spotify_search_artist(name):
    """Return (artist_id, artist_url) or (None, None)."""
    tok = spotify_token()
    if not tok:
        return None, None
    params = urllib.parse.urlencode({'q': name, 'type': 'artist', 'limit': 5})
    data = http_get_json(
        f"https://api.spotify.com/v1/search?{params}",
        headers={'Authorization': f'Bearer {tok}'}
    )
    if not data:
        return None, None
    target = clean_name(name)
    for r in data.get('artists', {}).get('items', []):
        if clean_name(r.get('name', '')) == target:
            return r['id'], r['external_urls'].get('spotify', '')
    return None, None

def spotify_search_album(artist_name, album_title, year=None):
    """Return (album_id, album_url) or (None, None)."""
    tok = spotify_token()
    if not tok:
        return None, None
    query = f'album:"{album_title}" artist:"{artist_name}"'
    params = urllib.parse.urlencode({'q': query, 'type': 'album', 'limit': 5})
    data = http_get_json(
        f"https://api.spotify.com/v1/search?{params}",
        headers={'Authorization': f'Bearer {tok}'}
    )
    if not data:
        return None, None
    target_album = clean_name(album_title)
    target_artist = clean_name(artist_name)
    for r in data.get('albums', {}).get('items', []):
        if (clean_name(r.get('name', '')) == target_album and
                any(clean_name(a.get('name', '')) == target_artist
                    for a in r.get('artists', []))):
            return r['id'], r['external_urls'].get('spotify', '')
    return None, None


# ── Main search runners ───────────────────────────────────────────────────────

def find_artist_links(name):
    """Return dict with apple/spotify IDs and URLs."""
    result = {}
    apple_id, apple_url = apple_search_artist(name)
    if apple_id:
        result['apple_music_id'] = apple_id
        result['apple_music_url'] = apple_url
    spot_id, spot_url = spotify_search_artist(name)
    if spot_id:
        result['spotify_id'] = spot_id
        result['spotify_url'] = spot_url
    return result

def find_album_links(artist_name, album_title, year=None):
    """Return dict with apple/spotify IDs and URLs."""
    result = {}
    apple_id, apple_url = apple_search_album(artist_name, album_title, year)
    if apple_id:
        result['apple_music_id'] = apple_id
        result['apple_music_url'] = apple_url
    spot_id, spot_url = spotify_search_album(artist_name, album_title, year)
    if spot_id:
        result['spotify_id'] = spot_id
        result['spotify_url'] = spot_url
    return result


# ── Process artists ───────────────────────────────────────────────────────────

def process_artists(limit=None):
    artists = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8')) or []
    existing = load_yaml(OUT_ARTISTS)
    updated = 0

    for i, artist in enumerate(artists):
        if limit and updated >= limit:
            break
        slug = artist.get('slug', '')
        name = artist.get('name', '')
        if not slug or not name:
            continue
        if slug in existing:
            continue  # already tried (have data or confirmed not found)

        print(f"  [{i+1}/{len(artists)}] {name}...", end=' ', flush=True)
        links = find_artist_links(name)
        if links:
            existing[slug] = links
            print('+' + ','.join(links.keys()))
        else:
            existing[slug] = {}
            print('not found')
        updated += 1
        time.sleep(0.3)  # be polite to iTunes API

    save_yaml(OUT_ARTISTS, existing)
    print(f"  Artists: {updated} processed, saved to {OUT_ARTISTS}")


# ── Process albums ────────────────────────────────────────────────────────────

def process_albums(limit=None):
    existing = load_yaml(OUT_ALBUMS)
    updated = 0
    album_files = sorted(ALBUMS_DIR.glob('*.yaml'))

    for i, fpath in enumerate(album_files):
        if limit and updated >= limit:
            break
        album = yaml.safe_load(fpath.read_text(encoding='utf-8')) or {}
        slug = album.get('slug', '')
        artist = album.get('artist', '')
        title = album.get('title', '')
        year = album.get('year', '')
        if not slug or not artist or not title:
            continue
        if slug in existing:
            continue  # already tried (have data or confirmed not found)

        print(f"  [{i+1}/{len(album_files)}] {artist} — {title}...", end=' ', flush=True)
        links = find_album_links(artist, title, year)
        if links:
            existing[slug] = links
            print('+' + ','.join(links.keys()))
        else:
            existing[slug] = {}
            print('not found')
        updated += 1
        time.sleep(0.3)

    save_yaml(OUT_ALBUMS, existing)
    print(f"  Albums: {updated} processed, saved to {OUT_ALBUMS}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Find streaming music links')
    parser.add_argument('--section', choices=['artists', 'albums', 'both'], default='both')
    parser.add_argument('--limit', type=int, default=None,
                        help='Max new entries to process (for testing)')
    args = parser.parse_args()

    has_spotify = bool(os.environ.get('SPOTIFY_CLIENT_ID'))
    print(f"Apple Music: enabled (iTunes API)")
    print(f"Spotify: {'enabled' if has_spotify else 'disabled (set SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET)'}")
    print()

    if args.section in ('artists', 'both'):
        print("Processing artists...")
        process_artists(args.limit)
    if args.section in ('albums', 'both'):
        print("Processing albums...")
        process_albums(args.limit)

if __name__ == '__main__':
    main()
