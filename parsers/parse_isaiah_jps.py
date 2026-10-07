"""
Parse the JPS 1917 English translation of a biblical book (PDF) into one chunk per chapter.

Chapter numbers in this edition are large drop-cap digits (font size >= 18);
verse numbers are small. Every word is assigned to the chapter whose drop-cap
most recently precedes it on the page, so no verse-number guessing is needed.

Usage:
    python parsers/parse_isaiah_jps.py --pdf path/to/jps1917_isaiah.pdf --name isaiah_jps --out work/chunks/isaiah_jps_chunks_regex.json
"""

import argparse
import json
import os
import re

import pdfplumber

DROPCAP_MIN_SIZE = 18  # chapter digits render at ~30pt, verse numbers at ~11pt
FOOTER_TOP = 560       # page-number footer sits below this y-position


def dropcaps(page):
    """[(chapter, top)] for the drop-cap chapter numbers on a page; adjacent digits are merged."""
    digits = sorted((c for c in page.chars if c["text"].isdigit() and round(c["size"], 1) >= DROPCAP_MIN_SIZE),
                    key=lambda c: (round(c["top"], 1), c["x0"]))
    groups, i = [], 0
    while i < len(digits):
        j = i + 1
        while (j < len(digits) and abs(digits[j]["top"] - digits[i]["top"]) < 3
               and digits[j]["x0"] - digits[j - 1]["x1"] < 6):
            j += 1
        groups.append((int("".join(c["text"] for c in digits[i:j])), digits[i]["top"]))
        i = j
    return groups


def clean_text(words):
    text = " ".join(words)
    text = re.sub(r"\bL\s+ORD\b", "LORD", text)  # small-caps split
    text = re.sub(r"\bG\s+OD\b", "GOD", text)
    return re.sub(r"\s+", " ", text).strip()


def parse(pdf_path):
    chapters, cur = {}, None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            caps = dropcaps(page)
            words = sorted((w for w in page.extract_words() if w["top"] < FOOTER_TOP),
                           key=lambda w: (round(w["top"], 1), w["x0"]))
            ci = 0
            for w in words:
                while ci < len(caps) and w["top"] >= caps[ci][1] - 2:
                    cur = caps[ci][0]
                    chapters.setdefault(cur, [])
                    ci += 1
                if cur is not None:
                    chapters[cur].append(w["text"])
    return chapters


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--name", default="isaiah_jps")
    ap.add_argument("--out", default="work/chunks/isaiah_jps_chunks_regex.json")
    args = ap.parse_args()

    chapters = parse(args.pdf)
    chunks = []
    for ch in sorted(chapters):
        body = clean_text(chapters[ch])
        chunks.append({"id": f"{args.name}_ch{ch}", "chunk_num": ch - 1, "chapters": str(ch), "text": body,
                       "word_count": len(body.split()),
                       "verse_markers": len(re.findall(r"(?<!\d)(\d{1,3})(?=[A-Z])", body))})

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"source": args.name, "mode": "regex", "n_chunks": len(chunks), "chunks": chunks},
                  f, ensure_ascii=False, indent=2)

    found = [int(c["chapters"]) for c in chunks]
    print(f"{len(chunks)} chapters ({min(found)}..{max(found)}), in order: {found == list(range(1, len(found) + 1))}"
          f" -> {args.out}")


if __name__ == "__main__":
    main()
