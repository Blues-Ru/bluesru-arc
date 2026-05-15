#!/usr/bin/env python3
"""
Fetch Discogs artist and master-release IDs and store in data/artists.yaml
and data/albums/{artist-slug}/*.yaml.

Discogs API docs: https://www.discogs.com/developers/
Rate limits: 25 req/min unauthenticated; 60 req/min with personal access token.
Get a personal access token at https://www.discogs.com/settings/developers

LLM validation uses Claude (claude-sonnet-4-6) via ANTHROPIC_API_KEY for
ambiguous matches. Without the key, only high-confidence auto-matches are kept.

Scoring tiers:
  >= AUTO_ACCEPT  → write immediately
  >= LLM_THRESHOLD → queue for Claude validation (batches of 20)
  < LLM_THRESHOLD → discard

Usage:
    # Artists only
    DISCOGS_TOKEN=xxx ANTHROPIC_API_KEY=yyy \\
        python3 tools/streaming/fetch_discogs_ids.py --artists

    # Albums only (one artist for testing)
    DISCOGS_TOKEN=xxx ANTHROPIC_API_KEY=yyy \\
        python3 tools/streaming/fetch_discogs_ids.py --albums --artist albert-collins

    # Both (full run)
    DISCOGS_TOKEN=xxx ANTHROPIC_API_KEY=yyy \\
        python3 tools/streaming/fetch_discogs_ids.py --artists --albums

    # Dry-run (no API calls)
    python3 tools/streaming/fetch_discogs_ids.py --artists --albums --dry-run

Run from anywhere — paths are repo-relative.
"""

from __future__ import annotations

import argparse
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

ARC          = Path(__file__).resolve().parent.parent.parent
ARTISTS_YAML = ARC / "data" / "artists.yaml"
ALBUMS_DIR   = ARC / "data" / "albums"

DISCOGS_API  = "https://api.discogs.com"
USER_AGENT   = "BluesRuArchive/1.0 (https://blues.ru)"
CLAUDE_MODEL = "claude-sonnet-4-6"

# Scoring thresholds
AUTO_ACCEPT_ARTIST  = 0.90   # accept without LLM
LLM_THRESHOLD_ARTIST = 0.65  # below this: discard
AUTO_ACCEPT_ALBUM   = 0.82
LLM_THRESHOLD_ALBUM  = 0.52

LLM_BATCH = 20  # items per Claude call

# Delay between Discogs requests (60/min with token, 25/min without)
_DELAY_AUTH   = 1.2
_DELAY_NOAUTH = 2.6


# ── HTTP ───────────────────────────────────────────────────────────────────────

_SSL = ssl.create_default_context()
try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass


def _http_get(url: str, token: str | None, retries: int = 4) -> dict | None:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Discogs token={token}"
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After", "10"))
                print(f"    Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            if e.code == 404:
                return None
            print(f"    HTTP {e.code} for {url}")
            return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(3)
                continue
            print(f"    Error fetching {url}: {e}")
            return None
    return None


def _search(query_params: dict, token: str | None) -> list[dict]:
    qs = urllib.parse.urlencode(query_params)
    data = _http_get(f"{DISCOGS_API}/database/search?{qs}", token)
    return (data or {}).get("results", [])


# ── Name matching helpers ──────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


# Strip "(2000 Remaster)", "(Deluxe Edition)", etc. from titles before scoring
_EDITION_STRIP = re.compile(
    r'\s*[\(\[]?(?:remaster(?:ed)?(?:\s+\d{4})?|\d{4}\s+remaster(?:ed)?|'
    r'deluxe(?:\s+edition)?|anniversary(?:\s+edition)?|expanded|'
    r'bonus\s+tracks?|special\s+edition)\s*[\)\]]?\s*$',
    re.IGNORECASE,
)


def _title_norm(t: str) -> str:
    t = _EDITION_STRIP.sub("", t or "")
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return " ".join(t.split())


def _title_sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _title_norm(a), _title_norm(b)).ratio()


# Strip band-suffix variants so "Vidar Busk" matches "Vidar Busk & His True Believers"
_BAND_STRIP = re.compile(
    r'\s*[&,]\s*(his|her|the|and)\b.*$'
    r'|\s+and\s+(his|her|the)\b.*$'
    r'|\s+with\s+.*$'
    r'|\s+feat\..*$'
    r'|\s+ft\..*$',
    re.IGNORECASE,
)


def _artist_base(name: str) -> str:
    return _BAND_STRIP.sub("", name).strip()


def _artist_sim(our: str, theirs: str) -> float:
    """Compare artist names with awareness of band-suffix variants."""
    full = _similarity(our, theirs)
    if full >= 0.90:
        return full

    our_base   = _artist_base(our)
    their_base = _artist_base(theirs)
    base_score = max(
        _similarity(our_base, their_base),
        _similarity(our_base, theirs),
        _similarity(our,      their_base),
    )

    # Prefix check: "Vidar Busk" is a prefix of "Vidar Busk & His True Believers"
    our_n   = _normalize(our_base)
    their_n = _normalize(theirs)
    if their_n.startswith(our_n) and len(our_n) >= 4:
        base_score = max(base_score, 0.90)
    if our_n.startswith(_normalize(their_base)) and len(_normalize(their_base)) >= 4:
        base_score = max(base_score, 0.90)

    return max(full, base_score)


# ── LLM validation ────────────────────────────────────────────────────────────

_claude = None


def _get_claude():
    global _claude
    if _claude is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return None
        try:
            import anthropic
            _claude = anthropic.Anthropic(api_key=key)
        except ImportError:
            print("  anthropic package not installed — LLM validation disabled")
    return _claude


def _llm_validate_artists(batch: list[dict]) -> dict[str, str | None]:
    """
    Validate a batch of artist candidates.
    batch items: {slug, our_name, discogs_title, discogs_id}
    Returns: {slug: discogs_id or None}
    """
    claude = _get_claude()
    if not claude:
        return {}

    prompt = (
        "For each entry decide whether the Discogs artist is the same real-world artist.\n"
        "Consider: slight name variations (with/without band suffix, 'The', apostrophes) are OK.\n"
        "Completely different artists are NOT OK.\n\n"
        f"{json.dumps(batch, ensure_ascii=False, indent=2)}\n\n"
        'Return ONLY a JSON object mapping slug → discogs_id (string) or null:\n'
        '{"slug1": "id_or_null", ...}'
    )
    try:
        resp = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        m = re.search(r"(\{.*\})", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
    return {}


def _llm_validate_albums(batch: list[dict]) -> dict[str, str | None]:
    """
    Validate a batch of album master candidates.
    batch items: {path, artist, our_title, our_year, discogs_title, discogs_year, discogs_id}
    Returns: {path: discogs_master_id or None}
    """
    claude = _get_claude()
    if not claude:
        return {}

    prompt = (
        "For each entry decide whether the Discogs master release is the same album.\n"
        "Rules:\n"
        "- Remastered/deluxe/expanded editions of the same album COUNT as a match.\n"
        "- Live albums, compilations, or covers do NOT match studio originals.\n"
        "- Year off by 1–2 is OK (licensing/regional release dates).\n"
        "- Artist name variants (with/without band suffix) are OK.\n\n"
        f"{json.dumps(batch, ensure_ascii=False, indent=2)}\n\n"
        'Return ONLY a JSON object mapping path → discogs_master_id (string) or null:\n'
        '{"path1": "id_or_null", ...}'
    )
    try:
        resp = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        m = re.search(r"(\{.*\})", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
    except Exception as e:
        print(f"  LLM error: {e}", file=sys.stderr)
    return {}


def _flush_artist_batch(batch: list[dict], slug_to_artist: dict,
                        counters: dict) -> None:
    if not batch:
        return
    print(f"  LLM validating {len(batch)} artists...", end="", flush=True)
    results = _llm_validate_artists(batch)
    confirmed = 0
    for item in batch:
        slug = item["slug"]
        disc_id = results.get(slug)
        if disc_id and disc_id != "null":
            slug_to_artist[slug]["discogs_id"] = str(disc_id)
            counters["updated"] += 1
            confirmed += 1
        else:
            counters["not_found"] += 1
    print(f" {confirmed}/{len(batch)} confirmed")
    batch.clear()


def _flush_album_batch(batch: list[dict], counters: dict) -> None:
    if not batch:
        return
    print(f"  LLM validating {len(batch)} albums...", end="", flush=True)
    results = _llm_validate_albums(batch)
    confirmed = 0
    for item in batch:
        path_str = item["path"]
        master_id = results.get(path_str)
        if master_id and master_id != "null":
            path = Path(path_str)
            data = _load_yaml(path)
            if isinstance(data, dict):
                data["discogs_master_id"] = str(master_id)
                _save_yaml(path, data)
                counters["updated"] += 1
                confirmed += 1
        else:
            counters["not_found"] += 1
    print(f" {confirmed}/{len(batch)} confirmed")
    batch.clear()


# ── Artist search ──────────────────────────────────────────────────────────────

def _score_artists(name: str, results: list[dict]) -> list[tuple[float, dict]]:
    scored = [(  _artist_sim(name, r.get("title", "")), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def search_artist_candidates(name: str,
                              token: str | None) -> list[tuple[float, dict]]:
    results = _search({"q": name, "type": "artist", "per_page": "8"}, token)
    return _score_artists(name, results)


# ── Album (master release) search ─────────────────────────────────────────────

def _score_masters(artist: str, title: str, year: int | None,
                   results: list[dict]) -> list[tuple[float, dict]]:
    scored: list[tuple[float, dict]] = []
    for r in results:
        r_title_raw = r.get("title", "")
        if " - " in r_title_raw:
            r_artist, r_title = r_title_raw.split(" - ", 1)
        else:
            r_artist, r_title = "", r_title_raw

        a_sim = _artist_sim(artist, r_artist)
        t_sim = _title_sim(title, r_title)
        score = a_sim * 0.35 + t_sim * 0.65

        if year:
            r_year = r.get("year")
            if r_year:
                diff = abs(int(r_year) - year)
                if diff == 0:
                    score += 0.10
                elif diff == 1:
                    score += 0.05

        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def search_master_candidates(artist: str, title: str, year: int | None,
                              token: str | None,
                              delay: float = 0.0) -> list[tuple[float, dict]]:
    """Two-pass search returning all scored candidates."""
    results = _search({"q": f"{artist} {title}", "type": "master",
                       "per_page": "10"}, token)
    scored = _score_masters(artist, title, year, results)

    # Pass 2: title-only if pass 1 found nothing above threshold
    if not scored or scored[0][0] < LLM_THRESHOLD_ALBUM:
        if delay:
            time.sleep(delay)
        results2 = _search({"q": title, "type": "master", "per_page": "10"},
                            token)
        seen = {r["id"] for _, r in scored}
        new_results = [r for r in results2 if r["id"] not in seen]
        scored = _score_masters(artist, title, year, results + new_results)

    return scored


# ── YAML I/O ──────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _save_yaml(path: Path, data: dict | list) -> None:
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False,
                  sort_keys=False),
        encoding="utf-8",
    )


# ── Artists ────────────────────────────────────────────────────────────────────

def run_artists(token: str | None, dry_run: bool, limit: int | None) -> None:
    artists = _load_yaml(ARTISTS_YAML)
    if not artists:
        print("ERROR: artists.yaml not found or empty")
        sys.exit(1)

    has_llm = _get_claude() is not None
    print(f"LLM: {'✓ ' + CLAUDE_MODEL if has_llm else '✗ (auto-match only)'}")

    delay = _DELAY_AUTH if token else _DELAY_NOAUTH
    to_do = [a for a in artists if not a.get("discogs_id")]
    if limit:
        to_do = to_do[:limit]
    print(f"Artists without discogs_id: {len(to_do)}")

    if dry_run:
        for a in to_do[:20]:
            print(f"  would search: {a['name']}")
        if len(to_do) > 20:
            print(f"  ... and {len(to_do) - 20} more")
        return

    slug_to_artist = {a["slug"]: a for a in artists}
    counters = {"updated": 0, "not_found": 0}
    llm_batch: list[dict] = []

    for i, a in enumerate(to_do):
        name = a["slug_name"] if "slug_name" in a else a["name"]
        name = a["name"]
        scored = search_artist_candidates(name, token)
        time.sleep(delay)

        if not scored:
            counters["not_found"] += 1
            print(f"  [{i+1}/{len(to_do)}] {name} → no results")
            continue

        best_score, best = scored[0]

        if best_score >= AUTO_ACCEPT_ARTIST:
            slug_to_artist[a["slug"]]["discogs_id"] = str(best["id"])
            counters["updated"] += 1
            print(f"  [{i+1}/{len(to_do)}] {name} → {best['id']} "
                  f"({best.get('title', '')} {best_score:.2f})")
        elif best_score >= LLM_THRESHOLD_ARTIST and has_llm:
            llm_batch.append({
                "slug": a["slug"],
                "our_name": name,
                "discogs_title": best.get("title", ""),
                "discogs_id": str(best["id"]),
                "score": round(best_score, 3),
            })
            print(f"  [{i+1}/{len(to_do)}] {name} → LLM? "
                  f"({best.get('title', '')} {best_score:.2f})")
        else:
            counters["not_found"] += 1
            print(f"  [{i+1}/{len(to_do)}] {name} → skip "
                  f"({best.get('title', '')} {best_score:.2f})")

        if len(llm_batch) >= LLM_BATCH:
            _flush_artist_batch(llm_batch, slug_to_artist, counters)
            _save_yaml(ARTISTS_YAML, artists)

        if (i + 1) % 50 == 0:
            _save_yaml(ARTISTS_YAML, artists)
            print(f"  Checkpoint saved ({i+1} processed)")

    _flush_artist_batch(llm_batch, slug_to_artist, counters)
    _save_yaml(ARTISTS_YAML, artists)
    print(f"\nArtists done. Updated: {counters['updated']}, "
          f"Not found: {counters['not_found']}")


# ── Albums ─────────────────────────────────────────────────────────────────────

def run_albums(token: str | None, dry_run: bool,
               limit: int | None, only_artist: str | None) -> None:
    has_llm = _get_claude() is not None
    print(f"LLM: {'✓ ' + CLAUDE_MODEL if has_llm else '✗ (auto-match only)'}")

    delay = _DELAY_AUTH if token else _DELAY_NOAUTH

    if only_artist:
        artist_dirs = [ALBUMS_DIR / only_artist]
    else:
        artist_dirs = sorted(ALBUMS_DIR.iterdir()) if ALBUMS_DIR.exists() else []

    album_files: list[Path] = []
    for d in artist_dirs:
        if d.is_dir():
            album_files.extend(sorted(d.glob("*.yaml")))

    to_do = [f for f in album_files
             if not (_load_yaml(f) or {}).get("discogs_master_id")]
    if limit:
        to_do = to_do[:limit]
    print(f"Albums without discogs_master_id: {len(to_do)}")

    if dry_run:
        for f in to_do[:20]:
            d = _load_yaml(f) or {}
            print(f"  would search: {d.get('artist', '?')} — "
                  f"{d.get('title', '?')} ({d.get('year', '?')})")
        if len(to_do) > 20:
            print(f"  ... and {len(to_do) - 20} more")
        return

    counters = {"updated": 0, "not_found": 0}
    llm_batch: list[dict] = []

    for i, path in enumerate(to_do):
        data = _load_yaml(path)
        if not data or not isinstance(data, dict):
            continue
        artist = data.get("artist", "")
        title  = data.get("title", "")
        year   = data.get("year")
        if not artist or not title:
            counters["not_found"] += 1
            continue

        scored = search_master_candidates(artist, title, year, token, delay)
        time.sleep(delay)

        if not scored:
            counters["not_found"] += 1
            continue

        best_score, best = scored[0]
        disc_title = best.get("title", "")
        disc_year  = best.get("year", "")

        if best_score >= AUTO_ACCEPT_ALBUM:
            data["discogs_master_id"] = str(best["id"])
            _save_yaml(path, data)
            counters["updated"] += 1
            print(f"  [{i+1}/{len(to_do)}] {artist} — {title} "
                  f"→ {best['id']} ({disc_title} {best_score:.2f})")
        elif best_score >= LLM_THRESHOLD_ALBUM and has_llm:
            llm_batch.append({
                "path": str(path),
                "artist": artist,
                "our_title": title,
                "our_year": year,
                "discogs_title": disc_title,
                "discogs_year": disc_year,
                "discogs_id": str(best["id"]),
                "score": round(best_score, 3),
            })
            print(f"  [{i+1}/{len(to_do)}] {artist} — {title} "
                  f"→ LLM? ({disc_title} {best_score:.2f})")
        else:
            counters["not_found"] += 1
            if counters["not_found"] <= 5 or (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(to_do)}] {artist} — {title} "
                      f"→ skip ({disc_title} {best_score:.2f})")

        if len(llm_batch) >= LLM_BATCH:
            _flush_album_batch(llm_batch, counters)

    _flush_album_batch(llm_batch, counters)
    print(f"\nAlbums done. Updated: {counters['updated']}, "
          f"Not found: {counters['not_found']}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--artists", action="store_true", help="Fetch artist IDs")
    p.add_argument("--albums",  action="store_true", help="Fetch album master IDs")
    p.add_argument("--artist",  metavar="SLUG",
                   help="Process only this artist slug (albums mode)")
    p.add_argument("--limit",   type=int, metavar="N",
                   help="Stop after N items (for testing)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what would be done without making API calls")
    args = p.parse_args()

    if not args.artists and not args.albums:
        p.print_help()
        sys.exit(1)

    token = os.environ.get("DISCOGS_TOKEN")
    if not token and not args.dry_run:
        print("WARNING: DISCOGS_TOKEN not set — unauthenticated mode (25 req/min)")

    if args.artists:
        print("=== Fetching artist Discogs IDs ===")
        run_artists(token, args.dry_run, args.limit)

    if args.albums:
        print("=== Fetching album Discogs master IDs ===")
        run_albums(token, args.dry_run, args.limit, args.artist)


if __name__ == "__main__":
    main()
