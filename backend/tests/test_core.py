import math
import re

import pandas as pd

from app.config import SAMPLE_DIR
from app.mock.generate import generate_sheets
from app.services import briefs
from .conftest import upload_csv


def _truth():
    s = generate_sheets()
    return {y: pd.to_numeric(df["Actual Amount"], errors="coerce") for y, df in s.items()}


def test_totals_match_the_source_sheets(client, mock_id):
    truth = _truth()
    for row in client.get("/api/trend", params={"dataset_id": mock_id}).json():
        assert math.isclose(row["total"], truth[str(row["year"])].sum(), rel_tol=1e-9)
        assert math.isclose(row["total"], row["regular"] + row["exceptional"], rel_tol=1e-9)


def test_in_kind_is_missing_not_zero(client, mock_id):
    o = client.get("/api/overview", params={"dataset_id": mock_id}).json()
    assert o["kpis"]["in_kind_records"] == 12
    in_kind = [m for m in o["methods"] if m["label"] == "In-kind"][0]
    assert in_kind["amount"] is None and in_kind["count"] == 12      # N/A, never 0


def test_bands_cover_every_gift_exactly_once(client, mock_id):
    o = client.get("/api/overview", params={"dataset_id": mock_id}).json()
    assert math.isclose(sum(b["amount"] for b in o["bands"]), o["kpis"]["total"], rel_tol=1e-9)
    assert sum(b["count"] for b in o["bands"]) == o["kpis"]["records"] - o["kpis"]["in_kind_records"]


def test_scope_regular_excludes_exceptional_gifts(client, mock_id):
    a = client.get("/api/overview", params={"dataset_id": mock_id, "year": 2025, "scope": "all"}).json()
    r = client.get("/api/overview", params={"dataset_id": mock_id, "year": 2025, "scope": "regular"}).json()
    assert math.isclose(sum(b["amount"] for b in r["bands"]), a["kpis"]["regular_total"], rel_tol=1e-9)
    assert sum(b["amount"] for b in a["bands"]) > sum(b["amount"] for b in r["bands"])


def test_exceptional_threshold_is_a_parameter(client, mock_id):
    lo = client.get("/api/trend", params={"dataset_id": mock_id, "exceptional_threshold": 1_000_000}).json()
    hi = client.get("/api/trend", params={"dataset_id": mock_id, "exceptional_threshold": 100_000_000}).json()
    assert lo[-1]["n_exceptional"] > hi[-1]["n_exceptional"]


def test_ordinary_giving_and_totals_move_differently(client, mock_id):
    t = client.get("/api/trend", params={"dataset_id": mock_id}).json()
    assert t[1]["total_yoy_pct"] > 100 and t[2]["total_yoy_pct"] < 0           # headline swings
    assert t[1]["regular_yoy_pct"] > 0 and t[2]["regular_yoy_pct"] > 0         # ordinary giving does not


def test_journey_states_add_up(client, mock_id):
    j = client.get("/api/journey", params={"dataset_id": mock_id}).json()
    for y in j["years"]:
        if y["history_available"]:
            assert y["new"] + y["retained"] + y["reactivated"] == y["active"]
    f = j["funnel"][0]
    assert 0 <= f["first_time"]["rate"] < f["repeat"]["rate"] <= 1


def test_risk_backtest_is_out_of_sample_and_better_than_chance(client, mock_id):
    r = client.get("/api/risk", params={"dataset_id": mock_id}).json()
    m = r["metrics"]
    assert m["train"] == "2023→2024" and m["test"] == "2024→2025"
    assert m["auc_ci_low"] < m["auc"] < m["auc_ci_high"] and m["auc_ci_low"] > 0.5
    assert all(d["capped"] for d in r["donors"] if d["giving_last_year"] > 20_000_000)
    assert r["donors"] == sorted(r["donors"], key=lambda d: -d["value_at_risk"])


def test_matching_is_ranked_and_beats_random(client, mock_id):
    rk = client.get("/api/matching/rank", params={"dataset_id": mock_id, "target": "unit:Civil Engineering"}).json()
    scores = [c["score"] for c in rk["candidates"]]
    assert scores == sorted(scores, reverse=True) and all(c["evidence"] for c in rk["candidates"])
    ev = client.get("/api/matching/eval", params={"dataset_id": mock_id}).json()
    assert ev["holdout_year"] == 2025 and ev["history_through"] == 2024
    assert all(k["model"] > k["random"] for k in ev["by_k"])


def test_scenario_is_neutral_when_nothing_changes_and_ignores_exceptional_gifts(client, mock_id):
    base = client.post("/api/scenario", json={"dataset_id": mock_id}).json()
    assert math.isclose(base["scenario"]["delta_vs_baseline"], 0.0, abs_tol=1e-6)
    up = client.post("/api/scenario", json={"dataset_id": mock_id, "r1_uplift_pp": 10}).json()
    assert up["scenario"]["expected"] > base["scenario"]["expected"]
    gift = client.post("/api/scenario", json={"dataset_id": mock_id, "major_gift_ntd": 50_000_000}).json()
    assert math.isclose(gift["scenario"]["expected"], base["scenario"]["expected"], rel_tol=1e-9)
    assert gift["exceptional_line"]["total_if_gift_arrives"] > gift["scenario"]["expected"]
    assert "not a forecast" in base["label"].lower()


def test_brief_numbers_are_verified_and_tampering_is_caught(client, mock_id):
    b = client.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship"}).json()
    assert b["verification"]["verified"] and b["verification"]["numbers_checked"] > 5
    edited = b["draft_text"].replace("Last year", "Last year 777")
    v = client.post(f"/api/briefs/{b['id']}/verify", json={"text": edited}).json()["verification"]
    assert not v["verified"] and "777" in v["mismatches"]


def test_template_has_no_hand_typed_digits():
    facts = {"project": "P", "category": "Cat", "category_last_year": {"donors": 1, "median_gift": 1.0},
             "options": {"low": 1, "mid": 2, "high": 3}, "top_channel": {"name": "X", "pct": 1},
             "top_class": {"name": "Y", "pct": 1}, "alumni_share_top100_pct": 1, "lapsed_supporters": 1}
    text = briefs.draft_text(facts)
    static = re.sub(r"NT\$[\d,]+|\d+%?|\b\d+\b", "", text)
    assert not re.search(r"\d", static)


def test_donor_roll_never_leaks_anonymous_identities(client, mock_id):
    leak = client.get("/api/roll/leak-test", params={"dataset_id": mock_id}).json()
    assert leak["passed"] and leak["anonymous_rows"] > 0 and leak["anonymous_rows_unmasked"] == 0
    roll = client.get("/api/roll", params={"dataset_id": mock_id}).json()
    assert roll["stats"]["masked_entries"] > 0
    assert not re.search(r"\bD\d{4}\b", str(roll))                   # donor codes never appear in the roll


def test_renamed_workbook_gives_identical_results_and_blocks_missing_method(client, mock_id):
    base = client.get("/api/overview", params={"dataset_id": mock_id}).json()["kpis"]["total"]
    with open(SAMPLE_DIR / "mock_donations_renamed.xlsx", "rb") as f:
        p = client.post("/api/upload/preview", files={"file": ("r.xlsx", f, "application/octet-stream")}).json()
    got = {c["proposed_field"]: c["name"] for c in p["columns"] if c["proposed_field"]}
    assert got["project"] == "捐款項目" and got["amount"] == "Amount (NT$)" and "method" not in got
    out = client.post("/api/upload/confirm", json={"upload_id": p["upload_id"], "name": "renamed", "mapping": got}).json()
    assert math.isclose(client.get("/api/overview", params={"dataset_id": out["dataset_id"]}).json()["kpis"]["total"], base, rel_tol=1e-9)
    blocked = {c["id"]: c for c in out["capability"]}
    assert blocked["methods"]["status"] == "blocked" and "Donation method" in blocked["methods"]["reason"]
    assert client.get("/api/overview", params={"dataset_id": out["dataset_id"]}).json()["methods"] == []   # no invented "unknown" row


def test_no_donor_id_blocks_repeat_analysis_with_the_staff_wording(client):
    csv = "Creation Date,Actual Amount,Donation Project,Anonymous\n2025-01-05,1000,Campaign: Tree Adoption,No\n2025-02-05,,Campaign: Tree Adoption,No\n"
    out = upload_csv(client, csv)
    cap = {c["id"]: c for c in out["capability"]}
    assert cap["repeat"]["status"] == "blocked"
    assert "does not include information that identifies the same donor across years" in cap["repeat"]["reason"]
    o = client.get("/api/overview", params={"dataset_id": out["dataset_id"], "year": 2025}).json()
    assert o["kpis"]["total"] == 1000.0 and o["kpis"]["records"] == 2   # blank amount stays blank, not zero


def test_single_year_data_reports_missing_information_instead_of_guessing(client):
    csv = "Donor Code,Creation Date,Actual Amount,Donation Project,Anonymous\nA,2025-01-05,1000,Campaign: Tree Adoption,No\nB,2025-03-05,500,Campaign: Tree Adoption,No\n"
    out = upload_csv(client, csv)
    r = client.get("/api/journey", params={"dataset_id": out["dataset_id"]})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_data"
    assert "at least two years" in r.json()["detail"]


def test_review_queue_resolution_updates_every_affected_row(client, mock_id):
    items = client.get("/api/review", params={"dataset_id": mock_id, "status": "pending"}).json()
    item = next(i for i in items if i["kind"] == "purpose")
    r = client.post(f"/api/review/{item['id']}/resolve", json={"label": "Student clubs"}).json()
    assert r["status"] == "resolved"
    assert client.post(f"/api/review/{item['id']}/resolve", json={"label": "nonsense"}).status_code == 400
