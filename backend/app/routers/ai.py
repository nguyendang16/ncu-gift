"""AI endpoints. Off until a person turns them on; every call is logged with exactly what was sent."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, schemas
from ..ai import chats, features
from ..ai.agent import run_agent
from ..ai.config import get_config
from ..db import get_session
from ..i18n import t
from ..models import AiCall, Upload
from .data import _read
from .deps import exc_threshold, frame_for

router = APIRouter(prefix="/ai")


def _large(v: float | None) -> float:
    return v if v is not None else config.DEFAULT_LARGE_THRESHOLD


@router.get("/version")
def version():
    """What this running server can do. The interface checks it and says so when the server was started before an update."""
    return {"features": ["agent_links", "conversations", "plan_to_raise", "find_feature", "insight_actions"]}


@router.get("/status", response_model=schemas.AiStatus)
def status(session: Session = Depends(get_session)):
    cfg, s = get_config(), features.effective_settings(session)
    n, cost = features.usage_today(session)
    return schemas.AiStatus(configured=cfg.configured, demo=cfg.demo, model="demo" if cfg.demo else cfg.model, reasoning_effort=cfg.reasoning_effort,
                            enabled=s.enabled, share_project_names=s.share_project_names, share_column_headers=s.share_column_headers,
                            ready=s.enabled and (cfg.configured or cfg.demo), daily_cap=cfg.daily_cap, calls_today=n, cost_today_usd=round(cost, 4))


@router.put("/settings", response_model=schemas.AiStatus)
def update_settings(body: schemas.AiSettingsIn, session: Session = Depends(get_session)):
    s = features.get_settings(session)
    s.enabled, s.share_project_names, s.share_column_headers = body.enabled, body.share_project_names, body.share_column_headers
    session.commit()
    return status(session)


@router.post("/test", response_model=schemas.AiTestOut)
def test(session: Session = Depends(get_session)):
    return features.connection_test(session)


@router.post("/ask", response_model=schemas.AskOut)
def ask(body: schemas.AskIn, session: Session = Depends(get_session)):
    if not body.question.strip():
        raise HTTPException(400, t("ai.err.empty"))
    ds, df = frame_for(session, body.dataset_id)
    return features.ask(session, ds.id, df, question=body.question, history=[h.model_dump() for h in body.history], year=body.year,
                        exceptional=exc_threshold(body.exceptional_threshold), large=_large(body.large_threshold))


@router.post("/agent", response_model=schemas.AgentOut)
def agent(body: schemas.AskIn, session: Session = Depends(get_session)):
    if not body.question.strip():
        raise HTTPException(400, t("ai.err.empty"))
    ds, df = frame_for(session, body.dataset_id)
    history = chats.history_for_model(session, body.conversation_id) if body.conversation_id else [h.model_dump() for h in body.history]
    result = run_agent(session, ds.id, df, question=body.question, history=history,
                       exceptional=exc_threshold(body.exceptional_threshold), large=_large(body.large_threshold))
    result["conversation_id"] = chats.save_turn(session, body.conversation_id, ds.id, body.question, result)
    return result


@router.get("/conversations", response_model=list[schemas.ConversationRow])
def conversations(limit: int = 50, session: Session = Depends(get_session)):
    return chats.list_conversations(session, min(max(limit, 1), 200))


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationOut)
def conversation(conversation_id: int, session: Session = Depends(get_session)):
    c = chats.get_conversation(session, conversation_id)
    if c is None:
        raise HTTPException(404, "Not found")
    return c


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, session: Session = Depends(get_session)):
    return {"deleted": chats.delete_conversation(session, conversation_id)}


@router.delete("/conversations")
def delete_all_conversations(session: Session = Depends(get_session)):
    return {"deleted": chats.delete_conversation(session, None)}


@router.post("/insights", response_model=schemas.InsightsOut)
def insights(body: schemas.InsightsIn, session: Session = Depends(get_session)):
    ds, df = frame_for(session, body.dataset_id)
    return features.insights(session, ds.id, df, year=body.year, exceptional=exc_threshold(body.exceptional_threshold), large=_large(body.large_threshold))


@router.post("/map-columns", response_model=schemas.MapOut)
def map_columns(body: schemas.MapIn, session: Session = Depends(get_session)):
    up = session.get(Upload, body.upload_id)
    if up is None:
        raise HTTPException(404, t("err.upload_not_found"))
    return features.suggest_mapping(session, _read(Path(up.path), up.filename))


@router.post("/classify", response_model=schemas.ClassifyOut)
def classify(body: schemas.ClassifyIn, session: Session = Depends(get_session)):
    ds, _ = frame_for(session, body.dataset_id)
    return features.suggest_classification(session, ds.id, body.item_ids)


def _row(c: AiCall) -> dict:
    return dict(id=c.id, ts=c.ts.isoformat(), feature=c.feature, model=c.model, status=c.status, demo=c.demo, duration_ms=c.duration_ms,
                prompt_tokens=c.prompt_tokens, completion_tokens=c.completion_tokens, cost_usd=round(c.cost_usd, 6), verified=c.verified, error=c.error)


@router.get("/log", response_model=list[schemas.AiCallRow])
def log(limit: int = 50, session: Session = Depends(get_session)):
    return [_row(c) for c in session.query(AiCall).order_by(AiCall.id.desc()).limit(min(max(limit, 1), 200))]


@router.get("/log/{call_id}", response_model=schemas.AiCallDetail)
def log_detail(call_id: int, session: Session = Depends(get_session)):
    c = session.get(AiCall, call_id)
    if c is None:
        raise HTTPException(404, "Not found")
    return {**_row(c), "payload_json": c.payload_json, "response_excerpt": c.response_excerpt}
