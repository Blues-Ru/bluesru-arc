#!/usr/bin/env python3
"""
Find YouTube Music and YouTube video/playlist links for albums.

Phase 1 — YouTube Music (ytmusicapi, no auth):
  Search albums already on streaming platforms (Apple/Spotify/Deezer).
  Store MPREb_* browse IDs as ytmusic_id.

Phase 2 — YouTube bootlegs (yt-dlp, no auth):
  For albums with NO streaming links at all.
  Search for full-album videos or playlists.
  LLM validates matches using duration/title heuristics.
  Store youtube_video_id or youtube_playlist_id.

Usage:
  source ~/.bashrc
  python3 tools/streaming/find_youtube_links.py [--phase 1|2|both] [--artist SLUG] [--limit N] [--dry-run]

Run from anywhere — paths are repo-relative.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

ARC            = Path(__file__).resolve().parent.parent.parent
WORKSPACE      = ARC.parent
ALBUMS_DIR     = ARC / "data" / "albums"  # subdirs: {artist-slug}/*.yaml
ARTISTS_YAML   = ARC / "data" / "artists.yaml"
# NOTE: streaming IDs now per-album in ALBUMS_DIR/**/*.yaml (not flat streaming/albums.yaml)
# STREAMING_YAML → iterate ALBUMS_DIR.glob("**/*.yaml") instead.


def load_yaml(path):
    p = Path(path)
    return yaml.safe_load(p.read_text(encoding='utf-8')) or {} if p.exists() else {}

def save_yaml(path, data):
    Path(path).write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding='utf-8')


# ── YouTube Music (ytmusicapi) ─────────────────────────────────────────────────

_ytm = None

def get_ytm():
    global _ytm
    if _ytm is None:
        from ytmusicapi import YTMusic
        _ytm = YTMusic()  # anonymous, no auth
    return _ytm


def ytmusic_search_album(artist, title):
    """Return MPREb_* browse ID or None."""
    ytm = get_ytm()
    query = f"{artist} {title}"
    try:
        results = ytm.search(query, filter="albums", limit=5)
    except Exception as e:
        print(f"  YTMusic error: {e}", file=sys.stderr)
        return None

    title_lc = _norm(title)
    artist_lc = _norm(artist)

    for r in results:
        if r.get('resultType') != 'album':
            continue
        rtitle = _norm(r.get('title', ''))
        rartists = ' '.join(_norm(a.get('name', '')) for a in r.get('artists', []))
        browse_id = r.get('browseId', '')
        if not browse_id or not browse_id.startswith('MPREb_'):
            continue
        # Title must be close; artist can be partial match
        if _similarity(title_lc, rtitle) >= 0.80 and (
                artist_lc in rartists or rartists in artist_lc or
                _similarity(artist_lc, rartists) >= 0.70):
            return browse_id

    return None


# ── YouTube video/playlist search (yt-dlp) ────────────────────────────────────

def yt_search(query, max_results=8, search_type='video'):
    """
    Use yt-dlp to search YouTube. Returns list of result dicts.
    search_type: 'video' or 'playlist'
    """
    import subprocess, json as _json

    prefix = 'ytsearch' if search_type == 'video' else 'ytsearchall'
    search_query = f"ytsearch{max_results}:{query}" if search_type == 'video' else f"ytsearch{max_results}:playlist {query}"

    cmd = [
        'yt-dlp', '--flat-playlist', '--dump-json', '--no-warnings',
        '--quiet', search_query
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        items = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    items.append(_json.loads(line))
                except Exception:
                    pass
        return items
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        print(f"  yt-dlp error: {e}", file=sys.stderr)
        return []


def yt_search_playlist(query, max_results=5):
    """Search for playlists specifically."""
    import subprocess, json as _json
    cmd = [
        'yt-dlp', '--flat-playlist', '--dump-json', '--no-warnings',
        '--quiet', f"https://www.youtube.com/results?search_query={query}&sp=EgIQAw%253D%253D"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        items = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    d = _json.loads(line)
                    if d.get('_type') == 'playlist' or 'playlist' in d.get('url', '').lower():
                        items.append(d)
                except Exception:
                    pass
        return items[:max_results]
    except Exception as e:
        return []


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


def llm_validate_youtube(artist, title, year, candidates):
    """
    Ask LLM to pick best YouTube match from candidates.
    candidates: list of {id, type, title, duration_s, description, channel}
    Returns {video_id, playlist_id} or {} if no match.
    """
    claude = get_claude()
    if not claude or not candidates:
        return {}

    prompt = f"""Find the best YouTube match for this blues album:
Artist: {artist}
Album: {title}
Year: {year or 'unknown'}

YouTube candidates:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Rules for a VALID match:
- Video: duration must be > 1800 seconds (30 min) for a full album; title or description must mention the album/artist
- Playlist: must have 6+ tracks; title should mention artist or album; individual track durations 2-10 min
- Reject: live concerts of different albums, compilation mixes, unrelated content
- Prefer official/legitimate over bootlegs, but accept bootlegs if no official exists
- If no candidate is a confident match, return empty

Return ONLY JSON (no explanation):
{{"video_id": "..." or null, "playlist_id": "..." or null}}"""

    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}])
        text = resp.content[0].text.strip()
        text = re.sub(r'^```[a-z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        result = json.loads(text)
        return {k: v for k, v in result.items() if v and v != 'null'}
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
        return {}


def build_video_candidates(artist, title, year):
    """Search YouTube for full-album videos and playlists, return candidate list."""
    candidates = []
    queries = [
        f"{artist} {title} full album",
        f"{artist} {title}",
    ]
    seen_ids = set()

    for q in queries:
        # Videos
        for item in yt_search(q, max_results=6, search_type='video'):
            vid_id = item.get('id') or item.get('url', '').split('v=')[-1].split('&')[0]
            if not vid_id or vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            duration = item.get('duration') or 0
            if isinstance(duration, str):
                # Convert HH:MM:SS or MM:SS to seconds
                parts = [int(x) for x in duration.split(':')]
                duration = sum(p * 60**i for i, p in enumerate(reversed(parts)))
            candidates.append({
                'id': vid_id,
                'type': 'video',
                'title': item.get('title', ''),
                'duration_s': duration,
                'channel': item.get('channel') or item.get('uploader', ''),
                'description': (item.get('description') or '')[:200],
            })
        time.sleep(0.5)

        # Playlists
        for item in yt_search(q + ' playlist', max_results=3, search_type='video'):
            url = item.get('url', '') or item.get('webpage_url', '')
            if 'list=' not in url:
                continue
            pl_id = re.search(r'list=([A-Za-z0-9_-]+)', url)
            if not pl_id:
                continue
            pl_id = pl_id.group(1)
            if pl_id in seen_ids:
                continue
            seen_ids.add(pl_id)
            candidates.append({
                'id': pl_id,
                'type': 'playlist',
                'title': item.get('title', ''),
                'duration_s': 0,
                'channel': item.get('channel') or item.get('uploader', ''),
                'description': '',
            })
        time.sleep(0.5)

    # Filter: only videos > 20 min are worth considering
    filtered = [c for c in candidates if c['type'] == 'playlist' or c['duration_s'] > 1200]
    return filtered[:10]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _norm(t):
    return re.sub(r'[^\w\s]', ' ', (t or '').lower()).strip()

def _similarity(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_albums_by_artist():
    artists_data = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8')) or []
    id_to_artist = {str(a.get('id', '')): a for a in artists_data}
    by_artist = {}
    for fpath in sorted(ALBUMS_DIR.glob('*.yaml')):
        alb = yaml.safe_load(fpath.read_text(encoding='utf-8')) or {}
        artist = id_to_artist.get(str(alb.get('artist_id', '')))
        if not artist:
            continue
        slug = alb.get('slug', '')
        title = alb.get('title', '')
        if not slug or not title:
            continue
        artist_slug = artist.get('slug', '')
        by_artist.setdefault(artist_slug, []).append({
            'slug': slug,
            'title': title,
            'year': alb.get('year', ''),
            'artist_name': artist.get('name', ''),
        })
    return by_artist


# ── Phase 1: YouTube Music ─────────────────────────────────────────────────────

def run_phase1(albums_by_artist, streaming, filter_artist=None, limit=None, dry_run=False):
    """Find YouTube Music IDs for albums already on other platforms."""
    print("Phase 1: YouTube Music search")
    updated = 0

    for artist_slug, albums in albums_by_artist.items():
        if filter_artist and artist_slug != filter_artist:
            continue
        if limit and updated >= limit:
            break

        for alb in albums:
            slug = alb['slug']
            info = streaming.get(slug, {})
            # Only process albums that have other streaming links
            if not (info.get('apple_music_id') or info.get('spotify_id') or info.get('deezer_id')):
                continue
            # Skip if already have YT Music
            if info.get('ytmusic_id'):
                continue

            ytm_id = ytmusic_search_album(alb['artist_name'], alb['title'])
            if ytm_id:
                if not isinstance(info, dict):
                    info = {}
                info['ytmusic_id'] = ytm_id
                streaming[slug] = info
                updated += 1
                print(f"  ✓ {alb['artist_name']} — {alb['title']}: {ytm_id}")
                if not dry_run and updated % 50 == 0:
                    save_yaml(STREAMING_YAML, streaming)
            time.sleep(0.3)

    if not dry_run:
        save_yaml(STREAMING_YAML, streaming)
    print(f"Phase 1 done: {updated} YouTube Music IDs found")
    return updated


# ── Phase 2: YouTube bootleg videos ───────────────────────────────────────────

def run_phase2(albums_by_artist, streaming, filter_artist=None, limit=None, dry_run=False):
    """Find YouTube video/playlist for albums with NO streaming links."""
    print("Phase 2: YouTube bootleg search")
    updated = 0

    for artist_slug, albums in albums_by_artist.items():
        if filter_artist and artist_slug != filter_artist:
            continue
        if limit and updated >= limit:
            break

        for alb in albums:
            slug = alb['slug']
            info = streaming.get(slug, {})
            # Only process albums with NO streaming links at all
            has_streaming = any(info.get(k) for k in
                ('apple_music_id', 'spotify_id', 'deezer_id', 'ytmusic_id'))
            if has_streaming:
                continue
            # Skip if already tried YouTube
            if info.get('youtube_video_id') or info.get('youtube_playlist_id'):
                continue

            print(f"  Searching: {alb['artist_name']} — {alb['title']} ({alb['year']})", end='', flush=True)
            candidates = build_video_candidates(alb['artist_name'], alb['title'], alb['year'])

            if not candidates:
                print(" → no candidates")
                streaming[slug] = info or {}
                continue

            print(f" → {len(candidates)} candidates", end='', flush=True)
            match = llm_validate_youtube(alb['artist_name'], alb['title'], alb['year'], candidates)

            if match:
                if not isinstance(info, dict):
                    info = {}
                if match.get('video_id'):
                    info['youtube_video_id'] = match['video_id']
                if match.get('playlist_id'):
                    info['youtube_playlist_id'] = match['playlist_id']
                streaming[slug] = info
                updated += 1
                print(f" → matched: {match}")
            else:
                print(" → no match")
                streaming[slug] = info or {}

            if not dry_run and updated % 20 == 0:
                save_yaml(STREAMING_YAML, streaming)
            time.sleep(0.5)

    if not dry_run:
        save_yaml(STREAMING_YAML, streaming)
    print(f"Phase 2 done: {updated} YouTube links found")
    return updated


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['1', '2', 'both'], default='both')
    parser.add_argument('--artist', help='Process only this artist slug')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    has_llm = bool(os.environ.get('ANTHROPIC_API_KEY'))
    print(f"YouTube Music: ✓ (anonymous)  LLM: {'✓' if has_llm else '✗'}")
    if not has_llm:
        print("  WARNING: Phase 2 requires ANTHROPIC_API_KEY for validation")
    print()

    streaming = load_yaml(STREAMING_YAML)
    albums_by_artist = load_albums_by_artist()

    if args.phase in ('1', 'both'):
        run_phase1(albums_by_artist, streaming, args.artist, args.limit, args.dry_run)
    if args.phase in ('2', 'both'):
        run_phase2(albums_by_artist, streaming, args.artist, args.limit, args.dry_run)

    # Stats
    streaming = load_yaml(STREAMING_YAML)
    ytm  = sum(1 for v in streaming.values() if isinstance(v, dict) and v.get('ytmusic_id'))
    ytv  = sum(1 for v in streaming.values() if isinstance(v, dict) and v.get('youtube_video_id'))
    ytp  = sum(1 for v in streaming.values() if isinstance(v, dict) and v.get('youtube_playlist_id'))
    print(f"\nYouTube Music IDs: {ytm}")
    print(f"YouTube video:     {ytv}")
    print(f"YouTube playlist:  {ytp}")


if __name__ == '__main__':
    main()
