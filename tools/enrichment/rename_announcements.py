#!/usr/bin/env python3
"""
Rename announcement .md files to clean English slugs using Claude API.

Current names: 2001-01-03-v-razdel-b-atb-s-who-is-who-b-vnesena-spravka-na-a-href.md
Target names:  2001-01-03-atb-who-is-who-reference.md

Usage:
  python3 blues-dev/etl/rename_announcements.py [--dry-run] [--year YYYY]

Requires: ANTHROPIC_API_KEY environment variable.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
ANN_DIR = ARC / 'data' / 'updates'

BATCH_SIZE = 40  # announcements per API call


def read_frontmatter_and_body(path):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        return {}, text
    end = text.find('\n---', 3)
    if end < 0:
        return {}, text
    import yaml
    fm = yaml.safe_load(text[3:end]) or {}
    body = text[end + 4:].strip()
    return fm, body


def make_slug(s):
    """Normalize a raw slug string: lowercase, replace non-alnum with dashes."""
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:60]


def call_claude_batch(items, client):
    """
    items: list of dicts with keys: date, title, body_snippet
    Returns: list of slugs (same order)
    """
    prompt_lines = []
    for i, item in enumerate(items):
        prompt_lines.append(
            f"{i+1}. date={item['date']!r} title={item['title']!r}\n"
            f"   body: {item['body_snippet']}\n"
        )
    prompt = (
        "For each Russian-language blues.ru site announcement below, generate a clean English file slug "
        "(3-5 lowercase words, hyphen-separated, no dates, no articles, captures the main topic).\n"
        "Output ONLY a JSON array of strings, one per announcement, in the same order.\n"
        "Examples of good slugs: 'albert-king-biography-added', 'new-mp3-archive-section', "
        "'muddy-waters-book-update', 'site-news-update'\n\n"
        + "\n".join(prompt_lines)
        + "\nRespond with ONLY a JSON array."
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    # Extract JSON array from response
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON array in response: {raw[:200]}")
    slugs = json.loads(m.group(0))
    return [make_slug(s) for s in slugs]


def collect_files(year_filter=None):
    files = []
    for year_dir in sorted(ANN_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        if year_filter and year_dir.name != year_filter:
            continue
        for md in sorted(year_dir.glob('*.md')):
            files.append(md)
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--year', help='Only process a specific year')
    args = parser.parse_args()

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
        import httpx
    except ImportError:
        print("ERROR: pip install anthropic httpx", file=sys.stderr)
        sys.exit(1)

    # Use a plain httpx client to avoid socksio proxy issues in some environments
    http_client = httpx.Client(trust_env=False)
    client = anthropic.Anthropic(api_key=api_key, http_client=http_client)

    files = collect_files(args.year)
    print(f"Files to rename: {len(files)}")

    renamed = 0
    skipped = 0
    errors = 0

    for batch_start in range(0, len(files), BATCH_SIZE):
        batch = files[batch_start:batch_start + BATCH_SIZE]
        items = []
        for p in batch:
            fm, body = read_frontmatter_and_body(p)
            title = fm.get('title', '') or ''
            body_snippet = re.sub(r'<[^>]+>', ' ', body)[:300].replace('\n', ' ').strip()
            items.append({
                'date': p.name[:10],
                'title': title,
                'body_snippet': body_snippet,
                'path': p,
            })

        try:
            slugs = call_claude_batch(items, client)
        except Exception as e:
            print(f"  ERROR batch {batch_start}: {e}")
            errors += len(batch)
            continue

        if len(slugs) != len(batch):
            print(f"  ERROR: expected {len(batch)} slugs, got {len(slugs)}")
            errors += len(batch)
            continue

        for item, slug in zip(items, slugs):
            p = item['path']
            date_prefix = p.name[:10]
            new_name = f"{date_prefix}-{slug}.md"

            if p.name == new_name:
                skipped += 1
                continue

            dst = p.parent / new_name
            # Handle collisions by appending the original id
            if dst.exists():
                fm, _ = read_frontmatter_and_body(p)
                orig_id = str(fm.get('id', ''))
                if orig_id:
                    new_name = f"{date_prefix}-{slug}-{orig_id}.md"
                    dst = p.parent / new_name

            if args.dry_run:
                print(f"  DRY {p.name!r} → {new_name!r}")
            else:
                p.rename(dst)
            renamed += 1

        print(f"  Batch {batch_start//BATCH_SIZE + 1}: {len(batch)} files processed")
        time.sleep(0.3)  # be gentle to the API

    print(f"\nDone. Renamed: {renamed}, Skipped (no change): {skipped}, Errors: {errors}")


if __name__ == '__main__':
    main()
