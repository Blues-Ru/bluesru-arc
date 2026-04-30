#!/usr/bin/env python3
"""
Forum build planner — splits visible topics into N shard files.

Each shard file contains one line per topic:
    topic_id<TAB>page_num

Usage:
    python3 scripts/forum_plan.py [--nshards 8] [--out /path/to/forum-shards/]

Output files: shard-0.txt … shard-(N-1).txt
"""

import argparse
import sys
import yaml
from pathlib import Path

import os as _os
ARC  = Path(__file__).resolve().parent.parent
_ws  = Path(_os.environ.get('BLUESRU_ROOT', str(ARC.parent)))

# Reuse index-loading helpers from generate.py by importing them
sys.path.insert(0, str(ARC / 'scripts'))
from generate import _load_topics_index, _find_topic_yaml, _topic_is_all_deleted

PAGE_SIZE = 50


def main():
    parser = argparse.ArgumentParser(description='Generate forum shard plan files')
    parser.add_argument('--nshards', type=int, default=8, help='Number of shards (default 8)')
    parser.add_argument('--out', type=str,
                        default=str(_ws / 'forum-shards'),
                        help='Output directory for shard files')
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading topics index...")
    topics_index = _load_topics_index()

    topics_sorted = sorted(
        topics_index,
        key=lambda t: int(t.get('topic_id', 0)),
        reverse=True,
    )

    print(f"  {len(topics_sorted)} topics total, filtering visible...")

    topics_visible = []
    for tm in topics_sorted:
        tf = tm.get('_path') or _find_topic_yaml(tm['topic_id'])
        if not tf or not tf.exists():
            continue
        td = yaml.safe_load(tf.read_text())
        if not _topic_is_all_deleted(td):
            topics_visible.append(tm)

    print(f"  {len(topics_visible)} visible topics")

    # Build topic_id → forum index page number
    topic_to_page = {
        tm['topic_id']: (i // PAGE_SIZE) + 1
        for i, tm in enumerate(topics_visible)
    }

    # Split into N shards (round-robin for even distribution)
    shards = [[] for _ in range(args.nshards)]
    for i, tm in enumerate(topics_visible):
        tid = tm['topic_id']
        page = topic_to_page[tid]
        shards[i % args.nshards].append((tid, page))

    # Write shard files
    for n, shard in enumerate(shards):
        path = out_dir / f'shard-{n}.txt'
        path.write_text(
            ''.join(f'{tid}\t{page}\n' for tid, page in shard),
            encoding='utf-8'
        )

    sizes = [len(s) for s in shards]
    print(f"  Written {args.nshards} shards to {out_dir}/")
    print(f"  Topics per shard: min={min(sizes)} max={max(sizes)}")
    print()
    for n, size in enumerate(sizes):
        print(f"    shard-{n}.txt  {size} topics")


if __name__ == '__main__':
    main()
