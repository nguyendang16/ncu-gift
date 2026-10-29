from sqlalchemy.orm import Session

from .db import Base, engine
from .ingest import auto_mapping, ingest
from .mock.generate import generate_sheets
from .models import Dataset

MOCK_NAME = "Mock data 2023-2025 (synthetic)"


# columns added after a table first shipped: (table, column, SQL type and default). create_all never alters an existing table.
_NEW_COLUMNS = [("ai_messages", "feedback", "INTEGER NOT NULL DEFAULT 0")]


def init_db() -> None:
    Base.metadata.create_all(engine)
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in _NEW_COLUMNS:
            if table in insp.get_table_names() and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def seed_if_empty(session: Session) -> None:
    if session.query(Dataset).count():
        return
    sheets = generate_sheets()
    ingest(session, sheets, auto_mapping(sheets), MOCK_NAME, is_mock=True)
