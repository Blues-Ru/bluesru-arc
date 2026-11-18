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
    python3 register_new_atb.py --batch                # all, via Batch API (half price)

Re-tagging registered episodes (Batch API, half price):
    python3 register_new_atb.py --retag                 # submit, wait, save proposals, report
    python3 register_new_atb.py --retag-collect BATCH   # resume waiting for a submitted batch
    python3 register_new_atb.py --retag-apply FILE      # add proposed tags (never removes)
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
RETAG_DIR       = WORKSPACE / "extracted-data/atb/retag"  # batch manifests + proposals
EPISODES_YAML   = ARC / "data/atb/episodes.yaml"
ARTISTS_YAML    = ARC / "data/artists.yaml"
MODEL           = "claude-sonnet-5-5"

DATE_RE = re.compile(r"^(atb-(\d{4}-\d{2}-\d{2}))-(.+)$")
PART_RE = re.compile(r"-part-(\d+)$")

SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "slug_suffix": {"type": "string"},
        "summary": {"type": "string"},
        "artists_tags": {"type": "array", "items": {
            "type": "object",
            "properties": {"slug": {"type": "string"}, "name": {"type": "string"}},
            "required": ["slug", "name"],
            "additionalProperties": False,
        }},
    },
    "required": ["topic", "slug_suffix", "summary", "artists_tags"],
    "additionalProperties": False,
}


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
  (their music is played or they are the main subject). For an artist in the
  known-artists list ("slug — name" lines) copy its slug and name exactly. For anyone
  else use their usual English name and a lowercase-dashes slug made from it,
  e.g. {"slug": "big-mama-thornton", "name": "Big Mama Thornton"}.\
"""


def load_episodes():
    return yaml.safe_load(EPISODES_YAML.read_text(encoding="utf-8")) or []


def save_episodes(episodes):
    EPISODES_YAML.write_text(
        yaml.dump(episodes, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120),
        encoding="utf-8",
    )


def load_known_artists() -> dict:
    """slug → display name for every artist in artists.yaml."""
    if not ARTISTS_YAML.exists():
        return {}
    data = yaml.safe_load(ARTISTS_YAML.read_text(encoding="utf-8")) or []
    return {a["slug"]: a.get("name") or a["slug"] for a in data if a.get("slug")}


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


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


def request_params(stem, date, transcript, known_artists) -> dict:
    # The artist list is identical in every request: cache it with the system prompt.
    artist_list = "\n".join(f"{slug} — {name}" for slug, name in sorted(known_artists.items()))
    return {
        "model": MODEL,
        "max_tokens": 4096,
        "thinking": {"type": "between_tools"},
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
        "system": [
            {"type": "text", "text": REGISTER_SYSTEM},
            {"type": "text", "text": f"Known artists:\n{artist_list}",
             "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content": (
            f"Episode date: {date}\nFile stem: {stem}\n\nTranscript:\n{transcript}")}],
    }


def parse_result(msg):
    if msg.stop_reason != "end_turn":
        print(f"  stop_reason={msg.stop_reason}")
        return None
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def call_claude(stem, date, transcript, known_artists):
    client = anthropic.Anthropic()
    with client.messages.stream(**request_params(stem, date, transcript, known_artists)) as stream:
        return parse_result(stream.get_final_message())


def episode_transcript(ep):
    parts = [load_transcript(Path(f["filename"]).stem) for f in ep.get("files", [])]
    return "\n\n[next part]\n\n".join(p for p in parts if p)


def normalize_tags(raw: list, known_artists: dict) -> list:
    """Model tags → [{slug, name}], deduplicated; mapped onto a known artist when the
    slug or the name matches ignoring dashes, punctuation and a leading "the"
    (cj-chenier → c-j-chenier)."""
    def key(s):
        return re.sub(r"^the", "", re.sub(r"[^a-z0-9]", "", s.lower()))
    known_by_key = {key(k): k for k in known_artists}
    known_by_key.update({key(v): k for k, v in known_artists.items()})
    tags = {}
    for t in raw:
        slug = slugify(t["slug"] or t["name"])
        if slug not in known_artists:
            slug = known_by_key.get(key(t["name"])) or known_by_key.get(key(slug), slug)
        if slug and slug not in tags:
            tags[slug] = known_artists.get(slug) or t["name"].strip()
    return [{"slug": k, "name": v} for k, v in tags.items()]


def tag_slugs(ep) -> list:
    return [t["slug"] if isinstance(t, dict) else t for t in ep.get("artists_tags") or []]


def retag_submit(episodes, known_artists) -> str:
    requests = []
    for ep in episodes:
        transcript = episode_transcript(ep)
        if transcript:
            requests.append({"custom_id": ep["slug"][:64],
                             "params": request_params(ep["slug"], ep.get("date"), transcript,
                                                      known_artists)})
    batch = anthropic.Anthropic().messages.batches.create(requests=requests)
    RETAG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Submitted {batch.id}: {len(requests)} episodes")
    return batch.id


def retag_collect(batch_id, episodes, known_artists) -> Path:
    """Wait for the batch, save {slug: proposed tag slugs}, print gained/lost per episode."""
    client = anthropic.Anthropic()
    while (batch := client.messages.batches.retrieve(batch_id)).processing_status != "ended":
        c = batch.request_counts
        print(f"{batch_id}: {batch.processing_status}, processing {c.processing}, "
              f"succeeded {c.succeeded}", flush=True)
        time.sleep(60)
    by_id = {ep["slug"][:64]: ep for ep in episodes}
    proposals, failed = {}, []
    tokens = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0}
    for r in client.messages.batches.results(batch_id):
        if r.result.type != "succeeded":
            failed.append(f"{r.custom_id}: {r.result.type}")
            continue
        u = r.result.message.usage
        tokens["input"] += u.input_tokens
        tokens["cache_read"] += u.cache_read_input_tokens or 0
        tokens["cache_write"] += u.cache_creation_input_tokens or 0
        tokens["output"] += u.output_tokens
        try:
            result = parse_result(r.result.message)
        except json.JSONDecodeError as e:
            result = None
            print(f"  {r.custom_id}: {e}")
        if result is None:
            failed.append(r.custom_id)
            continue
        proposals[by_id[r.custom_id]["slug"]] = normalize_tags(result["artists_tags"], known_artists)
    out = RETAG_DIR / f"{batch_id}.json"
    out.write_text(json.dumps(proposals, ensure_ascii=False, indent=1), encoding="utf-8")

    gained = lost = unlinked = 0
    for slug, tags in sorted(proposals.items()):
        old = tag_slugs(next(ep for ep in episodes if ep["slug"] == slug))
        new = [t["slug"] for t in tags]
        add = [t for t in new if t not in old]
        drop = [t for t in old if t not in new]
        gained, lost = gained + len(add), lost + len(drop)
        unlinked += sum(1 for t in add if t not in known_artists)
        if add or drop:
            print(f"{slug}\n  + {add}\n  - {drop}")
    # Batch rate: half of $2 in / $10 out; cache reads 0.1x, writes 1.25x of input.
    usd = (tokens["input"] * 2 + tokens["cache_read"] * 0.2 + tokens["cache_write"] * 2.5
           + tokens["output"] * 10) / 1e6 / 2
    print(f"\n{len(proposals)} episodes: +{gained} tags ({unlinked} for artists not in "
          f"artists.yaml), -{lost} not re-proposed (kept)")
    print(f"Tokens {tokens}, ~${usd:.2f}")
    if failed:
        print(f"{len(failed)} failed: {failed}")
    print(f"Proposals: {out}\nApply (add-only): --retag-apply {out}")
    return out


def retag_apply(path, episodes, known_artists) -> None:
    proposals = json.loads(Path(path).read_text(encoding="utf-8"))
    added = 0
    for ep in episodes:
        old = tag_slugs(ep)
        for t in normalize_tags(proposals.get(ep["slug"], []), known_artists):
            if t["slug"] not in old:
                ep.setdefault("artists_tags", []).append(t)
                added += 1
    save_episodes(episodes)
    print(f"Added {added} tags to {EPISODES_YAML}")


def register_batch(pending, known_artists) -> dict:
    """Submit one request per pending episode, wait, return {stem: result}.
    Raw results are saved next to the retag ones so a failed apply can be redone."""
    client = anthropic.Anthropic()
    ids = {f"ep-{i}": p[0] for i, p in enumerate(pending)}  # stems can exceed 64 chars
    batch = client.messages.batches.create(requests=[
        {"custom_id": cid, "params": request_params(stem, date, transcript, known_artists)}
        for cid, (stem, _, _, date, transcript) in zip(ids, pending)])
    print(f"Submitted {batch.id}: {len(pending)} episodes", flush=True)
    while (b := client.messages.batches.retrieve(batch.id)).processing_status != "ended":
        print(f"  {b.processing_status}, succeeded {b.request_counts.succeeded}", flush=True)
        time.sleep(60)
    results, tokens = {}, {"input": 0, "cache_read": 0, "output": 0}
    for r in client.messages.batches.results(batch.id):
        if r.result.type != "succeeded":
            print(f"  {ids[r.custom_id]}: {r.result.type}")
            continue
        u = r.result.message.usage
        tokens["input"] += u.input_tokens
        tokens["cache_read"] += u.cache_read_input_tokens or 0
        tokens["output"] += u.output_tokens
        try:
            results[ids[r.custom_id]] = parse_result(r.result.message)
        except json.JSONDecodeError as e:
            print(f"  {ids[r.custom_id]}: {e}")
    RETAG_DIR.mkdir(parents=True, exist_ok=True)
    (RETAG_DIR / f"register-{batch.id}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    usd = (tokens["input"] * 2 + tokens["cache_read"] * 0.2 + tokens["output"] * 10) / 1e6 / 2
    print(f"Tokens {tokens}, ~${usd:.2f}")
    return results


def unique_slug(base: str, taken: set) -> str:
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    taken.add(slug)
    return slug


def group_parts(mp3s: list) -> dict:
    """stem without -part-N → that episode's MP3s in part order."""
    groups: dict = {}
    for mp3 in mp3s:
        groups.setdefault(PART_RE.sub("", mp3.stem), []).append(mp3)
    for files in groups.values():
        files.sort(key=lambda f: int(m[1]) if (m := PART_RE.search(f.stem)) else 0)
    return groups


def rename(old: Path, new: Path) -> None:
    if old.exists() and old != new:
        old.rename(new)
        print(f"  renamed: {old.name} → {new.name}")


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    args = sys.argv[1:]
    dry_run      = "--dry-run" in args
    filter_stem  = args[args.index("--episode") + 1] if "--episode" in args else None

    episodes      = load_episodes()
    known_artists = load_known_artists()

    if "--retag" in args:
        retag_collect(retag_submit(episodes, known_artists), episodes, known_artists)
        return
    if "--retag-collect" in args:
        retag_collect(args[args.index("--retag-collect") + 1], episodes, known_artists)
        return
    if "--retag-apply" in args:
        retag_apply(args[args.index("--retag-apply") + 1], episodes, known_artists)
        return
    known_files   = {f["filename"] for ep in episodes for f in ep.get("files", [])}
    taken_slugs   = {ep["slug"] for ep in episodes}

    print(f"Loaded {len(episodes)} registered episodes, {len(known_artists)} artists")

    new_mp3s = [f for f in sorted(MEDIA_DIR.glob("*.mp3")) if f.name not in known_files]
    groups = group_parts(new_mp3s)
    if filter_stem:
        groups = {k: v for k, v in groups.items() if k == PART_RE.sub("", filter_stem)}

    print(f"Unregistered MP3s: {len(new_mp3s)} in {len(groups)} episodes")

    registered = renamed = skipped = errors = 0

    pending = []  # (stem, mp3s, date_prefix, date, transcript)
    for stem, mp3s in groups.items():
        m = DATE_RE.match(stem)
        if not m:
            print(f"SKIP {stem}: doesn't match atb-YYYY-MM-DD-* pattern")
            skipped += 1
            continue
        parts = [load_transcript(f.stem) for f in mp3s]
        if not all(parts):
            print(f"SKIP {stem}: no transcript MD yet — run run_all_atb.py first")
            skipped += 1
            continue
        date_prefix, date, _ = m.groups()
        pending.append((stem, mp3s, date_prefix, date, "\n\n[next part]\n\n".join(parts)))

    if dry_run:
        print(f"\n[dry-run] would register {len(pending)} episodes")
        return

    if "--batch" in args:
        results = register_batch(pending, known_artists)
    else:
        results = {}
        for stem, _, _, date, transcript in pending:
            print(f"{stem}: calling Claude")
            try:
                results[stem] = call_claude(stem, date, transcript, known_artists)
            except (anthropic.APIError, json.JSONDecodeError) as e:
                print(f"  ERROR: {e}")

    json_dir = WORKSPACE / "extracted-data/atb/transcripts"
    for stem, mp3s, date_prefix, date, _ in pending:
        result = results.get(stem)
        slug_suffix = slugify(result["slug_suffix"]) if result else ""
        if not slug_suffix:
            print(f"ERROR {stem}: no usable result")
            errors += 1
            continue
        new_slug = unique_slug(f"{date_prefix}-{slug_suffix}", taken_slugs)
        artists_tags = normalize_tags(result["artists_tags"], known_artists)
        print(f"{stem} → {new_slug}: {result['summary'][:70]}")

        files = []
        for i, mp3 in enumerate(mp3s, 1):
            new_stem = f"{new_slug}-part-{i}" if len(mp3s) > 1 else new_slug
            new_filename = f"{new_stem}.mp3"
            if mp3.name != new_filename:
                rename(mp3, MEDIA_DIR / new_filename)
                renamed += 1
            rename(TRANSCRIPTS_DIR / f"{mp3.stem}.md", TRANSCRIPTS_DIR / f"{new_stem}.md")
            rename(json_dir / f"{mp3.stem}.json", json_dir / f"{new_stem}.json")
            files.append({"filename": new_filename, "path": f"/atb/{new_filename}"})

        episodes.append({
            "date":        date,
            "slug":        new_slug,
            "topic":       result["topic"].strip(),
            "summary":     result["summary"].strip(),
            "description": "",
            "description_ai": True,
            "files":       files,
            "artists_tags": artists_tags,
        })
        registered += 1

    if registered and not dry_run:
        episodes.sort(key=lambda e: (e.get("date") or "", e.get("slug") or ""))
        save_episodes(episodes)
        print(f"\nRegistered {registered} episodes, renamed {renamed} files")
        print("Next: make atb")
    if skipped or errors:
        print(f"Skipped: {skipped}  Errors: {errors}")


if __name__ == "__main__":
    main()
