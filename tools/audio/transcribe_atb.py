#!/usr/bin/env python3
"""
Transcribe ATB radio show MP3 using mlx-whisper (Apple Silicon).
Outputs: extracted-data/atb/transcripts/{slug}.json  (raw segments with timestamps)
         extracted-data/atb/transcripts/{slug}.txt   (plain text)

Usage:
    python3 transcribe_atb.py <mp3> [mp3 ...]
    python3 transcribe_atb.py /path/to/atb-dir/
"""

import json
import sys
from pathlib import Path

MODEL = "mlx-community/whisper-large-v3-turbo"
ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
OUT_DIR = WORKSPACE / "extracted-data/atb/transcripts"


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def transcribe(mp3_path: Path) -> dict:
    import mlx_whisper

    print(f"\n→ Transcribing: {mp3_path.name}")
    return mlx_whisper.transcribe(
        str(mp3_path),
        path_or_hf_repo=MODEL,
        language="ru",
        word_timestamps=True,
        condition_on_previous_text=False,
        verbose=True,
    )


def save(result: dict, mp3_path: Path, out_dir: Path):
    slug = mp3_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{slug}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    txt_path = out_dir / f"{slug}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(result["text"].strip())

    segs = result.get("segments", [])
    duration = fmt_time(segs[-1]["end"]) if segs else "?"
    print(f"  {len(segs)} segments, duration {duration}")
    print(f"  → {json_path.name}")
    print(f"  → {txt_path.name}")
    return json_path


def main():
    paths = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.mp3")))
        elif p.suffix.lower() == ".mp3":
            paths.append(p)
        else:
            print(f"Skipping: {arg}")

    if not paths:
        print(__doc__)
        sys.exit(1)

    for mp3 in paths:
        json_path = OUT_DIR / f"{mp3.stem}.json"
        if json_path.exists():
            print(f"Skip (exists): {mp3.name}")
            continue
        result = transcribe(mp3)
        save(result, mp3, OUT_DIR)


if __name__ == "__main__":
    main()
