#!/usr/bin/env python3
"""
Remove confirmed spam posts from forum YAML data files.

Reads post IDs from bluesru-arc/data/forum/spam-ids.yaml and walks every
topic YAML, removing those posts AND their entire subtrees.

Unlike the 'deleted' flag (which hides the post but bubbles children up),
spam posts are removed entirely along with all replies.

Run after adding new IDs to spam-ids.yaml. Safe to re-run (idempotent).
"""

import sys
import yaml
from pathlib import Path

ARC        = Path(__file__).resolve().parent.parent.parent  # bluesru-arc/ repo root
SPAM_YAML  = ARC / "data" / "forum" / "spam-ids.yaml"
TOPICS_DIR = ARC / "data" / "forum" / "topics"


def load_spam_ids():
    d = yaml.safe_load(SPAM_YAML.read_text(encoding='utf-8')) or {}
    return set(d.get('post_ids', []))


def purge_posts(posts, spam_ids):
    """Remove spam posts (and subtrees) from posts list. Returns (cleaned_list, count_removed)."""
    cleaned = []
    removed = 0
    for p in posts:
        if p.get('id') in spam_ids:
            # Count this post + entire subtree
            removed += 1 + count_subtree(p.get('replies', []))
        else:
            sub_cleaned, sub_removed = purge_posts(p.get('replies', []), spam_ids)
            if sub_removed:
                p = dict(p, replies=sub_cleaned)
            removed += sub_removed
            cleaned.append(p)
    return cleaned, removed


def count_subtree(posts):
    total = 0
    for p in posts:
        total += 1 + count_subtree(p.get('replies', []))
    return total


def yaml_dump(data):
    return yaml.dump(data, allow_unicode=True, sort_keys=False,
                     default_flow_style=False, width=120)


def main():
    if not SPAM_YAML.exists():
        print(f"Error: {SPAM_YAML} not found", file=sys.stderr)
        sys.exit(1)

    spam_ids = load_spam_ids()
    print(f"Spam IDs to purge: {len(spam_ids)}")

    yaml_files = sorted(TOPICS_DIR.rglob('*.yaml'))
    print(f"Topic YAML files: {len(yaml_files)}")

    stats = {'files_changed': 0, 'posts_removed': 0, 'files_skipped': 0}

    for yf in yaml_files:
        data = yaml.safe_load(yf.read_text(encoding='utf-8'))
        if not data or not isinstance(data, dict):
            stats['files_skipped'] += 1
            continue

        posts = data.get('posts', [])
        cleaned, removed = purge_posts(posts, spam_ids)

        if removed:
            data['posts'] = cleaned
            # Update post_count if present
            if 'post_count' in data:
                data['post_count'] = max(0, data['post_count'] - removed)
            yf.write_text(yaml_dump(data), encoding='utf-8')
            stats['files_changed'] += 1
            stats['posts_removed'] += removed

    print(f"Files changed:   {stats['files_changed']:,}")
    print(f"Posts removed:   {stats['posts_removed']:,}")
    print(f"Files skipped:   {stats['files_skipped']:,}")
    print(f"\nDone. Commit bluesru-arc/data/forum/topics/ to persist.")


if __name__ == '__main__':
    main()
