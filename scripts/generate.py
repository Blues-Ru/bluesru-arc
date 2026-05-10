#!/usr/bin/env python3
"""
Thin dispatcher for bluesru-arc section generators.

Usage: python3 scripts/generate.py --section SECTION [--shard-file FILE]

Sections: content forum-authors forum forum-index forum-topics reviews news updates bluesmen
          atb galleries photo homepage postprocess deploy

Individual scripts can also be run directly:
  python3 scripts/generate_forum.py
  python3 scripts/generate_reviews.py
  etc.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import SITE, postprocess_dead_links, copy_root_files
from generate_forum import generate_forum, generate_forum_index, generate_forum_topics_from_shard
from generate_forum_authors import generate_forum_authors
from generate_reviews import generate_reviews
from generate_news import generate_news
from generate_updates import generate_updates
from generate_bluesmen import generate_bluesmen
from generate_galleries import generate_galleries, generate_photo_index
from generate_content import generate_content
from generate_atb import generate_atb
from generate_homepage import generate_homepage

SECTIONS = {
    'content':      generate_content,
    'forum-authors': generate_forum_authors,
    'forum':        generate_forum,
    'forum-index':  generate_forum_index,
    'reviews':      generate_reviews,
    'news':         generate_news,
    'updates':      generate_updates,
    'bluesmen':     generate_bluesmen,
    'atb':          generate_atb,
    'galleries':    generate_galleries,
    'photo':        generate_photo_index,
    'homepage':     generate_homepage,
    'postprocess':  postprocess_dead_links,
    'deploy':       copy_root_files,
}


def main():
    args = sys.argv[1:]

    shard_file = None
    if '--shard-file' in args:
        idx = args.index('--shard-file')
        shard_file = args[idx + 1]

    if '--section' in args:
        idx = args.index('--section')
        section = args[idx + 1]
        if section == 'forum-topics':
            if not shard_file:
                print("--section forum-topics requires --shard-file", file=sys.stderr)
                sys.exit(1)
            generate_forum_topics_from_shard(shard_file)
        elif section not in SECTIONS:
            print(f"Unknown section: {section}. Available: {list(SECTIONS) + ['forum-topics']}")
            sys.exit(1)
        else:
            SECTIONS[section]()
    else:
        for name, fn in SECTIONS.items():
            if name not in ('forum-index', 'postprocess', 'deploy'):
                fn()
        postprocess_dead_links()
        copy_root_files()
    print(f"\nOutput: {SITE}")


if __name__ == '__main__':
    main()
