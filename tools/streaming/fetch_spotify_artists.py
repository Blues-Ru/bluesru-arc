#!/usr/bin/env python3
"""
Fetch Spotify artist IDs for blues artists and store in data/artists.yaml.

Requires Spotify API credentials. Get them at https://developer.spotify.com/dashboard
Set environment variables:
    SPOTIFY_CLIENT_ID=your_client_id
    SPOTIFY_CLIENT_SECRET=your_client_secret

Usage:
    SPOTIFY_CLIENT_ID=xxx SPOTIFY_CLIENT_SECRET=yyy python3 tools/streaming/fetch_spotify_artists.py
    python3 tools/streaming/fetch_spotify_artists.py --dry-run    # show what would be done

Run from anywhere — paths are repo-relative.
"""

import os
import sys
import ssl
import time
import json
import yaml
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
ARTISTS_YAML = ARC / "data" / "artists.yaml"


def get_spotify_token(client_id, client_secret):
    """Get Spotify client credentials token."""
    import base64
    credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode()
    req = urllib.request.Request(
        'https://accounts.spotify.com/api/token',
        data=data,
        headers={'Authorization': f'Basic {credentials}',
                 'Content-Type': 'application/x-www-form-urlencoded'}
    )
    with urllib.request.urlopen(req, context=_SSL_CTX) as resp:
        result = json.loads(resp.read())
    return result['access_token']


def search_spotify_artist(name, token):
    """Search for an artist on Spotify, return best match ID or None."""
    query = urllib.parse.urlencode({'q': name, 'type': 'artist', 'limit': '5'})
    req = urllib.request.Request(
        f'https://api.spotify.com/v1/search?{query}',
        headers={'Authorization': f'Bearer {token}'}
    )
    try:
        with urllib.request.urlopen(req, context=_SSL_CTX) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            retry_after = int(e.headers.get('Retry-After', '5'))
            print(f"  Rate limited, waiting {retry_after}s...")
            time.sleep(retry_after)
            return search_spotify_artist(name, token)
        return None

    items = data.get('artists', {}).get('items', [])
    if not items:
        return None

    # Return the first result's ID (usually best match)
    return items[0]['id']


def load_artists():
    """Load all artist names and slugs from data/artists.yaml."""
    artists_path = EXTRACTED / "blues-data" / "artists.yaml"
    if not artists_path.exists():
        print(f"ERROR: {artists_path} not found")
        sys.exit(1)
    return yaml.safe_load(artists_path.read_text(encoding='utf-8')) or []


def main():
    dry_run = '--dry-run' in sys.argv

    client_id = os.environ.get('SPOTIFY_CLIENT_ID')
    client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')

    if not dry_run and (not client_id or not client_secret):
        print("ERROR: Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables")
        print("Get credentials at https://developer.spotify.com/dashboard")
        sys.exit(1)

    # Load existing streaming data
    streaming = {}
    if ARTISTS_YAML.exists():
        streaming = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8')) or {}

    # Load artist list
    artists = load_artists()
    print(f"Artists to process: {len(artists)}")

    # Find artists without Spotify IDs
    to_fetch = []
    for a in artists:
        slug = a.get('slug', '')
        name = a.get('name', '')
        if not slug or not name:
            continue
        existing = streaming.get(slug, {})
        if existing.get('spotify_id'):
            continue  # Already have it
        to_fetch.append((slug, name))

    print(f"Artists without Spotify ID: {len(to_fetch)}")

    if dry_run:
        print("\nDry run — would fetch:")
        for slug, name in to_fetch[:20]:
            print(f"  {slug}: {name}")
        if len(to_fetch) > 20:
            print(f"  ... and {len(to_fetch) - 20} more")
        return

    token = get_spotify_token(client_id, client_secret)
    print("Got Spotify token")

    updated = 0
    not_found = 0
    for i, (slug, name) in enumerate(to_fetch):
        artist_id = search_spotify_artist(name, token)
        if artist_id:
            if slug not in streaming:
                streaming[slug] = {}
            streaming[slug]['spotify_id'] = artist_id
            updated += 1
            print(f"  [{i+1}/{len(to_fetch)}] {name} → {artist_id}")
        else:
            not_found += 1
            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(to_fetch)}] {name} → not found")

        # Rate limiting: ~100 requests/minute on free tier
        time.sleep(0.65)

        # Checkpoint every 50
        if (i + 1) % 50 == 0:
            ARTISTS_YAML.write_text(
                yaml.dump(streaming, allow_unicode=True, default_flow_style=False, sort_keys=True),
                encoding='utf-8'
            )
            print(f"  Checkpoint saved ({i+1} processed)")

    ARTISTS_YAML.write_text(
        yaml.dump(streaming, allow_unicode=True, default_flow_style=False, sort_keys=True),
        encoding='utf-8'
    )
    print(f"\nDone. Updated: {updated}, Not found: {not_found}")
    print(f"Saved to {ARTISTS_YAML}")


if __name__ == '__main__':
    main()
