"""What may leave the machine. Everything sent to the model is built from aggregate tables; this module is the last
line of defence if a donor identifier ever ends up in a payload by accident."""
from __future__ import annotations

import json
import re

CODE_PATTERNS = [re.compile(r"\bD\d{4}\b"), re.compile(r"\bUSER_\d+\b", re.I), re.compile(r"\buser_\d+\b")]
MAX_BYTES = 80_000


class UnsafePayload(Exception):
    pass


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _strings(v)


def assert_safe(payload: dict, known_identifiers: set[str] | None = None) -> str:
    """Raise UnsafePayload if the payload contains a donor code, or any donor name known to this dataset.
    Returns the serialised payload (exactly what will be sent)."""
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise UnsafePayload("payload too large")
    known = {k.lower() for k in (known_identifiers or set()) if k and len(k) >= 4}
    for s in _strings(payload):
        if any(p.search(s) for p in CODE_PATTERNS):
            raise UnsafePayload("donor code in payload")
        low = s.lower()
        if known and any(k in low for k in known):
            raise UnsafePayload("donor name in payload")
    return text
