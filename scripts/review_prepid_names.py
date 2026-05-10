#!/usr/bin/env python3
"""
Review pre-pid forum posts for potential inferred_person_id attribution.

Logic: a name is a CANDIDATE for attribution to an author if:
  - The author posted that name ≥ MIN_PID_ABS times WITH their pid
  - That count is ≥ MIN_PID_FRAC of the author's total pid posts
  - There exist posts with that name but WITHOUT any person_id

For each candidate, shows statistics and sample topics so a human can decide
whether to add inferred_person_id to those posts (via apply_inferred_pids.py).

Also flags CONFLICTS: names where two different registered authors both qualify.

Output: temp/review_prepid.yaml (candidates) + temp/review_conflicts.yaml

Usage:
    python review_prepid_names.py [--out DIR]
"""
import sys
import re
import yaml
import glob
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_forum_authors import _load_groups, _iter_posts
from generate_shared import TOPICS_DIR

MIN_PID_ABS = 3
MIN_PID_FRAC = 0.05


def _norm(name: str) -> str:
    name = ' '.join(name.split())
    name = re.sub(r'(\S)\(', r'\1 (', name)
    return name


def main():
    out_dir = Path('temp')
    if '--out' in sys.argv:
        out_dir = Path(sys.argv[sys.argv.index('--out') + 1])
    out_dir.mkdir(exist_ok=True)

    pid_to_key, group_name_to_key, key_to_group = _load_groups()

    # pid → int for lookup
    ak_to_pids = {ak: grp['pids'] for ak, grp in key_to_group.items()}

    def _post_author_key(p):
        pid = p.get('person_id') or p.get('inferred_person_id')
        if pid:
            pid = int(pid)
            return pid_to_key.get(pid, f'pid:{pid}')
        name = _norm((p.get('poster') or '').strip())
        if name and name in group_name_to_key:
            return group_name_to_key[name]
        return f'name:{name}' if name else None

    topic_files = sorted(glob.glob(str(TOPICS_DIR / '**/*.yaml'), recursive=True))
    print(f'Scanning {len(topic_files)} topic files…')

    # Per author: pid-name counts
    ak_pid_name_counts = collections.defaultdict(lambda: collections.defaultdict(int))
    # Per name (no pid, no inferred): list of (tid, title, year, post_id)
    nopid_name_topics = collections.defaultdict(list)

    for fpath in topic_files:
        t = yaml.safe_load(open(fpath, encoding='utf-8').read())
        tid = t.get('topic_id')
        title = t.get('title', '')
        year = str(t.get('first_post', '') or '')[:4]
        for p in _iter_posts(t.get('posts', [])):
            if p.get('deleted'):
                continue
            raw = (p.get('poster') or '').strip()
            if not raw:
                continue
            nname = _norm(raw)
            has_pid = bool(p.get('person_id') or p.get('inferred_person_id'))
            if has_pid:
                ak = _post_author_key(p)
                if ak and not ak.startswith('name:'):
                    ak_pid_name_counts[ak][nname] += 1
            elif nname not in group_name_to_key:
                nopid_name_topics[nname].append({
                    'tid': tid, 'title': title[:70], 'year': year,
                    'post_id': p.get('id'),
                })

    print(f'  Registered authors with pid posts: {len(ak_pid_name_counts)}')
    print(f'  Unique no-pid poster names:        {len(nopid_name_topics)}')

    # Build candidate map: name → list of qualifying authors
    name_to_candidates = collections.defaultdict(list)
    for ak, name_counts in ak_pid_name_counts.items():
        total = sum(name_counts.values())
        if not total:
            continue
        for nname, count in name_counts.items():
            if count >= MIN_PID_ABS and count / total >= MIN_PID_FRAC:
                if nname in nopid_name_topics:
                    name_to_candidates[nname].append({
                        'ak': ak,
                        'pid_posts': count,
                        'pid_total': total,
                        'pct': round(count / total * 100, 1),
                    })

    # Separate clean candidates from conflicts
    candidates = []   # one author qualifies
    conflicts = []    # multiple authors qualify

    for nname, cands in sorted(name_to_candidates.items()):
        nopid_posts = nopid_name_topics[nname]
        # dedupe by tid (count unique topics, not posts)
        tids = list({p['tid'] for p in nopid_posts})
        sample = sorted({p['tid']: p for p in nopid_posts}.values(),
                        key=lambda x: x['year'], reverse=True)[:5]

        entry = {
            'name': nname,
            'nopid_posts': len(nopid_posts),
            'nopid_topics': len(tids),
            'sample_topics': [
                f"{s['year']} topic{s['tid']}: {s['title']}" for s in sample
            ],
            'candidates': [
                {
                    'slug': c['ak'],
                    'canonical': key_to_group.get(c['ak'], {}).get('canonical', c['ak']),
                    'pid_posts_with_name': c['pid_posts'],
                    'pid_posts_total': c['pid_total'],
                    'pct_of_author': c['pct'],
                    'pids': sorted(ak_to_pids.get(c['ak'], set())),
                }
                for c in sorted(cands, key=lambda x: -x['pid_posts'])
            ],
        }

        if len(cands) > 1:
            conflicts.append(entry)
        else:
            candidates.append(entry)

    # Sort by descending nopid_posts so the most impactful are first
    candidates.sort(key=lambda x: -x['nopid_posts'])
    conflicts.sort(key=lambda x: -x['nopid_posts'])

    out_cands = out_dir / 'review_prepid.yaml'
    out_conf = out_dir / 'review_conflicts.yaml'
    out_cands.write_text(
        yaml.dump(candidates, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding='utf-8',
    )
    out_conf.write_text(
        yaml.dump(conflicts, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding='utf-8',
    )
    print(f'  Clean candidates: {len(candidates)} names → {out_cands}')
    print(f'  Conflicts:        {len(conflicts)} names → {out_conf}')


if __name__ == '__main__':
    main()
