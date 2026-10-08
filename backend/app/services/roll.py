"""WP8: donor recognition list. Anonymity is enforced in code: one function,
`display_name`, is the only place a name can enter the roll, and it masks every
record flagged anonymous. Names live in their own table, never in the analytics frame."""
from __future__ import annotations

import json
import re

import pandas as pd
from sqlalchemy.orm import Session

from .. import i18n, org
from ..i18n import t
from ..models import DonorName
from .frame import years_of



def mask() -> str:
    """The label shown instead of an anonymous donor's name ("Friends of NCU" / 中大之友)."""
    return t("roll.friends")


def names_for(session: Session, dataset_id: int) -> dict[str, str]:
    return {n.donor_code: n.display_name for n in session.query(DonorName).filter(DonorName.dataset_id == dataset_id)}


def display_name(anonymous: bool, donor_code: str, names: dict[str, str]) -> str:
    return mask() if anonymous else i18n.donor_name_label(names.get(donor_code, donor_code))


def build_roll(df: pd.DataFrame, names: dict[str, str], year: int) -> dict:
    cur = df[df["year"] == year]
    sections = []

    def section(heading, frame):
        projects = []
        for proj, g in frame.groupby("project_name", dropna=False):
            entries = {}
            for _, r in g.iterrows():
                nm = display_name(bool(r["anonymous"]), r["donor_code"], names)
                key = (r["donor_code"] if r["anonymous"] else nm, r["mode"] == "recurring")
                e = entries.setdefault(key, {"name": nm, "amount": 0.0, "recurring": r["mode"] == "recurring"})
                e["amount"] += float(r["amount_ntd"])
            projects.append({"project": t("roll.unspecified") if pd.isna(proj) else i18n.project_label(str(proj)),
                             "entries": sorted(entries.values(), key=lambda e: -e["amount"])})
        projects.sort(key=lambda p: -sum(e["amount"] for e in p["entries"]))
        if projects:
            sections.append({"heading": heading, "projects": projects})

    money = cur[(~cur["is_in_kind"]) & cur["amount_ntd"].notna()]
    section(i18n.group_label("university_fund"), money[money["purpose_group"] == "university_fund"])
    section(i18n.group_label("annual_campaign"), money[money["purpose_group"] == "annual_campaign"])
    for s in org.PURPOSE_SUBS:
        section(t("roll.h_designated", sub=i18n.purpose_label(s)), money[money["purpose_sub"] == s])
    section(t("class.unknown"), money[money["purpose_group"].isna()])
    ik = cur[cur["is_in_kind"]]
    in_kind = [{"name": display_name(bool(r["anonymous"]), r["donor_code"], names), "item": i18n.tr(f"item.{r['in_kind_item']}", r["in_kind_item"] or ""),
                "project": i18n.project_label(r["project_name"]) if pd.notna(r["project_name"]) else ""} for _, r in ik.iterrows()]
    return {"title": t("roll.title"), "year": year, "sections": sections, "in_kind": in_kind,
            "stats": {"cash_entries": int(len(money)), "masked_entries": int(money["anonymous"].sum()),
                      "in_kind_entries": int(len(ik)), "friends_label": mask()}}


def leak_test(df: pd.DataFrame, names: dict[str, str]) -> dict:
    anon = df[df["anonymous"] & df["donor_code"].notna()]
    unmasked = sum(1 for _, r in anon.iterrows() if display_name(True, r["donor_code"], names) != mask())
    allanon = df.dropna(subset=["donor_code"]).groupby("donor_code")["anonymous"].all()
    fully = [d for d in allanon[allanon].index]
    text = json.dumps([build_roll(df, names, y) for y in years_of(df)], ensure_ascii=False)
    hits = 0
    for d in fully:
        for needle in {names.get(d, d), i18n.donor_name_label(names.get(d, d)), d}:
            if re.search(rf"(?<![\w]){re.escape(needle)}(?![\w])", text):
                hits += 1
    return {"anonymous_rows": int(len(anon)), "anonymous_rows_unmasked": int(unmasked),
            "fully_anonymous_donors": int(len(fully)), "identity_occurrences_in_roll": int(hits),
            "passed": unmasked == 0 and hits == 0}
