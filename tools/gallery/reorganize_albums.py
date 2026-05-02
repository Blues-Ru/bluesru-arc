#!/usr/bin/env python3
"""
Move data/albums/{slug}.yaml → data/albums/{artist-slug}/{slug}.yaml.

Artists with artist_id in artists.yaml use their canonical slug.
Albums without artist_id get a slug derived from their artist name.
"""
import re
import yaml
import shutil
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
DATA = ARC / 'data'
ALBUMS_DIR = DATA / 'albums'
ARTISTS_YAML = DATA / 'artists.yaml'


def name_to_slug(name):
    s = (name or '').lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-') or 'unknown'


def main():
    artists_by_id = {
        str(a['id']): a['slug']
        for a in yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8'))
    }

    flat_yamls = list(ALBUMS_DIR.glob('*.yaml'))
    print(f"Albums to move: {len(flat_yamls)}")

    moved = 0
    skipped = 0
    for src in sorted(flat_yamls):
        album = yaml.safe_load(src.read_text(encoding='utf-8')) or {}

        # Determine artist slug
        artist_slug = album.get('artist_slug', '')
        if not artist_slug:
            aid = str(album.get('artist_id', '') or '')
            artist_slug = artists_by_id.get(aid) or name_to_slug(album.get('artist', ''))

        dst_dir = ALBUMS_DIR / artist_slug
        dst_dir.mkdir(exist_ok=True)
        dst = dst_dir / src.name

        if dst.exists():
            print(f"  SKIP (exists): {dst}")
            skipped += 1
            continue

        src.rename(dst)
        moved += 1

    print(f"Moved: {moved}, Skipped: {skipped}")

    # Update gallery YAML cache invalidation hint
    print("Done. Run build to regenerate.")


if __name__ == '__main__':
    main()
