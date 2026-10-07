"""
Step 5b — Combine several prompt variants' runs over the same pairs into an ensemble.

For every pair, counts how many variants flagged a connection (votes), then writes
  <out-dir>/agreement.json             vote histogram + every flagged pair with each variant's parallels
  <out-dir>/connections_ranked.txt     flagged pairs ordered by votes, with the quoted evidence

Note that one underlying parallel can appear once per variant with different wording,
so count pairs, not individual claims.

Usage:
    python aggregate_ensemble.py runs/enoch_isaiah/a.jsonl runs/enoch_isaiah/b.jsonl ... --out-dir runs/enoch_isaiah
"""

import argparse
import json
import os
from collections import Counter

from connections import load, normalize


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outputs", nargs="+", help="One run_prompts.py output per prompt variant")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--source-name", default="SOURCE")
    ap.add_argument("--target-name", default="TARGET")
    args = ap.parse_args()

    variants = [os.path.splitext(os.path.basename(p))[0] for p in args.outputs]
    n = len(variants)
    agg = {}
    for name, path in zip(variants, args.outputs):
        for rec in load(path):
            conn, pars = normalize(rec)
            a = agg.setdefault(rec["pair_id"], {"pair_id": rec["pair_id"], "source_ch": rec["source_ch"],
                                                "target_ch": rec["target_ch"], "votes": 0, "by_variant": {}})
            a["by_variant"][name] = {"connection": conn, "parallels": pars}
            a["votes"] += conn

    def order(a):
        return (-a["votes"], *(int(x) if str(x).isdigit() else 0 for x in (a["source_ch"], a["target_ch"])))

    flagged = sorted((a for a in agg.values() if a["votes"]), key=order)
    hist = Counter(a["votes"] for a in agg.values())
    summary = {"variants": variants, "n_pairs": len(agg), "vote_histogram": {k: hist.get(k, 0) for k in range(n + 1)},
               "unanimous": hist.get(n, 0), "majority": sum(hist.get(k, 0) for k in range(n // 2 + 1, n + 1)),
               "any": len(flagged)}

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "agreement.json"), "w", encoding="utf-8") as f:
        json.dump({**summary, "flagged": flagged}, f, ensure_ascii=False, indent=2)

    lines = ["=" * 74, f"{args.source_name} x {args.target_name} — ensemble connections ranked by agreement", "=" * 74,
             f"prompt variants ({n}): {', '.join(variants)}", f"pairs compared: {len(agg)}",
             f"unanimous ({n}/{n}): {summary['unanimous']}   majority (>={n // 2 + 1}/{n}): {summary['majority']}"
             f"   any (>=1/{n}): {summary['any']}", ""]
    lines += [f"  {v}/{n}: {hist.get(v, 0)}" for v in range(n, 0, -1)]
    current = None
    for a in flagged:
        if a["votes"] != current:
            current = a["votes"]
            lines += ["", f"########## {current}/{n} AGREEMENT ##########"]
        yes = [v for v in variants if a["by_variant"].get(v, {}).get("connection")]
        lines += ["", f"{args.source_name} {a['source_ch']}  x  {args.target_name} {a['target_ch']}"
                      f"    [{a['votes']}/{n}]  yes: {', '.join(yes)}", "-" * 50]
        for v in yes:
            for p in a["by_variant"][v]["parallels"]:
                lines.append(f"  ({v} | {p.get('confidence', '')})")
                lines += [f"    {k}: {val}" for k, val in p.items() if k != "confidence"]

    with open(os.path.join(args.out_dir, "connections_ranked.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
