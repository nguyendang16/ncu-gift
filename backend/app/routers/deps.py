from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import config
from ..i18n import t
from ..models import Dataset
from ..services.frame import load_df


def get_dataset(session: Session, dataset_id: int | None) -> Dataset:
    q = session.query(Dataset)
    ds = q.filter(Dataset.id == dataset_id).first() if dataset_id else q.order_by(Dataset.id).first()
    if ds is None:
        raise HTTPException(404, t("err.dataset_not_found"))
    return ds


def frame_for(session: Session, dataset_id: int | None):
    ds = get_dataset(session, dataset_id)
    return ds, load_df(session, ds.id)


def exc_threshold(v: float | None) -> float:
    return v if v is not None else config.DEFAULT_EXCEPTIONAL_THRESHOLD
