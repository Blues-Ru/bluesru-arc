#!/usr/bin/env python3
"""
Rename gallery YAML files using Claude API.

For each gallery:
- Generate a clean English slug (no year suffix — year goes in canonical_date)
- Confirm / fix canonical_date (YYYY-MM-DD or YYYY-MM or YYYY)
- Clean title: remove embedded dates, keep the event/place name only
- Store the clean title separately from the date

Current: paul-lamb-kingsnakes-mhat-2003.yaml  canonical_date='2003'  title='Paul Lamb in MHAT'
Target:  paul-lamb-kingsnakes-mhat.yaml        canonical_date='2003'  title='Paul Lamb & King Snakes at MHAT'

Usage:
  python3 blues-dev/etl/rename_galleries.py [--dry-run] [--year YYYY]

Requires: ANTHROPIC_API_KEY environment variable.
"""
import argparse
import json
import os
import re
import sys
import time
import yaml
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent.parent
GALLERIES_DIR = ARC / 'data' / 'galleries'
INDEX_PATH = GALLERIES_DIR / 'index.yaml'

BATCH_SIZE = 30


def make_slug(s):
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')[:80]


def call_claude_batch(items, client):
    """
    items: list of dicts with keys: current_slug, title, canonical_date, type, photo_count
    Returns: list of dicts with keys: slug, canonical_date, title
    """
    prompt_lines = []
    for i, item in enumerate(items):
        prompt_lines.append(
            f"{i+1}. slug={item['slug']!r} title={item['title']!r} "
            f"date={item['canonical_date']!r} photos={item['photo_count']}"
        )

    prompt = (
        "These are photo gallery records from blues.ru, a Russian blues music site.\n"
        "For each gallery, provide:\n"
        "  slug: clean English slug, NO year suffix (year goes in canonical_date), 2-5 words\n"
        "  canonical_date: best date in YYYY-MM-DD, YYYY-MM, or YYYY format (use existing if correct)\n"
        "  title: clean English title, NO year (year shown separately in UI), concise event/artist name\n\n"
        "Rules:\n"
        "- Remove trailing year from slug: 'efes-blues-festival-2000' → 'efes-blues-festival'\n"
        "- Remove year from title: 'Efes Pilsener Blues Festival 2000' → 'Efes Pilsener Blues Festival'\n"
        "- Keep artist names as-is in English\n"
        "- For NBF: 'Notodden Blues Festival'\n"
        "- For partial dates like '2003' keep as '2003'\n\n"
        "Output ONLY a JSON array, one object per gallery, same order:\n"
        '[{"slug":"...","canonical_date":"...","title":"..."},...]\n\n'
        + "\n".join(prompt_lines)
        + "\n\nRespond with ONLY the JSON array."
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON array in response: {raw[:300]}")
    results = json.loads(m.group(0))
    return results


def collect_galleries(year_filter=None):
    """Collect all per-gallery YAMLs that are not excluded."""
    galleries = []
    for p in GALLERIES_DIR.glob('*/*.yaml'):
        if p.name == 'index.yaml':
            continue
        d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        if d.get('exclude'):
            continue
        year = p.parent.name
        if year_filter and year != year_filter:
            continue
        galleries.append({
            'path': p,
            'slug': p.stem,
            'title': d.get('title', '') or '',
            'canonical_date': str(d.get('canonical_date', '') or ''),
            'type': d.get('type', ''),
            'photo_count': len(d.get('photos') or []),
            'data': d,
        })
    return galleries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--year', help='Only process a specific year subdirectory')
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

    galleries = collect_galleries(args.year)
    print(f"Galleries to process: {len(galleries)}")

    # Load index to update in bulk
    index = yaml.safe_load(INDEX_PATH.read_text(encoding='utf-8')) or []
    index_by_slug = {g['slug']: g for g in index}

    renamed = 0
    updated = 0
    errors = 0

    for batch_start in range(0, len(galleries), BATCH_SIZE):
        batch = galleries[batch_start:batch_start + BATCH_SIZE]

        try:
            results = call_claude_batch(batch, client)
        except Exception as e:
            print(f"  ERROR batch {batch_start//BATCH_SIZE + 1}: {e}")
            errors += len(batch)
            continue

        if len(results) != len(batch):
            print(f"  ERROR: expected {len(batch)} results, got {len(results)}")
            errors += len(batch)
            continue

        for item, result in zip(batch, results):
            p = item['path']
            data = item['data']
            old_slug = item['slug']

            new_slug = make_slug(result.get('slug', old_slug) or old_slug)
            new_date = (result.get('canonical_date', '') or item['canonical_date']).strip()
            new_title = (result.get('title', '') or item['title']).strip()

            if not new_slug:
                new_slug = old_slug

            # Update YAML data
            data['slug'] = new_slug
            data['canonical_date'] = new_date
            data['title'] = new_title

            new_name = f"{new_slug}.yaml"
            dst = p.parent / new_name

            if args.dry_run:
                if old_slug != new_slug:
                    print(f"  DRY RENAME: {p.name!r} → {new_name!r}  title={new_title!r}")
                else:
                    print(f"  DRY UPDATE: {p.name!r}  title={new_title!r}")
            else:
                # Write updated YAML
                with dst.open('w', encoding='utf-8') as f:
                    yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                # Remove old file if renamed
                if p != dst and p.exists():
                    p.unlink()

            # Update index entry
            if old_slug in index_by_slug:
                idx_entry = index_by_slug[old_slug]
                idx_entry['slug'] = new_slug
                idx_entry['canonical_date'] = new_date
                idx_entry['title'] = new_title
                if old_slug != new_slug:
                    # Re-key
                    del index_by_slug[old_slug]
                    index_by_slug[new_slug] = idx_entry

            if old_slug != new_slug:
                renamed += 1
            else:
                updated += 1

        print(f"  Batch {batch_start//BATCH_SIZE + 1}/{(len(galleries)+BATCH_SIZE-1)//BATCH_SIZE} done")
        time.sleep(0.3)

    # Write updated index
    if not args.dry_run:
        with INDEX_PATH.open('w', encoding='utf-8') as f:
            yaml.dump(list(index_by_slug.values()), f,
                      allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\nDone. Renamed: {renamed}, Updated (same slug): {updated}, Errors: {errors}")


if __name__ == '__main__':
    main()
