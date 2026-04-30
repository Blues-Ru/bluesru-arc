#!/usr/bin/env python3
"""
Generate 400px-wide thumbnails for all gallery photos.

Source:  bluesru-media/photo/**/*.jpg
Output:  bluesru-media.cache/photo/**/*-400w.jpg  (mirrors source tree)

Skips files that already exist in the cache. Safe to re-run incrementally.

Usage:
    python3 blues-dev/thumbs/generate_thumbs.py [--dry-run] [--width 400]

Then sync to R2:
    rclone sync /Users/fedor/bluesru/bluesru-media.cache/ r2:bluesru-media/bluesru-media.cache/
"""

import argparse
import subprocess
import sys
from pathlib import Path

WORKSPACE   = Path(__file__).resolve().parent.parent.parent  # /Users/fedor/bluesru
MEDIA_SRC   = WORKSPACE / "bluesru-media"
MEDIA_CACHE = WORKSPACE / "bluesru-media.cache"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def thumb_path(src_file: Path, width: int) -> Path:
    """Map source file to cache file path."""
    rel = src_file.relative_to(MEDIA_SRC)
    stem = src_file.stem
    suffix = src_file.suffix.lower()
    # Always output as .jpg regardless of source format
    return MEDIA_CACHE / rel.parent / f"{stem}-{width}w.jpg"


def generate_thumb(src: Path, dst: Path, width: int, dry_run: bool) -> bool:
    """Generate a thumbnail using sips (macOS built-in). Returns True on success."""
    if dry_run:
        print(f"  [dry-run] {src.relative_to(MEDIA_SRC)} → {dst.relative_to(MEDIA_CACHE)}")
        return True

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["sips", "-Z", str(width), str(src), "--out", str(dst)],
            capture_output=True, text=True
        )
        if result.returncode != 0 and not dst.exists():
            print(f"  ERROR {src.name}: {result.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"  ERROR {src.name}: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate gallery thumbnails")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--width", type=int, default=400, help="Thumbnail width in px (default 400)")
    parser.add_argument("--subdir", default="photo", help="Subdirectory to process (default: photo)")
    args = parser.parse_args()

    src_root = MEDIA_SRC / args.subdir
    if not src_root.exists():
        print(f"Source dir not found: {src_root}", file=sys.stderr)
        sys.exit(1)

    sources = sorted(
        f for f in src_root.rglob("*")
        if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
        and not f.stem.endswith(f"-{args.width}w")  # skip existing thumbs if any
    )

    total = len(sources)
    skipped = 0
    generated = 0
    errors = 0

    print(f"Source:  {src_root}")
    print(f"Cache:   {MEDIA_CACHE / args.subdir}")
    print(f"Width:   {args.width}px")
    print(f"Files:   {total} images found")
    if args.dry_run:
        print("Mode:    DRY RUN")
    print()

    for src in sources:
        dst = thumb_path(src, args.width)
        if dst.exists():
            skipped += 1
            continue
        ok = generate_thumb(src, dst, args.width, args.dry_run)
        if ok:
            generated += 1
            if not args.dry_run:
                print(f"  ✓ {src.relative_to(MEDIA_SRC)}")
        else:
            errors += 1

    print()
    print(f"Done: {generated} generated, {skipped} skipped (exist), {errors} errors")
    print()
    print("To sync to R2:")
    print(f"  rclone sync {MEDIA_CACHE}/ r2:bluesru-media/bluesru-media.cache/")


if __name__ == "__main__":
    main()
