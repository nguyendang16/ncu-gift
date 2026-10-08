"""Extra analyses behind the richer charts. All deterministic: no model, no LLM.

  concentration  how much of the money a few donors carry (Lorenz curve)
  bridge         why the total changed between two years (waterfall that adds up exactly)
  seasonality    ordinary giving by year x month (heatmap)
  purpose_tree   where the money is directed, group -> category -> project (treemap)
  highlights     plain-language "what to look at next" cards, each linking to the page that answers it
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .. import i18n, org
from ..i18n import t
from . import journey as jr, risk as rk, stats
from .frame import InsufficientData, active_sets, cash, years_of

GRID = [0, 1, 2, 3, 5, 7.5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def _totals(df: pd.DataFrame, year: int, exceptional: float | None = None) -> pd.Series:
    c = cash(df[df["year"] == year]).dropna(subset=["donor_code"])
    if exceptional is not None:
        c = c[c["amount_ntd"] < exceptional]
    return c.groupby("donor_code")["amount_ntd"].sum().sort_values(ascending=False)


def _gini(s: pd.Series) -> float:
    x = np.sort(s.to_numpy(dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


def _share_at(s: pd.Series, pct: float) -> float:
    if s.empty or s.sum() == 0:
        return 0.0
    k = max(1, math.ceil(pct / 100 * len(s))) if pct > 0 else 0
    return float(s.iloc[:k].sum() / s.sum())


def concentration(df: pd.DataFrame, year: int, exceptional: float) -> dict:
    ys = years_of(df)
    if year not in ys:
        raise InsufficientData(t("stats.no_year", year=year))
    allg, ordg = _totals(df, year), _totals(df, year, exceptional)
    if allg.empty:
        raise InsufficientData(t("stats.no_year", year=year))

    def summary(s: pd.Series) -> dict:
        return {"n_donors": int(len(s)), "top1_donor_share": float(s.iloc[0] / s.sum()) if len(s) and s.sum() else 0.0,
                "top1pct_share": _share_at(s, 1), "top10pct_share": _share_at(s, 10), "gini": _gini(s)}

    return {"year": year, "all": summary(allg), "ordinary": summary(ordg),
            "curve": [{"pct": p, "all": _share_at(allg, p), "ordinary": _share_at(ordg, p)} for p in GRID]}


def bridge(df: pd.DataFrame, year: int, exceptional: float) -> dict:
    """Waterfall from last year's total to this year's. Ordinary giving is split by what each donor did; exceptional gifts
    are one separate step. The steps add up exactly (asserted in tests)."""
    ys = years_of(df)
    prevs = [y for y in ys if y < year]
    if year not in ys or not prevs:
        raise InsufficientData(t("bridge.no_prev"))
    prev = max(prevs)
    A = active_sets(df)
    before_year = set().union(*[A[y] for y in A if y < year])
    cur_o, prev_o = _totals(df, year, exceptional), _totals(df, prev, exceptional)
    cur_all = cash(df[df["year"] == year])["amount_ntd"]
    prev_all = cash(df[df["year"] == prev])["amount_ntd"]
    cur_exc = float(cur_all[cur_all >= exceptional].sum())
    prev_exc = float(prev_all[prev_all >= exceptional].sum())
    start = float(prev_o.sum() + prev_exc)

    both = cur_o.index.intersection(prev_o.index)
    lapsed = prev_o.index.difference(cur_o.index)
    fresh = cur_o.index.difference(prev_o.index)
    new = [d for d in fresh if d not in before_year]
    returning = [d for d in fresh if d in before_year]
    steps = [
        ("lapsed", -float(prev_o.loc[lapsed].sum())),
        ("retained", float((cur_o.loc[both] - prev_o.loc[both]).sum())),
        ("new", float(cur_o.loc[new].sum())),
        ("returning", float(cur_o.loc[returning].sum())),
        ("exceptional", cur_exc - prev_exc),
    ]
    end = float(cur_o.sum() + cur_exc)
    counts = {"lapsed": len(lapsed), "retained": len(both), "new": len(new), "returning": len(returning)}
    return {"year": year, "prev_year": prev, "start": start, "end": end,
            "start_ordinary": float(prev_o.sum()), "end_ordinary": float(cur_o.sum()), "exceptional_start": prev_exc, "exceptional_end": cur_exc,
            "steps": [{"key": k, "label": t(f"bridge.{k}"), "value": v, "donors": counts.get(k)} for k, v in steps]}


def seasonality(df: pd.DataFrame, exceptional: float) -> dict:
    ys = years_of(df)
    c = cash(df)
    c = c[(c["amount_ntd"] < exceptional) & c["date"].notna() & (c["date"].dt.year == c["year"])]
    cells = []
    for yi, y in enumerate(ys):
        m = c[c["year"] == y].groupby(c["date"].dt.month)["amount_ntd"].sum()
        for month in range(1, 13):
            cells.append({"year": y, "month": month, "value": float(m.get(month, 0.0))})
    return {"years": ys, "cells": cells}


def purpose_tree(df: pd.DataFrame, year: int, exceptional: float, scope: str = "regular") -> list[dict]:
    c = cash(df[df["year"] == year])
    if scope == "regular":
        c = c[c["amount_ntd"] < exceptional]
    out = []

    def leaves(frame: pd.DataFrame, limit: int = 8) -> list[dict]:
        by = frame.groupby("project_name", dropna=False)["amount_ntd"].sum().sort_values(ascending=False)
        rows = [{"name": i18n.project_label(k) if isinstance(k, str) else t("roll.unspecified"), "value": float(v)} for k, v in by.items()]
        if len(rows) > limit:
            rest = sum(r["value"] for r in rows[limit:])
            rows = rows[:limit] + [{"name": t("tree.other"), "value": rest}]
        return rows

    for group in ("designated", "university_fund", "annual_campaign"):
        g = c[c["purpose_group"] == group]
        if g.empty:
            continue
        if group == "designated":
            kids = []
            for sub in org.PURPOSE_SUBS:
                sg = g[g["purpose_sub"] == sub]
                if len(sg):
                    kids.append({"name": i18n.purpose_label(sub), "value": float(sg["amount_ntd"].sum()), "children": leaves(sg, 5)})
            node = {"name": i18n.group_label(group), "value": float(g["amount_ntd"].sum()), "children": kids}
        else:
            node = {"name": i18n.group_label(group), "value": float(g["amount_ntd"].sum()), "children": leaves(g)}
        out.append(node)
    other = c[c["purpose_group"].isna()]
    if len(other):
        out.append({"name": t("class.unknown"), "value": float(other["amount_ntd"].sum()), "children": leaves(other, 4)})
    return out


# ------------------------------------------------------------------ highlights

def _pct(x: float, d: int = 0) -> str:
    return f"{x * 100:.{d}f}%"


def _signed(x: float) -> str:
    return f"{x:+.1f}%"


def _ntd_compact(x: float) -> str:
    """Compact money text in the active language (萬/億 for Chinese, M/k for English). The sign goes before NT$: -NT$18.7M."""
    if x < 0:
        return "-" + _ntd_compact(-x)
    if i18n.current() == "zh-TW":
        if x >= 1e8:
            return f"NT${x / 1e8:.2f}".rstrip("0").rstrip(".") + "億"
        if x >= 1e4:
            return f"NT${x / 1e4:,.0f}萬"
        return f"NT${x:,.0f}"
    if x >= 1e6:
        return f"NT${x / 1e6:.1f}M"
    if x >= 1e3:
        return f"NT${x / 1e3:.0f}k"
    return f"NT${x:,.0f}"


def highlights(df: pd.DataFrame, year: int, exceptional: float) -> list[dict]:
    """Rule-based, not AI: each card states a finding computed from the data and points to the page that explains it."""
    cards: list[dict] = []
    tr = {r["year"]: r for r in stats.trend(df, exceptional)}
    cur = tr.get(year)
    if cur and cur["total_yoy_pct"] is not None and cur["regular_yoy_pct"] is not None:
        a, b = cur["total_yoy_pct"], cur["regular_yoy_pct"]
        diverge = (a < 0) != (b < 0) or abs(a - b) > 30
        cards.append({"id": "divergence", "tone": "warn" if diverge else ("good" if b >= 0 else "warn"), "icon": "trend",
                      "title": t("hl.divergence_title" if diverge else "hl.steady_title"),
                      "text": t("hl.divergence_text" if diverge else "hl.steady_text", total=_signed(a), ordinary=_signed(b), year=year),
                      "link": "/"})
    try:
        conc = concentration(df, year, exceptional)
        cards.append({"id": "concentration", "tone": "info", "icon": "pie", "title": t("hl.concentration_title"),
                      "text": t("hl.concentration_text", year=year, all=_pct(conc["all"]["top1pct_share"]),
                                ordinary=_pct(conc["ordinary"]["top1pct_share"])), "link": "/#concentration"})
    except InsufficientData:
        pass
    try:
        j = jr.journey(df)
        f = next((x for x in j["funnel"] if x["next_year"] == year), None) or (j["funnel"][-1] if j["funnel"] else None)
        if f:
            ft, rp = f["first_time"], f["repeat"]
            cards.append({"id": "first_gift", "tone": "warn" if ft["rate"] < rp["rate"] / 2 else "info", "icon": "route",
                          "title": t("hl.first_gift_title"),
                          "text": t("hl.first_gift_text", n=ft["n"], year=f["cohort_year"], k=ft["returned"],
                                    rate=_pct(ft["rate"]), repeat=_pct(rp["rate"])), "link": "/journey"})
    except InsufficientData:
        pass
    try:
        r = rk.risk_report(df, top_n=20)
        total = sum(d["value_at_risk"] for d in r["donors"])
        cards.append({"id": "outreach", "tone": "warn", "icon": "phone", "title": t("hl.outreach_title", n=len(r["donors"])),
                      "text": t("hl.outreach_text", amount=_ntd_compact(total)), "link": "/risk"})
    except InsufficientData:
        pass
    cc = cash(df[df["year"] == year]).dropna(subset=["donor_code"])
    if len(cc) and (cc["donor_class"] == "alumni").any():
        al = cc[cc["donor_class"] == "alumni"]
        cards.append({"id": "alumni", "tone": "info", "icon": "people", "title": t("hl.alumni_title"),
                      "text": t("hl.alumni_text", donors=_pct(al["donor_code"].nunique() / cc["donor_code"].nunique()),
                                money=_pct(al["amount_ntd"].sum() / cc["amount_ntd"].sum())), "link": "/"})
    s = seasonality(df, exceptional)
    ym = pd.DataFrame([c for c in s["cells"] if c["year"] == year])
    if len(ym) and ym["value"].sum() > 0:
        top = ym.sort_values("value", ascending=False).iloc[0]
        month = i18n.month_label(int(top["month"]))
        cards.append({"id": "season", "tone": "info", "icon": "calendar", "title": t("hl.season_title", month=month),
                      "text": t("hl.season_text", month=month, share=_pct(top["value"] / ym["value"].sum())), "link": "/#when"})
    return cards[:6]
