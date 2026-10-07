"""
Build the 100-pair evaluation set for 1 Enoch x Isaiah: 10 known parallels
(positives) and 90 random chapter pairs (presumed negatives).

Only chapter numbers and labels are stored; build_prompts.py --pairs renders the texts.
Verse references in the notes are for the record — the model always sees full chapters.

Usage:
    python build_eval_set.py --source work/chunks/enoch_chunks_regex.json --target work/chunks/isaiah_jps_chunks_regex.json \
        --out work/eval/enoch_isaiah_eval_100.json
"""

import argparse
import json
import os
import random

GOLD = [
    ("49", "11", "1 En 49:3 spirit of wisdom and understanding on the Chosen One / Isa 11:2-3"),
    ("61", "11", "1 En 61:11 / Isa 11:2-3 spirit of the Lord"),
    ("14", "6", "1 En 14:18 throne vision / Isa 6 throne and seraphim"),
    ("48", "49", "1 En 48 Son of Man named before creation / Isa 49:1-8 servant named from the womb"),
    ("62", "49", "1 En 62 / Isa 49:1-6 the chosen one before the nations"),
    ("1", "24", "1 En 1:5 / Isa 24:21-23 punishment of the host of heaven"),
    ("91", "65", "1 En 91:16 new heaven / Isa 65:17 new heavens and new earth"),
    ("91", "66", "1 En 91:16 new heaven / Isa 66:22 new heavens endure"),
    ("45", "65", "1 En 45:4-5 renewed heaven and earth / Isa 65:17"),
    ("45", "66", "1 En 45:4-5 renewed heaven and earth / Isa 66:22"),
]


def chapters(path):
    with open(path, encoding="utf-8") as f:
        return [str(c["chapters"]) for c in json.load(f)["chunks"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="work/eval/enoch_isaiah_eval_100.json")
    args = ap.parse_args()

    src, tgt = chapters(args.source), chapters(args.target)
    gold = [{"source_ch": s, "target_ch": t, "label": True, "note": n}
            for s, t, n in GOLD if s in src and t in tgt]
    gold_keys = {(g["source_ch"], g["target_ch"]) for g in gold}

    random.seed(args.seed)
    candidates = [(s, t) for s in src for t in tgt if (s, t) not in gold_keys]
    rand = [{"source_ch": s, "target_ch": t, "label": False, "note": ""}
            for s, t in random.sample(candidates, args.n - len(gold))]
    pairs = gold + rand
    random.shuffle(pairs)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"n": len(pairs), "n_positive": len(gold), "pairs": pairs}, f, indent=2)
    print(f"{len(gold)} positives + {len(rand)} random pairs -> {args.out}")


if __name__ == "__main__":
    main()
