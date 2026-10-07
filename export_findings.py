"""
Step 5c — Turn commentary-comparison outputs into readable lists.

For prompts that return {"original_to_<source>": [...], "original_to_<target>": [...],
"shared_traditions": [...]}, writes three text files per run, grouped by chapter:
unique_to_<source>.txt, unique_to_<target>.txt and shared_traditions.txt.

Usage:
    python export_findings.py runs/eusebius_targum/haiku.jsonl --out-dir runs/eusebius_targum/findings \
        --source-name Eusebius --target-name "Targum Isaiah"
"""

import argparse
import json
import os

from connections import load


def pick(parsed, prefix, exclude=()):
    """First non-empty list under a key starting with prefix (e.g. 'original_to_')."""
    for k, v in parsed.items():
        if k.startswith(prefix) and not any(x in k for x in exclude) and v:
            return v
    return []


def fmt(items, shared=False):
    out = []
    for i, it in enumerate(items, 1):
        out += [f"  {i}. [{it.get('theme', 'untitled')}]", f"     {it.get('description', '')}"]
        refs = {k: v for k, v in it.items() if k.endswith("reference") and v}
        out += [f"     {k.replace('_', ' ')}: {v}" for k, v in refs.items()]
        out.append("")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", help="run_prompts.py output (JSONL)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--source-name", required=True)
    ap.add_argument("--target-name", required=True)
    args = ap.parse_args()

    sections = {"source": [], "target": [], "shared": []}
    totals = {k: 0 for k in sections}
    for rec in load(args.output):
        parsed = rec.get("parsed")
        if not isinstance(parsed, dict):
            continue
        ch = rec.get("paired_chapter", rec.get("source_ch"))
        found = {"source": pick(parsed, "original_to_", exclude=("targum", "target")),
                 "target": pick(parsed, "original_to_targum") or pick(parsed, "original_to_target"),
                 "shared": pick(parsed, "shared_")}
        for k, items in found.items():
            if items:
                sections[k] += [f"--- Chapter {ch} ---", *fmt(items)]
                totals[k] += len(items)

    os.makedirs(args.out_dir, exist_ok=True)
    slug = lambda s: s.lower().replace(" ", "_")
    files = {"source": f"unique_to_{slug(args.source_name)}.txt",
             "target": f"unique_to_{slug(args.target_name)}.txt", "shared": "shared_traditions.txt"}
    titles = {"source": f"UNIQUE TO {args.source_name.upper()}", "target": f"UNIQUE TO {args.target_name.upper()}",
              "shared": "SHARED TRADITIONS"}
    for k, name in files.items():
        with open(os.path.join(args.out_dir, name), "w", encoding="utf-8") as f:
            f.write("\n".join([titles[k], f"Total findings: {totals[k]}", "=" * 60, "", *sections[k]]))
    print(f"{args.source_name}: {totals['source']}  {args.target_name}: {totals['target']}  shared: {totals['shared']}"
          f" -> {args.out_dir}")


if __name__ == "__main__":
    main()
