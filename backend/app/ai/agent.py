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
import math
import re
from dataclasses import dataclass, field
from types import SimpleNamespace

import pandas as pd
from sqlalchemy.orm import Session

from .. import i18n, org
from ..i18n import t
from ..services import insights as ins, journey as jr, matching, risk as rk, roll, scenario as scn, stats
from ..services.frame import InsufficientData, cash, years_of
from . import actions as act_mod, client, guide
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
    links: list[dict] = field(default_factory=list)      # Open buttons: {label, to}
    visual: dict | None = None                  # a chart or card the app draws inside the answer (app-only, never sent to the model)


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
    Tool("list_matching_targets", "Find the purposes, departments or projects that donors can be matched to. Pass the department or project words from the question, including Chinese such as 資訊系. Returns target ids for find_prospects.",
         {"query": {"type": "string", "description": "Department, purpose or project words from the question, e.g. '資訊系' or 'scholarship'."}}),
    Tool("find_prospects", "Look up a department, institute or project in the records, then list existing donors most likely to give. Pass query as the person's own words, including a unit that is not in the preset list (for example 網路學習科技研究所). The tool searches projects, units and donor background first. Pass target_id only when list_matching_targets already returned one. The app shows the donor-roll names itself.",
         {"query": {"type": "string", "description": "The department, institute or project words from the question, unchanged."},
          "target_id": {"type": "string", "description": "Optional. A target id from list_matching_targets, such as 'unit:Computer Science'."},
          "count": {"type": "integer", "minimum": 5, "maximum": 50}}, []),
    Tool("explain_match_score", "Explain what the donor-matching score is based on: the six parts and their weights. Use when someone asks how the score is calculated or what it means. Quote the explained text. Do not invent weights.", {}),
    Tool("plan_to_raise", "Goal planning: what it would take to RAISE an extra amount of ordinary giving next year, lever by lever (keeping more first-time or repeat donors, "
         "recruiting more, recurring giving), how many typical gifts that is, and how much of the money at risk would need to be kept. Optionally for one purpose/project. "
         "Use for 'I want to raise about NT$1M, what should we do?'. The app shows the options table itself.",
         {"target_ntd": {"type": "number", "minimum": 100000, "maximum": 100000000, "description": "The extra amount to raise, in NT$ (1 million = 1000000)."},
          "focus_target_id": {"type": "string", "description": "Optional: a target id from list_matching_targets when the goal is for one purpose, department or project."}},
         ["target_ntd"]),
    Tool("find_feature", "Where something is in this system and how to use it (pages, charts, uploads, downloads, the review queue...). Use for 'where can I see...' or 'how do I...'. "
         "The app shows Open buttons for the pages you name.",
         {"query": {"type": "string", "description": "What the person wants to do or see, in a few words. Omit to list every page."}}),
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


_DEFAULT_PAGE = {"giving_overview": "overview", "giving_by_year": "overview", "why_total_changed": "bridge", "concentration": "concentration",
                 "monthly_pattern": "seasonality", "donor_retention": "journey", "at_risk_donors": "risk", "list_matching_targets": "matching"}


def _default_links(name: str, args: dict) -> list[dict]:
    """The Open button under a result: the page where the person can look at the same thing themselves."""
    if name == "find_prospects" and args.get("target_id"):
        return [guide.link("matching", target=str(args["target_id"]))]
    return [guide.link(_DEFAULT_PAGE[name])] if name in _DEFAULT_PAGE else []


def _safe_list(fn, *a, **k) -> list:
    try:
        return fn(*a, **k)
    except (InsufficientData, ValueError, KeyError, IndexError):
        return []


def _plain(o):
    """Python-only copy (numpy numbers, dates and NaN become plain JSON values) so a visual can be sent and stored."""
    if o is None:
        return None
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        o = o.item()
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    return o if isinstance(o, (str, int, float, bool)) else str(o)


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
    return ToolOut(res, t("agent.sum.overview", year=y, total=res["total"]["text"], ordinary=res["ordinary"]["text"], donors=k["donors"]), t("agent.arg.year", year=y),
                   visual={"type": "donut", "rows": [r for r in o["donor_classes"] if r["amount"]]})


def giving_by_year(c, a) -> ToolOut:
    rows = stats.trend(c.df, c.exceptional)
    res = {"years": [{"year": r["year"], "total": _m(r["total"]), "ordinary": _m(r["regular"]), "exceptional": _m(r["exceptional"]), "exceptional_gifts": r["n_exceptional"],
                      "donors": r["donors"], "total_change": _p(r["total_yoy_pct"], signed=True), "ordinary_change": _p(r["regular_yoy_pct"], signed=True)} for r in rows],
           "ordinary_giving_means": f"gifts below {ins._ntd_compact(c.exceptional)}",
           "exceptional_gift_means": f"a single gift of {ins._ntd_compact(c.exceptional)} or more; the `exceptional` figures are the total of these gifts"}
    last = res["years"][-1]
    return ToolOut(res, t("agent.sum.by_year", first=rows[0]["year"], last=last["year"], total=last["total"]["text"]), visual={"type": "trend", "rows": rows})


def why_total_changed(c, a) -> ToolOut:
    y = _year(c, a)
    b = ins.bridge(c.df, y, c.exceptional)
    res = {"from_year": b["prev_year"], "to_year": b["year"], "start_total": _m(b["start"]), "end_total": _m(b["end"]),
           "steps": [{"name": s["label"], "effect": _m(s["value"]), "donors": s["donors"]} for s in b["steps"]]}
    return ToolOut(res, t("agent.sum.bridge", start=res["start_total"]["text"], end=res["end_total"]["text"]), t("agent.arg.year", year=y), visual={"type": "bridge", "data": b})


def concentration(c, a) -> ToolOut:
    y = _year(c, a)
    k = ins.concentration(c.df, y, c.exceptional)
    res = {"year": y, "top_1_percent_of_donors_share_of_all_money": _share(k["all"]["top1pct_share"]),
           "top_1_percent_share_of_ordinary_money": _share(k["ordinary"]["top1pct_share"]),
           "top_10_percent_share_of_all_money": _share(k["all"]["top10pct_share"]),
           "top_10_percent_share_of_ordinary_money": _share(k["ordinary"]["top10pct_share"]),
           "largest_single_donor_share": _share(k["all"]["top1_donor_share"])}
    return ToolOut(res, t("agent.sum.conc", year=y, top1=res["top_1_percent_of_donors_share_of_all_money"]["text"]), t("agent.arg.year", year=y), visual={"type": "concentration", "data": k})


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
                   t("agent.sum.months", year=last["year"], month=last["busiest_months"][0]["month"]) if last else t("agent.sum.none"),
                   visual={"type": "season", "data": s})


def donor_retention(c, a) -> ToolOut:
    j = jr.journey(c.df)
    res = {"states_by_year": [{"year": y["year"], "new": y["new"], "retained": y["retained"], "reactivated": y["reactivated"], "lapsed_from_previous_year": y["lapsed"]}
                              for y in j["years"] if y["history_available"]],
           "second_gift": [{"first_time_donors_in": f["cohort_year"], "number": f["first_time"]["n"], "gave_again_next_year": f["first_time"]["returned"],
                            "share_who_gave_again": _share(f["first_time"]["rate"]),
                            "repeat_donors_share_who_gave_again": _share(f["repeat"]["rate"])} for f in j["funnel"]]}
    g = res["second_gift"][-1] if res["second_gift"] else None
    return ToolOut(res, t("agent.sum.retention", rate=g["share_who_gave_again"]["text"], year=g["first_time_donors_in"]) if g else t("agent.sum.none"), visual={"type": "sankey", "data": j})


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
                      "share_of_all_tested_donors_who_stopped": _share(m["lapse_rate_test"]),
                      "of_top_20_on_the_value_list_share_who_stopped": _share(m["precision_at_k"][0]["precision"]),
                      "note": "the value list holds mostly large donors, who stop less often than average; do not present its hit rate as proof the model works"} if m else None)}
    cols = [t("agent.col.donor"), t("agent.col.type"), t("agent.col.gave"), t("agent.col.chance"), t("agent.col.at_stake"), t("agent.col.why")]
    rows = [[d["donor_id"], d["donor_class_label"], i18n_money(d["giving_last_year"]), f"{d['p_lapse'] * 100:.0f}%", i18n_money(d["value_at_risk"]),
             "; ".join(d["reasons"][:2])] for d in donors]
    return ToolOut(res, t("agent.sum.risk", n=len(donors), total=res["value_at_risk_of_listed"]["text"]), t("agent.arg.count", n=n), _table(cols, rows),
                   visual={"type": "bubble", "points": r.get("points", [])})


def i18n_money(x: float) -> str:
    return ins._ntd_compact(x)


def list_matching_targets(c, a) -> ToolOut:
    q = str(a.get("query") or "").strip().lower()
    rows = matching.list_targets(c.df)
    if not c.share_names:
        rows = [r for r in rows if r["kind"] != "project"]
    hit = org.find_department(q) if q else None
    if hit:
        dept = hit[0]
        rows = [r for r in rows if r["id"] == f"unit:{dept}" or dept.lower() in r["id"].lower()]
        rows.sort(key=lambda r: (r["id"] != f"unit:{dept}", -r["donors"]))
    elif q:
        rows = [r for r in rows if q in r["label"].lower() or q in r["id"].lower()]
        rows.sort(key=lambda r: -r["donors"])
    else:
        rows.sort(key=lambda r: -r["donors"])
    rows = rows[:15]
    model = {"matched": len(rows), "targets": [{"target_id": r["id"], "label": r["label"], "kind": r["kind"], "donors_who_gave_to_it": r["donors"]} for r in rows]}
    summary = t("agent.sum.targets", n=len(rows))
    if q and not rows:
        bg = matching.related_background(c.df, str(a.get("query") or ""))
        if bg["found"]:
            model["looked_up"] = bg["phrase"]
            model["related_projects"] = len(bg["projects"])
            model["people_with_this_background"] = bg["donors"]
            model["next"] = "call find_prospects with query set to the same words"
            if c.share_names:
                model["project_names"] = [p["label"] for p in bg["projects"][:8]]
            purposes = []
            for p in bg["projects"]:
                if p["purpose_label"] and p["purpose_label"] not in purposes:
                    purposes.append(p["purpose_label"])
            summary = _background_line(bg["phrase"], len(bg["projects"]), bg["donors"], purposes[:4])
    return ToolOut(model, summary, t("agent.arg.query", q=q) if q else "")


def _gave_projects(df: pd.DataFrame, donor: str, kind: str, name: str) -> str:
    h = df[df["donor_code"] == donor]
    if kind == "unit":
        scoped = h[h["unit"] == name]
    elif kind == "sub":
        scoped = h[h["purpose_sub"] == name]
    else:
        scoped = h[h["project_name"] == name]
    if len(scoped):
        h = scoped
    named = h.dropna(subset=["project_name"])
    if named.empty:
        return "–"
    totals = named.groupby("project_name")["amount_ntd"].sum().sort_values(ascending=False)
    return "、".join(i18n.project_label(str(n)) for n in list(totals.head(2).index))


def _background_line(phrase: str, projects: int, donors: int, purposes: list[str]) -> str:
    phrase = str(phrase).replace("{", "").replace("}", "")
    if purposes:
        sep = "、" if i18n.current() == "zh-TW" else ", "
        return t("agent.sum.prospects_bg_purpose", phrase=phrase, projects=projects, donors=donors, purposes=sep.join(purposes))
    return t("agent.sum.prospects_bg", phrase=phrase, projects=projects, donors=donors)


def _safe_phrase(phrase: str) -> str:
    return str(phrase).replace("{", "").replace("}", "")


def _public_prospects(c, bg: dict, n: int) -> ToolOut:
    phrase = _safe_phrase(bg.get("phrase") or "")
    related = _safe_phrase(bg.get("public_related") or "")
    source = _safe_phrase(bg.get("public_source") or "")
    cands = bg.get("candidates") or []
    if not cands:
        key = "agent.sum.prospects_web_empty" if source else "agent.sum.prospects_web_empty_nosource"
        summary = t(key, phrase=phrase, related=related, source=source)
        return ToolOut({"found": False, "looked_up": phrase, "public_related": related, "source": source, "listed": 0},
                       summary, t("agent.arg.query", q=phrase) if phrase else "")
    kind, target_name = matching.parse_target(bg["target_id"]) if bg.get("target_id") else ("project", "")
    key = "agent.sum.prospects_web" if source else "agent.sum.prospects_web_nosource"
    summary = t(key, phrase=phrase, related=related, source=source, n=len(cands))
    out = _prospect_result(c, cands, bg["label"], kind, target_name, scored=bg["n_candidates"],
                           phrase=phrase, projects=bg.get("projects") or [], donors=bg["donors"], target_id=bg.get("target_id"),
                           summary=summary, extra={"public_related": related, "source": source, "from_public_page": True})
    out.args_text = (t("agent.arg.query", q=phrase) + (f" · {related}" if related else "")).strip()
    return out


def _prospect_result(c, cands, label: str, kind: str, target_name: str, *, scored: int, phrase: str, projects: list[dict], donors: int, target_id: str | None,
                     summary: str | None = None, extra: dict | None = None) -> ToolOut:
    by_class: dict[str, int] = {}
    for d in cands:
        by_class[d["donor_class_label"]] = by_class.get(d["donor_class_label"], 0) + 1
    purposes: list[str] = []
    for p in projects:
        if p.get("purpose_label") and p["purpose_label"] not in purposes:
            purposes.append(p["purpose_label"])
    public = label
    if not c.share_names and target_id and target_id.startswith("project:"):
        public = phrase or label
    res = {"found": True, "looked_up": phrase, "related_projects": len(projects), "people_with_this_background": donors,
           "purposes": purposes[:4], "target": public, "donors_scored": scored, "listed": len(cands),
           "top_score_out_of_100": round(cands[0]["score"]) if cands else None, "listed_by_donor_type": by_class,
           "meaning": "The records were searched for this name before anyone was listed. The app shows the names. Anonymous donors stay masked."}
    if extra:
        res.update(extra)
    if c.share_names:
        res["project_names"] = [p["label"] for p in projects[:8]]
    names = getattr(c, "names", {}) or {}
    cols = [t("agent.col.donor"), t("agent.col.type"), t("agent.col.score"), t("agent.col.last"), t("agent.col.projects"), t("agent.col.evidence")]
    rows = [[roll.display_name(d["anonymous"], d["donor_id"], names), d["donor_class_label"], f"{d['score']:.0f}", d["last_gift_year"],
             _gave_projects(c.df, d["donor_id"], kind, target_name), "; ".join(d["evidence"][:2])] for d in cands]
    line = _background_line(phrase or label, len(projects), donors, purposes[:4])
    if summary is None:
        summary = line + t("agent.sum.prospects", n=len(cands), target=label)
    args = t("agent.arg.query", q=phrase) if phrase else label
    if projects:
        args += " · " + "、".join(p["label"] for p in projects[:3])
    known = {r["id"] for r in matching.list_targets(c.df)}
    links = [guide.link("matching", target=target_id)] if target_id and target_id in known else [guide.link("matching")]
    return ToolOut(res, summary, args, _table(cols, rows), links=links)


def find_prospects(c, a) -> ToolOut:
    query = str(a.get("query") or "").strip()
    tid = str(a.get("target_id") or "").strip()
    n = int(_clamp(a.get("count"), 5, 50, 15))
    if query and not tid:
        bg = matching.prospects_for_text(c.df, query, n)
        phrase = bg["phrase"]
        if bg.get("via") == "public":
            return _public_prospects(c, bg, n)
        if not bg["found"] or not bg["candidates"]:
            return ToolOut({"found": False, "looked_up": phrase, "related_projects": 0, "people_with_this_background": 0},
                           t("agent.sum.prospects_none", phrase=str(phrase).replace("{", "").replace("}", "")),
                           t("agent.arg.query", q=phrase) if phrase else "")
        kind, target_name = matching.parse_target(bg["target_id"]) if bg.get("target_id") else ("project", "")
        return _prospect_result(c, bg["candidates"], bg["label"], kind, target_name, scored=bg["n_candidates"],
                                phrase=phrase, projects=bg["projects"], donors=bg["donors"], target_id=bg.get("target_id"))
    valid = {r["id"]: r for r in matching.list_targets(c.df)}
    if tid not in valid or (valid[tid]["kind"] == "project" and not c.share_names):
        raise ValueError("unknown target_id: pass query set to the person's words, or call list_matching_targets and use one of its ids")
    r = matching.rank(c.df, tid, n)
    kind, target_name = matching.parse_target(tid)
    cands = r["candidates"]
    by_class: dict[str, int] = {}
    for d in cands:
        by_class[d["donor_class_label"]] = by_class.get(d["donor_class_label"], 0) + 1
    res = {"target": r["label"], "donors_scored": r["n_candidates"], "listed": len(cands), "top_score_out_of_100": round(cands[0]["score"]) if cands else None,
           "listed_by_donor_type": by_class,
           "meaning": "Ranked from the donor roll by gifts already made to this target and to similar purposes. The app shows the names. Anonymous donors stay masked."}
    names = getattr(c, "names", {}) or {}
    cols = [t("agent.col.donor"), t("agent.col.type"), t("agent.col.score"), t("agent.col.last"), t("agent.col.projects"), t("agent.col.evidence")]
    rows = [[roll.display_name(d["anonymous"], d["donor_id"], names), d["donor_class_label"], f"{d['score']:.0f}", d["last_gift_year"],
             _gave_projects(c.df, d["donor_id"], kind, target_name), "; ".join(d["evidence"][:2])] for d in cands]
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
    lk = guide.link("strategy", r1=f"{r1:g}", r2=f"{r2:g}", mult=f"{mult:g}", rec=f"{rec:g}", gift=f"{gift:g}")
    return ToolOut(res, t("agent.sum.scenario", year=s["projection_year"], base=res["baseline_if_nothing_changes"]["expected"]["text"],
                          scen=res["with_these_changes"]["expected"]["text"]), text, None, lk["to"], [lk],
                   {"type": "whatif", "settings": {"r1": r1, "r2": r2, "mult": mult, "rec": rec, "gift": gift}, "scenario": s})


_LEVERS = [("first_time_retention_uplift_pts", "r1", 0.0, 20.0), ("repeat_retention_uplift_pts", "r2", 0.0, 10.0),
           ("new_donor_inflow_multiplier", "mult", 1.0, 1.5), ("recurring_conversion_pct", "rec", 0.0, 30.0)]
_STRETCH = {"r1": 10.0, "r2": 5.0, "mult": 1.25, "rec": 15.0}       # a demanding but plausible effort for each lever


def _delta(c, r1=0.0, r2=0.0, mult=1.0, rec=0.0) -> tuple[float, dict]:
    s = scn.scenario(c.df, c.exceptional, r1, r2, mult, rec, 0.0)
    return s["scenario"]["delta_vs_baseline"], s


def _solve(f, lo: float, hi: float, target: float) -> float | None:
    """Smallest x in [lo, hi] with f(x) >= target (f is non-decreasing); None if even hi falls short."""
    if f(hi) < target:
        return None
    for _ in range(24):
        mid = (lo + hi) / 2
        if f(mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def plan_to_raise(c, a) -> ToolOut:
    target = _clamp(a.get("target_ntd"), 100_000, 100_000_000, 1_000_000)
    base_delta, s0 = _delta(c)
    base = s0["baseline"]["expected"]
    obs, coh = s0["observed"], s0["cohorts"]
    n_first, n_repeat, n_new = obs["first_time_retention"]["n"], obs["repeat_retention"]["n"], coh[2]["donors"]
    people = {"r1": n_first, "r2": n_repeat, "mult": n_new}
    levers, rows = [], []
    for name, key, lo, hi in _LEVERS:
        f = lambda x, key=key: _delta(c, **{key: x})[0]
        need = _solve(f, lo, hi, target)
        top = f(hi)
        if need is None:
            levers.append({"lever": name, "reaches_target_alone": False, "most_it_can_add": _m(top), "at_setting": hi if key != "mult" else f"{(hi - 1) * 100:.0f}% more new donors"})
            rows.append([t(f"agent.lever.{key}"), t("agent.plan.cannot", most=ins._ntd_compact(top)), "–", t("agent.plan.no")])
            continue
        shown = need if key != "mult" else (need - 1) * 100
        who = people.get(key)
        extra = None if who is None else round(who * (need / 100 if key in ("r1", "r2") else (need - 1)))
        levers.append({"lever": name, "reaches_target_alone": True, "what_it_takes": t(f"agent.plan.need_{key}", x=f"{shown:.1f}".rstrip("0").rstrip(".")), "needed_setting": round(shown, 1), "setting_unit": {"r1": "percentage points", "r2": "percentage points",
                       "mult": "% more new donors than last year", "rec": "% of retained donors moved to recurring giving"}[key], "about_extra_donors": extra})
        rows.append([t(f"agent.lever.{key}"), t(f"agent.plan.need_{key}", x=f"{shown:.1f}".rstrip("0").rstrip(".")), "" if extra is None else f"≈ {extra}", t("agent.plan.yes")])
    # a balanced effort: every lever scaled together until the goal is met
    full = {k: v for k, v in _STRETCH.items()}
    scale_for = lambda sc: _delta(c, r1=min(full["r1"] * sc, 20), r2=min(full["r2"] * sc, 10), mult=1 + min((full["mult"] - 1) * sc, 0.5), rec=min(full["rec"] * sc, 30))[0]
    sc = _solve(scale_for, 0.0, 2.0, target)
    balanced = None
    if sc is not None:
        bs = {"r1": round(min(full["r1"] * sc, 20), 1), "r2": round(min(full["r2"] * sc, 10), 1), "mult": round(1 + min((full["mult"] - 1) * sc, 0.5), 2),
              "rec": round(min(full["rec"] * sc, 30), 1)}
        balanced = {"first_time_retention_uplift_points": bs["r1"], "repeat_retention_uplift_points": bs["r2"], "new_donor_inflow_multiplier": bs["mult"],
                    "new_donors_percent_more_than_last_year": round((bs["mult"] - 1) * 100, 1), "recurring_conversion_percent": bs["rec"],
                    "described_as": [t("agent.plan.need_r1", x=f"{bs['r1']:g}"), t("agent.plan.need_r2", x=f"{bs['r2']:g}"),
                                     t("agent.plan.need_mult", x=f"{(bs['mult'] - 1) * 100:.1f}".rstrip("0").rstrip(".")), t("agent.plan.need_rec", x=f"{bs['rec']:g}")], "adds_about": _m(_delta(c, **bs)[0]),
                    "meaning": "all four levers moved together; a demanding but plausible effort when the share of stretch used is below 100%",
                    "share_of_a_demanding_effort_used": round(min(sc, 2.0) * 100)}
    else:
        top = scale_for(2.0)
        balanced = {"reaches_target": False, "most_all_levers_can_add": _m(top)}
    # typical gifts
    cy = cash(c.df[c.df["year"] == c.years[-1]])
    ordv = cy[cy["amount_ntd"] < c.exceptional]["amount_ntd"]
    gifts = {}
    if len(ordv):
        med, p75 = float(ordv.median()), float(ordv.quantile(0.75))
        gifts = {"ordinary_gifts_last_year": int(len(ordv)), "median_gift": _m(med), "upper_quartile_gift": _m(p75),
                 "extra_gifts_needed_at_median": math.ceil(target / med), "extra_gifts_needed_at_upper_quartile": math.ceil(target / p75),
                 "as_share_of_last_years_gifts": _share(math.ceil(target / med) / len(ordv))}
        mid = ordv[(ordv >= 100_000) & (ordv < 1_000_000)]
        if len(mid) >= 3:
            gifts["mid_level_gifts_100k_to_1m"] = {"last_year": int(len(mid)), "median": _m(float(mid.median())), "extra_needed": math.ceil(target / float(mid.median()))}
    out = {"goal": {"extra_ordinary_giving": _m(target), "year": s0["projection_year"],
                    "baseline_ordinary_giving_if_nothing_changes": _m(base), "range_of_baseline": [_m(s0["baseline"]["low"]), _m(s0["baseline"]["high"])],
                    "assumption": "the goal is EXTRA ordinary giving on top of the baseline; tell the person this assumption and offer to redo it for one project"},
           "levers_each_on_its_own": levers, "levers_scope": "organisation-wide ordinary giving, even when a focus target is given: say so if there is a focus", "balanced_effort": balanced, "typical_gifts": gifts}
    links = []
    if sc is not None:
        q = {"r1": balanced["first_time_retention_uplift_points"], "r2": balanced["repeat_retention_uplift_points"], "mult": balanced["new_donor_inflow_multiplier"],
             "rec": balanced["recurring_conversion_percent"]}
        links.append(guide.link("strategy", **q))
    # money at risk
    try:
        r = rk.risk_report(c.df, top_n=50)
        d = r["donors"]
        v20, v50 = sum(x["value_at_risk"] for x in d[:20]), sum(x["value_at_risk"] for x in d[:50])
        out["money_at_risk"] = {"top_20_value_at_risk": _m(v20), "top_50_value_at_risk": _m(v50),
                                "share_of_top_20_to_keep_to_reach_goal": _share(target / v20) if target <= v20 else "more than all of it",
                                "share_of_top_50_to_keep_to_reach_goal": _share(target / v50) if target <= v50 else "more than all of it"}
        rows.append([t("agent.plan.keep"), t("agent.plan.keep_need", pct=ins._pct(target / v20, 0) if target <= v20 else ">100%", amount=ins._ntd_compact(v20)), "≈ 20", t("agent.plan.yes") if target <= v20 else t("agent.plan.no")])
        links.append(guide.link("risk"))
    except InsufficientData:
        pass
    if gifts:
        rows.append([t("agent.plan.gifts"), t("agent.plan.gifts_need", n=gifts["extra_gifts_needed_at_median"], gift=ins._ntd_compact(med)), f"≈ {gifts['extra_gifts_needed_at_median']}", t("agent.plan.yes")])
    # concrete next actions, from the system's own playbook (evidence and steps written from the data, not generic advice)
    include_actions = a.get("include_actions", True)         # the Goal planner page does not need them
    cands = _safe_list(act_mod.candidates, c.df, c.years[-1], c.exceptional, c.large) if include_actions else []
    picks = [act_mod.playbook(x) for x in act_mod.top(cands, 4)]
    out["concrete_next_actions"] = [{"title": p["title"], "why": p["why"], "steps": p["steps"], "expected_effect": p["expected_effect"], "where_in_the_system": guide.title(p["page"])} for p in picks]
    for p in picks:
        if p["link"] not in links:
            links.append(p["link"])
    plan_visual = None
    if sc is not None:
        plan_visual = {"type": "whatif", "settings": {"r1": bs["r1"], "r2": bs["r2"], "mult": bs["mult"], "rec": bs["rec"], "gift": 0.0}, "scenario": _delta(c, **bs)[1], "goal": target}
    summary = t("agent.sum.plan", goal=ins._ntd_compact(target), base=ins._ntd_compact(base))
    # optional: the same goal for one purpose / project
    tid = str(a.get("focus_target_id") or "").strip()
    args_text = t("agent.arg.goal", goal=ins._ntd_compact(target))
    if tid:
        valid = {x["id"]: x for x in matching.list_targets(c.df)}
        if tid in valid and not (valid[tid]["kind"] == "project" and not c.share_names):
            kind, name = matching.parse_target(tid)
            sub_df = cash(c.df[matching._mask(c.df, kind, name)])
            last = sub_df[sub_df["year"] == c.years[-1]]["amount_ntd"]
            past = set(sub_df[sub_df["year"] < c.years[-1]]["donor_code"].dropna()) - set(sub_df[sub_df["year"] == c.years[-1]]["donor_code"].dropna())
            focus = {"target": valid[tid]["label"], "donors_who_ever_gave_to_it": int(valid[tid]["donors"]), "gifts_last_year": int(len(last)),
                     "given_last_year": _m(float(last.sum())), "donors_who_gave_before_but_not_last_year": len(past)}
            if len(last):
                m = float(last.median())
                focus.update({"median_gift": _m(m), "extra_gifts_needed_at_median": math.ceil(target / m)})
            out["focus"] = focus
            args_text += " · " + valid[tid]["label"]
            links.append(guide.link("matching", target=tid))
            try:
                links.append(guide.link("briefs", project=tid))
            except KeyError:
                pass
    return ToolOut(out, summary, args_text, _table([t("agent.plan.col_lever"), t("agent.plan.col_need"), t("agent.plan.col_people"), t("agent.plan.col_alone")], rows),
                   None, links, plan_visual)


def explain_match_score(c, a) -> ToolOut:
    order = ("direct", "unit", "college", "sub", "active", "capacity")
    parts = [{"part": t(f"agent.score.{k}"), "weight": matching.WEIGHTS[k], "means": t(f"agent.score.{k}_means")} for k in order]
    total = round(matching.MAX_SCORE, 1)
    lines = [t("agent.score.lead", top=100)]
    lines += [t("agent.score.part", name=p["part"], weight=f"{p['weight']:g}", means=p["means"]) for p in parts]
    lines.append(t("agent.score.recent"))
    lines.append(t("agent.score.combine", total=f"{total:g}", top=100))
    text = " ".join(lines)
    model = {"score_out_of": 100, "weight_total": total, "parts": parts, "explained": text,
             "recent_gift_rule": t("agent.score.recent")}
    table = _table([t("agent.score.col_part"), t("agent.score.col_weight"), t("agent.score.col_means")],
                   [[p["part"], f"{p['weight']:g}", p["means"]] for p in parts])
    return ToolOut(model, text, "", table, links=[guide.link("matching")])


def find_feature(c, a) -> ToolOut:
    ids = guide.search(str(a.get("query") or ""))
    return ToolOut({"pages": [guide.describe(i) for i in ids]}, t("agent.sum.features", n=len(ids)), "",
                   None, None, [guide.link(i) for i in ids])


IMPL = {f.__name__: f for f in (plan_to_raise, find_feature, giving_overview, giving_by_year, why_total_changed, concentration, monthly_pattern, donor_retention, at_risk_donors,
                                list_matching_targets, find_prospects, explain_match_score, run_scenario)}


# ------------------------------------------------------------------------ the loop

AGENT_SYSTEM = ("You are the analyst inside NCU GIFT, a fundraising analytics tool used by university staff who are not data specialists. "
                "You can see NO data except what the tools return. Pick the tools that answer the question (usually one to three), then answer.\n"
                "How to answer:\n"
                "- Quote figures exactly as the tool's `text` fields give them. Never compute, round or combine figures yourself.\n"
                "- After every sentence that contains a figure, cite the tool results it came from as [n] using each result's `source` number, e.g. [1] or [1][2].\n"
                "- For 'who should we call / ask' questions, run at_risk_donors when they might stop giving. "
                "When they name a department, institute, college or project, or ask who is more likely to donate — including a unit that is not in any preset list, such as 網路學習科技研究所 — "
                "call find_prospects with query set to their words. Do not invent a target id. "
                "The tool first searches the gift records. If that name is absent, it reads a public web page about the unit and ranks people who already gave to the related fields named there, such as information engineering and education. "
                "If public_related is present, say that first, in the tool's words: the name is not in the gift records, and the public page connects it to public_related. Quote the listed count. Do not add a description the tool did not return. "
                "If it reports that nothing matched, say so in one sentence and do not recommend anyone. "
                "If the records themselves matched, first say what was found (the looked-up name, how many related projects, the purposes, how many people already gave), quoting those figures, "
                "then say the app lists the more likely donors beside your answer. Do not list donors yourself. Anonymous donors stay masked.\n"
                "- When they ask what the matching score is based on, or how it is calculated, call explain_match_score and repeat its `explained` text. Do not change the weights.\n"
                "- For goal questions ('I want to raise about NT$1M', 'how do we reach X', 'what should we do to ...'), call plan_to_raise with the amount "
                "(1 million = 1000000; 萬 = 10000) and, only if the person names one, a focus target. The goal means EXTRA ordinary giving on top of the baseline: say so. "
                "Answer in four short parts: what the goal means; the two or three most realistic options with their figures in plain words (people, gifts, shares), "
                "saying plainly when one lever alone cannot reach it; one recommended combination quoting the balanced-effort `described_as` lines and each lever's `what_it_takes` exactly as given (never convert, re-word or re-interpret them: '3.7% more new donors' is not '3.7 times'); the next three concrete actions, "
                "taken from `concrete_next_actions` in the tool result (say what to do, with whom or what, and in which page; never generic advice like 'review the options'). "
                "The app adds the Open buttons. Up to about 220 words for these.\n"
                "- For 'where can I see ...' or 'how do I ...' questions, call find_feature and describe each page in one or two sentences: what it shows and how to use it. "
                "Never invent a feature that the tool did not list. The app adds the Open buttons.\n"
                "- For 'what if' questions, put the person's wording into run_scenario. It is a sensitivity analysis, not a forecast: say so briefly.\n"
                "- Never forecast total revenue or a year beyond the data. If no tool can answer, say what is missing.\n"
                "- If the question is not about NCU's giving data (weather, general knowledge, anything else), do NOT call a tool: say in one sentence that you can only help with the giving data.\n"
                "- Keep other answers under about 130 words, plain sentences, at most 4 short bullet points.\n{glossary}" + RULES)

CITE = re.compile(r"\[(\d{1,2})\]")


def _strip_citations(text: str) -> tuple[str, list[int]]:
    cited = [int(x) for x in CITE.findall(text)]
    return re.sub(r"(?m)^\s*\d{1,2}[.)]\s+", "", CITE.sub("", text)), cited         # "1." list numbering is not a figure


def _parse_args(raw: str) -> dict:
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def run_agent(session: Session, dataset_id: int, df: pd.DataFrame, *, question: str, history: list[dict], exceptional: float, large: float, emit=None) -> dict:
    """`emit(event)` (optional) is told what is happening: {"type": "thinking"} before each model call and {"type": "step", "step": ...} as each analysis finishes."""
    emit = emit or (lambda _e: None)
    s = gate(session)
    cfg = get_config()
    known = known_identifiers(session, dataset_id)
    ctx = SimpleNamespace(df=df, years=years_of(df), exceptional=exceptional, large=large, share_names=s.share_project_names,
                          names=roll.names_for(session, dataset_id) if dataset_id is not None else {})
    steps: list[dict] = []
    results: list[dict] = []           # what the model saw, for the number check
    arg_log: list[dict] = []
    cost = 0.0
    repairs = 0
    call_ids: list[int] = []

    def execute(name: str, args: dict) -> dict:
        n = len(steps) + 1
        tool = BY_NAME.get(name)
        step = {"n": n, "tool": name, "title": t(f"agent.tool.{name}") if tool else name, "args_text": "", "summary": "", "table": None, "link": None, "links": [], "visual": None, "args_json": json.dumps(args, ensure_ascii=False), "ok": False}
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
        links = out.links or _default_links(name, args)
        step.update(args_text=out.args_text, summary=out.summary, table=out.table, links=links, link=out.link or (links[0]["to"] if links else None),
                    visual=_plain(out.visual), ok=True)
        results.append(out.model)
        arg_log.append(args)
        return payload

    if cfg.demo:
        return _demo(session, ctx, question, execute, steps, results, arg_log, emit)

    messages: list[dict] = [{"role": "system", "content": AGENT_SYSTEM.format(language=t("ai.lang_name"), glossary=t("ai.glossary"))}]
    for h in history[-3:]:
        messages += [{"role": "user", "content": h["question"][:300]}, {"role": "assistant", "content": h["answer"][:700]}]
    messages.append({"role": "user", "content": question.strip()[:600]})
    tools = schema_for_model()
    answer = ""
    for step_no in range(MAX_STEPS):
        last = step_no == MAX_STEPS - 1
        emit({"type": "thinking", "n": step_no})
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
                emit({"type": "step", "step": steps[-1]})
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
        emit({"type": "checking"})
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

def _names_a_unit(question: str) -> bool:
    if org.find_department(question):
        return True
    phrase = matching.subject_phrase(question)
    return any(phrase.endswith(suf) for suf in ("研究所", "學系", "學院", "學程", "中心"))


def _demo(session, ctx, question, execute, steps, results, arg_log, emit=lambda _e: None) -> dict:
    q = question.lower()
    plan: list[tuple[str, dict]]
    asks_score = ("配對分數" in question or "分數依據" in question or ("分數" in question and any(k in question for k in ("依據", "怎麼", "如何", "什麼", "計算", "組成")))
                  or ("score" in q and any(k in q for k in ("based", "how", "weight", "mean", "calculat"))))
    fundraising = any(k in q for k in ("募款", "找誰", "可能捐", "prospect", "fundrais", "推薦", "名單"))
    why = any(k in q for k in ("為什麼", "下降", "變動", "why", "drop", "fall", "change"))
    stop = any(k in q for k in ("流失", "風險", "停止", "lapse", "stop", "risk", "lose", "致電"))
    other = why or any(k in q for k in ("如果", "情境", "what if", "scenario", "總額", "多少", "how much", "total"))
    if asks_score:
        plan = [("explain_match_score", {})]
    elif _names_a_unit(question) and fundraising and not why and not stop:
        plan = [("find_prospects", {"query": question, "count": 10})]
    elif _names_a_unit(question) and not other and not stop and not any(k in q for k in ("call", "月", "集中", "month")):
        plan = [("find_prospects", {"query": question, "count": 10})]
    elif any(k in q for k in ("risk", "stop", "lapse", "lose", "call", "流失", "風險", "致電", "停止")):
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
        emit({"type": "thinking", "n": 0})
        payload = execute(name, args)
        st = steps[-1]
        emit({"type": "step", "step": st})
        if st["ok"]:
            lines.append(f"{st['summary']} [{st['n']}]")
    body = " ".join(lines) or t("agent.sum.none")
    answer = t("ai.demo.prefix") + body
    clean, cited = _strip_citations(answer)
    v = verify_numbers(clean, {"tools": results, "asked": question, "args": arg_log})
    return {"answer": answer, "verification": v, "steps": steps, "model": "demo", "demo": True, "cost_usd": 0.0, "call_ids": []}
