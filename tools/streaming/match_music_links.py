#!/usr/bin/env python3
"""
Match blues.ru albums to streaming platforms using artist catalog lookup + LLM.

Platforms: Spotify, Apple Music, Deezer (free, no auth)

Strategy per artist:
  1. Find ALL related artist IDs on each platform (handles name variants)
  2. Fetch full album catalogs for all related IDs
  3. LLM matches our albums against all platform catalogs in one call
  4. For albums still unmatched: LLM generates search queries → search → LLM picks
  5. Fallback to fuzzy matching when no ANTHROPIC_API_KEY

Output: data/albums/{artist-slug}/*.yaml (per-album streaming IDs)
  slug:
    spotify_id, spotify_url
    apple_music_id, apple_music_url
    deezer_id, deezer_url

Usage:
  source ~/.bashrc
  python3 tools/streaming/match_music_links.py [--artist SLUG] [--limit N] [--dry-run]
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

ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
ALBUMS_DIR = ARC / "data" / "albums"  # subdirs: {artist-slug}/*.yaml
ARTISTS_YAML = ARC / "data" / "artists.yaml"
# NOTE: IDs now stored per-album in ALBUMS_DIR/**/*.yaml (not flat streaming/albums.yaml)
# OUT_ALBUMS / OUT_ARTISTS → write back to individual YAML files; logic needs updating.

_SSL = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

SPOTIFY_ALBUM_URL = "https://open.spotify.com/album/{id}"
APPLE_ALBUM_URL   = "https://music.apple.com/us/album/{id}"
DEEZER_ALBUM_URL  = "https://www.deezer.com/album/{id}"


# ── HTTP ───────────────────────────────────────────────────────────────────────

def http_get(url, headers=None, retries=3):
    req = urllib.request.Request(url, headers=headers or {})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 5 * (attempt + 1)
                print(f"  [429 rate limit, sleeping {wait}s]", file=sys.stderr)
                time.sleep(wait)
            else:
                return None
        except Exception as e:
            print(f"  HTTP error: {e}", file=sys.stderr)
            return None
    return None


def load_yaml(path):
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding='utf-8')) or {} if p.exists() else {}

def save_yaml(path, data):
    Path(path).write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding='utf-8')


# ── Spotify ────────────────────────────────────────────────────────────────────

_spotify_token = None

def spotify_auth():
    global _spotify_token
    if not _spotify_token:
        cid = os.environ.get('SPOTIFY_CLIENT_ID', '')
        csc = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
        if not cid or not csc:
            return None
        creds = base64.b64encode(f'{cid}:{csc}'.encode()).decode()
        data = urllib.parse.urlencode({'grant_type': 'client_credentials'}).encode()
        req = urllib.request.Request(
            'https://accounts.spotify.com/api/token', data=data,
            headers={'Authorization': f'Basic {creds}',
                     'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req, timeout=10, context=_SSL) as r:
                _spotify_token = json.loads(r.read())['access_token']
        except Exception as e:
            print(f"  Spotify auth failed: {e}", file=sys.stderr)
            return None
    return {'Authorization': f'Bearer {_spotify_token}'}


def spotify_find_artist_ids(name):
    """Return [(id, display_name)] for all Spotify artists matching name."""
    auth = spotify_auth()
    if not auth:
        return []
    params = urllib.parse.urlencode({'q': name, 'type': 'artist', 'limit': 10})
    data = http_get(f"https://api.spotify.com/v1/search?{params}", auth)
    if not data:
        return []
    name_lc = name.lower()
    return [
        (a['id'], a['name'])
        for a in data.get('artists', {}).get('items', [])
        if name_lc in a['name'].lower() or a['name'].lower() in name_lc
    ]


def spotify_get_catalog(artist_id):
    auth = spotify_auth()
    if not auth:
        return []
    items, url = [], f"https://api.spotify.com/v1/artists/{artist_id}/albums?limit=10"
    while url:
        r = http_get(url, auth)
        if not r:
            break
        items.extend(r.get('items', []))
        url = r.get('next')
        if url:
            time.sleep(0.5)  # Spotify is aggressive with rate limits
    return [
        {'id': a['id'],
         'name': a['name'],
         'year': a.get('release_date', '')[:4],
         'url': SPOTIFY_ALBUM_URL.format(id=a['id']),
         'artists': [ar['name'] for ar in a.get('artists', [])]}
        for a in items
        if a.get('album_type') in ('album', 'compilation')
    ]


def spotify_search_album(query, limit=10):
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
         'url': SPOTIFY_ALBUM_URL.format(id=a['id']),
         'artists': [ar['name'] for ar in a.get('artists', [])]}
        for a in data.get('albums', {}).get('items', [])
    ]


# ── Apple Music ────────────────────────────────────────────────────────────────

def apple_find_artist_ids(name):
    params = urllib.parse.urlencode(
        {'term': name, 'entity': 'musicArtist', 'country': 'us', 'limit': 10})
    data = http_get(f"https://itunes.apple.com/search?{params}")
    if not data:
        return []
    name_lc = name.lower()
    return [
        (str(r['artistId']), r['artistName'])
        for r in data.get('results', [])
        if name_lc in r.get('artistName', '').lower()
           or r.get('artistName', '').lower() in name_lc
    ]


def apple_get_catalog(artist_id):
    data = http_get(
        f"https://itunes.apple.com/lookup?id={artist_id}&entity=album&limit=200")
    if not data:
        return []
    return [
        {'id': str(r['collectionId']),
         'name': r.get('collectionName', ''),
         'year': str(r.get('releaseDate', ''))[:4],
         'url': re.sub(r'\?.*', '', r.get('collectionViewUrl', '')),
         'artists': [r.get('artistName', '')]}
        for r in data.get('results', [])
        if r.get('wrapperType') == 'collection'
    ]


def apple_search_album(query, limit=10):
    params = urllib.parse.urlencode(
        {'term': query, 'entity': 'album', 'country': 'us', 'limit': limit})
    data = http_get(f"https://itunes.apple.com/search?{params}")
    if not data:
        return []
    return [
        {'id': str(r['collectionId']),
         'name': r.get('collectionName', ''),
         'year': str(r.get('releaseDate', ''))[:4],
         'url': re.sub(r'\?.*', '', r.get('collectionViewUrl', '')),
         'artists': [r.get('artistName', '')]}
        for r in data.get('results', [])
    ]


# ── Deezer (free, no auth) ─────────────────────────────────────────────────────

def deezer_find_artist_ids(name):
    params = urllib.parse.urlencode({'q': name, 'limit': 10})
    data = http_get(f"https://api.deezer.com/search/artist?{params}")
    if not data:
        return []
    name_lc = name.lower()
    return [
        (str(a['id']), a['name'])
        for a in data.get('data', [])
        if name_lc in a['name'].lower() or a['name'].lower() in name_lc
    ]


def deezer_get_catalog(artist_id):
    data = http_get(f"https://api.deezer.com/artist/{artist_id}/albums?limit=100")
    if not data:
        return []
    return [
        {'id': str(a['id']),
         'name': a['title'],
         'year': a.get('release_date', '')[:4],
         'url': DEEZER_ALBUM_URL.format(id=a['id']),
         'artists': []}
        for a in data.get('data', [])
        if a.get('record_type') in ('album', 'live', 'compilation', 'ep')
    ]


def deezer_search_album(query, limit=10):
    params = urllib.parse.urlencode({'q': query, 'limit': limit})
    data = http_get(f"https://api.deezer.com/search/album?{params}")
    if not data:
        return []
    return [
        {'id': str(a['id']),
         'name': a['title'],
         'year': '',
         'url': DEEZER_ALBUM_URL.format(id=a['id']),
         'artists': [a.get('artist', {}).get('name', '')]}
        for a in data.get('data', [])
    ]


# ── Catalog helpers ────────────────────────────────────────────────────────────

def collect_catalog(find_fn, catalog_fn, name):
    """Find all artist IDs for name, return deduplicated combined catalog."""
    artist_ids = find_fn(name)
    all_items = []
    for aid, aname in artist_ids:
        cat = catalog_fn(aid)
        all_items.extend(cat)
        time.sleep(0.2)
    # Deduplicate by (name_lower, year)
    seen, deduped = set(), []
    for a in all_items:
        key = (a['name'].lower(), a['year'])
        if key not in seen:
            seen.add(key)
            deduped.append(a)
    return deduped


# ── Fuzzy matching (fallback) ──────────────────────────────────────────────────

_EDITION_STRIP = re.compile(
    r'\s*[\(\[]?(?:remaster(?:ed)?(?:\s+\d{4})?|deluxe(?:\s+edition)?|'
    r'anniversary(?:\s+edition)?|expanded|bonus\s+tracks?|'
    r'\d{4}\s+remaster|special\s+edition)\s*[\)\]]?\s*$',
    re.IGNORECASE)

def _norm(t):
    t = _EDITION_STRIP.sub('', t).lower()
    t = re.sub(r'[^\w\s]', ' ', t)
    return ' '.join(t.split())

def fuzzy_match(our_albums, catalog, threshold=0.82):
    """Return dict slug→{id,url} for matches above threshold."""
    matches = {}
    norms = [(_norm(c['name']), c) for c in catalog]
    for alb in our_albums:
        our = _norm(alb['title'])
        best_score, best = max(
            ((difflib.SequenceMatcher(None, our, cn).ratio(), c) for cn, c in norms),
            key=lambda x: x[0], default=(0, None))
        if best_score >= threshold and best:
            matches[alb['slug']] = {'id': best['id'], 'url': best['url']}
    return matches


# ── LLM matching ───────────────────────────────────────────────────────────────

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


def llm_call(prompt):
    claude = get_claude()
    if not claude:
        return None
    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}])
        text = resp.content[0].text.strip()
        # Strip markdown fences
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        # Extract just the JSON array (handles trailing prose after the array)
        m = re.search(r'(\[.*\])', text, re.DOTALL)
        if m:
            text = m.group(1)
        return json.loads(text)
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
        return None


def llm_match_catalogs(our_albums, spotify_cat, apple_cat, deezer_cat):
    """
    Match our_albums against all 3 platform catalogs in one LLM call.
    Returns list of {slug, spotify, apple_music, deezer} dicts.
    """
    if not our_albums:
        return []
    if not spotify_cat and not apple_cat and not deezer_cat:
        return []

    catalogs = {}
    if spotify_cat:
        catalogs['spotify'] = spotify_cat
    if apple_cat:
        catalogs['apple_music'] = apple_cat
    if deezer_cat:
        catalogs['deezer'] = deezer_cat

    prompt = f"""Match each album in "our_albums" to entries in streaming catalogs.

our_albums:
{json.dumps(our_albums, ensure_ascii=False)}

catalogs:
{json.dumps(catalogs, ensure_ascii=False)}

Rules:
- Match album title (ignore "Remastered", "Deluxe Edition", "Live", edition/year suffixes)
- UK/US spelling variants count as match ("Colour"="Color")
- Match independently per platform — an album may exist on some but not others
- Set id to null if no confident match exists for that platform
- Do not guess on partial/ambiguous matches

Return ONLY a JSON array:
[{{"slug":"...","spotify":{{"id":"...|null","url":"...|null"}},"apple_music":{{"id":"...|null","url":"...|null"}},"deezer":{{"id":"...|null","url":"...|null"}}}}]"""

    return llm_call(prompt) or []


def llm_generate_queries(artist_name, unmatched_albums):
    """
    For albums not found via artist catalog, generate search queries.
    Returns list of {slug, queries} where queries is list of strings.
    """
    prompt = f"""Generate search queries to find these albums on music streaming platforms.
Artist: {artist_name}

Albums (slug, title, year):
{json.dumps(unmatched_albums, ensure_ascii=False)}

For each album generate 2-3 short search queries that maximize chance of finding it.
Rules:
- Drop "The", "A" when not essential
- Drop subtitles after " - " or ": " if title is still recognizable
- Include artist name
- Try a version with just artist + key title words
- For live albums, try with and without "Live"

Return ONLY JSON: [{{"slug":"...","queries":["query1","query2"]}}]"""

    return llm_call(prompt) or []


def llm_pick_matches(our_albums, search_results):
    """
    Given our albums and search results from all platforms, pick best match.
    search_results: {slug: {spotify: [...], apple_music: [...], deezer: [...]}}
    """
    prompt = f"""Pick the best streaming match for each album from search results.

our_albums:
{json.dumps(our_albums, ensure_ascii=False)}

search_results:
{json.dumps(search_results, ensure_ascii=False)}

Rules:
- Artist name must match (same person, allow "& The Broadcasters" variants)
- Title must match (ignore edition/remaster suffixes, spelling variants)
- Return null if no result is a confident match

Return ONLY JSON:
[{{"slug":"...","spotify":{{"id":"...|null","url":"...|null"}},"apple_music":{{"id":"...|null","url":"...|null"}},"deezer":{{"id":"...|null","url":"...|null"}}}}]"""

    return llm_call(prompt) or []


# ── Apply LLM results ──────────────────────────────────────────────────────────

def apply_llm_results(llm_results, existing):
    """Write LLM match results into existing dict. Returns count of new matches."""
    count = 0
    for item in llm_results:
        slug = item.get('slug', '')
        if not slug:
            continue
        entry = existing.get(slug, {})
        for platform, key_id, key_url in [
            ('spotify',     'spotify_id',      'spotify_url'),
            ('apple_music', 'apple_music_id',  'apple_music_url'),
            ('deezer',      'deezer_id',        'deezer_url'),
        ]:
            m = item.get(platform, {}) or {}
            mid = m.get('id') if m else None
            murl = m.get('url') if m else None
            if mid and mid != 'null':
                if not entry.get(key_id):  # don't overwrite existing good match
                    entry[key_id] = mid
                    entry[key_url] = murl or ''
                    count += 1
        existing[slug] = entry
    return count


# ── Process one artist ─────────────────────────────────────────────────────────

def process_artist(artist, albums_by_artist, existing, dry_run=False):
    slug = artist.get('slug', '')
    name = artist.get('name', '')

    our_albums = albums_by_artist.get(slug, [])
    if not our_albums:
        return 0

    # Skip albums already fully attempted (has any key or explicit empty)
    unmatched = [a for a in our_albums if a['slug'] not in existing]
    if not unmatched:
        return 0

    print(f"  {name}: {len(unmatched)} albums", end='', flush=True)

    # ── Collect catalogs (Apple Music + Deezer via artist catalog; Spotify via search only) ──
    apple_cat    = collect_catalog(apple_find_artist_ids,    apple_get_catalog,    name)
    deezer_cat   = collect_catalog(deezer_find_artist_ids,   deezer_get_catalog,   name)
    spotify_cat  = []  # Spotify used only in Phase 2 search fallback (avoids heavy rate limiting)

    # Use stored Apple Music ID if we have it (may find more variants)
    stored_artists = load_yaml(OUT_ARTISTS)
    stored_apple_id = stored_artists.get(slug, {}).get('apple_music_id')
    if stored_apple_id:
        extra = apple_get_catalog(stored_apple_id)
        seen = {a['id'] for a in apple_cat}
        apple_cat.extend(a for a in extra if a['id'] not in seen)

    # Cap catalog size to avoid LLM token overflow (large artists like B.B. King, Muddy Waters)
    MAX_CAT = 80
    spotify_cat = spotify_cat[:MAX_CAT]
    apple_cat   = apple_cat[:MAX_CAT]
    deezer_cat  = deezer_cat[:MAX_CAT]

    print(f" [SP:{len(spotify_cat)} AM:{len(apple_cat)} DZ:{len(deezer_cat)}]", end='', flush=True)

    matched = 0
    our_input = [{'slug': a['slug'], 'title': a['title'], 'year': str(a.get('year', ''))}
                 for a in unmatched]

    # ── Phase 1: LLM catalog match (Apple Music + Deezer; Spotify via search only) ──
    if get_claude() and (apple_cat or deezer_cat):
        results = llm_match_catalogs(our_input, [], apple_cat, deezer_cat)
        matched += apply_llm_results(results, existing)
        # Mark all as attempted even if no match found
        for a in unmatched:
            if a['slug'] not in existing:
                existing[a['slug']] = {}
    elif spotify_cat or apple_cat or deezer_cat:
        # Fuzzy fallback (no API key)
        for cat, key_id, key_url in [
            (spotify_cat, 'spotify_id', 'spotify_url'),
            (apple_cat,   'apple_music_id', 'apple_music_url'),
            (deezer_cat,  'deezer_id', 'deezer_url'),
        ]:
            if not cat:
                continue
            fm = fuzzy_match(unmatched, cat)
            for alb_slug, m in fm.items():
                entry = existing.get(alb_slug, {})
                if not entry.get(key_id):
                    entry[key_id] = m['id']
                    entry[key_url] = m['url']
                    matched += 1
                existing[alb_slug] = entry
        for a in unmatched:
            if a['slug'] not in existing:
                existing[a['slug']] = {}

    # ── Phase 2: Search fallback for still-unmatched albums ───────────────────
    still_unmatched = [a for a in unmatched
                       if not any(existing.get(a['slug'], {}).get(k)
                                  for k in ('spotify_id', 'apple_music_id', 'deezer_id'))]

    if still_unmatched and get_claude():
        queries_list = llm_generate_queries(
            name,
            [{'slug': a['slug'], 'title': a['title'], 'year': str(a.get('year', ''))}
             for a in still_unmatched]
        )
        if queries_list:
            search_results = {}
            for item in queries_list:
                alb_slug = item.get('slug', '')
                queries = item.get('queries', [])[:2]
                sr = {'spotify': [], 'apple_music': [], 'deezer': []}
                for q in queries:
                    sr['apple_music'].extend(apple_search_album(q, 8))
                    sr['deezer']     .extend(deezer_search_album(q, 8))
                    sp_res = spotify_search_album(q, 5)
                    if sp_res:
                        sr['spotify'].extend(sp_res)
                    time.sleep(0.3)
                search_results[alb_slug] = sr

            if search_results:
                pick_results = llm_pick_matches(
                    [{'slug': a['slug'], 'title': a['title'],
                      'artist': name, 'year': str(a.get('year', ''))}
                     for a in still_unmatched],
                    search_results
                )
                matched += apply_llm_results(pick_results, existing)

    print(f" → {matched}/{len(unmatched)}")

    if not dry_run:
        save_yaml(OUT_ALBUMS, existing)

    return matched


# ── Data loading ───────────────────────────────────────────────────────────────

def load_albums_by_artist():
    artists_data = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8')) or []
    id_to_slug = {str(a.get('id', '')): a.get('slug', '') for a in artists_data}
    by_artist = {}
    for fpath in sorted(ALBUMS_DIR.glob('*.yaml')):
        alb = yaml.safe_load(fpath.read_text(encoding='utf-8')) or {}
        artist_slug = id_to_slug.get(str(alb.get('artist_id', '')), '')
        if not artist_slug:
            continue
        s, t = alb.get('slug', ''), alb.get('title', '')
        if s and t:
            by_artist.setdefault(artist_slug, []).append(
                {'slug': s, 'title': t, 'year': alb.get('year', '')})
    return by_artist


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artist', help='Process only this artist slug')
    parser.add_argument('--limit', type=int, help='Max artists to process')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    has_llm = bool(os.environ.get('ANTHROPIC_API_KEY'))
    has_sp  = bool(os.environ.get('SPOTIFY_CLIENT_ID'))
    print(f"Spotify: {'✓' if has_sp else '✗'}  Apple Music: ✓  Deezer: ✓  LLM: {'✓' if has_llm else '✗ (set ANTHROPIC_API_KEY)'}")
    print()

    artists_data  = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8')) or []
    albums_by_artist = load_albums_by_artist()
    existing = load_yaml(OUT_ALBUMS)

    total_matched, processed = 0, 0
    for artist in artists_data:
        if args.artist and artist.get('slug') != args.artist:
            continue
        if args.limit and processed >= args.limit:
            break
        slug = artist.get('slug', '')
        if not slug or slug not in albums_by_artist:
            continue
        total_matched += process_artist(artist, albums_by_artist, existing, args.dry_run)
        processed += 1
        time.sleep(0.1)

    if not args.dry_run:
        save_yaml(OUT_ALBUMS, existing)

    total_with_link = sum(
        1 for v in existing.values()
        if v.get('spotify_id') or v.get('apple_music_id') or v.get('deezer_id'))
    print(f"\nDone. {total_matched} new matches this run, {total_with_link} total with links")


if __name__ == '__main__':
    main()
