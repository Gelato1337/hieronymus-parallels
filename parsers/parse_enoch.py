"""
Parse a 1 Enoch translation PDF (Nickelsburg & VanderKam layout) into one chunk per chapter.

Each chapter keeps two streams:
  text       verse text with running headers, footers and page numbers removed
  footnotes  the textual apparatus lines for that chapter, kept apart from the text

Chapter detection: a flush-left "N:1" opens chapter N. It tolerates a leading "{"
or "<" and a footnote letter glued to the verse number ("74:1c"). Any other
flush-left "N:V" (e.g. after a page break) also sets the current chapter.

Usage:
    python parsers/parse_enoch.py --pdf path/to/1enoch.pdf --body-start 28 --out work/chunks/enoch_chunks_regex.json
"""

import argparse
import json
import os
import re

import pdfplumber

RE_RUNHEADER = re.compile(r"^\s*(?:\d{1,3}\s+)?1\s*Enoch\s+\d+.*$", re.IGNORECASE)
RE_FOOTER = re.compile(r"EEnnoocch|iinndddd|\bindd\b", re.IGNORECASE)  # garbled running footer
RE_PAGENUM = re.compile(r"^\s*\d{1,3}\s*$")
RE_OPENER = re.compile(r"^\s*[\{<]?(\d{1,3}):1(?![0-9])[a-z]?\s*[/]?\s")
RE_CHAPVERSE = re.compile(r"^\s*[\{<]?(\d{1,3}):(\d{1,3})[a-z]?\s*[/]?\s")
RE_BAREVERSE = re.compile(r"^\s*(\d{1,3})\s*/?\s")
RE_FOOTNOTE = re.compile(r"^([a-z])\s+(\S.*)$")  # "a Mss read ..." — a letter, not a verse number


def is_noise(line):
    return not line.strip() or RE_RUNHEADER.match(line) or RE_FOOTER.search(line) or RE_PAGENUM.match(line)


def parse(pdf_path, body_start):
    with pdfplumber.open(pdf_path) as pdf:
        pages = [pdf.pages[i].extract_text() or "" for i in range(body_start, len(pdf.pages))]

    chapters, cur, in_footnote = {}, None, False

    def ensure(ch):
        chapters.setdefault(ch, {"text": [], "footnotes": []})

    for page in pages:
        for raw in page.splitlines():
            s = raw.rstrip()
            if is_noise(s):
                continue

            if m := RE_OPENER.match(s):
                cur = int(m.group(1)); ensure(cur); in_footnote = False
                chapters[cur]["text"].append(s.lstrip("{< ").rstrip())
                continue

            if (mf := RE_FOOTNOTE.match(s)) and cur is not None:
                chapters[cur]["footnotes"].append((mf.group(1), mf.group(2).strip()))
                in_footnote = True
                continue

            # Lines after a footnote that don't start with a number continue that footnote
            if in_footnote and cur is not None and not re.match(r"^\s*[\{<]?\d", s):
                if chapters[cur]["footnotes"]:
                    mk, note = chapters[cur]["footnotes"][-1]
                    chapters[cur]["footnotes"][-1] = (mk, f"{note} {s.strip()}".strip())
                continue

            if m := RE_CHAPVERSE.match(s):
                cur = int(m.group(1)); ensure(cur); in_footnote = False
                chapters[cur]["text"].append(s.lstrip("{< ").rstrip())
                continue

            if cur is not None:
                in_footnote = False
                chapters[cur]["text"].append(s)

    chunks = []
    for i, ch in enumerate(sorted(chapters)):
        body = "\n".join(chapters[ch]["text"]).strip()
        notes = [{"marker": mk, "note": n} for mk, n in chapters[ch]["footnotes"]]
        chunks.append({"id": f"enoch_ch{ch}", "chunk_num": i, "chapters": str(ch), "text": body,
                       "footnotes": notes, "word_count": len(body.split()), "footnote_count": len(notes)})
    return chunks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--body-start", type=int, default=28, help="0-indexed PDF page where chapter 1 begins")
    ap.add_argument("--out", default="work/chunks/enoch_chunks_regex.json")
    args = ap.parse_args()

    chunks = parse(args.pdf, args.body_start)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"source": "enoch", "mode": "regex", "n_chunks": len(chunks), "chunks": chunks},
                  f, ensure_ascii=False, indent=2)

    found = [int(c["chapters"]) for c in chunks]
    missing = [c for c in range(min(found), max(found) + 1) if c not in found]
    print(f"{len(chunks)} chapters ({min(found)}..{max(found)}), missing: {missing} -> {args.out}")


if __name__ == "__main__":
    main()
