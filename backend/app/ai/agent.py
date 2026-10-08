"""The analyst agent: the model chooses which of the system's own analyses to run; the system runs them; the model words the result.

What makes it safe and checkable:
  * the model has no data of its own, only an allow-list of tools that call the same functions the dashboard uses;
  * every tool result is aggregate (no donor name or code) and passes the safety gate before it is shown to the model;
  * tables of donors (who to call, who to ask) are drawn by the app from the tool result and never go through the model;
  * every figure in the answer must appear in a tool result (or in the question); sources are cited as [1], [2] and shown;
  * a hard cap on steps, arguments are validated and clamped, and a failing tool becomes a message, not a crash.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import SimpleNamespace

import pandas as pd
from sqlalchemy.orm import Session

from .. import i18n
from ..i18n import t
from ..services import insights as ins, journey as jr, matching, risk as rk, scenario as scn, stats
from ..services.frame import InsufficientData, years_of
from . import client
from .client import AiError
from .config import get_config
from .facts import _m, _p, _rows, _share
from ..models import AiCall
from .features import Blocked, RULES, _log, gate, known_identifiers
from .safety import UnsafePayload, assert_safe
from .verify import verify_numbers

MAX_STEPS = 6                       # model calls per question, the last one without tools


@dataclass
class ToolOut:
    model: dict                                 # what the model sees (aggregate, pre-formatted)
    summary: str                                # one line for the person
    args_text: str = ""
    table: dict | None = None                   # drawn by the app only
    link: str | None = None


@dataclass
class Tool:
    name: str
    description: str
    params: dict                                # JSON-schema "properties"
    required: list[str] = field(default_factory=list)


def _year_param() -> dict:
    return {"year": {"type": "integer", "description": "Report year. Omit for the latest year."}}


TOOLS: list[Tool] = [
    Tool("giving_overview", "Totals, donor count, and breakdowns (donor type, purpose, payment method, gift size, college) for one year.", _year_param()),
    Tool("giving_by_year", "Total, ordinary and exceptional giving and number of donors for every year, with year-on-year changes.", {}),
    Tool("why_total_changed", "Step-by-step explanation of why total giving changed from the previous year (new, stopped, returning donors, exceptional gifts).", _year_param()),
    Tool("concentration", "How much of the money comes from the top 1% and top 10% of donors, with and without exceptional gifts.", _year_param()),
    Tool("monthly_pattern", "Which months bring in the most ordinary giving, per year.", {}),
    Tool("donor_retention", "New, retained, returning and lapsed donors per year, and how many first-time donors gave again.", {}),
    Tool("at_risk_donors", "Donors most likely to stop giving, ranked by money at stake, with the model's out-of-sample accuracy. The app shows the list itself.",
         {"count": {"type": "integer", "minimum": 5, "maximum": 50, "description": "How many donors to list (default 20)."}}),
    Tool("list_matching_targets", "Find the purposes, departments or projects that donors can be matched to. Returns target ids for find_prospects.",
         {"query": {"type": "string", "description": "Part of a name to look for, e.g. 'scholarship'. Omit for the largest targets."}}),
    Tool("find_prospects", "Existing donors who are the best prospects for one target (use an id from list_matching_targets). The app shows the list itself.",
         {"target_id": {"type": "string", "description": "A target id such as 'sub:Student clubs' from list_matching_targets."},
          "count": {"type": "integer", "minimum": 5, "maximum": 50}}, ["target_id"]),
    Tool("run_scenario", "What-if on next year's ORDINARY giving: change retention, new-donor inflow or recurring conversion. A sensitivity analysis, not a forecast.",
         {"first_time_retention_uplift_pts": {"type": "number", "minimum": 0, "maximum": 20, "description": "Extra percentage points of first-time donors who give again."},
          "repeat_retention_uplift_pts": {"type": "number", "minimum": 0, "maximum": 10},
          "new_donor_inflow_multiplier": {"type": "number", "minimum": 0.5, "maximum": 1.5, "description": "1.0 = same number of new donors as last year."},
          "recurring_conversion_pct": {"type": "number", "minimum": 0, "maximum": 30, "description": "Percent of retained donors moved to recurring giving."},
          "major_gift_ntd": {"type": "number", "minimum": 0, "maximum": 100000000, "description": "An exceptional gift to add on top, in NT$. Usually 0."}}),
]
BY_NAME = {x.name: x for x in TOOLS}


def schema_for_model() -> list[dict]:
    return [{"type": "function", "function": {"name": x.name, "description": x.description,
                                              "parameters": {"type": "object", "properties": x.params, "required": x.required, "additionalProperties": False}}}
            for x in TOOLS]


# ------------------------------------------------------------------------ helpers

def _clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return min(max(v, lo), hi)


def _year(c, a) -> int:
    y = a.get("year")
    try:
        y = int(y) if y is not None else None
    except (TypeError, ValueError):
        y = None
    return y if y in c.years else c.years[-1]


def _table(columns: list[str], rows: list[list]) -> dict:
    return {"columns": columns, "rows": rows}


# ------------------------------------------------------------------------ tools

def giving_overview(c, a) -> ToolOut:
    y = _year(c, a)
    o = stats.overview(c.df, y, c.exceptional, c.large, "all")
    k = o["kpis"]
    res = {"year": y, "ordinary_giving_means": f"gifts below {ins._ntd_compact(c.exceptional)}",
           "exceptional_gift_means": f"a single gift of {ins._ntd_compact(c.exceptional)} or more; the `exceptional` figures are the total of these gifts",
           "total": _m(k["total"]), "ordinary": _m(k["regular_total"]), "exceptional": _m(k["exceptional_total"]), "exceptional_gifts": k["n_exceptional"],
           "donors": k["donors"], "gift_records": k["records"], "repeat_donors": k["repeat_selected"],
           "large_gifts": {"threshold": _m(c.large), "count": k["large_gifts"], "amount": _m(k["large_gifts_amount"])},
           "by_donor_type": _rows(o["donor_classes"]), "by_purpose_group": _rows(o["purpose_groups"]), "by_designated_purpose": _rows(o["purpose_subs"]),
           "by_payment_method": _rows(o["methods"]),
           "by_gift_size": [{"name": b["label"], "amount": _m(b["amount"]), "gifts": b["count"]} for b in o["bands"]],
           "by_college": _rows(o["colleges"])}
    return ToolOut(res, t("agent.sum.overview", year=y, total=res["total"]["text"], ordinary=res["ordinary"]["text"], donors=k["donors"]), t("agent.arg.year", year=y))


def giving_by_year(c, a) -> ToolOut:
    rows = stats.trend(c.df, c.exceptional)
    res = {"years": [{"year": r["year"], "total": _m(r["total"]), "ordinary": _m(r["regular"]), "exceptional": _m(r["exceptional"]), "exceptional_gifts": r["n_exceptional"],
                      "donors": r["donors"], "total_change": _p(r["total_yoy_pct"], signed=True), "ordinary_change": _p(r["regular_yoy_pct"], signed=True)} for r in rows],
           "ordinary_giving_means": f"gifts below {ins._ntd_compact(c.exceptional)}",
           "exceptional_gift_means": f"a single gift of {ins._ntd_compact(c.exceptional)} or more; the `exceptional` figures are the total of these gifts"}
    last = res["years"][-1]
    return ToolOut(res, t("agent.sum.by_year", first=rows[0]["year"], last=last["year"], total=last["total"]["text"]))


def why_total_changed(c, a) -> ToolOut:
    y = _year(c, a)
    b = ins.bridge(c.df, y, c.exceptional)
    res = {"from_year": b["prev_year"], "to_year": b["year"], "start_total": _m(b["start"]), "end_total": _m(b["end"]),
           "steps": [{"name": s["label"], "effect": _m(s["value"]), "donors": s["donors"]} for s in b["steps"]]}
    return ToolOut(res, t("agent.sum.bridge", start=res["start_total"]["text"], end=res["end_total"]["text"]), t("agent.arg.year", year=y))


def concentration(c, a) -> ToolOut:
    y = _year(c, a)
    k = ins.concentration(c.df, y, c.exceptional)
    res = {"year": y, "top_1_percent_of_donors_share_of_all_money": _share(k["all"]["top1pct_share"]),
           "top_1_percent_share_of_ordinary_money": _share(k["ordinary"]["top1pct_share"]),
           "top_10_percent_share_of_all_money": _share(k["all"]["top10pct_share"]),
           "top_10_percent_share_of_ordinary_money": _share(k["ordinary"]["top10pct_share"]),
           "largest_single_donor_share": _share(k["all"]["top1_donor_share"])}
    return ToolOut(res, t("agent.sum.conc", year=y, top1=res["top_1_percent_of_donors_share_of_all_money"]["text"]), t("agent.arg.year", year=y))


def monthly_pattern(c, a) -> ToolOut:
    s = ins.seasonality(c.df, c.exceptional)
    cells = pd.DataFrame(s["cells"])
    out = []
    for y, g in cells.groupby("year"):
        tot = float(g["value"].sum())
        if tot <= 0:
            continue
        top = g.sort_values("value", ascending=False).head(3)
        out.append({"year": int(y), "ordinary_total": _m(tot),
                    "busiest_months": [{"month": i18n.month_label(int(r.month)), "amount": _m(r.value), "share_of_year": _share(r.value / tot)} for r in top.itertuples()]})
    last = out[-1] if out else None
    return ToolOut({"ordinary_giving_means": f"gifts below {ins._ntd_compact(c.exceptional)}",
           "exceptional_gift_means": f"a single gift of {ins._ntd_compact(c.exceptional)} or more; the `exceptional` figures are the total of these gifts", "years": out},
                   t("agent.sum.months", year=last["year"], month=last["busiest_months"][0]["month"]) if last else t("agent.sum.none"))


def donor_retention(c, a) -> ToolOut:
    j = jr.journey(c.df)
    res = {"states_by_year": [{"year": y["year"], "new": y["new"], "retained": y["retained"], "reactivated": y["reactivated"], "lapsed_from_previous_year": y["lapsed"]}
                              for y in j["years"] if y["history_available"]],
           "second_gift": [{"first_time_donors_in": f["cohort_year"], "number": f["first_time"]["n"], "gave_again_next_year": f["first_time"]["returned"],
                            "share_who_gave_again": _share(f["first_time"]["rate"]),
                            "repeat_donors_share_who_gave_again": _share(f["repeat"]["rate"])} for f in j["funnel"]]}
    g = res["second_gift"][-1] if res["second_gift"] else None
    return ToolOut(res, t("agent.sum.retention", rate=g["share_who_gave_again"]["text"], year=g["first_time_donors_in"]) if g else t("agent.sum.none"))


def at_risk_donors(c, a) -> ToolOut:
    n = int(_clamp(a.get("count"), 5, 50, 20))
    r = rk.risk_report(c.df, top_n=n)
    donors = r["donors"][:n]
    total = sum(d["value_at_risk"] for d in donors)
    m = r["metrics"]
    by_class: dict[str, int] = {}
    for d in donors:
        by_class[d["donor_class_label"]] = by_class.get(d["donor_class_label"], 0) + 1
    res = {"listed": len(donors), "for_year": r["next_year"], "value_at_risk_of_listed": _m(total), "listed_by_donor_type": by_class,
           "meaning": "value at risk = chance of stopping x last year's giving; gifts are capped so a single huge gift does not dominate",
           "model": ({"auc_out_of_sample": round(m["auc"], 2), "auc_95_interval": [round(m["auc_ci_low"], 2), round(m["auc_ci_high"], 2)],
                      "trained_on": m["train"], "tested_on": m["test"],
                      "of_top_20_flagged_share_who_really_stopped": _share(m["precision_at_k"][0]["precision"])} if m else None)}
    cols = [t("agent.col.donor"), t("agent.col.type"), t("agent.col.gave"), t("agent.col.chance"), t("agent.col.at_stake"), t("agent.col.why")]
    rows = [[d["donor_id"], d["donor_class_label"], i18n_money(d["giving_last_year"]), f"{d['p_lapse'] * 100:.0f}%", i18n_money(d["value_at_risk"]),
             "; ".join(d["reasons"][:2])] for d in donors]
    return ToolOut(res, t("agent.sum.risk", n=len(donors), total=res["value_at_risk_of_listed"]["text"]), t("agent.arg.count", n=n), _table(cols, rows))


def i18n_money(x: float) -> str:
    return ins._ntd_compact(x)


def list_matching_targets(c, a) -> ToolOut:
    q = str(a.get("query") or "").strip().lower()
    rows = matching.list_targets(c.df)
    if not c.share_names:
        rows = [r for r in rows if r["kind"] != "project"]
    if q:
        rows = [r for r in rows if q in r["label"].lower() or q in r["id"].lower()]
    rows = sorted(rows, key=lambda r: -r["donors"])[:15]
    return ToolOut({"targets": [{"target_id": r["id"], "label": r["label"], "kind": r["kind"], "donors_who_gave_to_it": r["donors"]} for r in rows]},
                   t("agent.sum.targets", n=len(rows)), t("agent.arg.query", q=q) if q else "")


def find_prospects(c, a) -> ToolOut:
    tid = str(a.get("target_id") or "")
    valid = {r["id"]: r for r in matching.list_targets(c.df)}
    if tid not in valid or (valid[tid]["kind"] == "project" and not c.share_names):
        raise ValueError("unknown target_id: call list_matching_targets first and use one of its ids")
    n = int(_clamp(a.get("count"), 5, 50, 15))
    r = matching.rank(c.df, tid, n)
    cands = r["candidates"]
    by_class: dict[str, int] = {}
    for d in cands:
        by_class[d["donor_class_label"]] = by_class.get(d["donor_class_label"], 0) + 1
    res = {"target": r["label"], "donors_scored": r["n_candidates"], "listed": len(cands), "top_score_out_of_100": round(cands[0]["score"]) if cands else None,
           "listed_by_donor_type": by_class,
           "meaning": "score 0-100 combines: gave to this target, gave to similar targets, recent and frequent giving, giving level, donor type fit"}
    cols = [t("agent.col.donor"), t("agent.col.type"), t("agent.col.score"), t("agent.col.last"), t("agent.col.evidence")]
    rows = [[d["donor_id"], d["donor_class_label"], f"{d['score']:.0f}", d["last_gift_year"], "; ".join(d["evidence"][:2])] for d in cands]
    return ToolOut(res, t("agent.sum.prospects", n=len(cands), target=r["label"]), r["label"], _table(cols, rows))


def run_scenario(c, a) -> ToolOut:
    r1 = _clamp(a.get("first_time_retention_uplift_pts"), 0, 20, 0.0)
    r2 = _clamp(a.get("repeat_retention_uplift_pts"), 0, 10, 0.0)
    mult = _clamp(a.get("new_donor_inflow_multiplier"), 0.5, 1.5, 1.0)
    rec = _clamp(a.get("recurring_conversion_pct"), 0, 30, 0.0)
    gift = _clamp(a.get("major_gift_ntd"), 0, 100_000_000, 0.0)
    s = scn.scenario(c.df, c.exceptional, r1, r2, mult, rec, gift)
    res = {"kind": s["label"], "year_projected": s["projection_year"], "based_on_year": s["base_year"],
           "ordinary_giving_means": f"gifts below {ins._ntd_compact(c.exceptional)}",
           "exceptional_gift_means": f"a single gift of {ins._ntd_compact(c.exceptional)} or more; the `exceptional` figures are the total of these gifts",
           "settings": {"first_time_retention_uplift_points": r1, "repeat_retention_uplift_points": r2, "new_donor_inflow_multiplier": mult,
                        "recurring_conversion_percent": rec, "extra_exceptional_gift": _m(gift)},
           "baseline_if_nothing_changes": {"expected": _m(s["baseline"]["expected"]), "range_low": _m(s["baseline"]["low"]), "range_high": _m(s["baseline"]["high"])},
           "with_these_changes": {"expected": _m(s["scenario"]["expected"]), "range_low": _m(s["scenario"]["low"]), "range_high": _m(s["scenario"]["high"]),
                                  "difference_vs_baseline": _m(s["scenario"]["delta_vs_baseline"])}}
    text = t("agent.arg.scenario", r1=f"{r1:g}", r2=f"{r2:g}", mult=f"{mult:g}", rec=f"{rec:g}", gift=ins._ntd_compact(gift))
    link = f"/strategy?r1={r1:g}&r2={r2:g}&mult={mult:g}&rec={rec:g}&gift={gift:g}"
    return ToolOut(res, t("agent.sum.scenario", year=s["projection_year"], base=res["baseline_if_nothing_changes"]["expected"]["text"],
                          scen=res["with_these_changes"]["expected"]["text"]), text, None, link)


IMPL = {f.__name__: f for f in (giving_overview, giving_by_year, why_total_changed, concentration, monthly_pattern, donor_retention, at_risk_donors,
                                list_matching_targets, find_prospects, run_scenario)}


# ------------------------------------------------------------------------ the loop

AGENT_SYSTEM = ("You are the analyst inside NCU GIFT, a fundraising analytics tool used by university staff who are not data specialists. "
                "You can see NO data except what the tools return. Pick the tools that answer the question (usually one to three), then answer.\n"
                "How to answer:\n"
                "- Quote figures exactly as the tool's `text` fields give them. Never compute, round or combine figures yourself.\n"
                "- After every sentence that contains a figure, cite the tool results it came from as [n] using each result's `source` number, e.g. [1] or [1][2].\n"
                "- For 'who should we call / ask' questions, run at_risk_donors or find_prospects. The app shows the donor table itself next to your answer: "
                "do not list donors, just say what the list is and the main pattern.\n"
                "- For 'what if' questions, put the person's wording into run_scenario. It is a sensitivity analysis, not a forecast: say so briefly.\n"
                "- Never forecast total revenue or a year beyond the data. If no tool can answer, say what is missing.\n"
                "- If the question is not about NCU's giving data (weather, general knowledge, anything else), do NOT call a tool: say in one sentence that you can only help with the giving data.\n"
                "- Keep it under about 130 words, plain sentences, at most 4 short bullet points.\n" + RULES)

CITE = re.compile(r"\[(\d{1,2})\]")


def _strip_citations(text: str) -> tuple[str, list[int]]:
    cited = [int(x) for x in CITE.findall(text)]
    return CITE.sub("", text), cited


def _parse_args(raw: str) -> dict:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def run_agent(session: Session, dataset_id: int, df: pd.DataFrame, *, question: str, history: list[dict], exceptional: float, large: float) -> dict:
    s = gate(session)
    cfg = get_config()
    known = known_identifiers(session, dataset_id)
    ctx = SimpleNamespace(df=df, years=years_of(df), exceptional=exceptional, large=large, share_names=s.share_project_names)
    steps: list[dict] = []
    results: list[dict] = []           # what the model saw, for the number check
    arg_log: list[dict] = []
    cost = 0.0
    repairs = 0
    call_ids: list[int] = []

    def execute(name: str, args: dict) -> dict:
        n = len(steps) + 1
        tool = BY_NAME.get(name)
        step = {"n": n, "tool": name, "title": t(f"agent.tool.{name}") if tool else name, "args_text": "", "summary": "", "table": None, "link": None, "args_json": json.dumps(args, ensure_ascii=False), "ok": False}
        steps.append(step)
        if tool is None:
            step["summary"] = t("agent.step.unknown")
            return {"source": n, "error": "unknown tool"}
        try:
            out = IMPL[name](ctx, args)
        except (InsufficientData, ValueError) as e:
            step["summary"] = str(e)
            return {"source": n, "error": str(e)}
        payload = {"source": n, **out.model}
        try:
            assert_safe(payload, known)
        except UnsafePayload:
            step["summary"] = t("ai.block.leak")
            _log(session, "agent", status="blocked", error="tool result contained a donor identifier", payload_json="")
            raise Blocked("leak", t("ai.block.leak"))
        step.update(args_text=out.args_text, summary=out.summary, table=out.table, link=out.link, ok=True)
        results.append(out.model)
        arg_log.append(args)
        return payload

    if cfg.demo:
        return _demo(session, ctx, question, execute, steps, results, arg_log)

    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM.format(language=t("ai.lang_name"))}]
    for h in history[-3:]:
        messages += [{"role": "user", "content": h["question"][:300]}, {"role": "assistant", "content": h["answer"][:700]}]
    messages.append({"role": "user", "content": question.strip()[:600]})
    tools = schema_for_model()
    answer = ""
    for step_no in range(MAX_STEPS):
        last = step_no == MAX_STEPS - 1
        try:
            resp = client.chat(messages, feature="agent", tools=tools, tool_choice="none" if last else None)
        except AiError as e:
            _log(session, "agent", status="error", error=e.message, payload_json=json.dumps(messages[-1], ensure_ascii=False)[:2000])
            raise
        row = _log(session, "agent", status="ok", duration_ms=resp.latency_ms, prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
                   cost_usd=client.cost_usd(resp), payload_json=json.dumps(messages[-1], ensure_ascii=False)[:4000],
                   response_excerpt=(resp.text or json.dumps([c["name"] for c in resp.tool_calls]))[:800])
        cost += row.cost_usd
        call_ids.append(row.id)
        if resp.tool_calls and not last:
            messages.append(resp.message or {"role": "assistant", "tool_calls": []})
            for tc in resp.tool_calls[:4]:
                args = _parse_args(tc["arguments"])
                payload = execute(tc["name"], args)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(payload, ensure_ascii=False)})
            continue
        answer = resp.text
        break
    if not answer:
        raise AiError("empty", t("ai.err.empty"))

    allowed = {"tools": results, "asked": question, "args": arg_log}
    clean, cited = _strip_citations(answer)
    v = verify_numbers(clean, allowed)
    bad_cites = [c for c in cited if c < 1 or c > len(steps)]
    if (not v["ok"] or bad_cites) and results:
        repairs = 1
        fix = [{"role": "assistant", "content": answer},
               {"role": "user", "content": "These figures or sources are not in the tool results: " + ", ".join(v["unverified"] + [f"[{c}]" for c in bad_cites]) +
                ". Rewrite the answer using only figures quoted from the tool results and citing only existing source numbers. Same language and format."}]
        resp = client.chat(messages + fix, feature="agent", tools=tools, tool_choice="none")
        row = _log(session, "agent", status="ok", duration_ms=resp.latency_ms, prompt_tokens=resp.prompt_tokens, completion_tokens=resp.completion_tokens,
                   cost_usd=client.cost_usd(resp), payload_json="repair", response_excerpt=resp.text[:800])
        cost += row.cost_usd
        call_ids.append(row.id)
        answer = resp.text
        clean, cited = _strip_citations(answer)
        v = verify_numbers(clean, allowed)
        bad_cites = [c for c in cited if c < 1 or c > len(steps)]
        if bad_cites:
            v = {**v, "ok": False, "unverified": v["unverified"] + [f"[{c}]" for c in bad_cites]}
    if call_ids:
        last_row = session.get(AiCall, call_ids[-1])
        last_row.verified = v["ok"]
        session.commit()
    return {"answer": answer, "verification": v, "steps": steps, "model": resp.model, "demo": False, "cost_usd": cost, "call_ids": call_ids,
            "repairs": repairs, "llm_calls": len(call_ids)}


# ------------------------------------------------------------------------ demo (no key): a keyword planner, canned wording

def _demo(session, ctx, question, execute, steps, results, arg_log) -> dict:
    q = question.lower()
    plan: list[tuple[str, dict]]
    if any(k in q for k in ("risk", "stop", "lapse", "lose", "call", "流失", "風險", "致電", "停止")):
        plan = [("at_risk_donors", {"count": 10})]
    elif any(k in q for k in ("what if", "scenario", "retention", "如果", "情境", "留存")):
        plan = [("run_scenario", {"first_time_retention_uplift_pts": 5})]
    elif any(k in q for k in ("ask", "prospect", "match", "invite", "邀請", "配對", "潛在")):
        targets = matching.list_targets(ctx.df)
        first = next((x for x in targets if x["kind"] == "purpose"), None)
        plan = [("find_prospects", {"target_id": first["id"], "count": 10})] if first else [("giving_overview", {})]
    elif any(k in q for k in ("why", "change", "fall", "drop", "為什麼", "下降", "變動")):
        plan = [("why_total_changed", {})]
    elif any(k in q for k in ("month", "busiest", "月")):
        plan = [("monthly_pattern", {})]
    elif any(k in q for k in ("few", "depend", "concentrat", "top", "集中", "少數")):
        plan = [("concentration", {})]
    else:
        plan = [("giving_overview", {})]
    lines = []
    for name, args in plan:
        payload = execute(name, args)
        st = steps[-1]
        if st["ok"]:
            lines.append(f"{st['summary']} [{st['n']}]")
    body = " ".join(lines) or t("agent.sum.none")
    answer = t("ai.demo.prefix") + body
    clean, cited = _strip_citations(answer)
    v = verify_numbers(clean, {"tools": results, "asked": question, "args": arg_log})
    return {"answer": answer, "verification": v, "steps": steps, "model": "demo", "demo": True, "cost_usd": 0.0, "call_ids": []}
