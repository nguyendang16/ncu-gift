"""DEMO MODE (NCU_GIFT_AI_DEMO=1): canned, rule-built replies so the screens, consent flow, number check and audit log can be
seen without an API key. It is not a model and the interface says so everywhere. It writes from the same summary the real
model would receive, so the verifier treats it exactly like a real answer."""
from __future__ import annotations

import json

from .. import ingest, org
from ..i18n import t
from .client import LLMResponse


def _payload(messages: list[dict]) -> dict:
    return json.loads(messages[1]["content"])


def _ask(p: dict) -> str:
    q, f = p["question"].lower(), p["facts"]
    year = f["context"]["selected_year"]
    cur = next(y for y in f["yearly"] if y["year"] == year)
    why = f.get("why_total_changed")
    if why and any(k in q for k in ("why", "fall", "drop", "declin", "rise", "chang", "為什麼", "下降", "減少", "變動", "增加")):
        top = max(why["steps"], key=lambda s: abs(s["effect"]["value"]))
        return t("ai.demo.why", year=year, start=why["start_total"]["text"], end=why["end_total"]["text"], step=top["name"], effect=top["effect"]["text"])
    j = f.get("donor_journey")
    if j and j["second_gift"] and any(k in q for k in ("second", "first", "retain", "return", "回流", "第二", "首次", "續捐")):
        g = j["second_gift"][-1]
        return t("ai.demo.first_gift", year=g["first_time_donors_in"], n=g["number"], k=g["gave_again_next_year"], rate=g["share_who_gave_again"]["text"],
                 repeat=g["repeat_donors_share_who_gave_again"]["text"])
    c = f.get("concentration")
    if c and any(k in q for k in ("concentrat", "few", "top", "depend", "集中", "少數", "依賴")):
        return t("ai.demo.concentration", all=c["top_1_percent_of_donors_share_of_all_money"]["text"], ordinary=c["top_1_percent_share_of_ordinary_money"]["text"])
    return t("ai.demo.general", year=year, total=cur["total"]["text"], ordinary=cur["ordinary"]["text"],
             change=(cur["ordinary_change_vs_previous_year"] or {"text": "–"})["text"])


def _insights(p: dict) -> dict:
    f = p["facts"]
    year = f["context"]["selected_year"]
    cur = next(y for y in f["yearly"] if y["year"] == year)
    detail = f["selected_year_detail"]
    change = (cur["ordinary_change_vs_previous_year"] or {"text": "–"})["text"]
    view = f["context"].get("years_in_view") or []
    yearly = f["yearly"]
    if len(view) > 1 and len(yearly) > 1:
        first, last = yearly[0], yearly[-1]
        compare_text = t("ai.demo.span", start_year=first["year"], end_year=last["year"],
                         total_start=first["total"]["text"], total_end=last["total"]["text"],
                         ordinary_start=first["ordinary"]["text"], ordinary_end=last["ordinary"]["text"])
    else:
        compare_text = t("ai.demo.general", year=year, total=cur["total"]["text"], ordinary=cur["ordinary"]["text"], change=change)
    cards = detail.get("credit_card_gifts")
    repeat = detail.get("repeat_donors") or 0
    large = detail["large_gifts"]["count"]
    base = t("ai.demo.base", repeat=repeat, cards=cards, large=large) if cards is not None else t("ai.demo.base_nocard", repeat=repeat, large=large)
    c = f.get("concentration") or {}
    observations = [
        {"key": "compare", "text": compare_text},
        {"key": "base", "text": base},
        {"key": "concentration", "text": t("ai.demo.concentration",
                                            all=c.get("top_1_percent_of_donors_share_of_all_money", {}).get("text", "–"),
                                            ordinary=c.get("top_1_percent_share_of_ordinary_money", {}).get("text", "–"))},
        {"key": "accounts", "text": t("ai.demo.accounts")},
    ]
    recommendations = [t(f"ai.demo.rec{i}") for i in range(1, 6)]
    return {"observations": observations, "recommendations": recommendations}


def _brief(p: dict) -> str:
    f = p["facts"]
    c = f["category_last_year"]
    return t("ai.demo.brief", project=f["project"], donors=c["donors"], median=c["median_gift"], low=f["options"]["low"], high=f["options"]["high"])


def _map(p: dict) -> dict:
    out = []
    for c in p["columns"]:
        best, score = "none", 0.0
        for field in ingest.FIELDS:
            s = ingest.header_score(c["column"], field)
            if s > score:
                best, score = field, s
        out.append({"column": c["column"], "field": best if score >= 0.5 else "none", "confidence": round(min(score, 0.7), 2), "reason": "demo: header wording"})
    return {"columns": out}


def _classify(p: dict) -> dict:
    out = []
    for it in p["items"]:
        text = it["text"].lower()
        label = "unsure"
        if any(k in text for k in ("student", "學生")):
            label = "University-wide scholarships"
        elif any(k in text for k in ("support", "general", "misc", "donation", "一般", "支持")):
            label = "university_fund"
        out.append({"index": it["index"], "label": label, "confidence": 0.55 if label != "unsure" else 0.2})
    return {"results": out}


def chat(feature: str, messages: list[dict], schema: dict | None) -> LLMResponse:
    p = _payload(messages)
    body = {"ask": lambda: t("ai.demo.prefix") + _ask(p), "brief": lambda: t("ai.demo.prefix") + _brief(p),
            "insights": lambda: json.dumps(_insights(p), ensure_ascii=False), "map": lambda: json.dumps(_map(p), ensure_ascii=False),
            "classify": lambda: json.dumps(_classify(p), ensure_ascii=False),
            "test": lambda: "OK"}[feature]()
    return LLMResponse(text=body, model="demo", demo=True, latency_ms=5)
