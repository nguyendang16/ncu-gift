import os
import tempfile
from pathlib import Path

# Isolated database and upload folder, set before the app is imported.
_TMP = tempfile.mkdtemp(prefix="ncu_gift_test_")
os.environ["NCU_GIFT_DATA_DIR"] = _TMP
os.environ["NCU_GIFT_DB"] = str(Path(_TMP) / "test.db")
os.environ["NCU_GIFT_NO_DOTENV"] = "1"          # never read backend/.env in tests
for _k in ("OPENAI_API_KEY", "NCU_GIFT_AI_DEMO", "NCU_GIFT_LLM_MODEL", "NCU_GIFT_LLM_REASONING", "NCU_GIFT_AI_DAILY_CAP"):
    os.environ.pop(_k, None)

import pytest                                    # noqa: E402
from fastapi.testclient import TestClient        # noqa: E402

from app.main import app                         # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def mock_id(client):
    return client.get("/api/datasets").json()[0]["id"]


def upload_csv(client, csv_text: str, name: str = "t.csv") -> dict:
    r = client.post("/api/upload/preview", files={"file": (name, csv_text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    p = r.json()
    mapping = {c["proposed_field"]: c["name"] for c in p["columns"] if c["proposed_field"]}
    r = client.post("/api/upload/confirm", json={"upload_id": p["upload_id"], "name": name, "mapping": mapping})
    assert r.status_code == 200, r.text
    return r.json()
