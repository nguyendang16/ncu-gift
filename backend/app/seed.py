from sqlalchemy.orm import Session

from .db import Base, engine
from .ingest import auto_mapping, ingest
from .mock.generate import generate_sheets
from .models import Dataset

MOCK_NAME = "Mock data 2023-2025 (synthetic)"


def init_db() -> None:
    Base.metadata.create_all(engine)


def seed_if_empty(session: Session) -> None:
    if session.query(Dataset).count():
        return
    sheets = generate_sheets()
    ingest(session, sheets, auto_mapping(sheets), MOCK_NAME, is_mock=True)
