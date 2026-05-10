#!/usr/bin/env python3
"""
Apply inferred_person_id to pre-pid forum posts based on reviewed name mappings.

Reads temp/review_prepid.yaml. Skips names flagged as too wide.
Adds inferred_person_id to posts where:
  - poster name matches a safe candidate
  - post has no person_id and no existing inferred_person_id

Amends source YAML files in place. Run --dry-run first to preview.

Usage:
    python apply_inferred_pids.py [--dry-run] [--review temp/review_prepid.yaml]
"""
import sys
import re
import yaml
import glob
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_shared import TOPICS_DIR

# Names flagged by reviewer as too wide / need extra review before applying
SKIP_NAMES = {
    'Андрей', 'Sanya', 'Вова', 'Олег', 'Natalia', 'Ash', 'Дмитрий А.', 'Иван',
    'John John', 'AvA', 'Ирина', 'Junior', 'Денис', 'andrew', 'Надежда (Надежда)',
    'металлисты', 'Konstantin', 'hipster', 'valen', 'Виталий', 'DaniL', 'sergey',
    'Алина (Алина)', 'Артем', 'Надежда', 'Артём',
}


def _norm(name: str) -> str:
    name = ' '.join(name.split())
    name = re.sub(r'(\S)\(', r'\1 (', name)
    return name


def load_mappings(review_path: Path):
    """Return (name → pid dict, skipped list)."""
    entries = yaml.safe_load(review_path.read_text(encoding='utf-8')) or []
    mappings = {}
    skipped = []
    for e in entries:
        name = e['name']
        if name in SKIP_NAMES:
            skipped.append(name)
            continue
        cands = e.get('candidates', [])
        if len(cands) != 1:
            skipped.append(f'{name} (conflict)')
            continue
        c = cands[0]
        slug = c.get('slug', '')
        if slug.startswith('pid:'):
            try:
                pid = int(slug[4:])
            except ValueError:
                continue
        else:
            pids = c.get('pids', [])
            if not pids:
                continue
            pid = pids[0]
        mappings[name] = pid
    return mappings, skipped


def _apply_to_posts(posts: list, name_to_pid: dict) -> int:
    """Recursively set inferred_person_id on matching posts. Returns count modified."""
    count = 0
    for p in posts:
        if (not p.get('deleted')
                and not p.get('person_id')
                and not p.get('inferred_person_id')):
            raw = (p.get('poster') or '').strip()
            if raw:
                nname = _norm(raw)
                if nname in name_to_pid:
                    p['inferred_person_id'] = name_to_pid[nname]
                    count += 1
        replies = p.get('replies') or []
        if replies:
            count += _apply_to_posts(replies, name_to_pid)
    return count


def main():
    dry_run = '--dry-run' in sys.argv
    review_path = Path('temp/review_prepid.yaml')
    if '--review' in sys.argv:
        review_path = Path(sys.argv[sys.argv.index('--review') + 1])

    if not review_path.exists():
        print(f'Review file not found: {review_path}', file=sys.stderr)
        sys.exit(1)

    mappings, skipped = load_mappings(review_path)
    print(f'Mappings to apply:  {len(mappings)} names')
    print(f'Skipped (too wide): {len(skipped)} names')

    if dry_run:
        print('\nDRY RUN — no files modified\n')
        for name, pid in sorted(mappings.items(), key=lambda x: x[0]):
            print(f'  pid {pid:6d}  {name}')
        print()

    topic_files = sorted(glob.glob(str(TOPICS_DIR / '**/*.yaml'), recursive=True))
    total_posts = 0
    files_changed = 0
    per_name = collections.Counter()

    for fpath in topic_files:
        raw_text = open(fpath, encoding='utf-8').read()
        t = yaml.safe_load(raw_text)
        posts = t.get('posts', [])

        # Count per-name hits in this file
        def _count(ps):
            c = collections.Counter()
            for p in ps:
                if (not p.get('deleted') and not p.get('person_id')
                        and not p.get('inferred_person_id')):
                    raw = (p.get('poster') or '').strip()
                    if raw:
                        nname = _norm(raw)
                        if nname in mappings:
                            c[nname] += 1
                c.update(_count(p.get('replies') or []))
            return c
        hits = _count(posts)
        if not hits:
            continue

        per_name.update(hits)
        total_posts += sum(hits.values())
        files_changed += 1

        if not dry_run:
            _apply_to_posts(posts, mappings)
            open(fpath, 'w', encoding='utf-8').write(
                yaml.dump(t, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=10000)
            )

    action = 'Would modify' if dry_run else 'Modified'
    print(f'{action} {total_posts} posts across {files_changed} topic files\n')
    print('Per-name breakdown:')
    for name, cnt in sorted(per_name.items(), key=lambda x: -x[1]):
        pid = mappings[name]
        print(f'  {cnt:5d}  pid {pid:6d}  {name}')


if __name__ == '__main__':
    main()
