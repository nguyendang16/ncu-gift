"""Saved conversations with the analyst: list, reopen, continue, delete. Stored locally, next to the data they are about."""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AiConversation, AiMessage


def _title(question: str) -> str:
    q = re.sub(r"\s+", " ", question).strip()
    return q if len(q) <= 60 else q[:57] + "…"


def history_for_model(session: Session, conversation_id: int, turns: int = 3) -> list[dict]:
    """The last few question/answer pairs, so a follow-up such as "and for 2024?" makes sense."""
    msgs = session.query(AiMessage).filter(AiMessage.conversation_id == conversation_id).order_by(AiMessage.id).all()
    out, q = [], None
    for m in msgs:
        if m.role == "user":
            q = m.text
        elif q is not None:
            out.append({"question": q, "answer": m.text})
            q = None
    return out[-turns:]


def save_turn(session: Session, conversation_id: int | None, dataset_id: int | None, question: str, result: dict) -> int:
    conv = session.get(AiConversation, conversation_id) if conversation_id else None
    if conv is None:
        conv = AiConversation(title=_title(question), dataset_id=dataset_id)
        session.add(conv)
        session.flush()
    now = datetime.utcnow()
    session.add(AiMessage(conversation_id=conv.id, role="user", text=question.strip(), created_at=now))
    payload = {"steps": result.get("steps", []), "verification": result.get("verification"), "demo": bool(result.get("demo"))}
    session.add(AiMessage(conversation_id=conv.id, role="assistant", text=result["answer"], payload_json=json.dumps(payload, ensure_ascii=False, default=str),
                          created_at=now))
    conv.updated_at = now
    session.commit()
    return conv.id


def list_conversations(session: Session, limit: int = 50) -> list[dict]:
    rows = session.query(AiConversation, func.count(AiMessage.id)).outerjoin(AiMessage, AiMessage.conversation_id == AiConversation.id) \
        .group_by(AiConversation.id).order_by(AiConversation.updated_at.desc()).limit(limit).all()
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat(), "n_messages": n} for c, n in rows]


def get_conversation(session: Session, conversation_id: int) -> dict | None:
    conv = session.get(AiConversation, conversation_id)
    if conv is None:
        return None
    msgs = []
    for m in session.query(AiMessage).filter(AiMessage.conversation_id == conv.id).order_by(AiMessage.id):
        p = json.loads(m.payload_json or "{}")
        for s in p.get("steps", []):
            s.setdefault("links", [])
        msgs.append({"id": m.id, "role": m.role, "text": m.text, "steps": p.get("steps", []), "verification": p.get("verification"),
                     "demo": bool(p.get("demo")), "created_at": m.created_at.isoformat()})
    return {"id": conv.id, "title": conv.title, "messages": msgs}


def delete_conversation(session: Session, conversation_id: int | None = None) -> int:
    """One conversation, or all of them when no id is given."""
    q = session.query(AiConversation)
    if conversation_id is not None:
        q = q.filter(AiConversation.id == conversation_id)
    ids = [c.id for c in q]
    if ids:
        session.query(AiMessage).filter(AiMessage.conversation_id.in_(ids)).delete(synchronize_session=False)
        session.query(AiConversation).filter(AiConversation.id.in_(ids)).delete(synchronize_session=False)
        session.commit()
    return len(ids)
