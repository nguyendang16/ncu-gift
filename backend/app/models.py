"""SQLite schema. Every derived table is keyed by dataset_id, so a re-upload
never overwrites earlier work. Donor names live in their own table, apart from
transactions, so analytics code never touches identifying text."""
import datetime as dt
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    mapping_json: Mapped[str] = mapped_column(Text, default="{}")        # canonical field -> source column
    mapped_fields: Mapped[str] = mapped_column(Text, default="[]")       # JSON list of canonical fields present
    extra_columns: Mapped[str] = mapped_column(Text, default="[]")       # JSON list of preserved extra columns


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    txn_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    donor_code: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    receipt_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    report_year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    amount_ntd: Mapped[float | None] = mapped_column(Float, nullable=True)   # null = not monetary / missing (never 0)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(20), nullable=True)      # one_time | recurring
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    project_raw: Mapped[str | None] = mapped_column(String(300), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)   # canonical catalogue name
    purpose_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    purpose_sub: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    college: Mapped[str | None] = mapped_column(String(80), nullable=True)
    class_conf: Mapped[float | None] = mapped_column(Float, nullable=True)
    donor_class: Mapped[str | None] = mapped_column(String(30), nullable=True)
    donor_class_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    grad_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dept: Mapped[str | None] = mapped_column(String(80), nullable=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    is_in_kind: Mapped[bool] = mapped_column(Boolean, default=False)
    in_kind_item: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extras: Mapped[str] = mapped_column(Text, default="{}")


class DonorName(Base):
    __tablename__ = "donor_names"
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), primary_key=True)
    donor_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    purpose_group: Mapped[str | None] = mapped_column(String(40), nullable=True)
    purpose_sub: Mapped[str | None] = mapped_column(String(80), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    college: Mapped[str | None] = mapped_column(String(80), nullable=True)
    year_first_seen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class ReviewItem(Base):
    """One item per distinct raw value, so resolving it updates every affected row."""
    __tablename__ = "review_queue"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))              # purpose | donor_class
    raw_value: Mapped[str] = mapped_column(String(300))
    proposed_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    resolved_label: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Brief(Base):
    __tablename__ = "briefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    facts_json: Mapped[str] = mapped_column(Text)
    draft_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiSettings(Base):
    """One row. Everything defaults to OFF: AI is opt-in, and each kind of sharing is a separate permission."""
    __tablename__ = "ai_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    share_project_names: Mapped[bool] = mapped_column(Boolean, default=False)
    share_column_headers: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiCall(Base):
    """Audit trail: what was sent, when, to which model, what it cost. Lets staff see exactly what left the machine."""
    __tablename__ = "ai_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    feature: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20))            # ok | error | blocked
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="")
    response_excerpt: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectRef(Base):
    """The staff's own project table (網站-芳名錄 name -> plan number, code, category, management-fee rate).
    Not tied to one dataset: it is reference knowledge, uploaded once and applied to any dataset."""
    __tablename__ = "project_refs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_key: Mapped[str] = mapped_column(String(300), index=True)
    name: Mapped[str] = mapped_column(String(300))
    serial: Mapped[str | None] = mapped_column(String(40), nullable=True)
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    category_raw: Mapped[str] = mapped_column(String(120))
    fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)


class AnnualProject(Base):
    """Which projects were that year's 年度專案 (the list changes every year)."""
    __tablename__ = "annual_projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    name_key: Mapped[str] = mapped_column(String(300), index=True)
    name: Mapped[str] = mapped_column(String(300))


class RefMeta(Base):
    __tablename__ = "ref_meta"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AiConversation(Base):
    """A saved chat with the analyst. Questions, answers and the cards under them stay on this machine, in this database."""
    __tablename__ = "ai_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AiMessage(Base):
    __tablename__ = "ai_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(12))                       # user | assistant
    text: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")      # assistant: steps, verification, demo
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
