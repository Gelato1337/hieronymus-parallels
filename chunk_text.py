"""
Step 2 — Split extracted text into one chunk per chapter.

Modes:
  regex       split where a chapter marker matches --pattern (group 1 = chapter,
              optional group 2 = verse); one chunk per chapter
  section     split at section headers that name the chapters they cover, e.g.
              "Section XL [Gen 45-47]"; group 1 = roman section number,
              group 2 = chapter range. The chunk records every covered chapter
              in `chapter_map`, so it pairs with each of them later.
  word_count  fixed-size chunks (fallback when a text has no markers)

Chunks over --max-words are split into pieces.

Output: <out-dir>/<name>_chunks_<mode>.json  {"source", "chunks": [{id, chapters, chapter_map, text, word_count}]}

Usage:
    python chunk_text.py --input work/raw/targum_isaiah.txt --name targum_isaiah --mode regex \
        --pattern '(?:^|\\n)\\s*CHAPTER\\s+(\\d+)\\b' --fallback '(?:^|\\n)\\s*(\\d+)\\s*:\\s*(\\d+)\\s'
    python chunk_text.py --input work/raw/commentary_isaiah.txt --name commentary_isaiah --mode regex \
        --pattern '\\[(\\d+):(\\d+)(?:[–\\-]\\d+)?\\]' --max-words 12000
    python chunk_text.py --input work/raw/commentary_genesis.txt --name commentary_genesis --mode section \
        --pattern 'Section\\s+([IVXLC]+)\\s*\\[Gen(?:esis)?\\s+([\\d\\s,\\-–—:]+)\\]' --max-words 9000
"""

import argparse
import json
import os
import re

DEFAULT_PATTERN = r"(?:^|\n)\s*(\d+)\s*:\s*(\d+)\s"


def _label(chapters):
    unique = sorted(set(chapters))
    return ", ".join(str(c) for c in unique) if unique else "preamble"


def _split_oversized(text, max_words, chapters):
    words = text.split()
    return [{"text": " ".join(words[i:i + max_words]), "word_count": len(words[i:i + max_words]),
             "chapters": _label(chapters), "chapter_map": list(chapters), "note": "split_from_oversized"}
            for i in range(0, len(words), max_words)]


def roman_to_int(roman):
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total, prev = 0, 0
    for ch in reversed(roman.strip().upper()):
        v = values.get(ch, 0)
        total += -v if v < prev else v
        prev = v
    return total


def parse_chapter_range(ref):
    """'45-47' -> [45,46,47]; '2:5-3:24' -> [2,3]; '4:1-16' -> [4]; '1-3, 5' -> [1,2,3,5]."""
    s = re.sub(r"(?i)gen(?:esis)?\s*", "", ref).strip()
    chapters = []
    for part in (p.strip() for p in s.split(",")):
        if m := re.match(r"(\d+):\d+\s*[-–—]\s*(\d+):\d+", part):
            chapters += range(int(m.group(1)), int(m.group(2)) + 1)
        elif m := re.match(r"(\d+):(\d+)\s*[-–—]\s*(\d+)$", part):
            ch, v1, v2 = map(int, m.groups())
            chapters += [ch] if v2 >= v1 else range(ch, v2 + 1)
        elif m := re.match(r"(\d+)\s*[-–—]\s*(\d+):\d+", part):
            chapters += range(int(m.group(1)), int(m.group(2)) + 1)
        elif m := re.match(r"(\d+)\s*[-–—]\s*(\d+)$", part):
            chapters += range(int(m.group(1)), int(m.group(2)) + 1)
        elif m := re.match(r"(\d+)(?::\d+)?$", part):
            chapters.append(int(m.group(1)))
    return sorted(set(chapters))


def chunk_by_word_count(text, target_words):
    words = text.split()
    return [{"text": " ".join(words[i:i + target_words]), "word_count": len(words[i:i + target_words]),
             "chapters": "", "chapter_map": []} for i in range(0, len(words), target_words)]


def _segments_to_chunks(segments, max_words):
    chunks = []
    for seg in segments:
        if seg["word_count"] <= max_words:
            chunks.append({"text": seg["text"], "word_count": seg["word_count"],
                           "chapters": _label(seg["chapters"]), "chapter_map": seg["chapters"],
                           **({"section_num": seg["section_num"]} if "section_num" in seg else {})})
        else:
            for piece in _split_oversized(seg["text"], max_words, seg["chapters"]):
                if "section_num" in seg:
                    piece["section_num"] = seg["section_num"]
                chunks.append(piece)
    return chunks


def chunk_by_regex(text, pattern, fallbacks, max_words):
    matches = list(re.finditer(pattern, text))
    for fb in fallbacks:
        if matches:
            break
        matches = list(re.finditer(fb, text, re.MULTILINE))
    if not matches:
        print("  no chapter markers found; falling back to word_count")
        return chunk_by_word_count(text, max_words)

    markers = []
    for m in matches:
        try:
            markers.append((int(m.group(1)), m.start()))
        except (IndexError, ValueError):
            markers.append((0, m.start()))

    # Split where the chapter number changes; text before the first marker is the preamble
    splits = [0, markers[0][1]]
    prev = markers[0][0]
    for ch, pos in markers:
        if ch != prev:
            splits.append(pos)
            prev = ch
    splits = sorted(set(splits + [len(text)]))

    segments = []
    for a, b in zip(splits, splits[1:]):
        seg = text[a:b].strip()
        if seg:
            chs = sorted({ch for ch, pos in markers if a <= pos < b})
            segments.append({"text": seg, "word_count": len(seg.split()), "chapters": chs})
    return _segments_to_chunks(segments, max_words)


def chunk_by_sections(text, pattern, max_words):
    matches = list(re.finditer(pattern, text))
    if not matches:
        print("  no section markers found; falling back to word_count")
        return chunk_by_word_count(text, max_words)

    sections = [{"num": roman_to_int(m.group(1)) if m.group(1) else 0,
                 "chapters": parse_chapter_range(m.group(2)) if m.group(2) else [],
                 "pos": m.start()} for m in matches]
    splits = sorted(set([0] + [s["pos"] for s in sections] + [len(text)]))

    segments = []
    for a, b in zip(splits, splits[1:]):
        seg = text[a:b].strip()
        if not seg:
            continue
        sec = next((s for s in sections if a <= s["pos"] < b), None)
        segments.append({"text": seg, "word_count": len(seg.split()),
                         "chapters": sec["chapters"] if sec else [], "section_num": sec["num"] if sec else 0})
    return _segments_to_chunks(segments, max_words)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--name", required=True, help="Source name used in the output file name")
    ap.add_argument("--mode", choices=["regex", "section", "word_count"], default="regex")
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--fallback", action="append", default=[], help="Tried in order if --pattern finds nothing")
    ap.add_argument("--max-words", type=int, default=8000)
    ap.add_argument("--target-words", type=int, default=3000, help="word_count mode only")
    ap.add_argument("--out-dir", default="work/chunks")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        text = f.read()

    if args.mode == "regex":
        chunks = chunk_by_regex(text, args.pattern, args.fallback, args.max_words)
    elif args.mode == "section":
        chunks = chunk_by_sections(text, args.pattern, args.max_words)
    else:
        chunks = chunk_by_word_count(text, args.target_words)

    for i, c in enumerate(chunks):
        c["id"], c["chunk_num"] = f"chunk_{i}", i

    out = {"source": args.name, "chunk_method": args.mode, "total_chunks": len(chunks),
           "total_words": len(text.split()), "chunks": chunks}
    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, f"{args.name}_chunks_{args.mode}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    for c in chunks:
        print(f"  {c['id']}: {c['word_count']} words [{c['chapters']}]")
    print(f"{len(chunks)} chunks -> {path}")


if __name__ == "__main__":
    main()
