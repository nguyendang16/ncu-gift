"""The summary the model is allowed to see: the same aggregate tables the dashboard shows, with each figure pre-formatted
in the user's language (`text`) so the model quotes rather than computes. No donor names, no donor codes."""
from __future__ import annotations

import pandas as pd

from .. import i18n
from ..i18n import t
from ..services import insights as ins, journey as jr, risk as rk, stats
from ..services.frame import InsufficientData, years_of


def _m(x: float) -> dict:
    return {"value": round(float(x), 2), "text": ins._ntd_compact(x)}


def _p(x: float | None, d: int = 0, signed: bool = False) -> dict | None:
    if x is None:
        return None
    return {"value": round(float(x), 4), "text": ins._signed(x) if signed else f"{x:.{d}f}%"}


def _share(x: float, d: int = 0) -> dict:
    return {"value": round(float(x), 4), "text": ins._pct(x, d)}


def _rows(rows: list[dict]) -> list[dict]:
    return [{"name": r["label"], "amount": _m(r["amount"]), "share_of_money": _share(r["share_amount"] or 0)} for r in rows if r["amount"] is not None]


def build_facts(df: pd.DataFrame, year: int, exceptional: float, large: float, *, share_project_names: bool) -> dict:
    ys = years_of(df)
    o = stats.overview(df, year, exceptional, large, "all")
    k = o["kpis"]
    facts: dict = {
        "context": {
            "organisation": "National Central University (NCU), Taiwan: an alumni and fundraising office",
            "data": "donation records, pseudonymised; no donor names or codes are included",
            "currency": "New Taiwan dollars (NT$)",
            "years_available": ys, "selected_year": year,
            "ordinary_giving_means": f"gifts below {ins._ntd_compact(exceptional)}",
            "exceptional_gift_means": f"a single gift of {ins._ntd_compact(exceptional)} or more",
        },
        "yearly": [{"year": r["year"], "total": _m(r["total"]), "ordinary": _m(r["regular"]), "exceptional": _m(r["exceptional"]),
                    "exceptional_gifts": r["n_exceptional"], "donors": r["donors"],
                    "total_change_vs_previous_year": _p(r["total_yoy_pct"], signed=True),
                    "ordinary_change_vs_previous_year": _p(r["regular_yoy_pct"], signed=True)} for r in stats.trend(df, exceptional)],
        "selected_year_detail": {
            "donors": k["donors"], "gift_records": k["records"], "repeat_donors": k["repeat_selected"],
            "large_gifts": {"threshold": _m(large), "count": k["large_gifts"], "amount": _m(k["large_gifts_amount"])},
            "by_donor_type": _rows(o["donor_classes"]), "by_purpose_group": _rows(o["purpose_groups"]),
            "by_payment_method": _rows(o["methods"]), "by_gift_size": [{"name": b["label"], "amount": _m(b["amount"]), "gifts": b["count"]} for b in o["bands"]],
            "repeat_donors": k["repeat_selected"], "credit_card_gifts": k["card_gifts"],
            "million_projects": k["million_projects"],
            "million_share": _share(k["million_share"]) if k["million_share"] is not None else None,
            "top_project_share": _share(k["top_project_share"]) if k["top_project_share"] is not None else None,
            "accounting_office": "not in these records: do not invent cash receipts or cash surplus",
        },
        "data_notes": o["notes"],
    }
    if share_project_names:
        facts["selected_year_detail"]["largest_projects"] = [{"name": p["project"], "amount": _m(p["amount"])} for p in o["projects_over_1m"][:8]]
    try:
        j = jr.journey(df)
        facts["donor_journey"] = {
            "states_by_year": [{"year": y["year"], "new": y["new"], "retained": y["retained"], "reactivated": y["reactivated"], "lapsed_from_previous_year": y["lapsed"]}
                               for y in j["years"] if y["history_available"]],
            "second_gift": [{"first_time_donors_in": f["cohort_year"], "number": f["first_time"]["n"], "gave_again_next_year": f["first_time"]["returned"],
                             "share_who_gave_again": _share(f["first_time"]["rate"]), "repeat_donors_share_who_gave_again": _share(f["repeat"]["rate"])}
                            for f in j["funnel"]]}
    except InsufficientData:
        pass
    try:
        b = ins.bridge(df, year, exceptional)
        facts["why_total_changed"] = {"from_year": b["prev_year"], "to_year": b["year"], "start_total": _m(b["start"]), "end_total": _m(b["end"]),
                                      "steps": [{"name": s["label"], "effect": _m(s["value"]), "donors": s["donors"]} for s in b["steps"]]}
    except InsufficientData:
        pass
    try:
        c = ins.concentration(df, year, exceptional)
        facts["concentration"] = {"top_1_percent_of_donors_share_of_all_money": _share(c["all"]["top1pct_share"]),
                                  "top_1_percent_share_of_ordinary_money": _share(c["ordinary"]["top1pct_share"]),
                                  "top_10_percent_share_of_all_money": _share(c["all"]["top10pct_share"]),
                                  "top_10_percent_share_of_ordinary_money": _share(c["ordinary"]["top10pct_share"]),
                                  "largest_single_donor_share": _share(c["all"]["top1_donor_share"])}
    except InsufficientData:
        pass
    try:
        r = rk.risk_report(df, top_n=20)
        facts["outreach"] = {"donors_on_call_list": len(r["donors"]), "value_at_risk_on_call_list": _m(sum(d["value_at_risk"] for d in r["donors"])),
                             "model_quality_auc": round(r["metrics"]["auc"], 2) if r["metrics"] else None,
                             "meaning": "value at risk = chance of stopping x last year's giving"}
    except InsufficientData:
        pass
    s = ins.seasonality(df, exceptional)
    ym = pd.DataFrame([c for c in s["cells"] if c["year"] == year])
    if len(ym) and ym["value"].sum() > 0:
        top = ym.sort_values("value", ascending=False).iloc[0]
        facts["seasonality"] = {"busiest_month_for_ordinary_giving": i18n.month_label(int(top["month"])), "its_share_of_the_year": _share(top["value"] / ym["value"].sum())}
    return facts
