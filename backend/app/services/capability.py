"""Capability matrix: which analyses the current data can support, and why not.
Messages follow the staff's own wording. Nothing is silently skipped or zero-filled."""
from __future__ import annotations

import json

import pandas as pd

from ..i18n import field_label, t
from ..models import Dataset
from .frame import cash, years_of

F = lambda *keys: [field_label(k) for k in keys]


def _cov(df: pd.DataFrame, field: str) -> float:
    if df.empty:
        return 0.0
    if field == "amount":
        c = df[~df["is_in_kind"]]
        return float(c["amount_ntd"].notna().mean()) if len(c) else 0.0
    col = {"donor_id": "donor_code", "date": "date", "report_year": "year", "method": "method", "project": "project_name",
           "donor_category": "donor_class", "mode": "mode"}.get(field)
    if col is None:
        return 1.0
    s = df[col]
    if field == "donor_category":
        return float((s != "unknown").mean())
    return float(s.notna().mean())


def capability(ds: Dataset, df: pd.DataFrame) -> list[dict]:
    mapped = set(json.loads(ds.mapped_fields))
    by_name = json.loads(ds.mapping_json or "{}").get("__donor_key") == "name"
    name_caveat = [t("cap.cav_name_key")] if by_name else []
    extras = [e.lower() for e in json.loads(ds.extra_columns)]
    n_years = len(years_of(df))
    out = []

    def add(id_, missing=(), caveats=(), blocked_msg=None, requires=()):
        label = t(f"cap.{id_}")
        miss = list(missing)
        if miss:
            status = "blocked"
            reason = blocked_msg or t("cap.blocked_generic", label=label, fields=t("cap.list_sep").join(F(*miss)))
        elif caveats:
            status, reason = "caveat", " ".join(caveats)
        else:
            status, reason = "available", ""
        out.append({"id": id_, "label": label, "status": status, "reason": reason, "requires": F(*requires),
                    "missing": F(*miss)})

    ok = lambda f: f in mapped and _cov(df, f) >= 0.5
    add("overview", [f for f in ["amount"] if not ok(f)],
        [] if "donor_id" in mapped else [t("cap.cav_overview_donors")], requires=["amount", "donor_id"])
    cav = [] if "receipt_date" in mapped else [t("cap.cav_monthly")]
    add("trends", [f for f in ["amount"] if not ok(f)] + ([] if ("report_year" in mapped or ok("date")) else ["report_year"]),
        cav, requires=["amount", "report_year", "date"])
    add("methods", [f for f in ["method"] if not ok(f)], [] if "mode" in mapped else [t("cap.cav_mode")],
        requires=["method", "mode", "amount"])
    add("bands", [f for f in ["amount"] if not ok(f)], requires=["amount"])
    add("classes", [f for f in ["donor_category"] if not ok(f)], requires=["donor_category", "amount"])
    add("purposes", [f for f in ["project"] if not ok(f)], requires=["project", "amount"])
    no_id = "donor_id" not in mapped
    add("repeat", ["donor_id"] if no_id or n_years < 2 else [], name_caveat,
        blocked_msg=t("cap.repeat_no_id") if no_id else t("cap.repeat_years"), requires=["donor_id", "report_year"])
    needs = [f for f in ["donor_id", "amount"] if not ok(f)]
    add("risk", needs if (needs or n_years >= 2) else ["donor_id"],
        name_caveat + ([] if n_years >= 3 else [t("cap.cav_one_transition")]),
        blocked_msg=None if needs else t("cap.risk_years"), requires=["donor_id", "amount", "report_year"])
    add("matching", [f for f in ["donor_id", "project"] if not ok(f)],
        name_caveat + ([] if n_years >= 3 else [t("cap.cav_match_eval")]), requires=["donor_id", "project"])
    add("scenario", needs if (needs or n_years >= 3) else ["donor_id"],
        blocked_msg=None if needs else t("cap.scenario_years"), requires=["donor_id", "amount", "report_year"])
    roll_missing = [f for f in ["donor_id", "anonymous"] if f not in mapped]
    add("roll", roll_missing, [] if "donor_name" in mapped else [t("cap.cav_roll_names")],
        blocked_msg=t("cap.roll_no_anon") if "anonymous" in roll_missing else None, requires=["donor_id", "anonymous", "donor_name"])
    has_sol = any("solicit" in e for e in extras)
    out.append({"id": "solicited", "label": t("cap.solicited"), "status": "available" if has_sol else "blocked",
                "reason": "" if has_sol else t("cap.solicited_missing"),
                "requires": [t("cap.solicited_req")], "missing": [] if has_sol else [t("cap.solicited_req")]})
    return out


def solicited_breakdown(df: pd.DataFrame) -> dict | None:
    key = None
    parsed = []
    for raw in df["extras"].fillna("{}"):
        try:
            d = json.loads(raw)
        except Exception:
            d = {}
        parsed.append(d)
        if key is None:
            key = next((k for k in d if "solicit" in k.lower()), None)
    if key is None:
        return None
    flag = pd.Series([str(d.get(key, "")).strip().lower() in {"yes", "y", "true", "1", "是"} for d in parsed], index=df.index)
    known = pd.Series([str(d.get(key, "")).strip() != "" for d in parsed], index=df.index)
    c = cash(df.assign(_s=flag, _k=known))
    c = c[c["_k"]]
    tiers = [(t("tier.0"), 0, 500_000), (t("tier.1"), 500_000, 1_000_000), (t("tier.2"), 1_000_000, 10_000_000),
             (t("tier.3"), 10_000_000, float("inf"))]
    rows = []
    for label, lo, hi in tiers:
        band = c[(c["amount_ntd"] >= lo) & (c["amount_ntd"] < hi)]       # not `t`: that name is the translate function
        s, u = band[band["_s"]], band[~band["_s"]]
        rows.append({"tier": label, "solicited_amount": float(s["amount_ntd"].sum()), "solicited_count": int(len(s)),
                     "unsolicited_amount": float(u["amount_ntd"].sum()), "unsolicited_count": int(len(u))})
    return {"column": key, "tiers": rows}
