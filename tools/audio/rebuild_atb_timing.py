#\!/usr/bin/env python3
"""
Rebuild ATB transcript MDs from existing Claude-cleaned speech + original JSON music boundaries.

This fixes timing drift caused by incorrect music block merging in earlier postprocess runs.
No Claude API calls — uses existing speech text from MDs + recalculates music structure from JSON.

Limitation: Russian speech blocks that the old code deleted are NOT recovered.
For full recovery, re-run run_all_atb.py --postprocess-only after deleting MDs.

Usage:
    python3 rebuild_atb_timing.py [--dry-run] [--slug SLUG]
"""

import json
import re
import sys
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
JSON_DIR  = WORKSPACE / "extracted-data/atb/transcripts"
MD_DIR    = ARC / "data/atb/transcripts"
SONG_GAP  = 25.0

sys.path.insert(0, str(Path(__file__).parent))
from postprocess_atb import (
    build_annotated, _parse_blocks, _is_real_speech, add_anchors,
    fmt_time, slug_to_meta, time_to_secs,
)

ANCHOR_RE = re.compile(r'<a id="([tm])(\d+)"></a>')
MUSIC_BOLD_RE = re.compile(r'\*\*\[MUSIC:[^\]]+\]\*\*')


def extract_speech_from_md(md_text: str) -> dict[str, str]:
    """Extract speech blocks from existing MD, indexed by timestamp string."""
    parts = ANCHOR_RE.split(md_text)
    speech = {}
    i = 1
    while i + 2 < len(parts):
        kind, secs_str, content = parts[i], parts[i+1], parts[i+2].strip()
        if kind == 't':
            # Strip any MUSIC bold markers that might have leaked into content
            content = MUSIC_BOLD_RE.sub('', content).strip()
            if content:
                s = int(secs_str)
                m, sec = divmod(s, 60)
                h, m2 = divmod(m, 60)
                ts = f"{h}:{m2:02d}:{sec:02d}" if h else f"{m2:02d}:{sec:02d}"
                speech[ts] = content
        i += 3
    return speech


def rebuild_md(slug: str, segments: list, md_speech: dict[str, str]) -> str:
    duration = fmt_time(segments[-1]["end"])
    meta = slug_to_meta(slug)

    annotated = build_annotated(segments)
    orig_blocks = _parse_blocks(annotated, strip_inline_ts=True)

    parts: list[str] = []
    pending_music: tuple[str, str] | None = None

    for b in orig_blocks:
        if b[0] == 't':
            text = md_speech.get(b[1], '').strip()
            if text:
                if pending_music:
                    parts.append(f"[MUSIC: {pending_music[0]}–{pending_music[1]}]")
                    pending_music = None
                parts.append(f"[T:{b[1]}]\n{text}")
            else:
                if _is_real_speech(b[2]):
                    if pending_music:
                        parts.append(f"[MUSIC: {pending_music[0]}–{pending_music[1]}]")
                        pending_music = None
        else:
            start, end = b[1], b[2]
            if pending_music:
                pending_music = (pending_music[0], end)
            else:
                pending_music = (start, end)

    if pending_music:
        parts.append(f"[MUSIC: {pending_music[0]}–{pending_music[1]}]")

    body = add_anchors('\n\n'.join(parts))
    header = f"# {meta['title']}\n\n*{meta['date']} · {duration}*\n\n---\n\n"
    return header + body


def main():
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    filter_slug = None
    if '--slug' in args:
        filter_slug = args[args.index('--slug') + 1]

    json_files = sorted(JSON_DIR.glob("*.json"))
    updated = skipped = errors = 0

    for json_path in json_files:
        slug = json_path.stem
        if filter_slug and slug != filter_slug:
            continue
        md_path = MD_DIR / f"{slug}.md"
        if not md_path.exists():
            continue

        try:
            data = json.loads(json_path.read_text(encoding='utf-8'))
            segs = data.get('segments', [])
            if not segs:
                continue

            md_speech = extract_speech_from_md(md_path.read_text(encoding='utf-8'))
            new_md = rebuild_md(slug, segs, md_speech)

            if dry_run:
                print(f"  [dry] {slug}")
            else:
                md_path.write_text(new_md, encoding='utf-8')
                print(f"  {slug}")
            updated += 1
        except Exception as e:
            print(f"  ERROR {slug}: {e}")
            errors += 1

    print(f"\nUpdated: {updated}  Errors: {errors}  (dry_run={dry_run})")


if __name__ == '__main__':
    main()
