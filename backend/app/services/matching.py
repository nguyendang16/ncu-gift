"""WP5: opportunity identification and donor matching ("CauseMatch").

Direction used by the dashboard: given a target (purpose category, department or
project) rank donors by affinity, with an evidence card per donor. Scores are
bounded, additive and fully inspectable; weights are constants below.

Evaluation (design from the plan): temporal holdout at purpose-category and
department level. History up to year T-1, ask who gives to each target in year T,
compare with baselines. New-project matching is shown as a qualitative case study.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import i18n, org
from ..i18n import t
from .frame import InsufficientData, cash, years_of

WEIGHTS = {"direct": 3.0, "unit": 2.0, "college": 1.0, "sub": 1.5, "active": 0.8, "capacity": 0.4}
MAX_SCORE = sum(WEIGHTS.values())


def _mask(df: pd.DataFrame, kind: str, name: str) -> pd.Series:
    col = {"sub": "purpose_sub", "unit": "unit", "project": "project_name"}[kind]
    return df[col] == name


def parse_target(target: str) -> tuple[str, str]:
    kind, _, name = target.partition(":")
    if kind not in ("sub", "unit", "project") or not name:
        raise ValueError(t("match.err_target"))
    return kind, name


def target_info(df: pd.DataFrame, kind: str, name: str) -> dict:
    rows = df[_mask(df, kind, name)]
    if rows.empty:
        raise InsufficientData(t("match.no_records", name=i18n.target_label(kind, name)))
    pick = lambda c: rows[c].dropna().mode().iloc[0] if rows[c].notna().any() else None
    info = {"kind": kind, "name": name, "sub": pick("purpose_sub"), "unit": pick("unit"), "college": pick("college")}
    if kind == "sub":
        info["sub"], info["unit"], info["college"] = name, None, None
    if kind == "unit":
        info["unit"] = name
        info["college"] = org.DEPT_TO_COLLEGE.get(name, info["college"])
    return info


def score_frame(df: pd.DataFrame, kind: str, name: str, as_of: int, info: dict | None = None) -> pd.DataFrame:
    """Score every donor with history up to `as_of`."""
    info = info or target_info(df, kind, name)
    h = df[(df["year"] <= as_of) & df["donor_code"].notna()].copy()
    w = 0.5 ** (as_of - h["year"])
    key = h["donor_code"]
    sat = lambda s: 1 - np.exp(-s)
    tm = _mask(h, kind, name)
    direct = sat((w * tm).groupby(key).sum())
    unit = pd.Series(0.0, index=direct.index)
    if info["unit"]:
        unit = sat((w * (h["unit"] == info["unit"])).groupby(key).sum())
        dept = h.groupby("donor_code")["dept"].first()
        unit = np.maximum(unit, (dept == info["unit"]).reindex(unit.index).fillna(False).astype(float))
    college = sat((w * (h["college"] == info["college"])).groupby(key).sum()) if info["college"] else pd.Series(0.0, index=direct.index)
    sub = sat((w * (h["purpose_sub"] == info["sub"])).groupby(key).sum()) if info["sub"] else pd.Series(0.0, index=direct.index)
    n_years = max(1, len([y for y in years_of(h)]))
    active = h.groupby("donor_code")["year"].nunique() / n_years
    tot = cash(h).groupby("donor_code")["amount_ntd"].sum().reindex(direct.index).fillna(0.0)
    capacity = np.log1p(tot) / max(np.log1p(tot).max(), 1)
    S = pd.DataFrame({"direct": direct, "unit": unit, "college": college, "sub": sub, "active": active, "capacity": capacity})
    S["score"] = sum(S[k] * WEIGHTS[k] for k in WEIGHTS) / MAX_SCORE * 100
    return S


def _evidence(df, donor, kind, name, info, as_of, S_row) -> list[str]:
    h = df[(df["donor_code"] == donor) & (df["year"] <= as_of)]
    ev: list[tuple[float, str]] = []
    th = h[_mask(h, kind, name)]
    if len(th):
        last = th.sort_values("year").iloc[-1]
        has_amt = pd.notna(last["amount_ntd"])
        what = i18n.target_label(kind, name)
        key = "match.gave_to_project" if kind == "project" else "match.gave_to_target"
        ev.append((S_row["direct"] * WEIGHTS["direct"],
                   t(key + ("_amt" if has_amt else ""), name=what, year=int(last["year"]), amount=last["amount_ntd"] if has_amt else 0)))
    dept = h["dept"].dropna()
    unit_txt = i18n.dept_label(info["unit"])
    if info["unit"] and len(dept) and dept.iloc[0] == info["unit"]:
        gy = h["grad_year"].dropna()
        ev.append((WEIGHTS["unit"], t("match.alumnus_cohort", unit=unit_txt, year=int(gy.iloc[0])) if len(gy)
                   else t("match.alumnus", unit=unit_txt)))
    elif info["unit"] and S_row["unit"] > 0 and not (kind == "unit" and len(th)):
        ev.append((S_row["unit"] * WEIGHTS["unit"], t("match.gave_to_unit_before", unit=unit_txt)))
    if info["college"] and S_row["college"] > 0:
        n = int((h["college"] == info["college"]).sum())
        ev.append((S_row["college"] * WEIGHTS["college"], t("match.college_gifts", n=n, college=i18n.college_label(info["college"]))))
    total_years = len(years_of(df[df["year"] <= as_of]))
    if info["sub"] and S_row["sub"] > 0 and kind != "sub":
        yrs = h[h["purpose_sub"] == info["sub"]]["year"].nunique()
        ev.append((S_row["sub"] * WEIGHTS["sub"], t("match.gave_to_sub_years", name=i18n.purpose_label(info["sub"]), k=yrs, n=total_years)))
    elif kind == "sub" and len(th):
        ev.append((S_row["sub"] * WEIGHTS["sub"], t("match.gave_to_sub_years", name=i18n.purpose_label(name), k=th["year"].nunique(), n=total_years)))
    ev.append((S_row["active"] * WEIGHTS["active"], t("match.active_years", k=h["year"].nunique(), n=total_years)))
    c = cash(h)
    if len(c):
        ev.append((S_row["capacity"] * WEIGHTS["capacity"], t("match.typical_gift", amount=c["amount_ntd"].median())))
    ev.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, text in ev:
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:4]


def list_targets(df: pd.DataFrame) -> list[dict]:
    out = []
    for s in org.PURPOSE_SUBS:
        n = df[df["purpose_sub"] == s]["donor_code"].nunique()
        if n:
            out.append({"id": f"sub:{s}", "kind": "purpose", "label": i18n.purpose_label(s), "donors": int(n)})
    for d, _, _ in org.DEPARTMENTS:
        n = df[df["unit"] == d]["donor_code"].nunique()
        if n:
            out.append({"id": f"unit:{d}", "kind": "department", "label": i18n.dept_label(d), "donors": int(n)})
    projects = df.dropna(subset=["project_name"]).groupby("project_name").agg(
        donors=("donor_code", "nunique"), first=("year", "min"), rows=("year", "size"))
    for name, r in projects.sort_values("donors", ascending=False).iterrows():
        if r["rows"] >= 3:
            out.append({"id": f"project:{name}", "kind": "project", "label": i18n.project_label(name), "donors": int(r["donors"]),
                        "first_year": int(r["first"])})
    return out


def rank(df: pd.DataFrame, target: str, top_n: int = 25, as_of: int | None = None) -> dict:
    kind, name = parse_target(target)
    ys = years_of(df)
    as_of = as_of or ys[-1]
    info = target_info(df, kind, name)
    S = score_frame(df, kind, name, as_of, info)
    S = S.sort_values("score", ascending=False)
    first = df.groupby("donor_code").agg(cls=("donor_class", "first"), anon=("anonymous", "max"))
    total = cash(df[df["year"] <= as_of]).groupby("donor_code")["amount_ntd"].sum()
    last_year = df[df["year"] <= as_of].groupby("donor_code")["year"].max()
    out = []
    for donor, r in S.head(top_n).iterrows():
        out.append({"donor_id": donor, "donor_class": first.loc[donor, "cls"],
                    "donor_class_label": i18n.class_label(first.loc[donor, "cls"]), "score": float(r["score"]),
                    "evidence": _evidence(df, donor, kind, name, info, as_of, r), "last_gift_year": int(last_year[donor]),
                    "total_given": float(total.get(donor, 0.0)), "anonymous": bool(first.loc[donor, "anon"]),
                    "components": {k: float(r[k] * WEIGHTS[k] / MAX_SCORE * 100) for k in WEIGHTS}})
    return {"target": target, "label": i18n.target_label(kind, name), "as_of_year": as_of, "n_candidates": int(len(S)), "candidates": out,
            "weights": WEIGHTS}


def evaluate(df: pd.DataFrame, ks=(20, 50), min_pos: int = 5, seed: int = 0) -> dict:
    ys = years_of(df)
    if len(ys) < 3:
        raise InsufficientData(t("match.eval_three_years"))
    last, hist = ys[-1], ys[-2]
    h = df[(df["year"] <= hist) & df["donor_code"].notna()]
    cands = sorted(h["donor_code"].unique())
    N = len(cands)
    rng = np.random.default_rng(seed)
    tie = pd.Series(rng.random(N), index=cands)
    activity = h.groupby("donor_code").size().reindex(cands).fillna(0)
    targets = [("sub", s) for s in org.PURPOSE_SUBS] + [("unit", d) for d, _, _ in org.DEPARTMENTS]
    rows = []
    for kind, name in targets:
        lastmask = (df["year"] == last) & _mask(df, kind, name)
        pos = set(df[lastmask]["donor_code"].dropna()) & set(cands)
        if len(pos) < min_pos:
            continue
        S = score_frame(df, kind, name, hist)
        S = S.reindex(cands).fillna(0.0)
        y = pd.Series([c in pos for c in cands], index=cands)
        prev = set(df[(df["year"] == hist) & _mask(df, kind, name)]["donor_code"].dropna()) & set(cands)
        row = {"target": i18n.target_label(kind, name), "positives": len(pos), "base_rate": len(pos) / N}
        order_model = S["score"].add(tie * 1e-6).sort_values(ascending=False).index
        order_pop = (activity + tie * 1e-6).sort_values(ascending=False).index
        s_prev, pos_in_prev = len(prev), len(prev & pos)
        for k in ks:
            row[f"model_p{k}"] = float(y[order_model[:k]].mean())
            row[f"popularity_p{k}"] = float(y[order_pop[:k]].mean())
            if s_prev >= k:
                row[f"lastyear_p{k}"] = pos_in_prev / s_prev
            else:
                rest = (len(pos) - pos_in_prev) / max(N - s_prev, 1)
                row[f"lastyear_p{k}"] = (pos_in_prev + (k - s_prev) * rest) / k
            row[f"random_p{k}"] = row["base_rate"]
        rows.append(row)
    if not rows:
        raise InsufficientData(t("match.eval_no_targets"))
    res = {"history_through": hist, "holdout_year": last, "n_candidates": N, "n_targets": len(rows), "by_k": []}
    boot_rng = np.random.default_rng(seed + 1)
    for k in ks:
        entry = {"k": k}
        for m in ("model", "lastyear", "popularity", "random"):
            vals = np.array([r[f"{m}_p{k}"] for r in rows])
            b = [vals[boot_rng.integers(0, len(vals), len(vals))].mean() for _ in range(500)]
            entry[m] = float(vals.mean())
            entry[f"{m}_ci_low"], entry[f"{m}_ci_high"] = float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))
        res["by_k"].append(entry)
    res["targets"] = [{"target": r["target"], "positives": r["positives"], "model_p20": r.get("model_p20"),
                       "lastyear_p20": r.get("lastyear_p20"), "random_p20": r["random_p20"]} for r in rows]
    res["notes"] = [t("match.note_cands"), t("match.note_new_projects")]
    return res
