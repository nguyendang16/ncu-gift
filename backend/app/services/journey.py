"""WP4 (part 1): donor lifecycle states and the first-to-second-gift funnel.

States for year y (needs a previous year):
  new          never gave in any earlier year of the data
  retained     gave in y-1 and y
  reactivated  gave in y, not in y-1, but did give earlier
  lapsed       gave in y-1 but not in y (reported against year y)
The first year has no history, so everyone is "active" and nothing is labelled new.
"""
from __future__ import annotations

from ..i18n import t
from .frame import InsufficientData, active_sets, wilson, years_of


def journey(df) -> dict:
    ys = years_of(df)
    if len(ys) < 2:
        raise InsufficientData(t("journey.one_year"))
    A = active_sets(df)
    rows = []
    for i, y in enumerate(ys):
        cur = A.get(y, set())
        if i == 0:
            rows.append({"year": y, "history_available": False, "active": len(cur), "new": None, "retained": None,
                         "reactivated": None, "lapsed": None})
            continue
        prev = A[ys[i - 1]]
        earlier = set().union(*[A[x] for x in ys[:i]])
        before_prev = set().union(*[A[x] for x in ys[: i - 1]]) if i > 1 else set()
        rows.append({"year": y, "history_available": True, "active": len(cur), "new": len(cur - earlier),
                     "retained": len(cur & prev), "reactivated": len((cur - prev) & before_prev),
                     "lapsed": len(prev - cur)})
    funnel = []
    for i in range(1, len(ys) - 1):
        c, nxt = ys[i], ys[i + 1]
        earlier = set().union(*[A[x] for x in ys[:i]])
        first = A[c] - earlier
        repeat = A[c] & A[ys[i - 1]]
        f_back, r_back = len(first & A[nxt]), len(repeat & A[nxt])
        fl, fh = wilson(f_back, len(first))
        rl, rh = wilson(r_back, len(repeat))
        funnel.append({
            "cohort_year": c, "next_year": nxt,
            "first_time": {"n": len(first), "returned": f_back, "rate": f_back / len(first) if first else 0.0, "ci_low": fl, "ci_high": fh},
            "repeat": {"n": len(repeat), "returned": r_back, "rate": r_back / len(repeat) if repeat else 0.0, "ci_low": rl, "ci_high": rh},
        })
    notes = [t("journey.note_rates")]
    if len(ys) < 3:
        notes.append(t("journey.note_three_years"))
    return {"years": rows, "funnel": funnel, "notes": notes}
