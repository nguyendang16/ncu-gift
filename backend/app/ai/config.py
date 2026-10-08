"""AI settings come from the environment (or backend/.env). The API key is never stored in the database, never returned
by any endpoint, and never logged."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import ROOT

_LOADED = False


def load_dotenv() -> None:
    """Tiny .env reader (KEY=VALUE per line; existing environment variables win). backend/.env is git-ignored."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    if os.environ.get("NCU_GIFT_NO_DOTENV"):      # the tests set this: they must never pick up a real key
        return
    for path in (ROOT / "backend" / ".env", ROOT / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class AiConfig:
    api_key: str | None
    model: str
    base_url: str
    reasoning_effort: str | None
    demo: bool
    daily_cap: int
    timeout: float
    max_output_tokens: int
    price_in: float      # USD per 1M input tokens
    price_cached: float  # USD per 1M cached input tokens
    price_out: float     # USD per 1M output tokens (reasoning tokens are billed as output)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def get_config() -> AiConfig:
    load_dotenv()
    e = os.environ.get
    effort = (e("NCU_GIFT_LLM_REASONING", "low") or "").strip().lower()
    return AiConfig(
        api_key=(e("OPENAI_API_KEY") or "").strip() or None,
        model=(e("NCU_GIFT_LLM_MODEL") or "gpt-6-luna").strip(),
        base_url=(e("NCU_GIFT_LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
        reasoning_effort=None if effort in ("", "default") else effort,
        demo=(e("NCU_GIFT_AI_DEMO", "") or "").strip().lower() in {"1", "true", "yes"},
        daily_cap=int(e("NCU_GIFT_AI_DAILY_CAP", "1000")),
        timeout=float(e("NCU_GIFT_LLM_TIMEOUT", "60")),
        max_output_tokens=int(e("NCU_GIFT_LLM_MAX_OUTPUT", "4000")),
        # defaults are the list prices on the model's documentation page; override if they change
        price_in=float(e("NCU_GIFT_LLM_PRICE_IN", "0.10")),
        price_cached=float(e("NCU_GIFT_LLM_PRICE_CACHED", "0.01")),
        price_out=float(e("NCU_GIFT_LLM_PRICE_OUT", "0.50")),
    )
