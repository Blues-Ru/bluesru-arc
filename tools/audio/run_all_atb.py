#!/usr/bin/env python3
"""
Full ATB transcription pipeline over all MP3 files in bluesru-media/atb/.

For each MP3:
  1. Transcribe with mlx-whisper (skipped if JSON exists)
  2. Post-process with Claude API (skipped if MD exists)

JSONs are always kept. Delete the .md to re-run post-processing only.
Delete both .json and .md to re-run everything for a file.

Usage:
    python3 run_all_atb.py [--postprocess-only] [--dry-run]

Options:
    --postprocess-only   Skip transcription, only run Claude on existing JSONs
    --dry-run            Print what would be done, do nothing
    --range START END    Process only files [START..END] (1-based, inclusive)
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
MEDIA_DIR = WORKSPACE / "bluesru-media/atb"
TRANSCRIPT_DIR = WORKSPACE / "extracted-data/atb/transcripts"      # JSONs (dev-only)
TRANSCRIPT_MD_DIR = ARC / "data/atb/transcripts"  # MDs (committed)
MODEL_WHISPER = "mlx-community/whisper-large-v3-turbo"

# Import post-processing functions from sibling module
sys.path.insert(0, str(Path(__file__).parent))
from postprocess_atb import process_segments, fmt_time  # noqa: E402


def transcribe_file(mp3_path: Path) -> dict | None:
    import mlx_whisper
    print(f"  [whisper] transcribing...")
    return mlx_whisper.transcribe(
        str(mp3_path),
        path_or_hf_repo=MODEL_WHISPER,
        language="ru",
        word_timestamps=True,
        condition_on_previous_text=False,
        verbose=False,
    )


def run(postprocess_only: bool = False, dry_run: bool = False,
        range_start: int = 1, range_end: int = 0):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_MD_DIR.mkdir(parents=True, exist_ok=True)

    mp3_files = sorted(MEDIA_DIR.glob("*.mp3"))
    total = len(mp3_files)
    end = range_end if range_end > 0 else total
    # Apply range (1-based, inclusive)
    mp3_files = mp3_files[range_start - 1:end]
    print(f"Found {total} MP3 files total, processing [{range_start}–{end}] ({len(mp3_files)} files)")
    print(f"JSON dir: {TRANSCRIPT_DIR}")
    print(f"MD dir:   {TRANSCRIPT_MD_DIR}\n")

    done_t = done_p = skip_t = skip_p = errors = 0

    for i, mp3 in enumerate(mp3_files, range_start):
        slug = mp3.stem
        json_path = TRANSCRIPT_DIR / f"{slug}.json"
        md_path = TRANSCRIPT_MD_DIR / f"{slug}.md"

        print(f"[{i:3d}/{total}] {slug}")

        # --- Step 1: Transcription ---
        if not postprocess_only:
            if json_path.exists():
                print(f"         transcription: skip (json exists)")
                skip_t += 1
            elif dry_run:
                print(f"         transcription: would run")
            else:
                t0 = time.time()
                try:
                    result = transcribe_file(mp3)
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                    segs = result.get("segments", [])
                    elapsed = time.time() - t0
                    print(f"         transcription: {len(segs)} segs, "
                          f"{fmt_time(segs[-1]['end']) if segs else '?'}, "
                          f"{elapsed:.0f}s")
                    done_t += 1
                except Exception as e:
                    print(f"         transcription: ERROR — {e}")
                    traceback.print_exc()
                    errors += 1
                    continue

        # --- Step 2: Post-processing ---
        if md_path.exists():
            print(f"         post-process:  skip (md exists)")
            skip_p += 1
            continue

        if not json_path.exists():
            print(f"         post-process:  skip (no json)")
            continue

        if dry_run:
            print(f"         post-process:  would run")
            continue

        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            segs = data.get("segments", [])
            if not segs:
                print(f"         post-process:  skip (empty json)")
                continue

            t0 = time.time()
            md = process_segments(slug, segs)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
            elapsed = time.time() - t0
            print(f"         post-process:  done, {len(md)} chars, {elapsed:.0f}s")
            done_p += 1
        except Exception as e:
            print(f"         post-process:  ERROR — {e}")
            traceback.print_exc()
            errors += 1

    print(f"\n{'='*60}")
    print(f"Transcribed: {done_t}  (skipped: {skip_t})")
    print(f"Post-processed: {done_p}  (skipped: {skip_p})")
    print(f"Errors: {errors}")


def main():
    args = sys.argv[1:]
    postprocess_only = "--postprocess-only" in args
    dry_run = "--dry-run" in args
    range_start, range_end = 1, 0
    if "--range" in args:
        idx = args.index("--range")
        range_start = int(args[idx + 1])
        range_end = int(args[idx + 2])
    run(postprocess_only=postprocess_only, dry_run=dry_run,
        range_start=range_start, range_end=range_end)


if __name__ == "__main__":
    main()
