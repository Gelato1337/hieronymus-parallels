"""Shared reader for parallel-detection outputs ({"connection": bool, "parallels": [...]})."""

import json
import re


def normalize(rec):
    """Output line -> (connection, parallels). A connection only counts if a parallel survived."""
    p = rec.get("parsed")
    raw = rec.get("raw") or ""
    if isinstance(p, dict):
        if "strength" in p:  # graded single-object schema
            strength = str(p.get("strength", "none")).lower()
            conn = bool(p.get("connection", strength in ("medium", "strong"))) and strength in ("medium", "strong")
            pars = [{"source_quote": str(p.get("enoch_anchor", p.get("source_anchor", ""))),
                     "target_quote": str(p.get("isaiah_anchor", p.get("target_anchor", ""))),
                     "explanation": str(p.get("explanation", "")),
                     "confidence": "high" if strength == "strong" else "medium"}] if conn else []
            return conn, pars
        pars = p.get("parallels", []) if p.get("connection") else []
        pars = [{k: str(v)[:800] for k, v in x.items()} for x in pars if isinstance(x, dict)] \
            if isinstance(pars, list) else []
        return bool(p.get("connection")) and bool(pars), pars
    if re.search(r'"connection"\s*:\s*true', raw, re.IGNORECASE):
        return True, []
    return False, []


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]
