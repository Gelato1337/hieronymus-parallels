# Hieronymus Project — LLM detection of shared interpretive traditions

This pipeline uses large language models to look for **shared exegetical traditions** between
ancient texts.

- **Commentary comparison.** A Church Father's commentary is compared with a Targum (Aramaic
  translation-paraphrase) of the same biblical chapter, with the biblical text given as a
  baseline. The model lists interpretations unique to each side and interpretations they share
  beyond the biblical text. Comparisons covered: Jerome's *Hebrew Questions on Genesis*,
  Ephraem's *Commentary on Genesis* and Eusebius' *Commentary on Isaiah*, against Targums
  Neofiti, Pseudo-Jonathan and Targum Isaiah.
- **Parallel detection.** Every chapter of one book is compared with every chapter of another.
  For 1 Enoch × Isaiah that is 108 × 66 = 7,128 pairs. The model must back any claimed
  connection with verbatim quotes from both sides. Prompts are first checked on a labelled eval
  set, then run as an ensemble. Pairs are ranked by how many prompt variants agree.

**This repository contains code and prompt templates only.** The source editions and
translations are copyrighted and not included. Bring your own PDFs or texts.

## Pipeline

```
PDF ─► extract_pdf.py ─► chunk_text.py ─┐       (or parsers/ for editions that need layout-aware parsing)
                                        ▼
                 build_prompts.py (cross | paired [+ baseline context]) ─► run_prompts.py (vLLM | Anthropic API)
                        ▲                                                       │
        build_eval_set.py (labelled pairs)            ┌─────────────────────────┼──────────────────────┐
                                                      ▼                         ▼                      ▼
                                               score_eval.py          aggregate_ensemble.py    export_findings.py
                                           (recall / FP rate)       (votes, ranked evidence)  (unique / shared lists)
```

| Step | Script | What it does |
|---|---|---|
| 1 | `extract_pdf.py` | Extracts text from a range of book pages. Joins multi-volume editions and removes text repeated at volume boundaries. Drops header and watermark lines by regex. |
| 2 | `chunk_text.py` | Splits text into one chunk per chapter using chapter:verse markers, or using section headers that list the chapters they cover (`chapter_map`). Splits oversized chunks. |
| 2′ | `parsers/parse_enoch.py` | Layout-aware parser for the Nickelsburg & VanderKam *1 Enoch* translation. Keeps the textual apparatus out of the verse text. |
| 2′ | `parsers/parse_isaiah_jps.py` | Parser for the JPS 1917 translation. Assigns words to chapters by the position of the drop-cap chapter numbers. |
| 3 | `build_eval_set.py` | 10 known Enoch–Isaiah parallels plus 90 random pairs. Stores only chapter numbers. |
| 3 | `build_prompts.py` | Renders a template for every pair: `cross` uses all pairs, `paired` uses same-chapter pairs and can inject the baseline text as context. |
| 4 | `run_prompts.py` | Resumable inference. vLLM is tensor-parallel; on LUMI it ran Qwen3.5-122B-A10B on 8 GPUs. The Anthropic API backend reads `ANTHROPIC_API_KEY`. |
| 5a | `score_eval.py` | Recall on known parallels, false-positive rate on random pairs, and precision, per prompt variant. |
| 5b | `aggregate_ensemble.py` | Agreement votes across prompt variants, plus a ranked list of flagged pairs with their quoted evidence. |
| 5c | `export_findings.py` | Lists unique and shared traditions per chapter, for the commentary comparisons. |

## Example: 1 Enoch × Isaiah

```bash
python parsers/parse_enoch.py --pdf 1enoch.pdf --out work/chunks/enoch.json
python parsers/parse_isaiah_jps.py --pdf jps1917_isaiah.pdf --out work/chunks/isaiah.json

# choose prompts on the eval set
python build_eval_set.py --source work/chunks/enoch.json --target work/chunks/isaiah.json --out work/eval/eval100.json
for v in a c d e; do
  python build_prompts.py --source work/chunks/enoch.json --target work/chunks/isaiah.json \
      --template prompts/enoch_vs_isaiah_$v.txt --pairs work/eval/eval100.json --out work/prompts/eval_$v.jsonl
  sbatch run_prompts.sbatch work/prompts/eval_$v.jsonl runs/eval/$v.jsonl
done
python score_eval.py runs/eval/*.jsonl

# full cross-product as an ensemble
for v in a c d e; do
  python build_prompts.py --source work/chunks/enoch.json --target work/chunks/isaiah.json \
      --template prompts/enoch_vs_isaiah_$v.txt --out work/prompts/full_$v.jsonl
  sbatch run_prompts.sbatch work/prompts/full_$v.jsonl runs/full/$v.jsonl
done
python aggregate_ensemble.py runs/full/*.jsonl --out-dir runs/full --source-name ENOCH --target-name ISAIAH
```

## Example: Eusebius × Targum Isaiah, with Isaiah as the baseline

```bash
python extract_pdf.py --pdf commentary_vol*.pdf --out work/raw/eusebius.txt
python chunk_text.py --input work/raw/eusebius.txt --name eusebius_isaiah \
    --pattern '\[(\d+):(\d+)(?:[–\-]\d+)?\]' --max-words 12000
python chunk_text.py --input work/raw/targum_isaiah.txt --name targum_isaiah \
    --pattern '(?:^|\n)\s*CHAPTER\s+(\d+)\b' --fallback '(?:^|\n)\s*(\d+)\s*:\s*(\d+)\s'
python build_prompts.py --pairing paired --chapters 2-3,6,13-14,30,57,62,64-66 \
    --source work/chunks/eusebius_isaiah_chunks_regex.json --target work/chunks/targum_isaiah_chunks_regex.json \
    --context work/chunks/isaiah.json --target-label "Targum Isaiah" \
    --template prompts/eusebius_vs_targum_isaiah.txt --out work/prompts/eusebius_targum.jsonl
python run_prompts.py --backend anthropic --model claude-haiku-4-5-20251001 --max-tokens 16384 --temperature 0.3 \
    --prompts work/prompts/eusebius_targum.jsonl --out runs/eusebius_targum/haiku.jsonl
python export_findings.py runs/eusebius_targum/haiku.jsonl --out-dir runs/eusebius_targum/findings \
    --source-name Eusebius --target-name "Targum Isaiah"
```

`run_prompts.sbatch` is the SLURM launcher used on LUMI (AMD MI250X, ROCm vLLM container). Set
the account, container and cache paths before use.
