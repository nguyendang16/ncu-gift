from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, schemas
from ..db import get_session
from ..services import matching, risk, scenario as scn
from .deps import exc_threshold, frame_for

router = APIRouter()


@router.get("/risk", response_model=schemas.RiskOut)
def risk_list(dataset_id: int | None = None, top_n: int = 50, cap: float = config.RISK_VALUE_CAP,
              session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return risk.risk_report(df, cap=cap, top_n=min(max(top_n, 5), 200))


@router.get("/matching/targets", response_model=list[schemas.Target])
def targets(dataset_id: int | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return matching.list_targets(df)


@router.get("/matching/rank", response_model=schemas.RankOut)
def rank(target: str, dataset_id: int | None = None, n: int = 25, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    try:
        return matching.rank(df, target, min(max(n, 5), 100))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/matching/eval", response_model=schemas.EvalOut)
def evaluate(dataset_id: int | None = None, session: Session = Depends(get_session)):
    _, df = frame_for(session, dataset_id)
    return matching.evaluate(df)


@router.post("/scenario", response_model=schemas.ScenarioOut)
def scenario(body: schemas.ScenarioIn, session: Session = Depends(get_session)):
    _, df = frame_for(session, body.dataset_id)
    return scn.scenario(df, exc_threshold(body.exceptional_threshold), body.r1_uplift_pp, body.r2_uplift_pp,
                        body.new_donor_multiplier, body.recurring_conversion_pct, body.major_gift_ntd)
