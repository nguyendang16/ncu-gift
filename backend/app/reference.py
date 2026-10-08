"""The staff's project table as the source of truth for classification.

Their sheet `院系、提撥比例` lists every project name used on the website donor roll with a category such as
`院系教學研究-工-機` (department teaching & research, College of Engineering, Mechanical) or `專案2026、2025`
(an annual campaign in those years). Using it replaces guessing with what the staff already decided. Rules in
`org.classify_project` remain as the fallback for names the table does not list; those go to the review queue.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

import pandas as pd
from sqlalchemy.orm import Session

from . import org
from .models import AnnualProject, ProjectRef, RefMeta

NAME_HEADERS = ("網站-芳名錄", "網站芳名錄", "專案名稱", "project")
CAT_HEADERS = ("分類", "category")
ANNUAL_RE = re.compile(r"專案\s*((?:19|20)\d{2})")
YEAR_HDR = re.compile(r"((?:19|20)\d{2})\s*年\s*專案")
SUB = org.PURPOSE_SUBS


def ref_key(s) -> str:
    """Spelling-tolerant key: full/half-width, spaces and case do not matter."""
    t = unicodedata.normalize("NFKC", str(s or "")).lower()
    return re.sub(r"[\s　]+", "", t).replace("：", ":").replace("—", "-").replace("–", "-")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_workbook(sheets: dict[str, pd.DataFrame]) -> dict:
    """Find the classification sheet (by its headers) and the annual-projects sheet (by `YYYY年專案` headers)."""
    refs, annual = [], []
    for name, df in sheets.items():
        cols = [str(c).strip() for c in df.columns]
        n_col = next((c for c in df.columns if any(h in str(c) for h in NAME_HEADERS)), None)
        c_col = next((c for c in df.columns if str(c).strip() in CAT_HEADERS), None)
        if n_col is not None and c_col is not None:
            serial = next((c for c in df.columns if "流水號" in str(c)), None)
            code = next((c for c in df.columns if str(c).strip() in ("代號", "code")), None)
            fee = next((c for c in df.columns if "提撥" in str(c)), None)
            for _, r in df.iterrows():
                n, c = r[n_col], r[c_col]
                if pd.isna(n) or pd.isna(c) or not str(n).strip() or not str(c).strip():
                    continue
                refs.append({"name": str(n).strip(), "serial": None if serial is None or pd.isna(r[serial]) else str(r[serial]).strip().removesuffix(".0"),
                             "code": None if code is None or pd.isna(r[code]) else str(r[code]).strip(),
                             "category_raw": str(c).strip(), "fee_rate": None if fee is None else _num(r[fee])})
        year_cols = [(c, YEAR_HDR.search(str(c))) for c in df.columns]
        year_cols = [(c, m) for c, m in year_cols if m]
        if year_cols:
            for c, m in year_cols:
                for v in df[c].dropna():
                    if str(v).strip():
                        annual.append({"year": int(m.group(1)), "name": str(v).strip()})
    return {"refs": refs, "annual": annual}


def replace_reference(session: Session, parsed: dict, filename: str) -> dict:
    for model in (ProjectRef, AnnualProject, RefMeta):
        session.query(model).delete()
    seen = set()
    for r in parsed["refs"]:
        k = (ref_key(r["name"]), r["category_raw"])
        if k in seen:
            continue
        seen.add(k)
        session.add(ProjectRef(name_key=k[0], **r))
    for a in parsed["annual"]:
        session.add(AnnualProject(year=a["year"], name_key=ref_key(a["name"]), name=a["name"]))
    session.add(RefMeta(filename=filename))
    session.commit()
    return status(session)


def status(session: Session) -> dict:
    meta = session.query(RefMeta).first()
    years: dict[int, int] = {}
    for (y,) in session.query(AnnualProject.year):
        years[y] = years.get(y, 0) + 1
    return {"loaded": meta is not None, "filename": meta.filename if meta else None,
            "uploaded_at": meta.uploaded_at.isoformat() if meta else None,
            "n_projects": session.query(ProjectRef).count(), "annual_by_year": {str(y): n for y, n in sorted(years.items())}}


class Reference:
    """In-memory view used while classifying a whole dataset."""

    def __init__(self, session: Session):
        self.by_key: dict[str, list[str]] = {}
        self.names: dict[str, str] = {}
        for r in session.query(ProjectRef):
            self.by_key.setdefault(r.name_key, []).append(r.category_raw)
            self.names.setdefault(r.name_key, r.name)
        self.annual: dict[int, set[str]] = {}
        for a in session.query(AnnualProject):
            self.annual.setdefault(a.year, set()).add(a.name_key)
        # what the table says about each "office：" prefix, learned from its own rows, for names it does not list
        self.prefix: dict[str, Counter] = {}
        self.campaign_names = {k for k, cats in self.by_key.items() if any(ANNUAL_RE.search(c) for c in cats)}
        for key, cats in self.by_key.items():
            pre = _prefix(self.names[key])
            if not pre:
                continue
            for tok in (t.strip() for c in cats for t in re.split(r"[、,，]", c)):
                hit = None if ANNUAL_RE.search(tok) else _from_token(tok)
                if hit and hit[0] == "designated":
                    self.prefix.setdefault(ref_key(pre), Counter())[hit[1:]] += 1

    def __bool__(self) -> bool:
        return bool(self.by_key)

    def classify(self, name: str | None, year: int | None) -> dict | None:
        """None when the table does not list the name (the caller falls back to rules and the review queue)."""
        key = ref_key(name)
        cats = self.by_key.get(key)
        if not cats:
            return None
        canonical = self.names.get(key) or (name or "").strip()
        tokens = [t.strip() for c in cats for t in re.split(r"[、,，]", c) if t.strip()]
        campaign_years = {int(y) for t in tokens for y in ANNUAL_RE.findall(t)}
        if "校務基金" in tokens:                                 # the fund and its anniversary campaigns stay "university fund"
            return _out("university_fund", None, None, None, 1.0, canonical)
        listed = year is not None and (year in campaign_years or key in self.annual.get(year, ()))
        if listed:                                              # that year's campaign list (專案紀錄) or the table's 專案YYYY tag
            return _out("annual_campaign", None, None, None, 1.0, canonical)
        for tok in tokens:
            if ANNUAL_RE.search(tok):
                continue
            hit = _from_token(tok)
            if hit:
                return _out(*hit, 1.0, canonical)
        # only ever an annual campaign, and not one in this report year: the table cannot say what it is then
        # a campaign in other years but not listed for this one: very likely the same campaign, so propose it for confirmation
        return _out("annual_campaign", None, None, None, 0.7, canonical) if campaign_years else None

    def guess(self, name: str | None, year: int | None) -> dict | None:
        """A proposal (never auto-accepted: confidence 0.7 is below the review threshold) for a name the table does not list.
        1) a project the table tags as a campaign in other years; 2) the same office/department prefix as listed projects."""
        key = ref_key(name)
        if key in self.campaign_names:
            return _out("annual_campaign", None, None, None, 0.7, (name or "").strip())
        pre = _prefix(name)
        counts = self.prefix.get(ref_key(pre)) if pre else None
        if not counts:
            return None
        scholarship = bool(re.search(r"獎學金|獎助|助學|獎勵", name or ""))
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        pick = next((k for k, _ in ranked if (k[0] in (SUB[1], SUB[2])) == scholarship), None)
        if pick is None:
            return None
        sub, unit, college = pick
        return _out("designated", sub, unit, college, 0.7, (name or "").strip())

    def is_annual_name(self, name: str | None, year: int | None) -> bool:
        """For names the table does not list: the year's own campaign list (專案紀錄) may still know them."""
        return year is not None and ref_key(name) in self.annual.get(year, ())


def _out(group, sub, unit, college, conf, canonical):
    return {"purpose_group": group, "purpose_sub": sub, "unit": unit, "college": college, "confidence": conf, "canonical": canonical}


def _prefix(name) -> str | None:
    m = re.match(r"^\s*([^:：]{2,12})[:：]", str(name or ""))
    return m.group(1).strip() if m else None


_DEPT_FIRST = re.compile(r"^(院系教學研究|院系獎助學金)-([^-]+)-(.+)$")
_DEPT_LAST = re.compile(r"^([^-]+)-([^-]+)-獎助學金$")


def _from_token(tok: str):
    """-> (group, sub, unit, college) for one category token, or None if it is not a recognised category."""
    if tok == "校務基金":
        return ("university_fund", None, None, None)
    m = _DEPT_FIRST.match(tok)
    if m:
        sub = SUB[0] if m.group(1) == "院系教學研究" else SUB[1]
        return ("designated", sub, f"{m.group(2)}-{m.group(3)}", m.group(2))
    m = _DEPT_LAST.match(tok)
    if m:
        return ("designated", SUB[1], f"{m.group(1)}-{m.group(2)}", m.group(1))
    if tok.startswith("院系教學研究"):
        return ("designated", SUB[0], None, None)
    if tok.startswith("院系獎助學金"):
        return ("designated", SUB[1], None, None)
    if tok.startswith("全校-院系教學研究"):
        return ("designated", SUB[0], None, None)
    if tok.startswith(("獎助學金(全校性)", "全校型")):
        return ("designated", SUB[2], None, None)
    if tok.startswith("總教學單位"):
        return ("designated", SUB[3], None, None)
    if tok.startswith("行政單位"):
        return ("designated", SUB[4], None, None)
    if tok.startswith("學生社團"):
        return ("designated", SUB[5], None, None)
    if tok.startswith("研究中心"):
        return ("designated", SUB[6], None, None)
    if "永續" in tok:
        return ("designated", SUB[7], None, None)
    return None
