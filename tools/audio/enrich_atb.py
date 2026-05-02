#!/usr/bin/env python3
"""
ATB episode enrichment via Claude API.

For each episode that lacks a good description or artist tags:
  1. Generate editorial summary + title from transcript
  2. Tag with artist slugs (matched against existing /artist/ slugs)

Writes enriched data back to data/atb/episodes.yaml.
JSONs are untouched — only episodes.yaml is modified.

Usage:
    python3 enrich_atb.py [--episode SLUG] [--force-desc] [--force-tags] [--dry-run]
    python3 enrich_atb.py                         # all episodes with gaps
    python3 enrich_atb.py --episode atb-2011-01-10-sam-chatmon
    python3 enrich_atb.py --force-desc            # regenerate all descriptions
    python3 enrich_atb.py --force-tags            # re-tag all episodes
"""

import json
import os
import re
import sys
import time
import yaml
from pathlib import Path

import anthropic

ARC             = Path(__file__).resolve().parent.parent.parent
WORKSPACE       = ARC.parent
EPISODES_YAML   = ARC / "data/atb/episodes.yaml"
TRANSCRIPTS_DIR = ARC / "data/atb/transcripts"  # MDs
ARTISTS_YAML    = ARC / "data/artists.yaml"
MODEL           = "claude-sonnet-4-6"

# Minimum description length to consider it "editorial" (not auto-generated stub)
MIN_DESC_LEN = 150


def load_episodes():
    return yaml.safe_load(EPISODES_YAML.read_text(encoding="utf-8")) or []


def save_episodes(episodes):
    EPISODES_YAML.write_text(
        yaml.dump(episodes, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120),
        encoding="utf-8",
    )


def load_known_slugs():
    """Load all artist slugs from bluesru-arc/data/artists.yaml."""
    if not ARTISTS_YAML.exists():
        return []
    data = yaml.safe_load(ARTISTS_YAML.read_text(encoding="utf-8")) or []
    return sorted(a["slug"] for a in data if a.get("slug"))


def load_transcript(slug, ep=None):
    """Load and concatenate transcript(s) for an episode.
    Returns plain text (stripped of markdown anchors and music markers).
    """
    seen = set()
    texts = []

    def try_path(p):
        if p.exists() and p not in seen:
            seen.add(p)
            texts.append(p.read_text(encoding="utf-8"))

    # Try exact slug first
    try_path(TRANSCRIPTS_DIR / f"{slug}.md")

    if not texts:
        # Try slug-part-1, slug-part-2 etc.
        for p in sorted(TRANSCRIPTS_DIR.glob(f"{slug}-part-*.md")):
            try_path(p)
        # Also try files from the episode's file list by matching prefix
        for p in sorted(TRANSCRIPTS_DIR.glob(f"{slug}*.md")):
            try_path(p)

    # Also try stems from episode's actual filenames (handles + in filename vs slug)
    if ep:
        for f in ep.get("files", []):
            stem = Path(f["filename"]).stem
            try_path(TRANSCRIPTS_DIR / f"{stem}.md")
            for p in sorted(TRANSCRIPTS_DIR.glob(f"{stem}-part-*.md")):
                try_path(p)

    if not texts:
        return None

    combined = "\n\n---\n\n".join(texts)
    # Strip markdown anchors and music blocks — keep plain speech text
    combined = re.sub(r'<a id="[^"]+"></a>', '', combined)
    combined = re.sub(r'\*\*\[MUSIC:[^\]]+\]\*\*', '[music]', combined)
    combined = re.sub(r'^#+.*$', '', combined, flags=re.MULTILINE)
    combined = re.sub(r'^\*.*\*$', '', combined, flags=re.MULTILINE)
    combined = re.sub(r'\n{3,}', '\n\n', combined)
    return combined.strip()


def needs_description(ep):
    if ep.get('description_ai'):  # AI-generated — safe to regenerate
        return True
    desc = (ep.get("description") or "").strip()
    summary = (ep.get("summary") or "").strip()
    if not desc and len(summary) < 80:
        return True  # Nothing there at all
    # Has existing content — eligible only if already classified as non-editorial
    return ep.get('description_editorial') is False


def needs_tags(ep):
    return not ep.get("artists_tags")


DESC_SYSTEM = """\
You are writing editorial summaries for a Russian blues radio show archive (blues.ru).
The show is «Весь этот блюз» ("All That Blues"), hosted by Andrei Evdokimov on Echo of Moscow.
Each episode focuses on one or more blues musicians.

Given a transcript of one episode, write:
1. A short summary (1-2 sentences, in Russian, max 160 chars) that names the featured artist(s)
   and the key theme or anniversary. This goes in the "summary" field.
2. A longer description (3-5 sentences, in Russian) that describes the episode content:
   which artists are featured, which songs/albums are discussed, notable facts mentioned.
   This goes in the "description" field.

Output ONLY valid JSON with keys "summary" and "description". No other text.\
"""

CLASSIFY_SYSTEM = """\
You are classifying episode descriptions for a Russian blues radio show archive.
The show «Весь этот блюз» was hosted by Andrei Evdokimov, who wrote editorial episode notes.

Determine if the given description is EDITORIAL (written by a human, the radio host)
or NON-EDITORIAL (auto-generated, stub, or too vague to be useful).

Editorial descriptions:
- Reference specific songs, albums, dates, or biographical facts from the episode
- Have a journalistic or personal tone
- Are substantive — not just repeating the artist's name

Non-editorial descriptions:
- Generic phrasing without specific episode content
- Just restate the episode slug or topic label
- Auto-generated boilerplate ("В этом выпуске...")
- Too vague to convey what the episode covers

Output ONLY one word: "editorial" or "non-editorial"\
"""

TAGS_SYSTEM = """\
You are tagging blues radio show episodes with featured artist slugs.

Given a transcript and a list of known artist slugs (from the blues.ru database),
tag an artist ONLY if at least one of these is true:
- A song or album of theirs is explicitly named AND music follows (they are played), OR
- They are the main subject of the episode or a significant segment (biographical story,
  anniversary, tribute, dedicated discussion of their career or style)

Do NOT tag:
- Artists mentioned only in passing ("...as recorded by Muddy Waters")
- Artists mentioned as influences or comparisons without their own music or story
- Band members tagged under the band's slug — prefer the individual musician slug when
  the story is about that person, not the band (e.g. "eric-clapton" not "cream")
- Session musicians who played on a track but are not the episode's subject

The known slug format is lowercase-dashes: "muddy-waters", "bb-king", "sam-chatmon".
Some artists in the transcript may not be in the known list — skip those.
Use the most specific individual musician slug available.

Output ONLY a JSON array of objects with "slug" and "name" (English display name).
Example: [{"slug": "muddy-waters", "name": "Muddy Waters"}]
Output [] if no strong matches.\
"""


def _call_claude(system, messages, max_tokens=512, retries=3):
    client = anthropic.Anthropic()
    for attempt in range(retries):
        try:
            return client.messages.create(
                model=MODEL, max_tokens=max_tokens,
                system=system, messages=messages,
            )
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  [retry {attempt+1}/{retries}] {e.__class__.__name__} — waiting {wait}s")
                time.sleep(wait)
            else:
                raise


def classify_description(ep) -> bool:
    """Return True if description is editorial (human-written), False if non-editorial."""
    text = (ep.get("description") or ep.get("summary") or "").strip()
    if not text:
        return False
    context = f"Episode: {ep.get('slug', '')}\nDescription: {text}"
    msg = _call_claude(CLASSIFY_SYSTEM, [{"role": "user", "content": context}], max_tokens=10)
    result = msg.content[0].text.strip().lower()
    return "non" not in result and "editorial" in result


def generate_description(transcript_text, ep):
    context = f"Episode slug: {ep['slug']}\nTopic: {ep.get('topic', '')}\n\nTranscript:\n{transcript_text[:8000]}"
    msg = _call_claude(DESC_SYSTEM, [{"role": "user", "content": context}])
    try:
        text = msg.content[0].text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        data = json.loads(text)
        return data.get("summary", ""), data.get("description", "")
    except (json.JSONDecodeError, KeyError, IndexError):
        return "", ""


def generate_tags(transcript_text, ep, known_slugs):
    slug_list = "\n".join(known_slugs)
    context = (
        f"Episode: {ep['slug']}\n"
        f"Summary: {ep.get('summary','')}\n\n"
        f"Known slugs:\n{slug_list}\n\n"
        f"Transcript:\n{transcript_text[:8000]}"
    )
    msg = _call_claude(TAGS_SYSTEM, [{"role": "user", "content": context}])
    try:
        text = msg.content[0].text.strip()
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            return json.loads(m.group())
        return []
    except (json.JSONDecodeError, IndexError):
        return []


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    args = sys.argv[1:]
    filter_slug = None
    if "--episode" in args:
        filter_slug = args[args.index("--episode") + 1]
    force_desc = "--force-desc" in args
    force_tags = "--force-tags" in args
    dry_run    = "--dry-run" in args

    episodes = load_episodes()
    known_slugs = load_known_slugs()
    print(f"Loaded {len(episodes)} episodes, {len(known_slugs)} known artist slugs")

    changed = 0
    for ep in episodes:
        slug = ep.get("slug", "")
        if not slug:
            continue
        if filter_slug and slug != filter_slug:
            continue

        # Classify existing description if unclassified (and not already AI-generated)
        has_content = bool((ep.get("description") or ep.get("summary") or "").strip())
        if has_content and not ep.get('description_ai') and 'description_editorial' not in ep:
            print(f"\n{slug}: classifying existing description...")
            if not dry_run:
                is_editorial = classify_description(ep)
                ep['description_editorial'] = is_editorial
                changed += 1
                print(f"  → {'editorial' if is_editorial else 'non-editorial'}")
            else:
                print(f"  [dry-run] would classify description")

        want_desc = force_desc or needs_description(ep)
        want_tags = force_tags or needs_tags(ep)
        if not want_desc and not want_tags:
            continue

        transcript = load_transcript(slug, ep)
        if not transcript:
            print(f"  {slug}: no transcript — skip")
            continue

        print(f"\n{slug}")

        if want_desc:
            print(f"  → generating description...")
            if not dry_run:
                summary, description = generate_description(transcript, ep)
                if summary:
                    ep["summary"] = summary
                    ep["description"] = description
                    ep["description_ai"] = True
                    print(f"  summary: {summary[:80]}...")
                    changed += 1
            else:
                print(f"  [dry-run] would generate description")

        if want_tags:
            print(f"  → generating artist tags...")
            if not dry_run:
                tags = generate_tags(transcript, ep, known_slugs)
                if tags is not None:
                    ep["artists_tags"] = tags
                    names = ", ".join(t["slug"] for t in tags) if tags else "(none)"
                    print(f"  tags: {names}")
                    changed += 1
            else:
                print(f"  [dry-run] would tag artists")

    if changed and not dry_run:
        save_episodes(episodes)
        print(f"\nSaved {changed} updates to {EPISODES_YAML}")
    elif dry_run:
        print(f"\n[dry-run] would write updates")
    else:
        print(f"\nNothing to update")


if __name__ == "__main__":
    main()
