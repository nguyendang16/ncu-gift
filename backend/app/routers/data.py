"""Datasets, flexible upload and column mapping, capability matrix, review queue."""
import io
import json
import uuid
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import config, i18n, ingest as ing, org, reference as ref_mod, schemas
from ..i18n import t
from ..db import get_session
from ..seed import MOCK_NAME
from ..models import Dataset, ReviewItem, Transaction, Upload
from ..services import capability as cap
from ..services.frame import load_df, years_of
from .deps import frame_for, get_dataset

router = APIRouter()
MAX_BYTES = 20 * 1024 * 1024


def _dataset_out(session: Session, ds: Dataset) -> schemas.DatasetOut:
    years = [r[0] for r in session.query(Transaction.report_year).filter(Transaction.dataset_id == ds.id).distinct() if r[0]]
    n = session.query(Transaction).filter(Transaction.dataset_id == ds.id).count()
    name = t("dataset.mock_name") if ds.is_mock and ds.name == MOCK_NAME else ds.name
    return schemas.DatasetOut(id=ds.id, name=name, is_mock=ds.is_mock, n_rows=n, years=sorted(years),
                              created_at=ds.created_at.isoformat(), mapped_fields=json.loads(ds.mapped_fields),
                              extra_columns=json.loads(ds.extra_columns))


@router.get("/meta", response_model=schemas.Meta)
def meta():
    purposes = [schemas.Option(value=s, label=i18n.purpose_label(s)) for s in org.PURPOSE_SUBS]
    purposes += [schemas.Option(value=g, label=i18n.group_label(g)) for g in ("annual_campaign", "university_fund")]
    return schemas.Meta(
        exceptional_threshold=config.DEFAULT_EXCEPTIONAL_THRESHOLD, large_threshold=config.DEFAULT_LARGE_THRESHOLD,
        risk_value_cap=config.RISK_VALUE_CAP, return_definitions=["retained", "returning_after_gap", "either"],
        purpose_labels=purposes,
        donor_classes=[schemas.Option(value=c, label=i18n.class_label(c)) for c in org.DONOR_CLASSES],
        fields=[schemas.FieldInfo(key=k, label=i18n.field_label(k)) for k in ing.FIELDS])


@router.get("/datasets", response_model=list[schemas.DatasetOut])
def datasets(session: Session = Depends(get_session)):
    return [_dataset_out(session, d) for d in session.query(Dataset).order_by(Dataset.id)]


def _read(path: Path, filename: str) -> dict[str, pd.DataFrame]:
    """Only the donation-ledger sheets (see ingest.ledger_sheets); the others are reported as skipped, never mixed in."""
    return _read_all(path, filename)[0]


def _read_all(path: Path, filename: str) -> tuple[dict[str, pd.DataFrame], list[str]]:
    if filename.lower().endswith((".csv", ".txt")):
        return {"Sheet1": pd.read_csv(path)}, []
    sheets = pd.read_excel(path, sheet_name=None, engine="openpyxl")
    sheets = {str(k): v.dropna(how="all") for k, v in sheets.items()}
    sheets = {k: v for k, v in sheets.items() if len(v.columns) and len(v)}
    return ing.ledger_sheets(sheets)


@router.post("/upload/preview", response_model=schemas.PreviewOut)
async def upload_preview(file: UploadFile, session: Session = Depends(get_session)):
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, t("err.file_too_large"))
    name = file.filename or "upload.xlsx"
    if not name.lower().endswith((".xlsx", ".xlsm", ".csv")):
        raise HTTPException(400, t("err.bad_extension"))
    uid = uuid.uuid4().hex[:12]
    path = config.UPLOAD_DIR / f"{uid}_{Path(name).name}"
    path.write_bytes(raw)
    try:
        sheets, skipped = _read_all(path, name)
    except Exception as e:  # unreadable file: say so, do not guess
        path.unlink(missing_ok=True)
        raise HTTPException(400, t("err.unreadable", error=e))
    if not sheets:
        raise HTTPException(400, t("err.no_rows"))
    session.add(Upload(id=uid, filename=name, path=str(path)))
    session.commit()
    prop = ing.propose_mapping(sheets)
    donors = next((c for c in prop["columns"] if c["proposed_field"] == "donor_id"), None)
    note = t("upload.row_note", n=prop["n_rows"])
    if skipped:
        note += " " + t("upload.skipped_sheets", sheets=t("cap.list_sep").join(skipped))
    if "donor_id" in prop["missing_fields"] and any(c["proposed_field"] == "donor_name" for c in prop["columns"]):
        note += " " + t("upload.name_as_key")
    return schemas.PreviewOut(upload_id=uid, filename=name, sheets=prop["sheets"], n_rows=prop["n_rows"],
                              columns=prop["columns"], missing_fields=prop["missing_fields"], row_note=note)


@router.post("/upload/confirm", response_model=schemas.ConfirmOut)
def upload_confirm(body: schemas.ConfirmIn, session: Session = Depends(get_session)):
    up = session.get(Upload, body.upload_id)
    if up is None:
        raise HTTPException(404, t("err.upload_not_found"))
    bad = [f for f in body.mapping if f not in ing.FIELDS]
    if bad:
        raise HTTPException(400, t("err.unknown_fields", fields=bad))
    sheets = _read(Path(up.path), up.filename)
    cols = {c for df in sheets.values() for c in df.columns} | {ing.SHEET_COL}
    missing = [v for v in body.mapping.values() if v not in cols]
    if missing:
        raise HTTPException(400, t("err.missing_columns", columns=missing))
    ds = ing.ingest(session, sheets, body.mapping, body.name or up.filename, source_file=up.filename)
    df = load_df(session, ds.id)
    n_review = session.query(ReviewItem).filter(ReviewItem.dataset_id == ds.id, ReviewItem.status == "pending").count()
    return schemas.ConfirmOut(dataset_id=ds.id, n_rows=len(df), review_items=n_review,
                              capability=[schemas.Capability(**c) for c in cap.capability(ds, df)])


@router.get("/capability", response_model=list[schemas.Capability])
def capability(dataset_id: int | None = None, session: Session = Depends(get_session)):
    ds, df = frame_for(session, dataset_id)
    return [schemas.Capability(**c) for c in cap.capability(ds, df)]


def _label_text(kind: str, value: str | None) -> str | None:
    if not value:
        return None
    if kind == "donor_class":
        return i18n.class_label(value)
    return i18n.purpose_label(value) if value in org.PURPOSE_SUBS else i18n.group_label(value) or value


def _review_out(r: ReviewItem) -> schemas.ReviewOut:
    return schemas.ReviewOut(id=r.id, kind=r.kind, raw_value=r.raw_value, proposed_label=r.proposed_label,
                             proposed_text=_label_text(r.kind, r.proposed_label), confidence=r.confidence, n_rows=r.n_rows,
                             status=r.status, resolved_label=r.resolved_label, resolved_text=_label_text(r.kind, r.resolved_label))


@router.get("/review", response_model=list[schemas.ReviewOut])
def review(dataset_id: int | None = None, status: str | None = None, session: Session = Depends(get_session)):
    ds = get_dataset(session, dataset_id)
    q = session.query(ReviewItem).filter(ReviewItem.dataset_id == ds.id)
    if status:
        q = q.filter(ReviewItem.status == status)
    return [_review_out(r) for r in q.order_by(ReviewItem.status.desc(), ReviewItem.n_rows.desc())]


@router.post("/review/{item_id}/resolve", response_model=schemas.ReviewOut)
def resolve(item_id: int, body: schemas.ResolveIn, session: Session = Depends(get_session)):
    item = session.get(ReviewItem, item_id)
    if item is None:
        raise HTTPException(404, t("err.review_not_found"))
    try:
        ing.resolve_review(session, item, body.label)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _review_out(item)


@router.post("/review/accept-suggestions", response_model=schemas.AcceptOut)
def accept_suggestions(body: schemas.AcceptIn, session: Session = Depends(get_session)):
    """Confirm every pending purpose suggestion at or above `min_confidence` in one go (a person still pressed the button)."""
    ds = get_dataset(session, body.dataset_id)
    items = session.query(ReviewItem).filter(ReviewItem.dataset_id == ds.id, ReviewItem.kind == "purpose", ReviewItem.status == "pending",
                                             ReviewItem.proposed_label.isnot(None), ReviewItem.confidence >= body.min_confidence).all()
    n = 0
    for item in items:
        try:
            ing.resolve_review(session, item, item.proposed_label)
            n += 1
        except ValueError:
            continue
    return schemas.AcceptOut(accepted=n)


@router.get("/reference", response_model=schemas.RefStatus)
def reference_status(session: Session = Depends(get_session)):
    return schemas.RefStatus(**ref_mod.status(session))


@router.post("/reference", response_model=schemas.RefStatus)
async def reference_upload(file: UploadFile, session: Session = Depends(get_session)):
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, t("err.file_too_large"))
    name = file.filename or "reference.xlsx"
    if not name.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, t("err.bad_extension"))
    try:
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, engine="openpyxl")
    except Exception as e:
        raise HTTPException(400, t("err.unreadable", error=e))
    parsed = ref_mod.parse_workbook({str(k): v for k, v in sheets.items()})
    if not parsed["refs"]:
        raise HTTPException(400, t("ref.err.none"))
    return schemas.RefStatus(**ref_mod.replace_reference(session, parsed, name))


@router.post("/reference/apply", response_model=schemas.ApplyRefOut)
def reference_apply(body: schemas.ApplyRefIn, session: Session = Depends(get_session)):
    if not ref_mod.status(session)["loaded"]:
        raise HTTPException(409, t("ref.err.not_loaded"))
    ds = get_dataset(session, body.dataset_id)
    return schemas.ApplyRefOut(**ing.reclassify(session, ds.id))


@router.get("/extras/solicited", response_model=schemas.SolicitedOut)
def solicited(dataset_id: int | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    res = cap.solicited_breakdown(df)
    if res is None:
        raise HTTPException(409, t("err.solicited_missing"))
    return res


SAMPLES = {"mock_donations.xlsx", "mock_donations_renamed.xlsx"}


@router.get("/samples/{name}")
def sample(name: str):
    """Synthetic sample workbooks for trying the upload flow."""
    path = config.SAMPLE_DIR / name
    if name not in SAMPLES or not path.exists():
        raise HTTPException(404, t("err.sample_not_found"))
    return FileResponse(path, filename=name)
