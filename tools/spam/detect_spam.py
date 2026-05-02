#!/usr/bin/env python3
"""
Forum spam detection for blues.ru archive.

Modes:
  --analyze          Show candidate stats + sample prompt (no API calls)
  --batch-submit     Submit candidates to Claude Haiku Batch API
  --batch-fetch ID   Fetch completed batch results, write spam-review.yaml
  --apply            Build spam-ids.yaml from confirmed entries in spam-review.yaml

Output files (all in this directory):
  spam-review.yaml   Per-post classification for human review
  spam-ids.yaml      Confirmed spam post IDs → copied to bluesru-arc/data/forum/

Usage:
  python3 detect_spam.py --analyze
  python3 detect_spam.py --batch-submit
  python3 detect_spam.py --batch-fetch msgbatch_xxxx
  python3 detect_spam.py --apply
"""

import argparse
import json
import os
import re
import sys
import yaml
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARC  = HERE.parent.parent  # bluesru-arc/ repo root
TOPICS_DIR = ARC / "data" / "forum" / "topics"
REVIEW_FILE = HERE / "spam-review.yaml"
BATCH_STATE = HERE / "spam-batch-state.json"
SPAM_IDS_OUT = ARC / "data" / "forum" / "spam-ids.yaml"

URL_RE = re.compile(r'https?://|\[url=', re.IGNORECASE)

# Pre-filter thresholds
MAX_AUTHOR_POSTS = 5   # authors with more posts than this are considered established
MAX_TEXT_LEN     = 1200  # posts longer than this go to LLM only if clearly spammy


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
            'date':        str(p.get('date', '') or ''),
            'subject':     p.get('subject', '') or '',
            'text':        p.get('text', '') or '',
            'deleted':     p.get('deleted', False),
            'depth':       depth,
            'reply_count': len(p.get('replies', [])),
        })
        flatten_posts(p.get('replies', []), topic_id, topic_title, result, depth + 1)
    return result


def load_all_posts():
    posts = []
    for yf in sorted(TOPICS_DIR.rglob('*.yaml')):
        d = yaml.safe_load(yf.read_text(encoding='utf-8'))
        if not d:
            continue
        tid   = d.get('topic_id')
        title = d.get('title', '') or ''
        flatten_posts(d.get('posts', []), tid, title, posts)
    return posts


def collect_candidates(all_posts, author_counts):
    """Posts that pass heuristic pre-filter for LLM review."""
    cands = []
    for p in all_posts:
        if p['deleted']:
            continue
        text = p['text']
        if not URL_RE.search(text):
            continue
        if author_counts[p['author']] > MAX_AUTHOR_POSTS:
            continue
        if len(text) > MAX_TEXT_LEN:
            continue
        cands.append(p)
    return cands


# ── Prompt building ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a spam classifier for blues.ru — a Russian-language blues music community forum archive.
Classify each post as spam or legitimate.

Spam characteristics:
- Advertises unrelated commercial services (escorts, casinos, SEO, construction, medical)
- Contains commercial links with no blues content
- Text is generic filler ("check this out", "very interesting") plus a link
- Author appears to be a bot or one-time visitor

Legitimate characteristics:
- Discusses blues music, musicians, albums, concerts
- Even if it includes a link, the context is blues-related
- Expresses personal opinion or participates in discussion

Respond with JSON only, no other text:
{"spam": true|false, "reason": "one sentence"}
"""


def build_user_message(p, author_post_count):
    return (
        f"Topic: {p['topic_title']}\n"
        f"Author: {p['author']} (has posted {author_post_count} time(s) in this forum)\n"
        f"Date: {p['date']}\n"
        f"Post:\n{p['text']}"
    )


# ── Modes ─────────────────────────────────────────────────────────────────────

def cmd_analyze(args):
    print("Loading forum posts...")
    all_posts = load_all_posts()
    author_counts = Counter(p['author'] for p in all_posts)

    cands = collect_candidates(all_posts, author_counts)

    total_non_deleted = sum(1 for p in all_posts if not p['deleted'])
    deleted_count     = sum(1 for p in all_posts if p['deleted'])
    url_count         = sum(1 for p in all_posts if not p['deleted'] and URL_RE.search(p['text']))

    print(f"\n{'='*60}")
    print(f"Forum post statistics")
    print(f"{'='*60}")
    print(f"Total posts:              {len(all_posts):,}")
    print(f"  Already deleted:        {deleted_count:,}")
    print(f"  Non-deleted with URL:   {url_count:,}")
    print(f"  Candidates for LLM:     {len(cands):,}  "
          f"(URL + author ≤{MAX_AUTHOR_POSTS} posts + text ≤{MAX_TEXT_LEN} chars)")

    # Breakdown by depth
    roots   = [c for c in cands if c['depth'] == 0]
    replies = [c for c in cands if c['depth'] > 0]
    print(f"    Root posts:           {len(roots):,}")
    print(f"    Reply posts:          {len(replies):,}")

    # Candidates with replies (subtree question)
    has_replies = [c for c in cands if c['reply_count'] > 0]
    print(f"  Candidates with replies:{len(has_replies):,}  ← subtree question")

    # Haiku cost estimate
    avg_chars = sum(len(c['text']) for c in cands) / max(len(cands), 1)
    est_tokens = len(cands) * (len(SYSTEM_PROMPT) // 4 + int(avg_chars) // 4 + 50)
    print(f"\nEstimated Haiku cost:     ${est_tokens / 1_000_000 * 0.8 * 0.5:.3f}  "
          f"(batch API, ~{est_tokens:,} tokens)")

    # Sample prompts for review
    print(f"\n{'='*60}")
    print(f"Sample of what gets sent to LLM  (first 5 candidates)")
    print(f"{'='*60}")
    for i, c in enumerate(cands[:5]):
        n = author_counts[c['author']]
        print(f"\n--- [{i+1}] post_id={c['post_id']} topic={c['topic_id']} "
              f"depth={c['depth']} replies={c['reply_count']} ---")
        print("USER MESSAGE:")
        print(build_user_message(c, n))
        print()

    # Candidates that have replies (subtree impact)
    if has_replies:
        print(f"\n{'='*60}")
        print(f"Candidates with replies (subtree decision)")
        print(f"{'='*60}")
        for c in has_replies[:5]:
            n = author_counts[c['author']]
            print(f"  post {c['post_id']} in topic {c['topic_id']} "
                  f"| {c['reply_count']} replies | author '{c['author']}' ({n} posts)")
            print(f"  text: {c['text'][:120]}")
            print()

    # Deleted post sample (potential training signal)
    deleted_with_url = [p for p in all_posts if p['deleted'] and URL_RE.search(p['text'])]
    print(f"\n{'='*60}")
    print(f"Deleted posts with URLs (ground-truth spam, {len(deleted_with_url)} total)")
    print(f"{'='*60}")
    for p in deleted_with_url[:5]:
        print(f"  post {p['post_id']} | '{p['author']}' | {p['date']}")
        print(f"  {p['text'][:150]}")
        print()


def cmd_batch_submit(args):
    import anthropic

    print("Loading forum posts...")
    all_posts = load_all_posts()
    author_counts = Counter(p['author'] for p in all_posts)
    cands = collect_candidates(all_posts, author_counts)
    print(f"Candidates: {len(cands)}")

    client = anthropic.Anthropic()
    batch_requests = [
        {
            "custom_id": f"post_{c['post_id']}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 100,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": build_user_message(c, author_counts[c['author']])}],
            },
        }
        for c in cands
    ]

    print(f"Submitting batch of {len(batch_requests)} requests to Claude Haiku...")
    batch = client.messages.batches.create(requests=batch_requests)
    print(f"Batch ID: {batch.id}")
    print(f"Status:   {batch.processing_status}")

    # Save state for fetch step
    BATCH_STATE.write_text(json.dumps({
        "batch_id": batch.id,
        "candidates": [
            {k: c[k] for k in ('post_id', 'topic_id', 'topic_title',
                                'author', 'date', 'text', 'depth', 'reply_count')}
            for c in cands
        ],
        "author_counts": dict(author_counts.most_common()),
    }, ensure_ascii=False, indent=2))
    print(f"\nSaved state to {BATCH_STATE}")
    print(f"Poll with: python3 detect_spam.py --batch-fetch {batch.id}")


def cmd_batch_fetch(args):
    import anthropic

    batch_id = args.batch_id
    if not batch_id and BATCH_STATE.exists():
        state = json.loads(BATCH_STATE.read_text())
        batch_id = state.get("batch_id")
    if not batch_id:
        print("Error: no batch ID. Run --batch-submit first or pass batch ID.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)
    print(f"Batch {batch_id}: {batch.processing_status}")
    if batch.processing_status != "ended":
        print("Not ready yet. Try again later.")
        return

    # Load candidate metadata
    state = json.loads(BATCH_STATE.read_text()) if BATCH_STATE.exists() else {}
    cands_by_id = {f"post_{c['post_id']}": c for c in state.get("candidates", [])}
    author_counts = state.get("author_counts", {})

    results = []
    spam_count = 0
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        c = cands_by_id.get(cid, {})
        if result.result.type == "succeeded":
            raw = result.result.message.content[0].text.strip()
            try:
                parsed = json.loads(raw)
                is_spam = parsed.get("spam", False)
                reason  = parsed.get("reason", "")
            except json.JSONDecodeError:
                is_spam = "spam" in raw.lower()
                reason  = raw[:120]
        else:
            is_spam = None
            reason  = f"error: {result.result.type}"

        if is_spam:
            spam_count += 1

        n = author_counts.get(c.get('author', ''), 0)
        results.append({
            "post_id":     c.get("post_id"),
            "topic_id":    c.get("topic_id"),
            "topic_title": c.get("topic_title"),
            "author":      c.get("author"),
            "author_posts": n,
            "date":        c.get("date"),
            "depth":       c.get("depth", 0),
            "reply_count": c.get("reply_count", 0),
            "text":        c.get("text"),
            "llm_spam":    is_spam,
            "llm_reason":  reason,
            "confirmed":   None,  # fill in manually: true / false
        })

    # Sort spam first, then by topic/post
    results.sort(key=lambda r: (0 if r["llm_spam"] else 1, r["topic_id"] or 0, r["post_id"] or 0))

    REVIEW_FILE.write_text(
        yaml.dump(results, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding='utf-8',
    )
    print(f"\nResults: {len(results)} total, {spam_count} classified as spam")
    print(f"Review file: {REVIEW_FILE}")
    print(f"\nNext: review {REVIEW_FILE.name}, set confirmed: true/false")
    print(f"Then run: python3 detect_spam.py --apply")


def cmd_apply(args):
    if not REVIEW_FILE.exists():
        print(f"Error: {REVIEW_FILE} not found. Run --batch-fetch first.", file=sys.stderr)
        sys.exit(1)

    entries = yaml.safe_load(REVIEW_FILE.read_text(encoding='utf-8')) or []
    confirmed_spam = [e for e in entries if e.get("confirmed") is True]
    unreviewed     = [e for e in entries if e.get("confirmed") is None]

    print(f"Total entries:    {len(entries)}")
    print(f"Confirmed spam:   {len(confirmed_spam)}")
    print(f"Unreviewed:       {len(unreviewed)}")

    if unreviewed:
        print(f"\nWarning: {len(unreviewed)} entries still unreviewed (confirmed: null).")
        resp = input("Continue anyway? [y/N] ").strip().lower()
        if resp != 'y':
            sys.exit(0)

    spam_ids = sorted(e["post_id"] for e in confirmed_spam if e.get("post_id"))
    output = {
        "description": "Confirmed spam post IDs. Applied at generation time to suppress posts+subtrees.",
        "count": len(spam_ids),
        "post_ids": spam_ids,
    }
    SPAM_IDS_OUT.write_text(
        yaml.dump(output, allow_unicode=True, sort_keys=False),
        encoding='utf-8',
    )
    print(f"\nWrote {len(spam_ids)} spam IDs to {SPAM_IDS_OUT}")
    print("Run generate.py --section forum to rebuild with spam filtered.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Forum spam detection")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--analyze",       action="store_true")
    group.add_argument("--batch-submit",  action="store_true")
    group.add_argument("--batch-fetch",   metavar="BATCH_ID", nargs="?", const="")
    group.add_argument("--apply",         action="store_true")
    args = parser.parse_args()

    if args.analyze:
        cmd_analyze(args)
    elif args.batch_submit:
        cmd_batch_submit(args)
    elif args.batch_fetch is not None:
        args.batch_id = args.batch_fetch
        cmd_batch_fetch(args)
    elif args.apply:
        cmd_apply(args)


if __name__ == "__main__":
    main()
