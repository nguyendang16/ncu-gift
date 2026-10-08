"""WP6 (part 1): strategy scenario explorer. SENSITIVITY ANALYSIS, NOT A FORECAST.

Total revenue is dominated by a few exceptional gifts, so no point forecast of the
total is attempted. We model only *ordinary* giving (gifts below the exceptional
threshold) with a transparent cohort model, show ranges, and keep any exceptional
gift as a separate, user-entered line that never feeds the ordinary estimate.

  ordinary(next) = first_time_last_year × r1 × avg_first
                 + not_first_last_year  × r2 × avg_notfirst
                 + new_donors           × avg_first
  r1, r2 are observed on the latest completed transition and assumed stable.
  Converting a share c of retained donors to recurring replaces r by (1-c)·r + c·r_rec.
"""
from __future__ import annotations

import pandas as pd

from ..i18n import t
from .frame import InsufficientData, active_sets, cash, wilson, years_of


def _rate(k, n):
    return (k / n) if n else 0.0


def scenario(df: pd.DataFrame, exceptional: float, r1_uplift_pp: float = 0.0, r2_uplift_pp: float = 0.0,
             new_donor_multiplier: float = 1.0, recurring_conversion_pct: float = 0.0, major_gift_ntd: float = 0.0) -> dict:
    ys = years_of(df)
    if len(ys) < 3:
        raise InsufficientData(t("scn.three_years"))
    last, prev = ys[-1], ys[-2]
    A = active_sets(df)
    before = lambda y: set().union(*[A[x] for x in ys if x < y])
    first_prev = A[prev] - before(prev)
    notfirst_prev = A[prev] - first_prev
    first_last = A[last] - before(last)
    notfirst_last = A[last] - first_last

    r1_k, r1_n = len(first_prev & A[last]), len(first_prev)
    r2_k, r2_n = len(notfirst_prev & A[last]), len(notfirst_prev)
    rec_prev = set(df[(df["year"] == prev) & (df["mode"] == "recurring")]["donor_code"].dropna())
    rr_k, rr_n = len(rec_prev & A[last]), len(rec_prev)
    r1, r2 = _rate(r1_k, r1_n), _rate(r2_k, r2_n)
    if rr_n >= 15:
        r_rec, rec_note = _rate(rr_k, rr_n), t("scn.rec_measured", n=rr_n)
        rr_lo, rr_hi = wilson(rr_k, rr_n)
    else:
        r_rec, rec_note, (rr_lo, rr_hi) = r2, t("scn.rec_assumed"), wilson(r2_k, r2_n)
    (r1_lo, r1_hi), (r2_lo, r2_hi) = wilson(r1_k, r1_n), wilson(r2_k, r2_n)

    c = cash(df[df["year"] == last])
    reg = c[c["amount_ntd"] < exceptional].groupby("donor_code")["amount_ntd"].sum()
    avg = lambda S: float(reg.reindex(list(S)).fillna(0.0).mean()) if S else 0.0
    avg_first, avg_notfirst = avg(first_last), avg(notfirst_last)
    n_first, n_notfirst = len(first_last), len(notfirst_last)

    def project(a1, a2, ar, mult, conv):
        e1 = (1 - conv) * a1 + conv * max(ar, a1)
        e2 = (1 - conv) * a2 + conv * max(ar, a2)
        parts = [n_first * e1 * avg_first, n_notfirst * e2 * avg_notfirst, n_first * mult * avg_first]
        return parts, e1, e2

    clamp = lambda x: min(max(x, 0.0), 1.0)
    conv = min(max(recurring_conversion_pct / 100.0, 0.0), 0.5)
    base_parts, b1, b2 = project(r1, r2, r_rec, 1.0, 0.0)
    scn_parts, s1, s2 = project(clamp(r1 + r1_uplift_pp / 100), clamp(r2 + r2_uplift_pp / 100), r_rec, new_donor_multiplier, conv)
    lo, _, _ = project(clamp(r1_lo + r1_uplift_pp / 100), clamp(r2_lo + r2_uplift_pp / 100), rr_lo, new_donor_multiplier, conv)
    hi, _, _ = project(clamp(r1_hi + r1_uplift_pp / 100), clamp(r2_hi + r2_uplift_pp / 100), rr_hi, new_donor_multiplier, conv)
    blo, _, _ = project(r1_lo, r2_lo, rr_lo, 1.0, 0.0)
    bhi, _, _ = project(r1_hi, r2_hi, rr_hi, 1.0, 0.0)
    base, scn = sum(base_parts), sum(scn_parts)

    hist = []
    for y in ys:
        cy = cash(df[df["year"] == y])
        e = cy[cy["amount_ntd"] >= exceptional]
        hist.append({"year": y, "ordinary": float(cy[cy["amount_ntd"] < exceptional]["amount_ntd"].sum()),
                     "n_exceptional": int(len(e)), "exceptional": float(e["amount_ntd"].sum())})
    cohorts = [
        {"cohort": t("scn.cohort_first", year=last), "donors": n_first, "retention_base": r1, "retention_scenario": s1,
         "avg_gift": avg_first, "expected_base": base_parts[0], "expected_scenario": scn_parts[0]},
        {"cohort": t("scn.cohort_repeat", year=last), "donors": n_notfirst, "retention_base": r2, "retention_scenario": s2,
         "avg_gift": avg_notfirst, "expected_base": base_parts[1], "expected_scenario": scn_parts[1]},
        {"cohort": t("scn.cohort_new", year=last + 1, mult=f"{new_donor_multiplier:g}"), "donors": int(round(n_first * new_donor_multiplier)),
         "retention_base": None, "retention_scenario": None, "avg_gift": avg_first,
         "expected_base": base_parts[2], "expected_scenario": scn_parts[2]},
    ]
    return {
        "label": t("scn.label"), "base_year": last, "projection_year": last + 1, "exceptional_threshold": exceptional,
        "ordinary_last_year": hist[-1]["ordinary"],
        "baseline": {"expected": base, "low": sum(blo), "high": sum(bhi)},
        "scenario": {"expected": scn, "low": sum(lo), "high": sum(hi), "delta_vs_baseline": scn - base},
        "exceptional_line": {"entered_gift": major_gift_ntd, "total_if_gift_arrives": scn + major_gift_ntd,
                             "note": t("scn.exc_note")},
        "observed": {"first_time_retention": {"k": r1_k, "n": r1_n, "rate": r1, "ci_low": r1_lo, "ci_high": r1_hi},
                     "repeat_retention": {"k": r2_k, "n": r2_n, "rate": r2, "ci_low": r2_lo, "ci_high": r2_hi},
                     "recurring_retention": {"k": rr_k, "n": rr_n, "rate": r_rec, "ci_low": rr_lo, "ci_high": rr_hi}},
        "cohorts": cohorts, "history": hist,
        "assumptions": [
            t("scn.assume_stable", prev=prev, last=last, nxt=last + 1),
            t("scn.assume_avg"),
            t("scn.assume_bands"),
            rec_note,
            t("scn.assume_no_forecast"),
        ],
    }
