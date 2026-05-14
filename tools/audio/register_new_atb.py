#!/usr/bin/env python3
"""
LLM-driven registration of new ATB episodes.

For each MP3 in bluesru-media/atb/ not yet in episodes.yaml:
  1. Requires a transcript MD in data/atb/transcripts/ — skip if missing
  2. Calls Claude to extract: topic, slug suffix, summary, artist tags
  3. Registers the episode in episodes.yaml
  4. Renames the MP3 (and transcript) from temp name to proper slug

Run after run_all_atb.py (which transcribes and produces the MDs).

Usage:
    python3 register_new_atb.py [--dry-run] [--episode STEM]
    python3 register_new_atb.py                    # all unregistered episodes with transcripts
    python3 register_new_atb.py --dry-run          # preview only
    python3 register_new_atb.py --episode atb-2016-11-20-clip11  # single file
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic
import yaml

ARC             = Path(__file__).resolve().parent.parent.parent
WORKSPACE       = ARC.parent
MEDIA_DIR       = WORKSPACE / "bluesru-media/atb"
TRANSCRIPTS_DIR = ARC / "data/atb/transcripts"
EPISODES_YAML   = ARC / "data/atb/episodes.yaml"
ARTISTS_YAML    = ARC / "data/artists.yaml"
MODEL           = "claude-sonnet-4-6"

DATE_RE = re.compile(r"^(atb-(\d{4}-\d{2}-\d{2}))-(.+)$")


REGISTER_SYSTEM = """\
You are registering episodes for a Russian blues radio show archive (blues.ru).
The show is «Весь этот блюз» ("All That Blues"), hosted by Andrei Evdokimov on Echo of Moscow.
Each episode features one or more blues artists.

Given a transcript of one episode, return JSON with these fields:

- "topic": short English title, e.g. "Big Mama Thornton", "Christmas Blues Special",
  "Muddy Waters 100", "B.B. King & Bobby Blue Bland". Max 6 words.

- "slug_suffix": URL-safe suffix for the episode slug, lowercase-dashes, no "atb-" prefix,
  no date. Based on the topic. E.g. "big-mama-thornton", "christmas-blues",
  "muddy-waters-100", "bb-king-bobby-blue-bland". Max 5 words.

- "summary": short label in Russian, max 120 chars. Direct title style — name the subject,
  NOT "Выпуск посвящён...". E.g. "90-летие Big Mama Thornton — певицы «Hound Dog»",
  "Rolling Stones «Blue and Lonesome» (2016): каверы Howlin' Wolf, Little Walter",
  "Grammy 2017: Bobby Rush, Lurrie Bell".

- "artists_tags": array of {slug, name} for artists who are clearly featured
  (their music is played or they are the main subject). Only use slugs from the provided
  known-slugs list. Empty array if none match.

Output ONLY valid JSON, no other text.\
"""


def load_episodes():
    return yaml.safe_load(EPISODES_YAML.read_text(encoding="utf-8")) or []


def save_episodes(episodes):
    EPISODES_YAML.write_text(
        yaml.dump(episodes, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120),
        encoding="utf-8",
    )


def load_known_slugs():
    if not ARTISTS_YAML.exists():
        return []
    data = yaml.safe_load(ARTISTS_YAML.read_text(encoding="utf-8")) or []
    return sorted(a["slug"] for a in data if a.get("slug"))


def load_transcript(stem):
    path = TRANSCRIPTS_DIR / f"{stem}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    # Strip markdown anchors and music markers
    text = re.sub(r'<a id="[^"]+"></a>', '', text)
    text = re.sub(r'\*\*\[MUSIC:[^\]]+\]\*\*', '[music]', text)
    text = re.sub(r'^#+.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\*.*\*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def call_claude(stem, date, transcript, known_slugs):
    client = anthropic.Anthropic()
    slug_list = "\n".join(known_slugs[:300])  # cap to avoid huge prompts
    context = (
        f"Episode date: {date}\n"
        f"File stem: {stem}\n\n"
        f"Known artist slugs:\n{slug_list}\n\n"
        f"Transcript (first 8000 chars):\n{transcript[:8000]}"
    )
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=512,
                system=REGISTER_SYSTEM,
                messages=[{"role": "user", "content": context}],
            )
            text = msg.content[0].text.strip()
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            # Collapse literal newlines inside JSON string values
            text = re.sub(r'(?<=: ")(.*?)(?=")', lambda m: m.group(0).replace('\n', ' '), text, flags=re.DOTALL)
            return json.loads(text)
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
            else:
                raise
        except json.JSONDecodeError as e:
            print(f"  JSON parse error: {e}\n  Raw: {text[:200]}")
            return None
    return None


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    args = sys.argv[1:]
    dry_run      = "--dry-run" in args
    filter_stem  = args[args.index("--episode") + 1] if "--episode" in args else None

    episodes    = load_episodes()
    known_slugs = load_known_slugs()
    known_files = {f["filename"] for ep in episodes for f in ep.get("files", [])}
    known_slugs_set = {ep["slug"] for ep in episodes}

    print(f"Loaded {len(episodes)} registered episodes, {len(known_slugs)} artist slugs")

    mp3_files = sorted(MEDIA_DIR.glob("*.mp3"))
    new_mp3s = [f for f in mp3_files if f.name not in known_files]

    if filter_stem:
        new_mp3s = [f for f in new_mp3s if f.stem == filter_stem]

    print(f"Unregistered MP3s: {len(new_mp3s)}")

    registered = renamed = skipped = errors = 0

    for mp3 in new_mp3s:
        stem = mp3.stem
        m = DATE_RE.match(stem)
        if not m:
            print(f"\nSKIP {mp3.name}: doesn't match atb-YYYY-MM-DD-* pattern")
            skipped += 1
            continue

        date_prefix, date, _ = m.groups()

        transcript = load_transcript(stem)
        if not transcript:
            print(f"\nSKIP {stem}: no transcript MD yet — run run_all_atb.py first")
            skipped += 1
            continue

        print(f"\n{stem}  ({date})")

        if dry_run:
            print(f"  [dry-run] would call Claude to register")
            continue

        result = call_claude(stem, date, transcript, known_slugs)
        if not result:
            print(f"  ERROR: Claude returned no parseable result")
            errors += 1
            continue

        topic        = result.get("topic", "").strip()
        slug_suffix  = result.get("slug_suffix", "").strip().lower()
        summary      = result.get("summary", "").strip()
        artists_tags = result.get("artists_tags", [])

        if not slug_suffix:
            print(f"  ERROR: empty slug_suffix from Claude")
            errors += 1
            continue

        # Build final slug, ensure uniqueness
        new_slug = f"{date_prefix}-{slug_suffix}"
        if new_slug in known_slugs_set:
            new_slug = f"{new_slug}-2"  # rare collision fallback
        known_slugs_set.add(new_slug)

        new_filename = f"{new_slug}.mp3"
        new_mp3_path = MEDIA_DIR / new_filename

        print(f"  topic:   {topic}")
        print(f"  slug:    {new_slug}")
        print(f"  summary: {summary[:80]}...")
        print(f"  artists: {[t['slug'] for t in artists_tags]}")

        # Rename MP3
        if mp3.name != new_filename:
            mp3.rename(new_mp3_path)
            renamed += 1
            print(f"  renamed: {mp3.name} → {new_filename}")
        else:
            new_mp3_path = mp3

        # Rename transcript MD if it exists under old stem
        old_md = TRANSCRIPTS_DIR / f"{stem}.md"
        new_md = TRANSCRIPTS_DIR / f"{new_slug}.md"
        if old_md.exists() and old_md != new_md:
            old_md.rename(new_md)
            print(f"  renamed: {old_md.name} → {new_md.name}")

        # Also rename JSON in extracted-data if present
        json_dir = WORKSPACE / "extracted-data/atb/transcripts"
        old_json = json_dir / f"{stem}.json"
        new_json = json_dir / f"{new_slug}.json"
        if old_json.exists() and old_json != new_json:
            old_json.rename(new_json)

        episode = {
            "date":        date,
            "slug":        new_slug,
            "topic":       topic,
            "summary":     summary,
            "description": "",
            "description_ai": True,
            "files":       [{"filename": new_filename, "path": f"/atb/{new_filename}"}],
            "artists_tags": artists_tags,
        }
        episodes.append(episode)
        registered += 1

    if registered and not dry_run:
        episodes.sort(key=lambda e: (e.get("date") or "", e.get("slug") or ""))
        save_episodes(episodes)
        print(f"\nRegistered {registered} episodes, renamed {renamed} files")
        print("Next: make atb")
    elif dry_run:
        print(f"\n[dry-run] would register {len(new_mp3s)} episodes")
    else:
        print(f"\nDone. Skipped: {skipped}  Errors: {errors}")


if __name__ == "__main__":
    main()
