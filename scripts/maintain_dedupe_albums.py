#!/usr/bin/env python3
"""One-shot: merge 3 duplicate album YAMLs (same ASIN, same artist, same title).

For each pair, keep the lower-id file, append reviews from the higher-id file,
delete the higher-id file. The deleted album_id is recorded under `alias_ids`
on the kept file so albumview.aspx?cdid=N keeps working.
"""
import sys
from pathlib import Path
import yaml

DATA = Path(__file__).resolve().parents[1] / 'data'

PAIRS = [
    # (keep, drop)
    ('big-twist-the-mellow-fellows/big-twist-the-mellow-fellows-playing-for-keeps.yaml',
     'big-twist-the-mellow-fellows/big-twist-the-mellow-fellows-playing-for-keeps-2.yaml'),
    ('groove-hogs/groove-hogs-wrong-side-of-the-street.yaml',
     'groove-hogs/groove-hogs-wrong-side-of-the-street-2.yaml'),
    ('jimmy-johnson/jimmy-johnson-north-south.yaml',
     'jimmy-johnson/jimmy-johnson-north-south-2.yaml'),
]


def merge_pair(keep_rel: str, drop_rel: str) -> None:
    keep_p = DATA / 'albums' / keep_rel
    drop_p = DATA / 'albums' / drop_rel
    if not drop_p.exists():
        print(f"  skip (already gone): {drop_rel}")
        return
    keep = yaml.safe_load(keep_p.read_text(encoding='utf-8'))
    drop = yaml.safe_load(drop_p.read_text(encoding='utf-8'))

    if keep.get('asin') != drop.get('asin'):
        print(f"  REFUSE merge: ASIN mismatch {keep_p.name} vs {drop_p.name}")
        return

    keep_reviews = keep.get('reviews') or []
    drop_reviews = drop.get('reviews') or []
    have_ids = {r.get('id') for r in keep_reviews}
    for r in drop_reviews:
        if r.get('id') not in have_ids:
            keep_reviews.append(r)
    keep['reviews'] = sorted(keep_reviews, key=lambda r: str(r.get('date', '')))

    alias_ids = keep.get('alias_ids') or []
    drop_id = drop.get('id')
    if drop_id and drop_id not in alias_ids:
        alias_ids.append(drop_id)
    if alias_ids:
        keep['alias_ids'] = sorted(alias_ids)

    keep_p.write_text(
        yaml.dump(keep, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding='utf-8',
    )
    drop_p.unlink()
    print(f"  merged {drop_p.name} → {keep_p.name} (alias_ids={keep.get('alias_ids')}, reviews={len(keep_reviews)})")


def main() -> None:
    print("Deduping albums…")
    for keep_rel, drop_rel in PAIRS:
        merge_pair(keep_rel, drop_rel)
    print("Done.")


if __name__ == '__main__':
    main()
