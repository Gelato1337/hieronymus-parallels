"""
Step 5a — Score prompt variants on the labelled eval set.

Per output file: recall on the known parallels, false-positive rate on the
random pairs, and precision.

Usage:
    python score_eval.py runs/eval/a.jsonl runs/eval/b.jsonl runs/eval/c.jsonl
"""

import argparse
import json
import os

from connections import load, normalize


def score(records):
    gold = [r for r in records if r.get("label")]
    rand = [r for r in records if r.get("label") is False]
    hit = lambda r: normalize(r)[0]
    tp, fp = sum(map(hit, gold)), sum(map(hit, rand))
    return {"gold_total": len(gold), "gold_recovered": tp, "recall": round(tp / len(gold), 3) if gold else 0.0,
            "random_total": len(rand), "false_positives": fp, "fp_rate": round(fp / len(rand), 3) if rand else 0.0,
            "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
            "missed": [r["pair_id"] for r in gold if not hit(r)],
            "false_positive_pairs": [r["pair_id"] for r in rand if hit(r)]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outputs", nargs="+")
    ap.add_argument("--summary", help="Optional JSON file for the full results")
    args = ap.parse_args()

    results = {}
    print(f"{'variant':<24}{'recall':>8}{'fp_rate':>9}{'precision':>11}")
    for path in args.outputs:
        name = os.path.splitext(os.path.basename(path))[0]
        results[name] = s = score(load(path))
        print(f"{name:<24}{s['recall']:>8.3f}{s['fp_rate']:>9.3f}{s['precision']:>11.3f}")
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
