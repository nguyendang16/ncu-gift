"""Central configuration and analysis defaults.

Every default below is a *parameter*, not a rule: staff asked for adjustable
periods, bands and thresholds, so the API accepts overrides for all of them.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("NCU_GIFT_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = Path(os.environ.get("NCU_GIFT_DB", DATA_DIR / "ncu_gift.db"))
SAMPLE_DIR = ROOT / "sample_data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Defaults pending confirmation by staff (meeting notes 4.3).
DEFAULT_EXCEPTIONAL_THRESHOLD = 10_000_000   # staff deck excludes gifts >= NT$10m
DEFAULT_LARGE_THRESHOLD = 100_000            # "large donation" in the requirements sheet
RISK_VALUE_CAP = 20_000_000                  # cap used only when ranking by value at risk

# Gift-size bands from the requirements sheet. Non-overlapping: (lo, hi], except that the last band starts AT lo (>= 1M).
BANDS = [
    ("NT$10k or less", None, 10_000),
    ("10k - 50k", 10_000, 50_000),
    ("50k - 100k", 50_000, 100_000),
    ("100k - 500k", 100_000, 500_000),
    ("500k - 1M", 500_000, 1_000_000),
    ("NT$1M or more", 1_000_000, None),
]
