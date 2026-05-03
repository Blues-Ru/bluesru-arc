#!/usr/bin/env python3
"""Generate forum pages (index + all topics)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from generate_shared import *


def generate_forum():
    """Generate full forum (index + all topics). Used by make forum."""
    print("Generating forum pages...")
    topics_visible, topic_to_page = _forum_visible_topics()
    print(f"  Topics: {len(topics_visible)} visible")
    _generate_forum_index(topics_visible)
    _clean_stale_topic_files(topics_visible)
    _generate_forum_topics(topics_visible, topic_to_page)
    _copy_forum_static()


def generate_forum_index():
    """Generate forum index pages only (make forum-index)."""
    print("Generating forum index pages...")
    topics_visible, _ = _forum_visible_topics()
    _generate_forum_index(topics_visible)
    _copy_forum_static()
    print(f"  Topics visible: {len(topics_visible)}")


def generate_forum_topics_from_shard(shard_file):
    """Generate topic HTML files listed in shard_file (make forum-shard-N)."""
    path = Path(shard_file)
    if not path.exists():
        print(f"Shard file not found: {shard_file}", file=sys.stderr)
        sys.exit(1)

    entries = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        entries.append((parts[0], int(parts[1])))

    topics_index = _load_topics_index()
    meta_by_id = {str(tm['topic_id']): tm for tm in topics_index}

    print(f"Generating {len(entries)} forum topics from {path.name}...")
    _generate_forum_topics(
        [meta_by_id[tid] for tid, _ in entries if tid in meta_by_id],
        {tid: page for tid, page in entries},
    )
    print(f"  Done: {path.name}")


def _clean_stale_topic_files(topics_visible):
    """Delete topicN.html files for topics no longer visible (e.g. all-spam topics)."""
    valid_ids = {str(tm.get('topic_id')) for tm in topics_visible}
    forum_dir = SITE / 'forum'
    if not forum_dir.exists():
        return
    removed = 0
    for f in forum_dir.glob('topic*.html'):
        tid = f.stem[5:]  # strip 'topic'
        if tid not in valid_ids:
            f.unlink()
            removed += 1
    if removed:
        print(f"  Removed {removed} stale topic file(s)")


def _generate_forum_index(topics_visible):
    PAGE_SIZE = 50
    total = len(topics_visible)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    tmpl_index = JINJA_ENV.get_template('forum_index.html.j2')

    for page_num in range(pages):
        start = page_num * PAGE_SIZE
        page_topics_meta = topics_visible[start:start + PAGE_SIZE]
        rendered_topics = []
        for tm in page_topics_meta:
            tf = tm.get('_path') or _find_topic_yaml(tm['topic_id'])
            td = yaml.safe_load(tf.read_text()) if (tf and tf.exists()) else None
            rendered_topics.append(render_topic_html(td, tm, full=False))
        fname = 'index.html' if page_num == 0 else f'page{page_num + 1}.html'
        dst = SITE / 'forum' / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        out = tmpl_index.render(
            page=page_num + 1,
            has_next=page_num + 1 < pages,
            topics=rendered_topics,
            render_topic=lambda t, full=False: t,
            canonical_url='https://blues.ru/forum/' if page_num == 0 else None,
        )
        dst.write_text(out, encoding='utf-8')
    print(f"  Forum index: {pages} pages")


def _generate_forum_topics(topics_meta, topic_to_page):
    tmpl_topic = JINJA_ENV.get_template('forum_topic.html.j2')
    generated = 0
    for tm in topics_meta:
        topic_id = tm.get('topic_id')
        tf = tm.get('_path') or _find_topic_yaml(topic_id)
        if not tf or not tf.exists():
            continue
        td = yaml.safe_load(tf.read_text())
        posts = td.get('posts', [])
        if not posts:
            continue
        first = posts[0]
        fp = topic_to_page.get(str(topic_id), topic_to_page.get(topic_id, 1))
        rendered = render_topic_html(td, tm, full=True, forum_page=fp)
        out = tmpl_topic.render(
            topic=tm,
            first_poster=html_mod.escape(first.get('poster', '') or ''),
            render_topic=lambda t, full=True: rendered,
        )
        dst = SITE / 'forum' / f'topic{topic_id}.html'
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out, encoding='utf-8')
        generated += 1
    print(f"  Forum topics: {generated}")


def _copy_forum_static():
    for f in (ARC / 'forum').iterdir():
        shutil.copy2(f, SITE / 'forum' / f.name)


def main():
    args = sys.argv[1:]
    shard_file = None
    if '--shard-file' in args:
        idx = args.index('--shard-file')
        shard_file = args[idx + 1]

    if '--section' in args:
        section = args[args.index('--section') + 1]
        if section == 'forum':
            generate_forum()
        elif section == 'forum-index':
            generate_forum_index()
        elif section == 'forum-topics':
            if not shard_file:
                print("--section forum-topics requires --shard-file", file=sys.stderr)
                sys.exit(1)
            generate_forum_topics_from_shard(shard_file)
        else:
            print(f"Unknown section: {section}", file=sys.stderr)
            sys.exit(1)
    elif shard_file:
        generate_forum_topics_from_shard(shard_file)
    else:
        generate_forum()


if __name__ == '__main__':
    main()
