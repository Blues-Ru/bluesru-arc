#!/usr/bin/env python3
"""
Add Spotify links for albums already matched on Apple Music / Deezer.

Strategy: per-album targeted search (avoids catalog pagination rate limits).
For each album with Apple/Deezer but no Spotify:
  - Search Spotify: "artist title"
  - Pick match with highest title similarity + year proximity
  - LLM validates batches of 20 ambiguous matches

Much friendlier to Spotify rate limits than full catalog pagination.

Usage:
  source ~/.bashrc
  python3 tools/streaming/add_spotify_links.py [--artist SLUG] [--limit N] [--dry-run]

Run from anywhere — paths are repo-relative.
"""

import argparse
import base64
import difflib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ARC        = Path(__file__).resolve().parent.parent.parent
WORKSPACE  = ARC.parent
ALBUMS_DIR = ARC / "data" / "albums"  # subdirs: {artist-slug}/*.yaml
ARTISTS_YAML = ARC / "data" / "artists.yaml"
# NOTE: IDs now stored per-album in ALBUMS_DIR/**/*.yaml (not flat streaming/albums.yaml)
# OUT_ALBUMS → write back to individual YAML files; logic needs updating.

_SSL = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

SEARCH_DELAY = 0.4   # seconds between search calls
BATCH_SIZE = 20      # albums per LLM validation batch


# ── HTTP ───────────────────────────────────────────────────────────────────────

def http_get(url, headers=None, retries=4):
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 15 * (attempt + 1)
                print(f"\n  [429 rate limit, sleeping {wait}s]", file=sys.stderr)
                time.sleep(wait)
            elif e.code in (400, 401, 403):
                if e.code in (401, 403):
                    global _spotify_token
                    _spotify_token = None
                return None
            else:
                return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                print(f"  HTTP error: {e}", file=sys.stderr)
                return None
    return None


# ── Spotify ────────────────────────────────────────────────────────────────────

_spotify_token = None

def spotify_auth():
    global _spotify_token
    if not _spotify_token:
        cid = os.environ.get('SPOTIFY_CLIENT_ID', '')
        csc = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
        if not cid or not csc:
            print("ERROR: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not set", file=sys.stderr)
            return None
        creds = base64.b64encode(f'{cid}:{csc}'.encode()).decode()
        data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode()
        req = urllib.request.Request(
            'https://accounts.spotify.com/api/token', data=data,
            headers={'Authorization': f'Basic {creds}',
                     'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
                _spotify_token = json.loads(r.read())['access_token']
        except Exception as e:
            print(f"  Spotify auth failed: {e}", file=sys.stderr)
            return None
    return {'Authorization': f'Bearer {_spotify_token}'}


def spotify_search(query, limit=5):
    """Search Spotify albums. Returns list of {id, name, year, artists}."""
    auth = spotify_auth()
    if not auth:
        return []
    params = urllib.parse.urlencode({'q': query, 'type': 'album', 'limit': limit})
    data = http_get(f"https://api.spotify.com/v1/search?{params}", auth)
    if not data:
        return []
    return [
        {'id': a['id'],
         'name': a['name'],
         'year': a.get('release_date', '')[:4],
         'artists': [ar['name'] for ar in a.get('artists', [])]}
        for a in data.get('albums', {}).get('items', [])
        if a.get('id')
    ]


# ── Matching helpers ───────────────────────────────────────────────────────────

_EDITION_STRIP = re.compile(
    r'\s*[\(\[]?(?:remaster(?:ed)?(?:\s+\d{4})?|deluxe(?:\s+edition)?|'
    r'anniversary(?:\s+edition)?|expanded|bonus\s+tracks?|'
    r'\d{4}\s+remaster|special\s+edition)\s*[\)\]]?\s*$',
    re.IGNORECASE)

def _norm(t):
    t = _EDITION_STRIP.sub('', t or '').lower()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())

def title_score(a, b):
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()

def year_ok(our_year, sp_year):
    """True if years are compatible (within 5 years, or either unknown)."""
    if not our_year or not sp_year:
        return True
    try:
        return abs(int(our_year) - int(sp_year)) <= 5
    except ValueError:
        return True

def best_match(our_title, our_year, candidates):
    """
    Pick best Spotify candidate. Returns (item, score) or (None, 0).
    score >= 0.85: confident auto-match
    score 0.65-0.85: needs LLM validation
    score < 0.65: no match
    """
    best, best_sc = None, 0.0
    for c in candidates:
        sc = title_score(our_title, c['name'])
        if sc > best_sc:
            best_sc, best = sc, c
    if best and not year_ok(our_year, best.get('year', '')):
        best_sc *= 0.7  # penalize year mismatch
    return best, best_sc


# ── LLM validation ────────────────────────────────────────────────────────────

_claude = None

def get_claude():
    global _claude
    if _claude is None:
        key = os.environ.get('ANTHROPIC_API_KEY')
        if not key:
            return None
        import anthropic
        _claude = anthropic.Anthropic(api_key=key)
    return _claude


def llm_validate_batch(candidates_batch):
    """
    Validate a batch of (slug, our_title, our_year, artist, sp_item) tuples.
    Returns {slug: spotify_id or None}.
    """
    claude = get_claude()
    if not claude:
        return {}

    items = [
        {
            'slug': slug,
            'our_title': our_title,
            'our_year': our_year,
            'artist': artist,
            'spotify_title': sp['name'],
            'spotify_year': sp.get('year', ''),
            'spotify_id': sp['id'],
            'spotify_artists': sp.get('artists', []),
        }
        for slug, our_title, our_year, artist, sp in candidates_batch
    ]

    prompt = f"""For each entry, decide if the Spotify album is a match for our album.
Match = same album (editions/remasters count as match if title core is same and artist matches).

{json.dumps(items, ensure_ascii=False, indent=2)}

Return ONLY a JSON object mapping slug → spotify_id (or null if no match):
{{"slug1": "spotify_id or null", "slug2": "...", ...}}"""

    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}])
        text = resp.content[0].text.strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        m = re.search(r'(\{.*\})', text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
    return {}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_yaml(path):
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding='utf-8')) or {} if p.exists() else {}

def save_yaml(path, data):
    Path(path).write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding='utf-8')

def load_albums_needing_spotify(existing, filter_artist=None):
    """Return list of (artist_slug, artist_name, album) for albums with Apple/Deezer but no Spotify."""
    artists_data = yaml.safe_load(Path(ARTISTS_YAML).read_text(encoding='utf-8')) or []
    id_to_artist = {str(a['id']): a for a in artists_data}

    result = []
    for fpath in sorted(ALBUMS_DIR.glob('*.yaml')):
        alb = yaml.safe_load(fpath.read_text(encoding='utf-8')) or {}
        slug = alb.get('slug', '')
        if not slug:
            continue
        if filter_artist:
            artist = id_to_artist.get(str(alb.get('artist_id', '')), {})
            if artist.get('slug', '') != filter_artist:
                continue
        info = existing.get(slug, {})
        if not isinstance(info, dict):
            continue
        if not (info.get('apple_music_id') or info.get('deezer_id')):
            continue
        if info.get('spotify_id'):
            continue
        artist = id_to_artist.get(str(alb.get('artist_id', '')), {})
        result.append({
            'artist_slug': artist.get('slug', ''),
            'artist_name': artist.get('name', alb.get('artist', '')),
            'slug': slug,
            'title': alb.get('title', ''),
            'year': str(alb.get('year', '') or ''),
        })
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artist', help='Process only this artist slug')
    parser.add_argument('--limit', type=int, help='Max albums to process')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    auth = spotify_auth()
    if not auth:
        print("No Spotify credentials. Set SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET.")
        sys.exit(1)

    has_llm = bool(get_claude())
    print(f"Spotify: ✓  LLM: {'✓' if has_llm else '✗ (auto-match only, threshold 0.85)'}")

    existing = load_yaml(OUT_ALBUMS)
    albums = load_albums_needing_spotify(existing, filter_artist=args.artist)

    if args.limit:
        albums = albums[:args.limit]

    print(f"Albums needing Spotify: {len(albums)}\n")

    auto_matched = 0
    llm_pending = []   # (slug, our_title, our_year, artist_name, sp_item)
    no_match = 0
    processed = 0

    for alb in albums:
        slug = alb['slug']
        title = alb['title']
        year = alb['year']
        artist = alb['artist_name']

        # Build search query: artist + title (keep it short for better recall)
        query = f"{artist} {title}"
        candidates = spotify_search(query, limit=5)
        time.sleep(SEARCH_DELAY)

        if not candidates:
            no_match += 1
            processed += 1
            continue

        match, score = best_match(title, year, candidates)

        if score >= 0.85:
            # High confidence: accept immediately
            entry = existing.get(slug, {})
            if not isinstance(entry, dict):
                entry = {}
            entry['spotify_id'] = match['id']
            existing[slug] = entry
            auto_matched += 1
            processed += 1
            if processed % 50 == 0:
                print(f"  {processed}/{len(albums)} done — {auto_matched} matched, {len(llm_pending)} pending LLM")
        elif score >= 0.65 and has_llm:
            # Medium confidence: queue for LLM validation
            llm_pending.append((slug, title, year, artist, match))
            processed += 1
        else:
            no_match += 1
            processed += 1

        # Flush LLM batch
        if len(llm_pending) >= BATCH_SIZE:
            print(f"  LLM batch of {len(llm_pending)}...", end='', flush=True)
            results = llm_validate_batch(llm_pending)
            llm_matched = 0
            for s, sp_id in results.items():
                if sp_id and sp_id != 'null':
                    entry = existing.get(s, {})
                    if not isinstance(entry, dict):
                        entry = {}
                    entry['spotify_id'] = sp_id
                    existing[s] = entry
                    llm_matched += 1
            print(f" {llm_matched}/{len(llm_pending)} confirmed")
            auto_matched += llm_matched
            llm_pending = []

        # Periodic save
        if not args.dry_run and processed % 100 == 0:
            save_yaml(OUT_ALBUMS, existing)

    # Flush remaining LLM batch
    if llm_pending:
        print(f"  LLM batch of {len(llm_pending)}...", end='', flush=True)
        results = llm_validate_batch(llm_pending)
        llm_matched = 0
        for s, sp_id in results.items():
            if sp_id and sp_id != 'null':
                entry = existing.get(s, {})
                if not isinstance(entry, dict):
                    entry = {}
                entry['spotify_id'] = sp_id
                existing[s] = entry
                llm_matched += 1
        print(f" {llm_matched}/{len(llm_pending)} confirmed")
        auto_matched += llm_matched

    if not args.dry_run:
        save_yaml(OUT_ALBUMS, existing)

    existing = load_yaml(OUT_ALBUMS)
    spotify_total = sum(1 for v in existing.values()
                        if isinstance(v, dict) and v.get('spotify_id'))

    print(f"\nResults:")
    print(f"  Albums processed: {processed}")
    print(f"  Matched: {auto_matched}")
    print(f"  No match found: {no_match}")
    print(f"  Total Spotify links now: {spotify_total}")


if __name__ == '__main__':
    main()
