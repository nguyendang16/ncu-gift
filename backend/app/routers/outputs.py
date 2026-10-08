import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import i18n, schemas
from ..i18n import t
from ..db import get_session
from ..models import Brief
from ..ai import features as ai_features
from ..services import briefs, roll
from ..services.frame import years_of
from .deps import exc_threshold, frame_for

router = APIRouter()


def _brief_out(b: Brief, years: list[int]) -> schemas.BriefOut:
    facts = json.loads(b.facts_json)
    return schemas.BriefOut(id=b.id, title=b.title, facts=facts, draft_text=b.draft_text, verification=briefs.verify_text(b.draft_text, facts, years),
                            source=facts.get("_source", "template"), ai_note=facts.get("_ai_note"))


@router.post("/briefs", response_model=schemas.BriefOut)
def create_brief(body: schemas.BriefIn, session: Session = Depends(get_session)):
    ds, df = frame_for(session, body.dataset_id)
    exc = exc_threshold(body.exceptional_threshold)
    if body.use_ai:
        facts, text, _v, note = ai_features.draft_brief(session, ds.id, df, project=body.project, exceptional=exc)
        facts["_source"], facts["_ai_note"] = ("template" if note else "ai"), note
    else:
        facts = briefs.build_facts(df, body.project, exc)
        text, facts["_source"] = briefs.draft_text(facts), "template"
    b = Brief(dataset_id=ds.id, title=t("brief.title", project=i18n.project_label(body.project)), facts_json=json.dumps(facts), draft_text=text)
    session.add(b)
    session.commit()
    return _brief_out(b, years_of(df))


@router.post("/briefs/{brief_id}/verify", response_model=schemas.BriefOut)
def verify_brief(brief_id: int, body: schemas.VerifyIn, session: Session = Depends(get_session)):
    b = session.get(Brief, brief_id)
    if b is None:
        raise HTTPException(404, t("err.brief_not_found"))
    _, df = frame_for(session, b.dataset_id)
    b.draft_text = body.text          # an edited draft is re-checked against the same locked facts
    session.commit()
    return _brief_out(b, years_of(df))


@router.get("/roll", response_model=schemas.RollOut)
def get_roll(dataset_id: int | None = None, year: int | None = None, session: Session = Depends(get_session)):
    ds, df = frame_for(session, dataset_id)
    return roll.build_roll(df, roll.names_for(session, ds.id), year or years_of(df)[-1])


@router.get("/roll/leak-test", response_model=schemas.LeakOut)
def leak(dataset_id: int | None = None, session: Session = Depends(get_session)):
    ds, df = frame_for(session, dataset_id)
    return roll.leak_test(df, roll.names_for(session, ds.id))
