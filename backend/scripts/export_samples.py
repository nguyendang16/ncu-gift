"""Write two synthetic workbooks to sample_data/ for trying the upload flow.

mock_donations.xlsx          canonical headers, one sheet per year (like the staff export)
mock_donations_renamed.xlsx  one sheet; renamed + reordered columns (one in Chinese), the payment-method
                             column removed, and extra columns added -> exercises the mapper, the confirmation
                             step, extra-column passthrough and the "blocked analysis" message.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import SAMPLE_DIR          # noqa: E402
from app.mock.generate import generate_sheets  # noqa: E402

SAMPLE_DIR.mkdir(exist_ok=True)
sheets = generate_sheets()
with pd.ExcelWriter(SAMPLE_DIR / "mock_donations.xlsx") as w:
    for y, df in sheets.items():
        df.to_excel(w, sheet_name=y, index=False)

rng = np.random.default_rng(3)
big = pd.concat([df.assign(**{"Fiscal Year": int(y)}) for y, df in sheets.items()], ignore_index=True)
big = big.drop(columns=["Donation Method"])
big["Event Source"] = rng.choice(["Gala dinner", "Alumni reunion", "Online campaign", "Letter appeal", ""], len(big))
big = big.rename(columns={"Donation Mode": "Type", "Creation Date": "Gift Date", "Donor Code": "Donor ID",
                          "Donation Details": "Original Amount", "Actual Amount": "Amount (NT$)",
                          "Donation Project": "捐款項目", "Donor Category": "Constituency", "Anonymous": "Anon?",
                          "Solicited": "Was Solicited?"})
cols = list(big.columns)
rng.shuffle(cols)
big[cols].to_excel(SAMPLE_DIR / "mock_donations_renamed.xlsx", sheet_name="Donations", index=False)
print("wrote", [p.name for p in SAMPLE_DIR.glob("*.xlsx")])
