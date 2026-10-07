"""
Step 4 — Run a prompt file through an LLM. Resumable.

Backends:
  vllm       offline batched inference, tensor-parallel (used on LUMI with Qwen3.5-122B-A10B, 8 GPUs)
  anthropic  Messages API; the key is read from ANTHROPIC_API_KEY

Each output line holds the input metadata, the raw response and the parsed JSON
(or null). Rerunning the same command continues after the last complete line.

Usage:
    python run_prompts.py --prompts work/prompts/enoch_isaiah_a.jsonl --out runs/enoch_isaiah/a.jsonl
    python run_prompts.py --prompts work/prompts/eusebius_targum.jsonl --out runs/eusebius_targum/haiku.jsonl \
        --backend anthropic --model claude-haiku-4-5-20251001 --max-tokens 16384 --temperature 0.3
"""

import argparse
import json
import os
import re
import time


def parse_json(text):
    """Model output -> dict/list, trying a fenced block, the whole text, then the outermost {...}/[...]."""
    text = (text or "").strip()
    candidates = []
    if m := re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL):
        candidates.append(m.group(1).strip())
    candidates.append(text)
    for pattern in (r"(\{.*\})", r"(\[.*\])"):
        if m := re.search(pattern, text, re.DOTALL):
            candidates.append(m.group(1))
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def count_done(path):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                break
            n += 1
    return n


def write_batch(path, records, texts):
    with open(path, "a", encoding="utf-8") as f:
        for rec, text in zip(records, texts):
            out = {k: v for k, v in rec.items() if k != "prompt"}
            out["raw"] = text
            out["parsed"] = parse_json(text)
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def run_vllm(args, records, start):
    from vllm import LLM, SamplingParams

    llm = LLM(model=args.model, tensor_parallel_size=args.tp, max_model_len=args.max_model_len,
              gpu_memory_utilization=args.gpu_util, enforce_eager=True, trust_remote_code=True)
    tok = llm.get_tokenizer()
    sampling = SamplingParams(temperature=args.temperature, max_tokens=args.max_tokens)

    def chat(prompt):
        kwargs = {"tokenize": False, "add_generation_prompt": True}
        if not args.thinking:
            kwargs["enable_thinking"] = False
        return tok.apply_chat_template([{"role": "user", "content": prompt}], **kwargs)

    for i in range(start, len(records), args.batch):
        batch = records[i:i + args.batch]
        t0 = time.time()
        outs = llm.generate([chat(r["prompt"]) for r in batch], sampling)
        write_batch(args.out, batch, [o.outputs[0].text for o in outs])
        print(f"[{i}:{i + len(batch)}] {len(batch) / max(time.time() - t0, 1e-6):.1f} prompts/s", flush=True)


def run_anthropic(args, records, start):
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    for i in range(start, len(records)):
        text = ""
        for attempt in range(3):
            try:
                resp = client.messages.create(model=args.model, max_tokens=args.max_tokens,
                                              temperature=args.temperature,
                                              messages=[{"role": "user", "content": records[i]["prompt"]}])
                text = "".join(b.text for b in resp.content if hasattr(b, "text"))
                break
            except Exception as e:
                wait = max(2 ** (attempt + 1), 15 if "429" in str(e) or "rate" in str(e).lower() else 0)
                print(f"  attempt {attempt + 1} failed: {str(e)[:100]}; retrying in {wait}s")
                time.sleep(wait)
        write_batch(args.out, [records[i]], [text])
        print(f"[{i + 1}/{len(records)}] {records[i]['pair_id']}", flush=True)
        time.sleep(args.delay)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompts", required=True, help="JSONL from build_prompts.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", choices=["vllm", "anthropic"], default="vllm")
    ap.add_argument("--model", default="Qwen/Qwen3.5-122B-A10B")
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--limit", type=int, help="Only the first N prompts (smoke test)")
    # vllm
    ap.add_argument("--tp", type=int, default=8)
    ap.add_argument("--max-model-len", type=int, default=32768)
    ap.add_argument("--gpu-util", type=float, default=0.90)
    ap.add_argument("--batch", type=int, default=2000, help="Prompts per generate() call / checkpoint")
    ap.add_argument("--thinking", action="store_true",
                    help="Allow reasoning mode; by default enable_thinking=False is passed (Qwen3.x)")
    # anthropic
    ap.add_argument("--delay", type=float, default=0.5, help="Seconds between API calls")
    args = ap.parse_args()

    with open(args.prompts, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    if args.limit:
        records = records[:args.limit]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    start = count_done(args.out)
    print(f"{len(records)} prompts, {start} already done -> {args.out}")
    if start < len(records):
        (run_vllm if args.backend == "vllm" else run_anthropic)(args, records, start)


if __name__ == "__main__":
    main()
