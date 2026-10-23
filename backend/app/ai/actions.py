"""Next actions for the Overview: what staff could do this month, each tied to figures from the data.

`candidates()` computes the evidence and the estimated effect of every possible action with the system's own analyses (nothing is
generated). `playbook()` turns one candidate into plain-language text from the locale catalogues. The AI chooses and orders four of
the candidates and words them for this year; if it fails, or in demo mode, the playbook text is used as it is.
Every effect is an "if ..." with its assumption written next to it: a sensitivity, never a forecast."""
from __future__ import annotations

import pandas as pd

from .. import i18n
from ..i18n import t
from ..services import insights as ins, journey as jr, risk as rk, scenario as scn
from ..services.frame import InsufficientData, active_sets, cash, years_of
from . import guide
from .facts import _m, _share

PAGE = {"retain_first_time": "journey", "call_list": "risk", "recurring": "strategy", "upgrade_mid": "matching", "broaden_base": "concentration",
        "calendar": "seasonality", "clean_data": "data_review", "reactivate": "journey"}


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (InsufficientData, ValueError, KeyError, IndexError):
        return None


def candidates(df: pd.DataFrame, year: int, exceptional: float, large: float, *, pending_review: int = 0) -> list[dict]:
    out: list[dict] = []
    ys = years_of(df)

    def add(id_, evidence, impact=None, score=0.0):
        out.append({"id": id_, "page": PAGE[id_], "evidence": evidence, "estimated_effect": impact, "_score": float(score)})

    # keep first-time donors
    j = _safe(jr.journey, df)
    if j and j["funnel"]:
        f = j["funnel"][-1]
        s = _safe(scn.scenario, df, exceptional, 5.0, 0.0, 1.0, 0.0, 0.0)
        n, k = f["first_time"]["n"], f["first_time"]["returned"]
        d = s["scenario"]["delta_vs_baseline"] if s else None
        add("retain_first_time", {"year": f["cohort_year"], "first_time_donors": n, "gave_again": k, "share_gave_again": _share(f["first_time"]["rate"]),
                                  "repeat_donors_share_gave_again": _share(f["repeat"]["rate"]), "extra_donors_if_5_points_more_give_again": round(n * 0.05)},
            {"adds": _m(d), "assumption": t("act.assume.first5")} if d else None, d or 0)
    # call the donors most likely to stop
    r = _safe(rk.risk_report, df, top_n=20)
    if r and r["donors"]:
        var = sum(x["value_at_risk"] for x in r["donors"])
        m = r["metrics"]
        ev = {"donors": len(r["donors"]), "value_at_stake": _m(var)}
        if m:
            ev["share_of_the_top_20_flagged_in_the_test_that_really_stopped"] = _share(m["precision_at_k"][0]["precision"])
        add("call_list", ev, {"adds": _m(var * 0.25), "assumption": t("act.assume.keep_quarter")}, var * 0.25)
    # recurring giving
    s = _safe(scn.scenario, df, exceptional, 0.0, 0.0, 1.0, 10.0, 0.0)
    if s:
        d = s["scenario"]["delta_vs_baseline"]
        rec = len(set(df[(df["year"] == ys[-1]) & (df["mode"] == "recurring")]["donor_code"].dropna()))
        add("recurring", {"recurring_donors": rec}, {"adds": _m(d), "assumption": t("act.assume.rec10")} if d > 0 else None, d)
    # step up the mid-size donors
    cy = cash(df[df["year"] == year])
    per = cy[cy["amount_ntd"] < exceptional].dropna(subset=["donor_code"]).groupby("donor_code")["amount_ntd"].sum()
    low, high = per[(per >= 10_000) & (per < 100_000)], per[(per >= 100_000) & (per < 1_000_000)]
    if len(low) >= 10 and len(high) >= 5:
        gain = len(low) * 0.10 * (float(high.median()) - float(low.median()))
        add("upgrade_mid", {"donors_giving_10k_to_100k": len(low), "their_median_total": _m(float(low.median())), "donors_giving_100k_to_1m": len(high),
                            "their_median_total_next_level": _m(float(high.median()))},
            {"adds": _m(gain), "assumption": t("act.assume.mid10")} if gain > 0 else None, max(gain, 0))
    # concentration
    c = _safe(ins.concentration, df, year, exceptional)
    if c:
        small = per[per < 10_000]
        add("broaden_base", {"top_1_percent_share_of_all_money": _share(c["all"]["top1pct_share"]), "top_1_percent_share_of_ordinary_money": _share(c["ordinary"]["top1pct_share"]),
                             "top_10_percent_share_of_all_money": _share(c["all"]["top10pct_share"]),
                             "donors_giving_under_10k": len(small), "their_share_of_ordinary_money": _share(float(small.sum() / per.sum())) if per.sum() else None},
            None, c["all"]["top1pct_share"] * 1e6)
    # calendar
    cells = pd.DataFrame(ins.seasonality(df, exceptional)["cells"])
    cur = cells[cells["year"] == year] if len(cells) else cells
    if len(cur) and cur["value"].sum() > 0:
        tot = float(cur["value"].sum())
        top, bottom = cur.sort_values("value").iloc[-1], cur[cur["value"] > 0].sort_values("value").iloc[0]
        add("calendar", {"busiest_month": i18n.month_label(int(top["month"])), "busiest_month_share": _share(top["value"] / tot),
                         "quietest_month": i18n.month_label(int(bottom["month"])), "quietest_month_share": _share(bottom["value"] / tot)}, None, top["value"] / tot * 1e5)
    # data
    if pending_review > 0:
        unk = df[df["purpose_group"].isna() & df["amount_ntd"].notna()]["amount_ntd"].sum()
        tot_all = df[df["amount_ntd"].notna()]["amount_ntd"].sum()
        add("clean_data", {"project_names_waiting": pending_review, "share_of_money_without_a_confirmed_purpose": _share(float(unk / tot_all)) if tot_all else None}, None, pending_review * 1e3)
    # win back
    if len(ys) >= 2:
        A = active_sets(df)
        lapsed = A.get(ys[-2], set()) - A.get(ys[-1], set())
        prev = cash(df[df["year"] == ys[-2]])
        gave = float(prev[(prev["donor_code"].isin(lapsed)) & (prev["amount_ntd"] < exceptional)]["amount_ntd"].sum())
        if lapsed and gave > 0:
            add("reactivate", {"donors_who_stopped": len(lapsed), "what_they_gave_the_year_before": _m(gave)},
                {"adds": _m(gave * 0.10), "assumption": t("act.assume.back10")}, gave * 0.10)
    return out


def public(cands: list[dict]) -> list[dict]:
    """What the model is shown: no internal score."""
    return [{k: v for k, v in c.items() if k != "_score"} for c in cands]


def _flat(d: dict | None, prefix: str = "") -> dict:
    out = {}
    for k, v in (d or {}).items():
        out[prefix + k] = v["text"] if isinstance(v, dict) and "text" in v else ("–" if v is None else v)
    return out


def _say(key: str, ns: dict) -> str:
    """t() that tolerates a figure the data did not have (shown as a dash rather than failing)."""
    ns = dict(ns)
    for _ in range(12):
        try:
            return t(key, **ns)
        except KeyError as e:
            ns[e.args[0]] = "–"
    return t(key, **ns)


def playbook(c: dict) -> dict:
    """Deterministic text for one candidate, from the catalogue."""
    ns = {**_flat(c["evidence"]), **_flat(c.get("estimated_effect"))}
    i = c["id"]
    effect = _say(f"act.{i}.effect", ns) if c.get("estimated_effect") else t("act.noimpact")
    why_key = f"act.{i}.why_basic" if i == "call_list" and "share_of_the_top_20_flagged_in_the_test_that_really_stopped" not in c["evidence"] else f"act.{i}.why"
    return {"candidate_id": i, "title": t(f"act.{i}.title"), "why": _say(why_key, ns),
            "steps": [_say(f"act.{i}.s{n}", ns) for n in (1, 2, 3)], "now": "", "expected_effect": effect, "measure": t(f"act.{i}.measure"), "page": c["page"], "link": guide.link(c["page"])}


def top(cands: list[dict], n: int = 4) -> list[dict]:
    return sorted(cands, key=lambda c: -c["_score"])[:n]
