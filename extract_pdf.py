"""
Step 1 — Extract plain text from a PDF edition.

Book page numbers are mapped to PDF pages with --front-matter (pages before
book page 1). Several PDFs can be concatenated in order (e.g. a multi-volume
commentary); text repeated across a volume boundary is detected and dropped.
Lines matching any --drop-line regex (running headers, watermarks) are removed.

Usage:
    python extract_pdf.py --pdf edition.pdf --out work/raw/targum_isaiah.txt --front-matter 12 --start 1 --end 140
    python extract_pdf.py --pdf vol1.pdf vol2.pdf vol3.pdf --out work/raw/commentary.txt --drop-line "^Copyright"
"""

import argparse
import os
import re
from difflib import SequenceMatcher

import pdfplumber


def extract_pages(pdf_path, front_matter=0, start=1, end=None, drop_patterns=()):
    with pdfplumber.open(pdf_path) as pdf:
        first = start + front_matter - 1
        last = min(end + front_matter, len(pdf.pages)) if end else len(pdf.pages)
        pages = []
        for i in range(first, last):
            text = pdf.pages[i].extract_text() or ""
            if drop_patterns:
                text = "\n".join(l for l in text.split("\n") if not any(p.search(l) for p in drop_patterns))
            if text.strip():
                pages.append(text.strip())
    return "\n\n".join(pages)


def append_dedup(combined, new_text, min_overlap=80):
    """Append new_text, skipping its opening if it repeats the end of combined."""
    if not combined:
        return new_text
    tail = " ".join(combined.split()[-300:])
    head = " ".join(new_text.split()[:300])
    m = SequenceMatcher(None, tail, head).find_longest_match(0, len(tail), 0, len(head))
    if m.size > min_overlap:
        overlap = head[m.b:m.b + m.size]
        pos = new_text.find(overlap)
        if pos >= 0:
            skip = pos + len(overlap)
            period = new_text.find(".", skip)
            if 0 <= period - skip < 200:
                skip = period + 1
            new_text = new_text[skip:].strip()
            print(f"  overlap of {m.size} chars removed at volume boundary")
    return combined + "\n\n" + new_text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", nargs="+", required=True, help="One PDF, or several volumes in order")
    ap.add_argument("--out", required=True)
    ap.add_argument("--front-matter", type=int, default=0, help="PDF pages before book page 1")
    ap.add_argument("--start", type=int, default=1, help="First book page")
    ap.add_argument("--end", type=int, default=None, help="Last book page (inclusive)")
    ap.add_argument("--drop-line", action="append", default=[], help="Regex; matching lines are removed")
    args = ap.parse_args()

    drop = [re.compile(p) for p in args.drop_line]
    combined = ""
    for path in args.pdf:
        print(f"Extracting {path}")
        combined = append_dedup(combined, extract_pages(path, args.front_matter, args.start, args.end, drop))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(combined)
    print(f"{len(combined):,} chars -> {args.out}")


if __name__ == "__main__":
    main()
