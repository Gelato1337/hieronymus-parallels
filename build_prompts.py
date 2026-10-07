"""
Step 3 — Pair source and target chunks and render one prompt per pair.

Pairing:
  cross   every source chunk x every target chunk (e.g. 108 Enoch x 66 Isaiah = 7,128)
  paired  only chunks that cover the same chapter (uses `chapter_map`, so a commentary
          section covering Gen 45-47 pairs with Targum chapters 45, 46 and 47)

Template placeholders:
  {source_text} {target_text}      the two chunks
  {source_label} {target_label}    --source-label / --target-label, or the chunk's chapter number
  {context_text}                   paired mode: the --context chunk for the same chapter
                                   (e.g. the biblical text as a baseline)

--pairs restricts the output to the labelled pairs of an eval set (see build_eval_set.py).

Output: JSONL, one {"pair_id", "source_ch", "target_ch", "paired_chapter", "label"?, "prompt"} per line.

Usage:
    python build_prompts.py --source work/chunks/enoch_chunks_regex.json --target work/chunks/isaiah_jps_chunks_regex.json \
        --template prompts/enoch_vs_isaiah_a.txt --pairing cross --out work/prompts/enoch_isaiah_a.jsonl
    python build_prompts.py --source work/chunks/commentary_isaiah_chunks_regex.json --target work/chunks/targum_isaiah_chunks_regex.json \
        --context work/chunks/isaiah_jps_chunks_regex.json --chapters 2-3,6,13-14 --pairing paired \
        --source-label "Eusebius's Commentary" --target-label "Targum Isaiah" \
        --template prompts/eusebius_vs_targum_isaiah.txt --out work/prompts/eusebius_targum.jsonl
"""

import argparse
import json
import os


def parse_chapters(spec):
    """'1-3,7,10-12' -> {'1','2','3','7','10','11','12'}; None -> None (all)."""
    if not spec:
        return None
    out = set()
    for part in (p.strip() for p in spec.split(",")):
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.update(str(c) for c in range(int(lo), int(hi) + 1))
        else:
            out.add(part)
    return out


def item_chapters(chunk):
    if isinstance(chunk.get("chapter_map"), list) and chunk["chapter_map"]:
        return {str(c) for c in chunk["chapter_map"]}
    s = str(chunk.get("chapters", ""))
    return set() if s in ("", "preamble") else {c.strip() for c in s.split(",") if c.strip()}


def load_chunks(path, allowed):
    with open(path, encoding="utf-8") as f:
        chunks = json.load(f)["chunks"]
    return [c for c in chunks if allowed is None or item_chapters(c) & allowed]


def fill(template, src, tgt, src_label, tgt_label, context=None):
    p = (template.replace("{source_text}", src["text"]).replace("{target_text}", tgt["text"])
                 .replace("{source_label}", src_label or str(src.get("chapters", "")))
                 .replace("{target_label}", tgt_label or str(tgt.get("chapters", ""))))
    return p.replace("{context_text}", context) if context is not None else p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--pairing", choices=["cross", "paired"], default="cross")
    ap.add_argument("--chapters", help="Chapter filter for both sides, e.g. '1-50' or '2-3,6'")
    ap.add_argument("--context", help="Paired mode: chunk file injected as {context_text}")
    ap.add_argument("--source-label")
    ap.add_argument("--target-label")
    ap.add_argument("--pairs", help="Eval set JSON; only its pairs are rendered and labels are kept")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    allowed = parse_chapters(args.chapters)
    sources, targets = load_chunks(args.source, allowed), load_chunks(args.target, allowed)
    with open(args.template, encoding="utf-8") as f:
        template = f.read()

    records = []
    if args.pairing == "cross":
        labels = None
        if args.pairs:
            with open(args.pairs, encoding="utf-8") as f:
                labels = {(p["source_ch"], p["target_ch"]): p["label"] for p in json.load(f)["pairs"]}
        for s in sources:
            for t in targets:
                key = (str(s["chapters"]), str(t["chapters"]))
                if labels is not None and key not in labels:
                    continue
                rec = {"pair_id": f"S{key[0]}xT{key[1]}", "source_ch": key[0], "target_ch": key[1]}
                if labels is not None:
                    rec["label"] = labels[key]
                rec["prompt"] = fill(template, s, t, args.source_label, args.target_label)
                records.append(rec)
    else:
        context = {}
        if args.context:
            for c in load_chunks(args.context, allowed):
                for ch in item_chapters(c):
                    context[ch] = c["text"]
        src_by_ch, tgt_by_ch = {}, {}
        for s in sources:
            for ch in item_chapters(s):
                src_by_ch.setdefault(ch, []).append(s)
        for t in targets:
            for ch in item_chapters(t):
                tgt_by_ch.setdefault(ch, []).append(t)
        for ch in sorted(set(src_by_ch) & set(tgt_by_ch), key=lambda x: int(x) if x.isdigit() else 0):
            ctx = context.get(ch, f"[No context available for chapter {ch}]") if args.context else None
            for s in src_by_ch[ch]:
                for t in tgt_by_ch[ch]:
                    records.append({"pair_id": f"ch{ch}_{s['id']}x{t['id']}", "source_ch": s["chapters"],
                                    "target_ch": t["chapters"], "paired_chapter": ch,
                                    "prompt": fill(template, s, t, args.source_label, args.target_label, ctx)})

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(sources)} source x {len(targets)} target chunks, {args.pairing} -> {len(records)} prompts -> {args.out}")


if __name__ == "__main__":
    main()
