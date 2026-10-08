"""The AI never produces a number the data did not give it: every figure in an answer is checked against the figures in
the summary that was sent. Anything unmatched is reported, never silently accepted."""
from __future__ import annotations

import re

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> set[float]:
    out = set()
    for tok in NUM_RE.findall(text):
        try:
            out.add(round(float(tok.replace(",", "").rstrip(".")), 6))
        except ValueError:
            pass
    return out


def allowed_numbers(facts) -> set[float]:
    """Numeric leaves, plus every number appearing in any string (the pre-formatted `text` fields, labels, notes)."""
    out: set[float] = set()

    def walk(o):
        if isinstance(o, bool):
            return
        if isinstance(o, (int, float)):
            out.add(round(float(o), 6))
        elif isinstance(o, str):
            out.update(_numbers_in(o))
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(str(k))                 # field names the system wrote ("top_10_percent...") may be quoted too
                walk(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                walk(v)

    walk(facts)
    return out


def verify_numbers(text: str, facts) -> dict:
    allowed = allowed_numbers(facts)
    checked = _numbers_in(text)
    bad = sorted(n for n in checked if n not in allowed and -1 * n not in allowed)
    return {"ok": not bad, "checked": len(checked), "unverified": [f"{n:.6f}".rstrip("0").rstrip(".") for n in bad]}   # plain digits, never 1e+09
