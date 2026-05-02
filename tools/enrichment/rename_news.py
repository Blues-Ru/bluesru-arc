#!/usr/bin/env python3
"""
Rename blues-data news .md files to clean English slugs using Claude API.

Current: 2001-10-15-kniga-billa-vaymana.md
Target:  2001-10-15-bill-wyman-blues-odyssey-book.md

Usage:
  python3 blues-dev/etl/rename_news.py [--dry-run] [--year YYYY]

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
NEWS_DIR = ARC / 'data' / 'news'

BATCH_SIZE = 40


def read_title(path):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        return ''
    end = text.find('\n---', 3)
    if end < 0:
        return ''
    import yaml
    fm = yaml.safe_load(text[3:end]) or {}
    return fm.get('title', '') or ''


def make_slug(s):
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:60]


def call_claude_batch(items, client):
    prompt_lines = []
    for i, item in enumerate(items):
        prompt_lines.append(f"{i+1}. title={item['title']!r}")

    prompt = (
        "For each Russian-language blues.ru news title below, generate a clean English file slug "
        "(3-5 lowercase words, hyphen-separated, no dates, no articles, captures the main topic).\n"
        "Output ONLY a JSON array of strings, one per title, in the same order.\n"
        "Examples: 'bill-wyman-blues-odyssey-book', 'muddy-waters-biography-release', "
        "'new-album-bb-king', 'chicago-blues-festival-2001'\n\n"
        + "\n".join(prompt_lines)
        + "\nRespond with ONLY a JSON array."
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON array in response: {raw[:200]}")
    slugs = json.loads(m.group(0))
    return [make_slug(s) for s in slugs]


def collect_files(year_filter=None):
    files = []
    for year_dir in sorted(NEWS_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        if year_filter and year_dir.name != year_filter:
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for md in sorted(month_dir.glob('*.md')):
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
            title = read_title(p)
            items.append({'title': title, 'path': p})

        try:
            slugs = call_claude_batch(items, client)
        except Exception as e:
            print(f"  ERROR batch {batch_start//BATCH_SIZE + 1}: {e}")
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
            if dst.exists() and dst != p:
                # collision: append original id from frontmatter
                import yaml
                text = p.read_text(encoding='utf-8')
                end = text.find('\n---', 3)
                fm = yaml.safe_load(text[3:end]) if end > 0 else {}
                orig_id = str(fm.get('id', ''))
                if orig_id:
                    new_name = f"{date_prefix}-{slug}-{orig_id}.md"
                    dst = p.parent / new_name

            if args.dry_run:
                print(f"  DRY {p.name!r} → {new_name!r}")
            else:
                p.rename(dst)
            renamed += 1

        print(f"  Batch {batch_start//BATCH_SIZE + 1}/{(len(files)+BATCH_SIZE-1)//BATCH_SIZE}: {len(batch)} files")
        time.sleep(0.3)

    print(f"\nDone. Renamed: {renamed}, Skipped (no change): {skipped}, Errors: {errors}")


if __name__ == '__main__':
    main()
