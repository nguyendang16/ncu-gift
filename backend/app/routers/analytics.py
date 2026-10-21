from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, schemas
from ..db import get_session
from ..i18n import t
from ..services import insights as ins, journey as jr, stats
from .deps import exc_threshold, frame_for

router = APIRouter()


@router.get("/trend", response_model=list[schemas.TrendRow])
def trend(dataset_id: int | None = None, exceptional_threshold: float | None = None,
          band_low: float | None = None, band_high: float | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    low = 500_000.0 if band_low is None else band_low
    high = 1_000_000.0 if band_high is None else band_high
    if not (low > 0 and high > low):
        raise HTTPException(400, t("err.band_order"))
    return stats.trend(df, exc_threshold(exceptional_threshold), low, high)


@router.get("/class-compare", response_model=schemas.ClassCompare)
def class_compare(dataset_id: int | None = None, scope: str = "all", exceptional_threshold: float | None = None,
                  amount_min: float | None = None, amount_max: float | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    if (amount_min is not None and amount_min < 0) or (amount_max is not None and amount_max < 0):
        raise HTTPException(400, t("err.class_range"))
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(400, t("err.class_range"))
    return stats.class_compare(df, exc_threshold(exceptional_threshold),
                               scope if scope in ("all", "regular") else "all", amount_min, amount_max)


@router.get("/overview", response_model=schemas.OverviewOut)
def overview(dataset_id: int | None = None, year: int | None = None, compare_year: int | None = None, scope: str = "all",
             exceptional_threshold: float | None = None, large_threshold: float | None = None,
             return_definition: str = "retained", session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    from ..services.frame import years_of
    y = year or years_of(df)[-1]
    return stats.overview(df, y, exc_threshold(exceptional_threshold),
                          large_threshold if large_threshold is not None else config.DEFAULT_LARGE_THRESHOLD,
                          scope if scope in ("all", "regular") else "all", return_definition, compare_year)


@router.get("/journey", response_model=schemas.JourneyOut)
def journey(dataset_id: int | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return jr.journey(df)


def _year(df, year):
    from ..services.frame import years_of
    return year or years_of(df)[-1]


@router.get("/concentration", response_model=schemas.ConcentrationOut)
def concentration(dataset_id: int | None = None, year: int | None = None, exceptional_threshold: float | None = None,
                  session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return ins.concentration(df, _year(df, year), exc_threshold(exceptional_threshold))


@router.get("/bridge", response_model=schemas.BridgeOut)
def bridge(dataset_id: int | None = None, year: int | None = None, compare_year: int | None = None,
           exceptional_threshold: float | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return ins.bridge(df, _year(df, year), exc_threshold(exceptional_threshold), compare_year)


@router.get("/seasonality", response_model=schemas.SeasonOut)
def seasonality(dataset_id: int | None = None, exceptional_threshold: float | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return ins.seasonality(df, exc_threshold(exceptional_threshold))


@router.get("/purpose-tree", response_model=list[schemas.TreeNode])
def purpose_tree(dataset_id: int | None = None, year: int | None = None, scope: str = "regular",
                 exceptional_threshold: float | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return ins.purpose_tree(df, _year(df, year), exc_threshold(exceptional_threshold), "all" if scope == "all" else "regular")


@router.get("/highlights", response_model=list[schemas.Highlight])
def highlights(dataset_id: int | None = None, year: int | None = None, compare_year: int | None = None,
               exceptional_threshold: float | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return ins.highlights(df, _year(df, year), exc_threshold(exceptional_threshold), compare_year)
