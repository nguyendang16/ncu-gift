"""WP3: core statistics, rule-based and parametrised. No model, no LLM; every
number on the dashboard comes from these functions."""
from __future__ import annotations

import pandas as pd

from .. import config, i18n, org
from ..i18n import t
from .frame import InsufficientData, active_sets, cash, pct_change, years_of


def _band_index(a: float) -> int:
    """The staff's labels read literally: 1萬(含)以下 | 1萬至5萬(含) | 5萬至10萬(含) | 10萬至50萬(含) | 50萬至100萬 | 100萬(含)以上.
    So a gift of exactly NT$1,000,000 belongs to the last band, not to 50萬至100萬."""
    last = len(config.BANDS) - 1
    if a >= config.BANDS[last][1]:
        return last
    for i, (_label, lo, hi) in enumerate(config.BANDS):
        if (lo is None or a > lo) and (hi is None or a <= hi):
            return i
    return len(config.BANDS) - 1


def _rows(frame: pd.DataFrame, key: str, labels=None, order: list | None = None) -> list[dict]:
    """`labels` is a callable raw-key -> display text (so the language is applied in one place)."""
    g = frame.groupby(key, dropna=False)["amount_ntd"].agg(["sum", "count"])
    tot_a, tot_n = float(g["sum"].sum()), int(g["count"].sum())
    rows = []
    for k, r in g.iterrows():
        raw = "unknown" if pd.isna(k) else k
        rows.append({"label": labels(raw) if labels else str(raw), "amount": float(r["sum"]), "count": int(r["count"]),
                     "share_amount": float(r["sum"]) / tot_a if tot_a else 0.0,
                     "share_count": int(r["count"]) / tot_n if tot_n else 0.0, "_key": raw})
    if order:
        rows.sort(key=lambda r: order.index(r["_key"]) if r["_key"] in order else 99)
    else:
        rows.sort(key=lambda r: -r["amount"])
    for r in rows:
        r.pop("_key")
    return rows


def trend(df: pd.DataFrame, exceptional: float) -> list[dict]:
    out = []
    for y in years_of(df):
        cur = df[df["year"] == y]
        c = cash(cur)
        reg = c[c["amount_ntd"] < exceptional]
        exc = c[c["amount_ntd"] >= exceptional]
        out.append({"year": y, "total": float(c["amount_ntd"].sum()), "regular": float(reg["amount_ntd"].sum()),
                    "exceptional": float(exc["amount_ntd"].sum()), "n_exceptional": int(len(exc)),
                    "donors": int(cur["donor_code"].nunique()), "records": int(len(cur))})
    for i, r in enumerate(out):
        prev = out[i - 1] if i else None
        r["total_yoy_pct"] = pct_change(r["total"], prev["total"]) if prev else None
        r["regular_yoy_pct"] = pct_change(r["regular"], prev["regular"]) if prev else None
    return out


def overview(df: pd.DataFrame, year: int, exceptional: float, large: float, scope: str = "all",
             return_definition: str = "retained") -> dict:
    ys = years_of(df)
    if year not in ys:
        raise InsufficientData(t("stats.no_year", year=year))
    cur = df[df["year"] == year]
    c = cash(cur)
    reg = c[c["amount_ntd"] < exceptional]
    exc = c[c["amount_ntd"] >= exceptional]
    scoped = c if scope == "all" else reg
    prev_year = max([y for y in ys if y < year], default=None)

    tr = {r["year"]: r for r in trend(df, exceptional)}
    A = active_sets(df)
    cur_d = A.get(year, set())
    retained = returning = None
    if prev_year is not None:
        before = set().union(*[A[y] for y in A if y < prev_year]) if any(y < prev_year for y in A) else set()
        retained = len(cur_d & A[prev_year])
        returning = len((cur_d - A[prev_year]) & before) if before else None
    sel = {"retained": retained, "returning_after_gap": returning,
           "either": None if retained is None else retained + (returning or 0)}[return_definition]

    large_rows = c[c["amount_ntd"] >= large]
    kpis = {
        "total": float(c["amount_ntd"].sum()), "regular_total": float(reg["amount_ntd"].sum()),
        "exceptional_total": float(exc["amount_ntd"].sum()), "n_exceptional": int(len(exc)),
        "share_exceptional": float(exc["amount_ntd"].sum() / c["amount_ntd"].sum()) if len(c) else 0.0,
        "records": int(len(cur)), "in_kind_records": int(cur["is_in_kind"].sum()),
        "donors": int(cur["donor_code"].nunique()),
        "large_gifts": int(len(large_rows)), "large_gifts_amount": float(large_rows["amount_ntd"].sum()),
        "total_yoy_pct": tr[year]["total_yoy_pct"], "regular_yoy_pct": tr[year]["regular_yoy_pct"],
        "retained_donors": retained, "returning_donors": returning, "repeat_selected": sel,
    }

    # monthly view: creation date is not receipt date, so rows whose date falls outside the report year are excluded
    cm = c.copy()
    valid = cm["date"].notna() & (cm["date"].dt.year == year)
    cm["month"] = cm["date"].dt.month.where(valid)
    monthly = []
    for m in range(1, 13):
        x = cm[cm["month"] == m]
        monthly.append({"month": m, "total": float(x["amount_ntd"].sum()),
                        "regular": float(x[x["amount_ntd"] < exceptional]["amount_ntd"].sum()),
                        "exceptional": float(x[x["amount_ntd"] >= exceptional]["amount_ntd"].sum()), "records": int(len(x))})
    excluded = int((~valid).sum())

    bands = scoped.assign(band=scoped["amount_ntd"].map(_band_index))
    has_method = bool(scoped["method"].notna().any())
    methods = _rows(scoped, "method", i18n.method_label) if has_method else []
    in_kind = int(cur["is_in_kind"].sum())
    if has_method and scope == "all" and in_kind:
        methods.append({"label": i18n.method_label("in_kind"), "amount": None, "count": in_kind, "share_amount": None, "share_count": None})

    sub_frame = scoped[scoped["purpose_group"] == "designated"]
    by_proj = scoped.groupby("project_name")["amount_ntd"].sum()      # canonical names, so they can be translated
    colleges = scoped[scoped["purpose_sub"].isin(org.PURPOSE_SUBS[:2]) & scoped["college"].notna()]

    notes = []
    if excluded:
        notes.append(t("stats.note_monthly_excluded", n=excluded, year=year))
    unclassified = int(scoped["purpose_group"].isna().sum())
    if unclassified:
        notes.append(t("stats.note_unclassified", n=unclassified))
    if scope == "regular":
        notes.append(t("stats.note_scope_regular", n=len(exc), threshold=exceptional))

    return {
        "year": year, "prev_year": prev_year, "years": ys, "scope": scope,
        "scope_label": t("stats.scope_all") if scope == "all" else t("stats.scope_regular", threshold=exceptional),
        "kpis": kpis, "monthly": monthly,
        "bands": _rows(bands, "band", lambda i: t(f"band.{int(i)}"), list(range(len(config.BANDS)))),
        "donor_classes": _rows(scoped, "donor_class", i18n.class_label, org.DONOR_CLASSES + ["unknown"]),
        "methods": methods,
        "purpose_groups": _rows(scoped, "purpose_group", lambda g: i18n.group_label(g) if g != "unknown" else t("class.unknown"),
                                ["annual_campaign", "university_fund", "designated", "unknown"]),
        "purpose_subs": _rows(sub_frame, "purpose_sub", i18n.purpose_label, org.PURPOSE_SUBS),
        "colleges": _rows(colleges, "college", i18n.college_label),
        "projects_over_1m": [{"project": i18n.project_label(k), "amount": float(v)} for k, v in by_proj.sort_values(ascending=False).items() if v >= 1_000_000][:12],
        "notes": notes,
    }
