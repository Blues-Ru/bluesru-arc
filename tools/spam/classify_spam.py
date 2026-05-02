#!/usr/bin/env python3
"""
Single-request spam classification using Claude Sonnet.

Sends all candidates in one large-context request, gets back
spam/legit/unsure verdict per post, then writes three report files:

  spam-report.txt     — posts classified as spam
  unsure-report.txt   — uncertain cases needing human review
  legit-report.txt    — posts classified as legitimate

Usage:
  python3 classify_spam.py --classify     # call API, write raw results JSON
  python3 classify_spam.py --report       # re-generate reports from saved results
  python3 classify_spam.py --apply        # write spam-ids.yaml from spam verdict

Results saved to:
  spam-results.json   — raw LLM output, keep for re-reporting without re-running
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

HERE       = Path(__file__).resolve().parent
ARC        = HERE.parent.parent  # bluesru-arc/ repo root
TOPICS_DIR = ARC / "data" / "forum" / "topics"
RESULTS_FILE  = HERE / "spam-results.json"
SPAM_IDS_OUT  = ARC / "data" / "forum" / "spam-ids.yaml"

URL_RE = re.compile(r'https?://|\[url=', re.IGNORECASE)
MAX_AUTHOR_POSTS = 5
MAX_TEXT_LEN     = 1200


# ── Data loading ──────────────────────────────────────────────────────────────

def flatten_posts(posts, topic_id, topic_title, result=None, depth=0):
    if result is None:
        result = []
    for p in posts:
        result.append({
            'post_id':     p.get('id'),
            'topic_id':    topic_id,
            'topic_title': topic_title,
            'author':      p.get('poster', '') or '',
            'person_id':   p.get('person_id'),
            'date':        str(p.get('date', '') or ''),
            'text':        p.get('text', '') or '',
            'deleted':     p.get('deleted', False),
            'depth':       depth,
            'reply_count': len(p.get('replies', [])),
        })
        flatten_posts(p.get('replies', []), topic_id, topic_title, result, depth + 1)
    return result


def author_key(p):
    pid = p.get('person_id')
    return ('id', pid) if pid is not None else ('name', p['author'])


def load_all_posts():
    posts = []
    for yf in sorted(TOPICS_DIR.rglob('*.yaml')):
        d = yaml.safe_load(yf.read_text(encoding='utf-8'))
        if not d:
            continue
        flatten_posts(d.get('posts', []), d.get('topic_id'), d.get('title', '') or '', posts)
    return posts


def collect_candidates(all_posts, key_counts):
    return [
        p for p in all_posts
        if not p['deleted']
        and URL_RE.search(p['text'])
        and key_counts[author_key(p)] <= MAX_AUTHOR_POSTS
        and len(p['text']) <= MAX_TEXT_LEN
    ]


# ── Prompt building ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a spam classifier for blues.ru — a Russian-language blues music community forum archive.
The forum ran from roughly 2000–2020. Posts are in Russian and English.

Classify each candidate post as one of:
  spam    — commercial spam unrelated to blues music
  legit   — genuine participation, even if it includes a link
  unsure  — genuinely ambiguous, needs human review

Spam indicators:
- Advertises escorts, casinos, SEO, construction, medical services, etc.
- Generic filler text plus a commercial link
- No connection to blues music or the discussion thread
- Author appears to be a one-time bot

Legit indicators:
- Discusses blues music, musicians, albums, concerts
- Participates in existing thread with relevant content
- Personal opinion or reaction, even brief
- Link is to a music resource, video, or relevant site

IMPORTANT: Output ONLY compact JSON, one object per line, NO other text:
{"i":POST_ID,"v":"spam"}  or  {"i":POST_ID,"v":"legit"}  or  {"i":POST_ID,"v":"unsure"}

Every candidate post_id must appear. No reasons, no explanation, no preamble.
"""


def build_prompt(cands, posts_by_key, key_counts):
    lines = [
        f"Classify these {len(cands)} forum posts. "
        "For each candidate I also show other posts by the same author for context.\n"
        "=" * 70
    ]

    # Group candidates by author key
    cand_ids = {p['post_id'] for p in cands}
    cands_by_key = defaultdict(list)
    for p in cands:
        cands_by_key[author_key(p)].append(p)

    for key in sorted(cands_by_key, key=lambda k: (k[0], str(k[1]))):
        sample = posts_by_key[key][0]
        n = key_counts[key]
        if key[0] == 'id':
            label = f"PersonId={key[1]} name={repr(sample['author'])}"
        else:
            label = f"ANONYMOUS name={repr(key[1])}"
        lines.append(f"\nAUTHOR: {label}  ({n} total post(s))")
        lines.append("-" * 50)

        for p in sorted(posts_by_key[key], key=lambda x: x['date']):
            is_cand = p['post_id'] in cand_ids
            marker = "  *** CANDIDATE — CLASSIFY THIS ***" if is_cand else "  (context only)"
            lines.append(
                f"\n[{p['date']}] post_id={p['post_id']} "
                f"topic={p['topic_id']} {repr(p['topic_title'][:50])}{marker}"
            )
            lines.append(p['text'][:600])

    return "\n".join(lines)


# ── Classify ──────────────────────────────────────────────────────────────────

def cmd_classify():
    import anthropic

    print("Loading posts...", file=sys.stderr)
    all_posts = load_all_posts()
    key_counts = Counter(author_key(p) for p in all_posts)
    posts_by_key = defaultdict(list)
    for p in all_posts:
        posts_by_key[author_key(p)].append(p)

    cands = collect_candidates(all_posts, key_counts)
    print(f"Candidates: {len(cands)}", file=sys.stderr)

    prompt = build_prompt(cands, posts_by_key, key_counts)
    prompt_tokens_est = len(prompt) // 4
    print(f"Prompt size: ~{len(prompt):,} chars / ~{prompt_tokens_est:,} tokens", file=sys.stderr)

    client = anthropic.Anthropic()

    # Split into batches to stay within 8192 output token limit
    # Compact format: ~12 tokens/line × 536 = ~6400 tokens, fits in one batch
    # but keep two batches for safety
    BATCH_SIZE = 300
    batches = [cands[i:i+BATCH_SIZE] for i in range(0, len(cands), BATCH_SIZE)]
    print(f"Splitting into {len(batches)} batch(es) of ≤{BATCH_SIZE}", file=sys.stderr)

    verdicts = {}
    total_in = total_out = 0

    for bi, batch in enumerate(batches):
        prompt = build_prompt(batch, posts_by_key, key_counts)
        print(f"Batch {bi+1}/{len(batches)}: {len(batch)} candidates, "
              f"~{len(prompt)//4:,} tokens...", file=sys.stderr)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        total_in  += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        print(f"  → in={resp.usage.input_tokens:,} out={resp.usage.output_tokens:,}", file=sys.stderr)

        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pid = obj.get('i') or obj.get('post_id')
                v   = obj.get('v') or obj.get('verdict', '')
                if pid is not None:
                    verdicts[pid] = {'verdict': v, 'reason': obj.get('reason', '')}
            except Exception as e:
                print(f"  parse error: {e}: {line[:80]}", file=sys.stderr)

    print(f"Total: in={total_in:,} out={total_out:,}", file=sys.stderr)

    # Attach metadata from candidates
    cands_by_id = {p['post_id']: p for p in cands}
    results = []
    for pid, v in verdicts.items():
        p = cands_by_id.get(pid, {})
        results.append({
            'post_id':    pid,
            'verdict':    v['verdict'],
            'reason':     v['reason'],
            'topic_id':   p.get('topic_id'),
            'topic_title': p.get('topic_title', ''),
            'author':     p.get('author', ''),
            'person_id':  p.get('person_id'),
            'date':       p.get('date', ''),
            'depth':      p.get('depth', 0),
            'reply_count': p.get('reply_count', 0),
            'text':       p.get('text', ''),
        })

    # Merge with any existing results (from a previous partial run)
    if RESULTS_FILE.exists():
        existing = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
        existing_ids = {r['post_id'] for r in existing}
        # Keep existing entries not re-classified, add/overwrite new ones
        new_ids = {r['post_id'] for r in results}
        merged = [r for r in existing if r['post_id'] not in new_ids] + results
        results = merged

    returned_ids = set(verdicts)
    missing = [p['post_id'] for p in cands if p['post_id'] not in returned_ids]
    if missing:
        print(f"Warning: {len(missing)} candidates not in response: {missing[:10]}", file=sys.stderr)
        print(f"Re-run --classify to retry missing (they are not in results file)", file=sys.stderr)

    RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    spam_n   = sum(1 for r in results if r['verdict'] == 'spam')
    unsure_n = sum(1 for r in results if r['verdict'] == 'unsure')
    legit_n  = sum(1 for r in results if r['verdict'] == 'legit')
    print(f"\nResults: {spam_n} spam, {unsure_n} unsure, {legit_n} legit", file=sys.stderr)
    print(f"Saved to {RESULTS_FILE}", file=sys.stderr)
    print("\nRun --report to generate human-readable reports.")


# ── Reports ───────────────────────────────────────────────────────────────────

def write_report(path, entries, title):
    lines = [
        title,
        "=" * 70,
        f"Total: {len(entries)} posts",
        "",
    ]

    # Stats
    authors = Counter()
    for e in entries:
        key = e.get('person_id') or e.get('author') or '?'
        authors[key] += 1
    lines.append(f"Unique authors: {len(authors)}")
    lines.append(f"Top authors: {authors.most_common(5)}")
    lines.append("")

    for e in sorted(entries, key=lambda x: (x.get('topic_id') or 0, x.get('post_id') or 0)):
        lines.append(f"\n{'─' * 60}")
        pid = e.get('post_id')
        tid = e.get('topic_id')
        author = e.get('author', '')
        person_id = e.get('person_id')
        date = e.get('date', '')
        depth = e.get('depth', 0)
        replies = e.get('reply_count', 0)
        title_str = (e.get('topic_title') or '')[:60]
        reason = e.get('reason', '')
        text = e.get('text', '')

        author_str = f"PersonId={person_id} {repr(author)}" if person_id else repr(author)
        lines.append(f"post_id={pid}  topic={tid}  {repr(title_str)}")
        lines.append(f"author: {author_str}  date={date}  depth={depth}  replies={replies}")
        lines.append(f"reason: {reason}")
        lines.append(f"text: {text}")

    path.write_text("\n".join(lines), encoding='utf-8')
    print(f"Wrote {len(entries):3d} entries → {path.name}")


def cmd_retry():
    """Re-classify only candidates missing from spam-results.json."""
    import anthropic

    print("Loading posts...", file=sys.stderr)
    all_posts = load_all_posts()
    key_counts = Counter(author_key(p) for p in all_posts)
    posts_by_key = defaultdict(list)
    for p in all_posts:
        posts_by_key[author_key(p)].append(p)

    cands = collect_candidates(all_posts, key_counts)
    existing_ids = set()
    if RESULTS_FILE.exists():
        existing = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
        existing_ids = {r['post_id'] for r in existing}

    missing_cands = [p for p in cands if p['post_id'] not in existing_ids]
    print(f"Missing candidates: {len(missing_cands)}", file=sys.stderr)
    if not missing_cands:
        print("Nothing to retry.", file=sys.stderr)
        return

    prompt = build_prompt(missing_cands, posts_by_key, key_counts)
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text
    print(f"in={resp.usage.input_tokens:,} out={resp.usage.output_tokens:,}", file=sys.stderr)

    new_verdicts = {}
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            pid = obj.get('i') or obj.get('post_id')
            v   = obj.get('v') or obj.get('verdict', '')
            if pid is not None:
                new_verdicts[pid] = v
        except Exception as e:
            print(f"  parse error: {e}: {line[:80]}", file=sys.stderr)

    cands_by_id = {p['post_id']: p for p in missing_cands}
    new_results = []
    for pid, v in new_verdicts.items():
        p = cands_by_id.get(pid, {})
        new_results.append({
            'post_id':     pid,
            'verdict':     v,
            'reason':      '',
            'topic_id':    p.get('topic_id'),
            'topic_title': p.get('topic_title', ''),
            'author':      p.get('author', ''),
            'person_id':   p.get('person_id'),
            'date':        p.get('date', ''),
            'depth':       p.get('depth', 0),
            'reply_count': p.get('reply_count', 0),
            'text':        p.get('text', ''),
        })

    existing = json.loads(RESULTS_FILE.read_text(encoding='utf-8')) if RESULTS_FILE.exists() else []
    merged = existing + new_results
    RESULTS_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
    still_missing = [p['post_id'] for p in missing_cands if p['post_id'] not in new_verdicts]
    print(f"Added {len(new_results)} results. Still missing: {len(still_missing)}", file=sys.stderr)
    if still_missing:
        print(f"  {still_missing}", file=sys.stderr)


def cmd_report():
    if not RESULTS_FILE.exists():
        print(f"Error: {RESULTS_FILE} not found. Run --classify first.", file=sys.stderr)
        sys.exit(1)

    results = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))

    spam   = [r for r in results if r['verdict'] == 'spam']
    unsure = [r for r in results if r['verdict'] == 'unsure']
    legit  = [r for r in results if r['verdict'] == 'legit']
    other  = [r for r in results if r['verdict'] not in ('spam', 'legit', 'unsure')]

    print(f"Loaded {len(results)} results: {len(spam)} spam, {len(unsure)} unsure, {len(legit)} legit, {len(other)} other")

    write_report(HERE / "spam-report.txt",   spam,   "SPAM POSTS")
    write_report(HERE / "unsure-report.txt", unsure, "UNSURE POSTS — needs human review")
    write_report(HERE / "legit-report.txt",  legit,  "LEGITIMATE POSTS")

    if other:
        write_report(HERE / "other-report.txt", other, "OTHER (unexpected verdict)")

    # Summary
    print(f"\nSummary")
    print(f"  spam:   {len(spam):3d} posts")
    print(f"  unsure: {len(unsure):3d} posts")
    print(f"  legit:  {len(legit):3d} posts")


# ── Apply ─────────────────────────────────────────────────────────────────────

def cmd_apply():
    if not RESULTS_FILE.exists():
        print(f"Error: {RESULTS_FILE} not found. Run --classify first.", file=sys.stderr)
        sys.exit(1)

    results = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
    spam = [r for r in results if r['verdict'] == 'spam']

    print(f"Results loaded: {len(results)} total, {len(spam)} spam")
    resp = input(f"Write {len(spam)} spam IDs to spam-ids.yaml? [y/N] ").strip().lower()
    if resp != 'y':
        sys.exit(0)

    spam_ids = sorted(r['post_id'] for r in spam if r.get('post_id'))
    output = {
        "description": "Confirmed spam post IDs. Applied at generation time to suppress posts+subtrees.",
        "count": len(spam_ids),
        "post_ids": spam_ids,
    }
    SPAM_IDS_OUT.write_text(
        yaml.dump(output, allow_unicode=True, sort_keys=False),
        encoding='utf-8',
    )
    print(f"Wrote {len(spam_ids)} spam IDs to {SPAM_IDS_OUT}")
    print("Run: python3 bluesru-arc/scripts/generate_forum.py to rebuild forum.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Single-request spam classifier using Sonnet")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--classify", action="store_true", help="Call API, save spam-results.json")
    group.add_argument("--retry",   action="store_true", help="Re-classify only missing candidates")
    group.add_argument("--report",  action="store_true", help="Generate report files from saved results")
    group.add_argument("--apply",   action="store_true", help="Write spam-ids.yaml from spam verdicts")
    args = parser.parse_args()

    if args.classify:
        cmd_classify()
    elif args.retry:
        cmd_retry()
    elif args.report:
        cmd_report()
    elif args.apply:
        cmd_apply()


if __name__ == "__main__":
    main()
