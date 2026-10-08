"""Thin client for the OpenAI Chat Completions API (supported by gpt-6-luna).

Deliberately small and defensive:
  * no temperature is sent (the model's documentation does not list it);
  * `reasoning_effort` is sent only when configured, and any optional parameter the API rejects is dropped and retried;
  * errors are translated into messages a non-technical person can act on, including OpenAI's own text for a wrong
    model name;
  * the transport is injectable, so tests never touch the network.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from ..i18n import t
from .config import AiConfig, get_config


class AiError(Exception):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    demo: bool = False
    tool_calls: list = field(default_factory=list)      # [{"id", "name", "arguments": str}] when the model asks for tools
    message: dict | None = None                         # the raw assistant message, to put back in the conversation


# (url, headers, json_body, timeout) -> (status_code, parsed_json_or_{})
Transport = Callable[[str, dict, dict, float], tuple[int, dict]]


def _http_transport(url: str, headers: dict, body: dict, timeout: float) -> tuple[int, dict]:
    r = httpx.post(url, headers=headers, json=body, timeout=timeout)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"error": {"message": r.text[:300]}}


_transport: Transport = _http_transport


def set_transport(fn: Transport | None) -> None:
    """Tests install a fake; None restores the real network transport."""
    global _transport
    _transport = fn or _http_transport


OPTIONAL = ("response_format", "reasoning_effort", "max_completion_tokens")


def _provider_message(data: dict) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    return (err.get("message") if isinstance(err, dict) else None) or str(data)[:300]


def _classify(status: int, data: dict, cfg: AiConfig) -> AiError:
    msg = _provider_message(data)
    if status == 401:
        return AiError("bad_key", t("ai.err.bad_key"), status)
    if status == 404 or (status == 400 and "model" in msg.lower() and ("not exist" in msg.lower() or "not found" in msg.lower())):
        return AiError("bad_model", t("ai.err.model", model=cfg.model, detail=msg), status)
    if status == 429:
        return AiError("rate_limited", t("ai.err.rate"), status)
    if status >= 500:
        return AiError("unavailable", t("ai.err.unavailable", detail=f"HTTP {status}"), status)
    return AiError("bad_request", t("ai.err.bad_request", detail=msg), status)


def chat(messages: list[dict], *, feature: str, schema: dict | None = None, schema_name: str = "result", tools: list[dict] | None = None,
         tool_choice: str | None = None) -> LLMResponse:
    cfg = get_config()
    if cfg.demo:
        from . import demo
        return demo.chat(feature, messages, schema)
    if not cfg.api_key:
        raise AiError("no_key", t("ai.err.no_key"))

    body: dict = {"model": cfg.model, "messages": messages, "max_completion_tokens": cfg.max_output_tokens}
    if cfg.reasoning_effort:
        body["reasoning_effort"] = cfg.reasoning_effort
    if tools:
        body["tools"] = tools
        body["reasoning_effort"] = "none"       # the model page: function calling on Chat Completions needs reasoning_effort "none"
        if tool_choice:
            body["tool_choice"] = tool_choice
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}}
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}

    started = time.perf_counter()
    for _attempt in range(len(OPTIONAL) + 1):
        try:
            status, data = _transport(f"{cfg.base_url}/chat/completions", headers, body, cfg.timeout)
        except httpx.HTTPError as e:
            raise AiError("unavailable", t("ai.err.unavailable", detail=type(e).__name__)) from None
        if status == 200:
            break
        msg = _provider_message(data).lower()
        dropped = next((p for p in OPTIONAL if p in body and p.split("_")[0] in msg and ("unsupported" in msg or "not supported" in msg
                                                                                          or "unknown" in msg or "invalid" in msg)), None)
        if status == 400 and dropped:
            body.pop(dropped)          # the model does not take this optional parameter: retry without it
            continue
        raise _classify(status, data, cfg)
    else:
        raise AiError("bad_request", t("ai.err.bad_request", detail="too many retries"))

    try:
        choice = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise AiError("empty", t("ai.err.empty")) from None
    if choice.get("refusal"):
        raise AiError("refused", t("ai.err.refused"))
    text = (choice.get("content") or "").strip()
    calls = [{"id": c.get("id") or f"call_{i}", "name": (c.get("function") or {}).get("name", ""), "arguments": (c.get("function") or {}).get("arguments") or "{}"}
             for i, c in enumerate(choice.get("tool_calls") or [])]
    if not text and not calls:
        raise AiError("empty", t("ai.err.empty"))
    u = data.get("usage") or {}
    return LLMResponse(text=text, prompt_tokens=int(u.get("prompt_tokens") or 0), completion_tokens=int(u.get("completion_tokens") or 0),
                       cached_tokens=int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0),
                       latency_ms=int((time.perf_counter() - started) * 1000), model=str(data.get("model") or cfg.model),
                       tool_calls=calls, message=choice if calls else None)


def cost_usd(r: LLMResponse, cfg: AiConfig | None = None) -> float:
    cfg = cfg or get_config()
    fresh = max(r.prompt_tokens - r.cached_tokens, 0)
    return (fresh * cfg.price_in + r.cached_tokens * cfg.price_cached + r.completion_tokens * cfg.price_out) / 1e6
