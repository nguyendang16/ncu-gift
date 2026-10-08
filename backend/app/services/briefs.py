"""WP6 (part 2): evidence-grounded fundraising briefs.

Rules: facts are computed here; the draft text only *wraps* those facts; and a
verifier re-reads the final text and blocks it if any number is not in the fact
table. The static template deliberately contains no digits.
TODO(LLM): `draft_text` could be produced by an LLM from `facts` (temperature 0,
structured output); the verifier below stays exactly the same.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import i18n, org
from ..i18n import t
from . import matching
from .frame import InsufficientData, cash, years_of

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def fmt_ntd(x: float) -> str:
    return f"NT${x:,.0f}"


def _nice(x: float) -> float:
    step = 100 if x < 5_000 else 500 if x < 50_000 else 5_000 if x < 500_000 else 50_000
    return float(max(step, round(x / step) * step))


def _flatten(o) -> list[float]:
    if isinstance(o, bool):
        return []
    if isinstance(o, (int, float)):
        return [float(o)]
    if isinstance(o, dict):
        return [v for x in o.values() for v in _flatten(x)]
    if isinstance(o, (list, tuple)):
        return [v for x in o for v in _flatten(x)]
    return []


def build_facts(df: pd.DataFrame, project: str, exceptional: float) -> dict:
    ys = years_of(df)
    if not ys:
        raise InsufficientData(t("brief.no_data"))
    last = ys[-1]
    rows = df[df["project_name"] == project]
    if rows.empty:
        raise InsufficientData(t("brief.no_records", name=i18n.project_label(project)))
    pick = lambda c: rows[c].dropna().mode().iloc[0] if rows[c].notna().any() else None
    sub, group, unit, college = pick("purpose_sub"), pick("purpose_group"), pick("unit"), pick("college")
    peer_label = i18n.purpose_label(sub) if sub else (i18n.group_label(group) if group else t("brief.this_category"))
    peers = df[(df["purpose_sub"] == sub) if sub else (df["purpose_group"] == group)]
    pl = peers[peers["year"] == last]
    c = cash(pl)
    c = c[c["amount_ntd"] < exceptional]
    if c.empty:
        raise InsufficientData(t("brief.no_ordinary", category=peer_label, year=last))
    q = c["amount_ntd"].quantile([0.25, 0.5, 0.75]).to_numpy()
    low, mid, high = _nice(q[0]), _nice(q[1]), _nice(q[2])
    if not low < mid < high:
        mid, high = low * 2, low * 4
    meth = c["method"].map(i18n.method_label).value_counts(normalize=True)
    cls = pl.groupby("donor_class")["donor_code"].nunique()
    cls = (cls / cls.sum()).sort_values(ascending=False)
    ranked = matching.rank(df, f"project:{project}", 100)["candidates"]
    alumni_share = np.mean([x["donor_class"] == "alumni" for x in ranked]) if ranked else 0.0
    before = set(peers[peers["year"] < last]["donor_code"].dropna())
    lapsed = len(before - set(pl["donor_code"].dropna()))
    return {
        "project": i18n.project_label(project), "category": peer_label, "unit": i18n.dept_label(unit),
        "college": i18n.college_label(college), "year": last,
        "category_last_year": {"donors": int(pl["donor_code"].nunique()), "gifts": int(len(c)),
                               "median_gift": float(q[1]), "total_ordinary": float(c["amount_ntd"].sum())},
        "options": {"low": low, "mid": mid, "high": high},
        "top_channel": {"name": str(meth.index[0]), "pct": int(round(meth.iloc[0] * 100))},
        "top_class": {"name": i18n.class_label(str(cls.index[0])), "pct": int(round(cls.iloc[0] * 100))},
        "alumni_share_top100_pct": int(round(alumni_share * 100)),
        "lapsed_supporters": int(lapsed),
    }


def draft_text(f: dict) -> str:
    c = f["category_last_year"]
    en = i18n.current() == "en"
    return t("brief.draft", project=f["project"], category=f["category"].lower() if en else f["category"],
             donors=c["donors"], median=c["median_gift"], low=f["options"]["low"], mid=f["options"]["mid"],
             high=f["options"]["high"], channel=f["top_channel"]["name"], channel_pct=f["top_channel"]["pct"],
             cls=f["top_class"]["name"].lower() if en else f["top_class"]["name"], cls_pct=f["top_class"]["pct"],
             alumni_pct=f["alumni_share_top100_pct"], lapsed=f["lapsed_supporters"])


def verify_text(text: str, facts: dict, years: list[int] | None = None) -> dict:
    allowed = _flatten(facts) + [float(y) for y in (years or [])]
    bad, n = [], 0
    for tok in NUM_RE.findall(text):
        n += 1
        v = float(tok.replace(",", "").rstrip("."))
        if not any(abs(v - a) < 1e-6 for a in allowed):
            bad.append(tok)
    return {"verified": not bad, "numbers_checked": n, "mismatches": bad}
