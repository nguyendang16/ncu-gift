"""Load a dataset into a DataFrame. All analytics work from this one function."""
from __future__ import annotations

import math

import pandas as pd
from sqlalchemy.orm import Session

from ..models import Transaction


class InsufficientData(Exception):
    """Raised when an analysis lacks required information. The message is shown to the user."""


def load_df(session: Session, dataset_id: int) -> pd.DataFrame:
    q = session.query(Transaction).filter(Transaction.dataset_id == dataset_id)
    df = pd.read_sql(q.statement, session.connection())
    df["year"] = df["report_year"]
    df["date"] = pd.to_datetime(df["date"])
    df["anonymous"] = df["anonymous"].astype(bool)
    df["is_in_kind"] = df["is_in_kind"].astype(bool)
    return df


def years_of(df: pd.DataFrame) -> list[int]:
    return sorted(int(y) for y in df["year"].dropna().unique())


def active_sets(df: pd.DataFrame) -> dict[int, set]:
    d = df.dropna(subset=["donor_code", "year"])
    return {int(y): set(g["donor_code"]) for y, g in d.groupby("year")}


def cash(df: pd.DataFrame) -> pd.DataFrame:
    """Monetary rows only. Missing amounts are excluded, never treated as zero."""
    return df[(~df["is_in_kind"]) & df["amount_ntd"].notna()]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def pct_change(new: float, old: float) -> float | None:
    return None if not old else (new - old) / old * 100.0
