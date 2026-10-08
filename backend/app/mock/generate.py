"""Synthetic donation data for the MVP.

NOTHING HERE IS REAL. Names are "Mock ...", amounts and behaviour are drawn from
simple distributions chosen to reproduce the *shape* of the problem the staff
described (a few exceptional gifts dominating annual totals, most donors giving
once, a weak first-to-second gift transition, messy free-text fields).
Numbers produced from this data illustrate the pipeline; they are not findings.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .. import org

YEARS = (2023, 2024, 2025)
SEASON = np.array([1, 1, 1.6, 1, 1.5, 1.2, 1, 0.9, 1.1, 1.1, 1.5, 1.8])
SEASON = SEASON / SEASON.sum()
CLASS_PROBS = {"alumni": 0.62, "friends": 0.12, "company": 0.09, "organisation": 0.07, "staff_student": 0.10}
MEDIAN = {"alumni": 8000, "friends": 10000, "company": 50000, "organisation": 40000, "staff_student": 3000}
SIGMA = {"alumni": 1.0, "friends": 1.1, "company": 1.2, "organisation": 1.2, "staff_student": 0.9}
ANON_PROB = {"alumni": 0.12, "friends": 0.40, "company": 0.05, "organisation": 0.05, "staff_student": 0.10}
RETAIN_ADJ = {"alumni": 0.03, "friends": 0.0, "company": -0.02, "organisation": 0.02, "staff_student": 0.0}

# Exceptional gifts, explicit so the "one month dwarfs the rest" skew is guaranteed.
MEGA = {
    2023: [("company", 1_500_000, "Computer Science: Teaching & Research Fund", False),
           ("organisation", 2_000_000, "Excellence Scholarship Fund", False)],
    2024: [("friends", 260_000_000, "Campus: New Teaching & Research Building", True),
           ("company", 12_000_000, "Electrical Engineering: Teaching & Research Fund", False),
           ("organisation", 3_000_000, "Need-based Scholarship Program", False)],
    2025: [("friends", 55_000_000, "University Fund: General", True),
           ("organisation", 12_000_000, "Campaign: Food Safety Initiative", False),
           ("company", 3_000_000, "Physics: Teaching & Research Fund", False)],
}
MEGA_MONTH = {2023: 6, 2024: 12, 2025: 1}
UNCLASSIFIABLE = ["Gift for students", "General support", "Misc. donation", "Supporting NCU"]
IN_KIND_ITEMS = ["Laboratory equipment (lot)", "Teaching software licences", "Desktop computers", "Library books (lot)",
                 "Sports equipment", "Renewable electricity credits"]


@dataclass
class Donor:
    code: str
    cls: str
    name: str
    dept: str | None
    grad_year: int | None
    raw_category: str
    anonymous: bool
    recurring: bool
    monthly: int
    pledge_date: pd.Timestamp | None
    kind: str = "regular"            # regular | major | mega
    hidden_prior: int = 0            # years given before the data starts
    active_years: list = field(default_factory=list)
    total: float = 0.0
    fav: int | None = None


def _round_amount(x: float) -> int:
    if x < 10_000:
        return int(max(200, round(x / 100) * 100))
    if x < 100_000:
        return int(round(x / 500) * 500)
    if x < 1_000_000:
        return int(round(x / 10_000) * 10_000)
    return int(round(x / 100_000) * 100_000)


def generate_sheets(seed: int = 21) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    cat = org.CATALOGUE
    depts = [d for d, _, _ in org.DEPARTMENTS]
    seq = {"n": 0, "rid": 30000}
    donors: list[Donor] = []

    def raw_category(cls, dept, grad):
        r = rng.random()
        if r < 0.01:
            return "Supporter"                       # unrecognisable on purpose -> review queue
        if r < 0.07:
            return ""                                # blank
        if cls == "alumni":
            short = dept.split()[0] if dept else "NCU"
            return rng.choice([f"Alumni - {dept} (class of {grad})", f"Alumni-{short}", f"alumnus / {dept}",
                               f"Alumni - {dept} {grad}"])
        return {"friends": "Friends of NCU", "company": rng.choice(["Company", "Corporation"]),
                "organisation": rng.choice(["Foundation", "Association"]),
                "staff_student": "Faculty & staff"}[cls]

    def new_donor(cls=None, kind="regular", anonymous=None) -> Donor:
        seq["n"] += 1
        if cls is None:
            cls = rng.choice(list(CLASS_PROBS), p=list(CLASS_PROBS.values()))
        dept = str(rng.choice(depts)) if cls == "alumni" else None
        grad = int(rng.integers(1975, 2024)) if cls == "alumni" else None
        anon = bool(rng.random() < ANON_PROB[cls]) if anonymous is None else anonymous
        recurring = kind == "regular" and rng.random() < 0.05
        name = {"company": f"Mock Corp. {seq['n']:04d}", "organisation": f"Mock Foundation {seq['n']:04d}"}.get(
            cls, f"Mock Donor {seq['n']:04d}")
        return Donor(code=f"D{seq['n']:04d}", cls=cls, name=name, dept=dept, grad_year=grad,
                     raw_category=str(raw_category(cls, dept, grad)), anonymous=anon, recurring=recurring,
                     monthly=int(rng.choice([500, 1000, 1500, 3000])),
                     pledge_date=pd.Timestamp(year=int(rng.integers(2019, 2026)), month=int(rng.integers(1, 13)),
                                              day=int(rng.integers(1, 28))) if recurring else None,
                     kind=kind)

    def p_retain(d: Donor) -> float:
        if d.kind == "mega":
            return 0.03
        tenure = d.hidden_prior + len(d.active_years)
        lt = np.log(max(d.total, 1000) / 3000)
        adj = RETAIN_ADJ[d.cls]
        if tenure <= 1:
            p = 0.11 + 0.02 * lt + adj + (0.30 if d.recurring else 0) - (0.04 if d.anonymous else 0)
            p -= 0.07 if d.kind == "major" else 0
            return float(np.clip(p, 0.03, 0.6))
        p = 0.58 + 0.04 * lt + adj + (0.20 if d.recurring else 0) - (0.06 if d.anonymous else 0)
        return float(np.clip(p, 0.35, 0.97))

    def pick_project(d: Donor, year: int):
        avail = [i for i, p in enumerate(cat) if p["first_year"] <= year]
        if d.fav is not None and cat[d.fav]["first_year"] <= year and rng.random() < 0.5:
            return d.fav
        w = np.array([cat[i]["weight"] for i in avail], dtype=float)
        for k, i in enumerate(avail):
            p = cat[i]
            if d.cls == "alumni" and d.dept and p["unit"] == d.dept:
                w[k] *= 8
            elif d.cls == "company" and p["purpose_sub"] in (org.PURPOSE_SUBS[0], org.PURPOSE_SUBS[6], org.PURPOSE_SUBS[4]):
                w[k] *= 3
            elif d.cls == "staff_student" and (p["purpose_group"] == "annual_campaign" or p["purpose_sub"] == org.PURPOSE_SUBS[5]):
                w[k] *= 3
            elif d.cls == "friends" and p["purpose_group"] == "annual_campaign":
                w[k] *= 2
            elif d.cls == "organisation" and p["purpose_sub"] in (org.PURPOSE_SUBS[1], org.PURPOSE_SUBS[2]):
                w[k] *= 2.5
        return avail[int(rng.choice(len(avail), p=w / w.sum()))]

    def pick_method(amount: float, recurring=False) -> str:
        if recurring:
            return str(rng.choice(["Credit card", "Postal giro"], p=[0.85, 0.15]))
        if amount >= 100_000:
            return str(rng.choice(["Bank transfer", "Check", "Cash", "Credit card"], p=[0.8, 0.1, 0.05, 0.05]))
        return str(rng.choice(["Credit card", "Bank transfer", "Cash", "Taiwan Pay", "Postal giro", "Convenience store", "Check"],
                              p=[0.50, 0.22, 0.14, 0.06, 0.04, 0.02, 0.02]))

    def solicited(amount: float) -> str:
        p = 0.75 if amount >= 500_000 else 0.40 if amount >= 100_000 else 0.08
        return "Yes" if rng.random() < p else "No"

    rows: dict[int, list[dict]] = {y: [] for y in YEARS}

    def add_row(year, d, project_idx, amount, mode="One-time", month=None, creation=None, method=None,
                in_kind=None, project_name=None, currency="TWD"):
        seq["rid"] += int(rng.integers(1, 4))
        m = int(month) if month else int(rng.choice(12, p=SEASON)) + 1
        created = creation if creation is not None else pd.Timestamp(year=year, month=m, day=int(rng.integers(1, 28)))
        name = project_name if project_name is not None else cat[project_idx]["name"]
        rows[year].append({
            "Record ID": seq["rid"], "Donation Mode": mode, "Creation Date": created.date(), "Donor Code": d.code,
            "Currency": currency, "Donation Details": (in_kind if in_kind else amount),
            "Actual Amount": (np.nan if in_kind else amount), "Donation Project": name,
            "Donor Category": d.raw_category, "Anonymous": "Yes" if d.anonymous else "No",
            "Donation Method": "In-kind" if in_kind else (method or pick_method(amount)),
            "Donor Name": d.name, "Solicited": ("" if in_kind else solicited(amount)),
            "In-kind Item": in_kind or "",
        })

    for yi, year in enumerate(YEARS):
        active: list[Donor] = []
        if yi == 0:
            for _ in range(520):
                d = new_donor(kind="major" if rng.random() < 0.035 else "regular")
                d.hidden_prior = int(rng.choice([0, 1, 2], p=[0.55, 0.20, 0.25]))
                active.append(d)
        else:
            for d in donors:
                gave_last = bool(d.active_years) and d.active_years[-1] == year - 1
                if gave_last:
                    if rng.random() < p_retain(d):
                        active.append(d)
                elif d.kind != "mega" and rng.random() < 0.04:
                    active.append(d)                                   # reactivation after a gap
            for _ in range({1: 400, 2: 410}[yi]):
                active.append(new_donor(kind="major" if rng.random() < 0.035 else "regular"))
            donors.extend(a for a in active if a not in donors)

        if yi == 0:
            donors.extend(active)

        # regular and major donors
        for d in active:
            d.active_years.append(year)
            if d.recurring:
                months = int(rng.integers(6, 13))
                amount = d.monthly * months
                d.total += amount
                add_row(year, d, None, amount, mode="Recurring", creation=d.pledge_date,
                        method=pick_method(amount, True), project_name=cat[pick_project(d, year)]["name"])
                if rng.random() > 0.15:
                    continue
            k = 1 if d.kind == "major" else int(rng.choice([1, 2, 3, 4], p=[0.86, 0.09, 0.03, 0.02]))
            for _ in range(k):
                pi = pick_project(d, year)
                if d.fav is None:
                    d.fav = pi
                if d.kind == "major":
                    raw = float(np.clip(rng.lognormal(np.log(400_000), 0.9), 100_000, 4_000_000))
                else:
                    raw = MEDIAN[d.cls] * float(np.exp(SIGMA[d.cls] * rng.standard_normal()))
                amount = _round_amount(raw)
                d.total += amount
                add_row(year, d, pi, amount)

        # exceptional gifts (explicit)
        for cls, amount, pname, anon in MEGA[year]:
            d = new_donor(cls=cls, kind="mega", anonymous=anon)
            d.active_years.append(year)
            donors.append(d)
            idx = next(i for i, p in enumerate(cat) if p["name"] == pname)
            add_row(year, d, idx, amount, month=MEGA_MONTH[year], method="Bank transfer")

        # in-kind gifts
        for _ in range(12):
            d = new_donor(cls=str(rng.choice(["company", "organisation"])))
            d.active_years.append(year)
            donors.append(d)
            pi = pick_project(d, year)
            add_row(year, d, pi, None, in_kind=str(rng.choice(IN_KIND_ITEMS)))

    sheets: dict[str, pd.DataFrame] = {}
    for year in YEARS:
        df = pd.DataFrame(rows[year])
        # messy free text: whitespace/case variants, and a few unclassifiable strings
        r = rng.random(len(df))
        df.loc[r < 0.012, "Donation Project"] = [str(rng.choice(UNCLASSIFIABLE)) for _ in range(int((r < 0.012).sum()))]
        df.loc[(r >= 0.012) & (r < 0.03), "Donation Project"] = df.loc[(r >= 0.012) & (r < 0.03), "Donation Project"].str.lower()
        df.loc[(r >= 0.03) & (r < 0.05), "Donation Project"] = df.loc[(r >= 0.03) & (r < 0.05), "Donation Project"].str.replace(": ", " - ", regex=False)
        # two foreign-currency gifts: Donation Details in USD, Actual Amount in NTD
        big = df[(df["Actual Amount"] >= 300_000) & (df["Actual Amount"] < 5_000_000)].index[:2]
        df.loc[big, "Currency"] = "USD"
        df.loc[big, "Donation Details"] = (df.loc[big, "Actual Amount"] / 31.5).round(-2)
        sheets[str(year)] = df.sort_values("Record ID").reset_index(drop=True)
    return sheets


def describe(sheets: dict[str, pd.DataFrame]) -> None:
    prev = None
    first_seen: set = set()
    for y, df in sheets.items():
        amt = pd.to_numeric(df["Actual Amount"], errors="coerce")
        donors = set(df["Donor Code"])
        print(f"{y}: rows={len(df)} donors={len(donors)} total={amt.sum():,.0f} "
              f"regular(<10M)={amt[amt < 1e7].sum():,.0f} max={amt.max():,.0f}")
        if prev is not None:
            kept = donors & prev
            new = donors - first_seen
            print(f"     retained from previous year: {len(kept)}/{len(prev)} = {len(kept)/len(prev):.1%}")
        first_seen |= donors
        prev = donors
