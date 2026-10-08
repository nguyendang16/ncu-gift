"""WP1: flexible ingestion. Proposes a column mapping (headers + content),
normalises values, classifies free text and loads everything into SQLite.

Principles from the staff meeting: missing is never zero; ambiguous columns are
confirmed by a person; extra columns are preserved for supplementary analysis.
The header+content heuristic below is the rule-based baseline; an LLM suggestion
would be merged in `propose_mapping` (see TODO) and still require confirmation.
"""
from __future__ import annotations

import difflib
import json
import re
import warnings
from collections import Counter

import pandas as pd
from sqlalchemy.orm import Session

from . import org
from .reference import Reference
from .i18n import t
from .models import Dataset, DonorName, Project, ReviewItem, Transaction

SHEET_COL = "(sheet name)"

FIELDS: dict[str, dict] = {
    "txn_id": {"aliases": ["record id", "id", "txn id", "transaction id", "gift id"]},
    "donor_id": {"aliases": ["donor code", "donor id", "donor", "user", "user id", "constituent id", "代號"]},
    "donor_name": {"aliases": ["donor name", "display name", "name", "姓名"]},
    "date": {"aliases": ["creation date", "gift date", "date", "date created", "donation date", "成立日期"]},
    "receipt_date": {"aliases": ["receipt date", "date received", "payment date", "received date", "入帳日"]},
    "report_year": {"aliases": ["report year", "fiscal year", "year", "sheet year"]},
    "amount": {"aliases": ["actual amount", "amount", "amount ntd", "amount nt", "ntd amount", "真實金額", "金額"]},
    "amount_original": {"aliases": ["donation details", "donation amount", "original amount", "捐款內容"]},
    "currency": {"aliases": ["currency", "幣別"]},
    "mode": {"aliases": ["donation mode", "mode", "donation type", "type", "模式"]},
    "method": {"aliases": ["donation method", "payment method", "method", "channel", "捐助方式"]},
    "project": {"aliases": ["donation project", "project", "fund", "fund project", "designation", "purpose", "捐助項目", "捐款項目"]},
    "donor_category": {"aliases": ["donor category", "category", "donor type", "identity", "constituency", "身份"]},
    "anonymous": {"aliases": ["anonymous", "anon", "anon?", "匿名"]},
    "in_kind_item": {"aliases": ["in kind item", "in-kind item", "item"]},
}

_YES_NO = {"yes", "no", "y", "n", "true", "false", "是", "否", "1", "0"}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w一-鿿 ]+", " ", str(s).lower())).strip()


def header_score(col: str, field: str) -> float:
    c = _clean(col)
    best = 0.0
    for alias in FIELDS[field]["aliases"]:
        a = _clean(alias)
        if c == a:
            return 1.0
        if len(a) >= 4 and len(c) >= 4 and (a in c or c in a):
            best = max(best, 0.8)
        else:
            r = difflib.SequenceMatcher(None, c, a).ratio()
            if r >= 0.8:
                best = max(best, r * 0.9)
    return best


def _sample(series: pd.Series, n: int = 200) -> pd.Series:
    s = series.dropna()
    s = s[s.astype(str).str.strip() != ""]
    return s.head(n)


def content_score(series: pd.Series, field: str) -> float | None:
    s = _sample(series)
    if len(s) == 0:
        return None
    strs = s.astype(str)
    if field in ("date", "receipt_date"):
        if pd.api.types.is_numeric_dtype(s):
            return 0.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return float(pd.to_datetime(s, errors="coerce").notna().mean())
    if field in ("amount", "amount_original"):
        num = pd.to_numeric(s, errors="coerce")
        return float((num.notna() & (num > 0)).mean())
    if field == "anonymous":
        return float(strs.str.lower().str.strip().isin(_YES_NO).mean())
    if field == "donor_category":
        return float(strs.map(lambda v: org.normalise_donor_class(v)[1] > 0.5).mean())
    if field == "method":
        return float(strs.map(lambda v: org.normalise_method(v) is not None).mean())
    if field == "mode":
        return float(strs.str.lower().str.contains("recurring|one-time|one time|monthly|定期|單次").mean())
    if field == "donor_id":
        u = strs.nunique() / len(strs)
        return 0.7 if (0.15 <= u <= 0.95 and strs.str.len().max() < 25) else 0.1
    if field == "project":
        return float(strs.map(lambda v: org.classify_project(v)["confidence"] > 0).mean()) if strs.str.len().mean() > 12 else 0.1
    if field == "report_year":
        num = pd.to_numeric(s, errors="coerce")
        ok = num.between(1990, 2100) & (num == num.round())
        return float(ok.mean()) if num.nunique() <= 15 else 0.1
    if field == "currency":
        return float(strs.str.lower().isin({"twd", "usd", "ntd", "jpy", "eur", "台幣", "美金"}).mean())
    return None


def ledger_sheets(sheets: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """A workbook often carries other sheets (a donor roll, notes, requirements). Keep the sheets whose headers look like a
    donation ledger (at least four recognised fields) and say which were skipped. If none qualify, keep everything."""
    def hits(df):
        return sum(1 for f in FIELDS if any(header_score(c, f) >= 0.8 for c in df.columns))
    scores = {k: hits(v) for k, v in sheets.items()}
    kept = {k: v for k, v in sheets.items() if scores[k] >= 4}
    if not kept:
        return sheets, []
    return kept, [str(k) for k in sheets if k not in kept]


def propose_mapping(sheets: dict[str, pd.DataFrame]) -> dict:
    """Return per-column proposals. TODO(LLM): merge an LLM suggestion for columns whose
    best confidence is below 0.8; the result would still be shown for confirmation."""
    frames = [df for df in sheets.values() if len(df.columns)]
    combined = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    cands: list[tuple[float, str, str]] = []
    per_col: dict[str, list[tuple[str, float]]] = {}
    for col in combined.columns:
        lst = []
        for field in FIELDS:
            h = header_score(col, field)
            c = content_score(combined[col], field)
            if h > 0:
                conf = 0.65 * h + 0.35 * (c if c is not None else 0.6)
            elif c is not None and c >= 0.8 and field in ("donor_category", "method", "mode", "anonymous", "currency", "date"):
                conf = 0.55 * c
            else:
                continue
            if conf >= 0.35:
                lst.append((field, round(conf, 3)))
                cands.append((conf, col, field))
        per_col[col] = sorted(lst, key=lambda x: -x[1])

    assigned_col: dict[str, tuple[str, float]] = {}
    assigned_field: set[str] = set()
    for conf, col, field in sorted(cands, reverse=True):
        if col in assigned_col or field in assigned_field:
            continue
        assigned_col[col] = (field, conf)
        assigned_field.add(field)

    sheet_years = len(sheets) > 1 and all(re.fullmatch(r"(19|20)\d{2}", str(n).strip()) for n in sheets)
    columns = []
    for col in combined.columns:
        field, conf = assigned_col.get(col, (None, 0.0))
        alts = [a for a in per_col[col] if a[0] != field]
        ambiguous = False
        if field:
            for other, lst in per_col.items():
                # a rival is another column whose *best* reading is the same field
                if other != col and lst and lst[0][0] == field and abs(lst[0][1] - conf) <= 0.15:
                    ambiguous = True
        samples = [str(v)[:40] for v in _sample(combined[col], 3).tolist()]
        columns.append({
            "name": str(col), "sample": samples, "proposed_field": field,
            "confidence": round(conf, 2), "ambiguous": ambiguous,
            "needs_confirmation": bool(field is None or conf < 0.8 or ambiguous),
            "alternatives": [{"field": f, "confidence": c} for f, c in alts[:3]],
        })
    if sheet_years and "report_year" not in assigned_field:
        columns.append({"name": SHEET_COL, "sample": [str(n) for n in list(sheets)[:3]], "proposed_field": "report_year",
                        "confidence": 0.9, "needs_confirmation": False, "ambiguous": False, "alternatives": []})
    mapped = {c["proposed_field"] for c in columns if c["proposed_field"]}
    return {"columns": columns, "missing_fields": [f for f in FIELDS if f not in mapped],
            "n_rows": int(sum(len(df) for df in sheets.values())), "sheets": [str(s) for s in sheets]}


# ------------------------------------------------------------------- ingest

def _none_if_nan(v):
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    return v


def ingest(session: Session, sheets: dict[str, pd.DataFrame], mapping: dict[str, str], name: str,
           is_mock: bool = False, source_file: str | None = None) -> Dataset:
    """mapping: canonical field -> source column name (or SHEET_COL for report_year)."""
    name_key = "donor_id" not in mapping and "donor_name" in mapping
    if name_key:           # no separate donor ID: the name identifies the donor (a pseudonym in anonymised exports)
        mapping = {**mapping, "donor_id": mapping["donor_name"]}
    parts = []
    for sname, df in sheets.items():
        d = df.copy()
        d["__sheet__"] = str(sname)
        parts.append(d)
    df = pd.concat(parts, ignore_index=True, sort=False)
    col = lambda f: df[mapping[f]] if f in mapping and mapping[f] in df.columns else None
    blank = lambda: pd.Series([None] * len(df), index=df.index, dtype=object)

    ds = Dataset(name=name, is_mock=is_mock, source_file=source_file)
    session.add(ds)
    session.flush()

    out = pd.DataFrame(index=df.index)
    c = col("txn_id")
    out["txn_id"] = c.astype(str).where(c.notna()) if c is not None else blank()
    c = col("donor_id")
    out["donor_code"] = c.astype(str).str.strip().where(c.notna()) if c is not None else blank()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dt = pd.to_datetime(col("date"), errors="coerce") if col("date") is not None else pd.Series(pd.NaT, index=df.index)
        rd = pd.to_datetime(col("receipt_date"), errors="coerce") if col("receipt_date") is not None else pd.Series(pd.NaT, index=df.index)
    out["date"] = dt.dt.date
    out["receipt_date"] = rd.dt.date

    if mapping.get("report_year") == SHEET_COL:
        ry = df["__sheet__"].str.extract(r"((?:19|20)\d{2})")[0].astype(float)
    elif col("report_year") is not None:
        ry = pd.to_numeric(col("report_year"), errors="coerce")
    else:
        ry = dt.dt.year.astype(float)
    out["report_year"] = ry

    c = col("method")
    method_norm = c.map(org.normalise_method) if c is not None else blank()
    item = col("in_kind_item") if col("in_kind_item") is not None else blank()
    item_present = item.notna() & (item.astype(str).str.strip() != "")
    is_in_kind = (method_norm == "in_kind") | item_present
    amt = pd.to_numeric(col("amount"), errors="coerce") if col("amount") is not None else pd.Series(float("nan"), index=df.index)
    out["amount_ntd"] = amt.where(~is_in_kind)             # missing stays missing; never coerced to 0
    out["is_in_kind"] = is_in_kind.astype(bool)
    out["in_kind_item"] = item.where(item_present)
    c = col("currency")
    out["currency"] = c.astype(str).where(c.notna()) if c is not None else blank()
    c = col("mode")
    out["mode"] = c.map(org.normalise_mode) if c is not None else blank()
    out["method"] = method_norm
    c = col("anonymous")
    out["anonymous"] = c.map(org.normalise_bool).astype(bool) if c is not None else False

    c = col("project")
    proj = c.astype(str).str.strip().where(c.notna()) if c is not None else blank()
    out["project_raw"] = proj
    ref = Reference(session)

    def classify(p, year):
        """The staff's table first (it knows the year's campaigns); rules only for names it does not list."""
        year = None if year is None or pd.isna(year) else int(year)
        hit = ref.classify(p, year) if ref else None
        if hit is None and ref and ref.is_annual_name(p, year):
            return {"purpose_group": "annual_campaign", "purpose_sub": None, "unit": None, "college": None, "confidence": 0.9, "canonical": str(p).strip()}
        if hit is None and ref:
            hit = ref.guess(p, year)
        return hit or org.classify_project(p)

    pairs = pd.DataFrame({"p": proj, "y": out["report_year"]})
    cls_by_pair = {(p, y): classify(p, y) for p, y in pairs.dropna(subset=["p"]).drop_duplicates().itertuples(index=False)}
    cls_cache = {}                              # raw name -> its (best) classification, for the project list and review queue
    for (p, _y), cl in cls_by_pair.items():
        if p not in cls_cache or cl["confidence"] < cls_cache[p]["confidence"]:
            cls_cache[p] = cl                    # the least certain reading wins: if any year is unclear, a person looks
    rowcls = [cls_by_pair.get((p, y)) if p is not None and not (isinstance(p, float) and pd.isna(p)) else None for p, y in zip(pairs["p"], pairs["y"])]
    out["project_name"] = [c["canonical"] if c else None for c in rowcls]
    for f, target in (("purpose_group", "purpose_group"), ("purpose_sub", "purpose_sub"), ("unit", "unit"),
                      ("college", "college"), ("confidence", "class_conf")):
        out[target] = [c[f] if c else None for c in rowcls]

    c = col("donor_category")
    if c is not None:
        out["donor_class_raw"] = c.astype(str).where(c.notna())
        norm = c.map(lambda v: org.normalise_donor_class(v)[0])
        out["donor_class"] = norm
        attrs = c.map(org.extract_alumni_attrs)
        is_al = norm == "alumni"
        out["grad_year"] = attrs.map(lambda a: a[0]).where(is_al)
        out["dept"] = attrs.map(lambda a: a[1]).where(is_al)
    else:
        out["donor_class_raw"] = blank()
        out["donor_class"] = "unknown"
        out["grad_year"] = blank()
        out["dept"] = blank()

    used = set(mapping.values()) | {"__sheet__"}
    extra_cols = [x for x in df.columns if x not in used]
    orig_col = mapping.get("amount_original")
    extras = []
    for i in df.index:
        e = {}
        for x in extra_cols:
            v = df.at[i, x]
            if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
                continue
            e[str(x)] = v if isinstance(v, (int, float, str, bool)) else str(v)
        if orig_col in df.columns:
            v = df.at[i, orig_col]
            if not (isinstance(v, float) and pd.isna(v)):
                e["amount_original"] = v if isinstance(v, (int, float, str, bool)) else str(v)
        extras.append(json.dumps(e, ensure_ascii=False, default=str))
    out["extras"] = extras

    records = []
    for r in out.to_dict("records"):
        rec = {k: _none_if_nan(v) for k, v in r.items()}
        rec["dataset_id"] = ds.id
        for k in ("report_year", "grad_year"):
            if rec.get(k) is not None:
                rec[k] = int(rec[k])
        rec["anonymous"] = bool(rec.get("anonymous"))
        rec["is_in_kind"] = bool(rec.get("is_in_kind"))
        records.append(rec)
    session.bulk_insert_mappings(Transaction, records)

    first_year = out.dropna(subset=["project_name"]).groupby("project_name")["report_year"].min()
    best: dict[str, dict] = {}
    for p, cl in cls_cache.items():
        key = cl["canonical"]
        if key not in best or cl["confidence"] > best[key]["confidence"]:
            best[key] = cl
    for key, cl in best.items():
        fy = first_year.get(key)
        session.add(Project(dataset_id=ds.id, name=key, purpose_group=cl["purpose_group"], purpose_sub=cl["purpose_sub"],
                            unit=cl["unit"], college=cl["college"], confidence=cl["confidence"],
                            year_first_seen=int(fy) if fy is not None and pd.notna(fy) else None))
    if col("donor_name") is not None and col("donor_id") is not None:
        names = pd.DataFrame({"c": out["donor_code"], "n": col("donor_name")}).dropna().drop_duplicates("c")
        session.bulk_save_objects([DonorName(dataset_id=ds.id, donor_code=str(a), display_name=str(b)) for a, b in zip(names.c, names.n)])
    elif col("donor_id") is not None:
        session.bulk_save_objects([DonorName(dataset_id=ds.id, donor_code=x, display_name=x) for x in out["donor_code"].dropna().unique()])

    counts = Counter(proj.dropna())
    for p, cl in cls_cache.items():
        if cl["confidence"] < org.REVIEW_THRESHOLD:
            guess = (cl["purpose_sub"] or cl["purpose_group"]) if cl["confidence"] > 0 else None   # identifiers, translated on output
            session.add(ReviewItem(dataset_id=ds.id, kind="purpose", raw_value=p, proposed_label=guess,
                                   confidence=float(cl["confidence"]), n_rows=counts[p]))
    if out["donor_class_raw"].notna().any():
        rawc = out.loc[out["donor_class"] == "unknown", "donor_class_raw"].dropna()
        rawc = rawc[rawc.str.strip() != ""]
        for v, k in Counter(rawc).items():
            session.add(ReviewItem(dataset_id=ds.id, kind="donor_class", raw_value=v, proposed_label=None,
                                   confidence=0.2, n_rows=k))

    stored = dict(mapping)
    if name_key:
        stored["__donor_key"] = "name"
    ds.mapping_json = json.dumps(stored, ensure_ascii=False)
    ds.mapped_fields = json.dumps(sorted(mapping))
    ds.extra_columns = json.dumps([str(x) for x in extra_cols])
    session.commit()
    return ds


def reclassify(session: Session, dataset_id: int) -> dict:
    """Apply the staff's project table to a dataset that is already loaded. Names the table does not list keep whatever they
    had (rules or a person's earlier answer); the project list and the pending review items are rebuilt from the result."""
    from sqlalchemy import func
    ref = Reference(session)
    changed = 0
    pairs = session.query(Transaction.project_raw, Transaction.report_year).filter(
        Transaction.dataset_id == dataset_id, Transaction.project_raw.isnot(None)).distinct().all()
    for raw, year in pairs:
        cl = ref.classify(raw, year) if ref else None
        if cl is None:
            continue
        n = session.query(Transaction).filter(Transaction.dataset_id == dataset_id, Transaction.project_raw == raw,
                                              Transaction.report_year == year).update(
            {"project_name": cl["canonical"], "purpose_group": cl["purpose_group"], "purpose_sub": cl["purpose_sub"],
             "unit": cl["unit"], "college": cl["college"], "class_conf": cl["confidence"]}, synchronize_session=False)
        changed += n
    session.flush()
    session.query(Project).filter(Project.dataset_id == dataset_id).delete()
    rows = session.query(Transaction.project_name, Transaction.purpose_group, Transaction.purpose_sub, Transaction.unit, Transaction.college,
                         func.min(Transaction.class_conf), func.min(Transaction.report_year)).filter(
        Transaction.dataset_id == dataset_id, Transaction.project_name.isnot(None)).group_by(Transaction.project_name).all()
    for name, g, s, u, c, conf, fy in rows:
        session.add(Project(dataset_id=dataset_id, name=name, purpose_group=g, purpose_sub=s, unit=u, college=c, confidence=conf, year_first_seen=fy))
    done = {r.raw_value for r in session.query(ReviewItem).filter(ReviewItem.dataset_id == dataset_id, ReviewItem.kind == "purpose",
                                                                 ReviewItem.status == "resolved")}
    session.query(ReviewItem).filter(ReviewItem.dataset_id == dataset_id, ReviewItem.kind == "purpose", ReviewItem.status == "pending").delete()
    n_review = 0
    for raw, conf, n in session.query(Transaction.project_raw, func.min(Transaction.class_conf), func.count(Transaction.id)).filter(
            Transaction.dataset_id == dataset_id, Transaction.project_raw.isnot(None)).group_by(Transaction.project_raw):
        if (conf or 0) < org.REVIEW_THRESHOLD and raw not in done:
            sub = session.query(Transaction.purpose_sub, Transaction.purpose_group).filter(
                Transaction.dataset_id == dataset_id, Transaction.project_raw == raw).first()
            guess = (sub[0] or sub[1]) if sub and (conf or 0) > 0 else None
            session.add(ReviewItem(dataset_id=dataset_id, kind="purpose", raw_value=raw, proposed_label=guess, confidence=float(conf or 0), n_rows=n))
            n_review += 1
    session.commit()
    return {"rows_updated": changed, "review_items": n_review}


def auto_mapping(sheets: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Accept every proposal (used to seed the mock dataset through the same path as an upload)."""
    prop = propose_mapping(sheets)
    return {c["proposed_field"]: c["name"] for c in prop["columns"] if c["proposed_field"]}


def resolve_review(session: Session, item: ReviewItem, label: str) -> None:
    q = session.query(Transaction).filter(Transaction.dataset_id == item.dataset_id)
    if item.kind == "purpose":
        if label in org.PURPOSE_SUBS:
            vals = {"purpose_group": "designated", "purpose_sub": label}
        elif label in ("annual_campaign", "university_fund"):
            vals = {"purpose_group": label, "purpose_sub": None}
        else:
            raise ValueError(t("err.unknown_purpose", label=label))
        rows = q.filter(Transaction.project_raw == item.raw_value)
        canon = rows.with_entities(Transaction.project_name).first()
        rows.update({**vals, "class_conf": 1.0})
        if canon and canon[0]:
            session.query(Project).filter(Project.dataset_id == item.dataset_id, Project.name == canon[0]).update({**vals, "confidence": 1.0})
    else:
        if label not in org.DONOR_CLASSES:
            raise ValueError(t("err.unknown_class", label=label))
        q.filter(Transaction.donor_class_raw == item.raw_value).update({"donor_class": label})
    item.status = "resolved"
    item.resolved_label = label
    session.commit()
