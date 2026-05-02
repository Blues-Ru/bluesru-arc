#!/usr/bin/env python3
"""
Download Amazon album cover images for all albums with ASIN.
Stores them in bluesru-arc/static/covers/{asin}.jpg

Run from anywhere — paths are repo-relative.
Requires network access to images-na.ssl-images-amazon.com

Usage:
  python3 tools/streaming/cache_amazon_covers.py
  python3 tools/streaming/cache_amazon_covers.py --dry-run
  python3 tools/streaming/cache_amazon_covers.py --limit 100
"""

import time
import sys
import subprocess
import yaml
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
ALBUMS_DIR = ARC / 'data' / 'albums'  # subdirs: {artist-slug}/*.yaml
COVERS_DIR = ARC / 'covers'

# Use MZZZZZZZ (~160px) matching original albumview.xsl
COVER_URL = 'https://images-na.ssl-images-amazon.com/images/P/{asin}.01.MZZZZZZZ.jpg'

# Polite delay between requests (seconds)
DELAY = 0.3


def load_asins():
    """Load list of (slug, asin) from all album YAMLs."""
    result = []
    for p in sorted(ALBUMS_DIR.glob('**/*.yaml')):
        a = yaml.safe_load(p.read_text(encoding='utf-8'))
        asin = a.get('asin', '').strip()
        if asin:
            result.append((a.get('slug', p.stem), asin))
    return result


def download_cover(asin, dst, dry_run=False):
    """Download cover image for ASIN to dst. Returns True on success."""
    url = COVER_URL.format(asin=asin)
    if dry_run:
        print(f'  [dry-run] would fetch {url}')
        return True
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', str(dst), '-w', '%{http_code}:%{size_download}',
             '--max-time', '10', '--user-agent', 'Mozilla/5.0', url],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return False
        parts = result.stdout.strip().split(':')
        http_code = int(parts[0]) if parts else 0
        size = int(parts[1]) if len(parts) > 1 else 0
        if http_code != 200 or size < 500:
            # Amazon returns 1x1 GIF for missing images
            if dst.exists():
                dst.unlink()
            return False
        return True
    except (subprocess.TimeoutExpired, OSError, ValueError):
        if dst.exists():
            dst.unlink()
        return False


def main():
    dry_run = '--dry-run' in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith('--limit='):
            limit = int(arg.split('=')[1])
        elif arg == '--limit' and sys.argv.index(arg) + 1 < len(sys.argv):
            limit = int(sys.argv[sys.argv.index(arg) + 1])

    COVERS_DIR.mkdir(parents=True, exist_ok=True)

    asins = load_asins()
    print(f'{len(asins)} albums with ASIN')

    already = {p.stem for p in COVERS_DIR.glob('*.jpg')}
    to_download = [(slug, asin) for slug, asin in asins if asin not in already]
    print(f'{len(already)} covers already cached, {len(to_download)} to download')

    if limit:
        to_download = to_download[:limit]
        print(f'  (limited to {limit})')

    ok = skip = fail = 0
    for i, (slug, asin) in enumerate(to_download):
        dst = COVERS_DIR / f'{asin}.jpg'
        if dst.exists():
            skip += 1
            continue
        success = download_cover(asin, dst, dry_run=dry_run)
        if success:
            ok += 1
            if (i + 1) % 50 == 0:
                print(f'  {i + 1}/{len(to_download)}: {ok} ok, {fail} failed...')
        else:
            fail += 1
            if fail <= 5:
                print(f'  FAIL: {slug} ({asin})')
        if not dry_run:
            time.sleep(DELAY)

    print(f'\nDone: {ok} downloaded, {skip} skipped (already cached), {fail} failed')
    print(f'Covers dir: {COVERS_DIR} ({len(list(COVERS_DIR.glob("*.jpg")))} total files)')


if __name__ == '__main__':
    main()
