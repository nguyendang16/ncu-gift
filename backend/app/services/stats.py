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


def class_compare(df: pd.DataFrame, exceptional: float, scope: str = "all",
                  amount_min: float | None = None, amount_max: float | None = None) -> dict:
    """Gift totals by donor category for every year. An amount window keeps gifts inside it, both ends included."""
    order = org.DONOR_CLASSES + ["unknown"]
    labels = [i18n.class_label(key) for key in order]
    series = []
    for year in years_of(df):
        part = cash(df[df["year"] == year])
        if scope == "regular":
            part = part[part["amount_ntd"] < exceptional]
        if amount_min is not None:
            part = part[part["amount_ntd"] >= amount_min]
        if amount_max is not None:
            part = part[part["amount_ntd"] <= amount_max]
        by_label = {row["label"]: row["amount"] for row in _rows(part, "donor_class", i18n.class_label, order)}
        series.append({"year": int(year), "amounts": [float(by_label.get(label, 0.0)) for label in labels]})
    keep = [i for i in range(len(labels)) if any(row["amounts"][i] for row in series)]
    return {
        "labels": [labels[i] for i in keep],
        "series": [{"year": row["year"], "amounts": [row["amounts"][i] for i in keep]} for row in series],
    }


def resolve_compare(years: list[int], year: int, compare_year: int | None) -> int | None:
    """The year a comparison uses. An explicit choice wins; otherwise the latest earlier year."""
    others = [y for y in years if y != year]
    if compare_year in others:
        return int(compare_year)
    earlier = [y for y in others if y < year]
    return max(earlier) if earlier else None


def trend(df: pd.DataFrame, exceptional: float, band_low: float = 500_000, band_high: float = 1_000_000) -> list[dict]:
    out = []
    for y in years_of(df):
        cur = df[df["year"] == y]
        c = cash(cur)
        reg = c[c["amount_ntd"] < exceptional]
        exc = c[c["amount_ntd"] >= exceptional]
        under = c[c["amount_ntd"] < band_low]
        mid = c[(c["amount_ntd"] >= band_low) & (c["amount_ntd"] < band_high)]
        over = c[c["amount_ntd"] >= band_high]
        out.append({"year": y, "total": float(c["amount_ntd"].sum()), "regular": float(reg["amount_ntd"].sum()),
                    "exceptional": float(exc["amount_ntd"].sum()), "n_exceptional": int(len(exc)),
                    "band_under": float(under["amount_ntd"].sum()), "band_mid": float(mid["amount_ntd"].sum()),
                    "band_over": float(over["amount_ntd"].sum()),
                    "donors": int(cur["donor_code"].nunique()), "records": int(len(cur))})
    for i, r in enumerate(out):
        prev = out[i - 1] if i else None
        r["total_yoy_pct"] = pct_change(r["total"], prev["total"]) if prev else None
        r["regular_yoy_pct"] = pct_change(r["regular"], prev["regular"]) if prev else None
    return out


def overview(df: pd.DataFrame, year: int, exceptional: float, large: float, scope: str = "all",
             return_definition: str = "retained", compare_year: int | None = None) -> dict:
    ys = years_of(df)
    if year not in ys:
        raise InsufficientData(t("stats.no_year", year=year))
    cur = df[df["year"] == year]
    c = cash(cur)
    reg = c[c["amount_ntd"] < exceptional]
    exc = c[c["amount_ntd"] >= exceptional]
    scoped = c if scope == "all" else reg
    prev_year = resolve_compare(ys, year, compare_year)

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
    prev_tr = tr.get(prev_year) if prev_year is not None else None

    def repeat_count(y: int) -> int | None:
        earlier = [yy for yy in A if yy < y]
        if not earlier or y not in A:
            return None
        prev = max(earlier)
        donors_now = A[y]
        kept = len(donors_now & A[prev])
        before_years = [yy for yy in A if yy < prev]
        came_back = len((donors_now - A[prev]) & set().union(*(A[yy] for yy in before_years))) if before_years else None
        if return_definition == "retained":
            return kept
        if return_definition == "returning_after_gap":
            return came_back
        if came_back is None:
            return None
        return kept + came_back

    prev_repeat = repeat_count(prev_year) if prev_year is not None else None
    has_method = bool(df["method"].notna().any())

    def year_cash(y: int) -> pd.DataFrame:
        part = cash(df[df["year"] == y])
        return part[part["amount_ntd"] < exceptional] if scope == "regular" else part

    def card_count(part: pd.DataFrame) -> int | None:
        if not has_method:
            return None
        return int((part["method"] == "credit_card").sum())

    def large_count(y: int) -> int:
        part = cash(df[df["year"] == y])
        return int((part["amount_ntd"] >= large).sum())

    card_gifts = card_count(scoped)
    prev_card = card_count(year_cash(prev_year)) if prev_year is not None else None
    prev_large = large_count(prev_year) if prev_year is not None else None
    earlier_years = [y for y in ys if prev_year is not None and y < prev_year]
    by_all = c.groupby("project_name")["amount_ntd"].sum()
    over_million = by_all[by_all >= 1_000_000]
    cash_total = float(c["amount_ntd"].sum())
    million_amount = float(over_million.sum()) if len(over_million) else 0.0
    kpis = {
        "total": cash_total, "regular_total": float(reg["amount_ntd"].sum()),
        "exceptional_total": float(exc["amount_ntd"].sum()), "n_exceptional": int(len(exc)),
        "share_exceptional": float(exc["amount_ntd"].sum() / cash_total) if cash_total else 0.0,
        "records": int(len(cur)), "in_kind_records": int(cur["is_in_kind"].sum()),
        "donors": int(cur["donor_code"].nunique()),
        "large_gifts": int(len(large_rows)), "large_gifts_amount": float(large_rows["amount_ntd"].sum()),
        "total_yoy_pct": pct_change(tr[year]["total"], prev_tr["total"]) if prev_tr else None,
        "regular_yoy_pct": pct_change(tr[year]["regular"], prev_tr["regular"]) if prev_tr else None,
        "retained_donors": retained, "returning_donors": returning, "repeat_selected": sel,
        "prev_total": None if prev_tr is None else prev_tr["total"],
        "prev_regular_total": None if prev_tr is None else prev_tr["regular"],
        "prev_repeat": prev_repeat,
        "repeat_delta": None if sel is None or prev_repeat is None else sel - prev_repeat,
        "repeat_ratio": None if sel is None or not prev_repeat else sel / prev_repeat,
        "card_gifts": card_gifts, "prev_card_gifts": prev_card,
        "card_delta": None if card_gifts is None or prev_card is None else card_gifts - prev_card,
        "card_yoy_pct": pct_change(card_gifts, prev_card) if card_gifts is not None and prev_card is not None else None,
        "prev_large_gifts": prev_large,
        "large_delta": None if prev_large is None else int(len(large_rows)) - prev_large,
        "large_prior_avg": (sum(large_count(y) for y in earlier_years) / len(earlier_years)) if earlier_years else None,
        "million_amount": million_amount, "million_projects": int(len(over_million)),
        "million_share": (million_amount / cash_total) if cash_total else 0.0,
        "top_project_share": float(over_million.max() / cash_total) if len(over_million) and cash_total else None,
    }

    def _snapshot(y: int) -> dict:
        raw = df[df["year"] == y]
        money = cash(raw)
        ordinary = money[money["amount_ntd"] < exceptional]
        exceptional_rows = money[money["amount_ntd"] >= exceptional]
        large_y = money[money["amount_ntd"] >= large]
        cards = money[money["method"] == "credit_card"] if has_method else None
        return {
            "year": int(y), "total": float(money["amount_ntd"].sum()),
            "regular_total": float(ordinary["amount_ntd"].sum()),
            "exceptional_total": float(exceptional_rows["amount_ntd"].sum()), "n_exceptional": int(len(exceptional_rows)),
            "donors": int(raw["donor_code"].nunique()), "records": int(len(raw)), "in_kind_records": int(raw["is_in_kind"].sum()),
            "repeat": repeat_count(y), "large_gifts": int(len(large_y)), "large_gifts_amount": float(large_y["amount_ntd"].sum()),
            "card_gifts": None if cards is None else int(len(cards)),
            "card_amount": None if cards is None else float(cards["amount_ntd"].sum()),
        }

    def _kpi_compare() -> list[dict]:
        shown = sorted({y for y in (year, prev_year) if y is not None})
        return [_snapshot(y) for y in shown]

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
        "kpis": kpis, "kpi_compare": _kpi_compare(), "monthly": monthly,
        "bands": _rows(bands, "band", lambda i: t(f"band.{int(i)}"), list(range(len(config.BANDS)))),
        "donor_classes": _rows(scoped, "donor_class", i18n.class_label, org.DONOR_CLASSES + ["unknown"]),
        "class_compare": class_compare(df, exceptional, scope),
        "methods": methods,
        "purpose_groups": _rows(scoped, "purpose_group", lambda g: i18n.group_label(g) if g != "unknown" else t("class.unknown"),
                                ["annual_campaign", "university_fund", "designated", "unknown"]),
        "purpose_subs": _rows(sub_frame, "purpose_sub", i18n.purpose_label, org.PURPOSE_SUBS),
        "colleges": _rows(colleges, "college", i18n.college_label),
        "projects_over_1m": [{"project": i18n.project_label(k), "amount": float(v)} for k, v in by_proj.sort_values(ascending=False).items() if v >= 1_000_000][:12],
        "notes": notes,
    }
