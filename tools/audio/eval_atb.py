#!/usr/bin/env python3
"""
Evaluate ATB transcript block boundaries against a golden reference.

Usage:
    python3 eval_atb.py <golden.txt> <transcript.md> [--prompt NAME] [--tol 10]
    python3 eval_atb.py golden/atb-2021-07-12-lj-hunter.txt outputs/v01/atb-2021-07-12-lj-hunter.md
    python3 eval_atb.py golden/atb-2021-07-12-lj-hunter.txt outputs/v01/atb-2021-07-12-lj-hunter.md --prompt v01_baseline

Golden format (one entry per line):
    MM:SS type     (type = "music" or "speech")

Metrics:
    recall    = fraction of golden boundaries with a predicted match within tolerance
    precision = fraction of predicted boundaries (within annotation window) matching golden
    avg_off   = mean |predicted - golden| in seconds for matched pairs
"""

import json
import re
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def parse_time(t: str) -> int:
    parts = list(map(int, t.strip().split(":")))
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] * 60 + parts[1]


def fmt_time(sec: int) -> str:
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


def load_golden(path: str) -> list[tuple[int, str]]:
    blocks = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            blocks.append((parse_time(parts[0]), parts[1]))
    return blocks


def load_predicted(path: str) -> list[tuple[int, str]]:
    """Extract block start times from a transcript .md file."""
    text = Path(path).read_text(encoding="utf-8")
    blocks = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'<a id="t(\d+)"></a>', line)
        if m:
            blocks.append((int(m.group(1)), "speech"))
            continue
        m = re.match(r'\*\*\[MUSIC:\s*([0-9:]+)\s*[–-]\s*([0-9:]+)\]\*\*', line)
        if m:
            blocks.append((parse_time(m.group(1)), "music"))
    return sorted(blocks)


def evaluate(golden: list, predicted: list, tol: int = 10) -> dict:
    """Compute precision, recall, avg offset per block type."""
    # Annotation window: 0 to last golden time + 60s
    window_end = max(g[0] for g in golden) + 60 if golden else 0

    results = {}
    for btype in ("speech", "music"):
        g_list = sorted(t for t, tp in golden if tp == btype)
        p_list = sorted(t for t, tp in predicted if tp == btype and t <= window_end)

        # For each golden, find closest predicted
        tp_g = []  # (golden_t, pred_t, offset) for hits
        fn = []    # golden_t for misses
        used_pred = set()

        for gt in g_list:
            best = min(p_list, key=lambda pt: abs(pt - gt), default=None)
            if best is not None and abs(best - gt) <= tol:
                tp_g.append((gt, best, abs(best - gt)))
                used_pred.add(best)
            else:
                fn.append(gt)

        # For each predicted, find closest golden
        tp_p = []  # predicted hits
        fp = []    # predicted misses

        for pt in p_list:
            best = min(g_list, key=lambda gt: abs(gt - pt), default=None)
            if best is not None and abs(best - pt) <= tol:
                tp_p.append(pt)
            else:
                fp.append(pt)

        n_golden = len(g_list)
        n_pred = len(p_list)
        n_tp_g = len(tp_g)
        n_tp_p = len(tp_p)

        recall    = n_tp_g / n_golden if n_golden else 1.0
        precision = n_tp_p / n_pred   if n_pred   else 1.0
        avg_off   = sum(o for _, _, o in tp_g) / len(tp_g) if tp_g else 0.0

        results[btype] = {
            "recall":     round(recall, 3),
            "precision":  round(precision, 3),
            "avg_off_sec": round(avg_off, 1),
            "n_golden":   n_golden,
            "n_predicted": n_pred,
            "hits":       n_tp_g,
            "fn_times":   [fmt_time(t) for t in fn],
            "fp_times":   [fmt_time(t) for t in fp],
            "hit_offsets": [(fmt_time(g), fmt_time(p), o) for g, p, o in tp_g],
        }

    return results


def print_report(results: dict, golden_path: str, pred_path: str, prompt: str, tol: int):
    print(f"\n{'='*60}")
    print(f"Golden:    {golden_path}")
    print(f"Predicted: {pred_path}")
    print(f"Prompt:    {prompt}")
    print(f"Tolerance: ±{tol}s")
    print(f"{'='*60}")
    for btype in ("speech", "music"):
        r = results[btype]
        print(f"\n{btype.upper()}")
        print(f"  recall    {r['recall']:.0%}  ({r['hits']}/{r['n_golden']} golden matched)")
        print(f"  precision {r['precision']:.0%}  ({r['hits']}/{r['n_predicted']} predicted matched)")
        print(f"  avg_off   {r['avg_off_sec']:.1f}s  (for hits)")
        if r['fn_times']:
            print(f"  MISSED golden: {', '.join(r['fn_times'])}")
        if r['fp_times']:
            print(f"  FALSE POS:     {', '.join(r['fp_times'])}")
    print()


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)

    golden_path = args[0]
    pred_path   = args[1]
    prompt_name = ""
    tol = 10

    i = 2
    while i < len(args):
        if args[i] == "--prompt" and i + 1 < len(args):
            prompt_name = args[i + 1]; i += 2
        elif args[i] == "--tol" and i + 1 < len(args):
            tol = int(args[i + 1]); i += 2
        else:
            i += 1

    if not prompt_name:
        prompt_name = Path(pred_path).parent.name  # infer from output dir name

    golden    = load_golden(golden_path)
    predicted = load_predicted(pred_path)
    results   = evaluate(golden, predicted, tol)

    print_report(results, golden_path, pred_path, prompt_name, tol)

    # Save JSON
    slug = Path(pred_path).stem
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{prompt_name}__{slug}.json"
    payload = {
        "episode": slug,
        "prompt":  prompt_name,
        "golden":  golden_path,
        "predicted": pred_path,
        "tolerance_sec": tol,
        "results": results,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
