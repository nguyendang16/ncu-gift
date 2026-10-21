"""The richer charts rest on these analyses, so their invariants are tested: the waterfall adds up exactly,
shares are monotone and bounded, the treemap equals the totals, and highlights exist in both languages."""
import math
import re

ZH = {"Accept-Language": "zh-TW"}


def test_bridge_adds_up_exactly(client, mock_id):
    for year in (2024, 2025):
        b = client.get("/api/bridge", params={"dataset_id": mock_id, "year": year}).json()
        assert math.isclose(b["start"] + sum(s["value"] for s in b["steps"]), b["end"], abs_tol=1e-6)
        assert {s["key"] for s in b["steps"]} == {"lapsed", "retained", "new", "returning", "exceptional"}
        lapsed = next(s for s in b["steps"] if s["key"] == "lapsed")
        assert lapsed["value"] <= 0 and lapsed["donors"] > 0


def test_ordinary_only_bridge_also_adds_up(client, mock_id):
    b = client.get("/api/bridge", params={"dataset_id": mock_id, "year": 2025}).json()
    ordinary_steps = sum(s["value"] for s in b["steps"] if s["key"] != "exceptional")
    assert math.isclose(b["start_ordinary"] + ordinary_steps, b["end_ordinary"], abs_tol=1e-6)
    assert math.isclose(b["start_ordinary"] + b["exceptional_start"], b["start"], abs_tol=1e-6)
    assert math.isclose(b["end_ordinary"] + b["exceptional_end"], b["end"], abs_tol=1e-6)


def test_bridge_start_and_end_are_the_published_totals(client, mock_id):
    t = {r["year"]: r for r in client.get("/api/trend", params={"dataset_id": mock_id}).json()}
    b = client.get("/api/bridge", params={"dataset_id": mock_id, "year": 2025}).json()
    assert math.isclose(b["start"], t[2024]["total"], rel_tol=1e-9) and math.isclose(b["end"], t[2025]["total"], rel_tol=1e-9)


def test_bridge_needs_an_earlier_year(client, mock_id):
    r = client.get("/api/bridge", params={"dataset_id": mock_id, "year": 2023})
    assert r.status_code == 409 and r.json()["code"] == "insufficient_data"


def test_concentration_curve_is_monotone_and_bounded(client, mock_id):
    c = client.get("/api/concentration", params={"dataset_id": mock_id, "year": 2025}).json()
    for key in ("all", "ordinary"):
        v = [p[key] for p in c["curve"]]
        assert v == sorted(v) and v[0] == 0 and math.isclose(v[-1], 1.0)
    # a few exceptional gifts make the whole far more concentrated than ordinary giving alone
    assert c["all"]["top1pct_share"] > c["ordinary"]["top1pct_share"]
    assert c["all"]["gini"] > c["ordinary"]["gini"]


def test_seasonality_covers_every_year_and_month(client, mock_id):
    s = client.get("/api/seasonality", params={"dataset_id": mock_id}).json()
    assert len(s["cells"]) == len(s["years"]) * 12 and all(c["value"] >= 0 for c in s["cells"])


def test_purpose_tree_adds_up_to_the_ordinary_total(client, mock_id):
    tree = client.get("/api/purpose-tree", params={"dataset_id": mock_id, "year": 2025}).json()
    ov = client.get("/api/overview", params={"dataset_id": mock_id, "year": 2025}).json()
    assert math.isclose(sum(n["value"] for n in tree), ov["kpis"]["regular_total"], rel_tol=1e-9)

    def names(nodes):
        found = []
        for node in nodes:
            kids = node.get("children") or []
            if kids:
                assert math.isclose(sum(c["value"] for c in kids), node["value"], rel_tol=1e-9)
                found.extend(names(kids))
            else:
                found.append(node["name"])
        return found
    listed = names(tree)
    assert "Other" not in listed and len(listed) == len(set(listed))


def test_highlights_are_translated_and_link_somewhere(client, mock_id):
    en = client.get("/api/highlights", params={"dataset_id": mock_id, "year": 2025}).json()
    zh = client.get("/api/highlights", params={"dataset_id": mock_id, "year": 2025}, headers=ZH).json()
    assert len(en) >= 4 and [h["id"] for h in en] == [h["id"] for h in zh]
    assert all(h["link"].startswith("/") and h["tone"] in {"info", "good", "warn"} for h in en)
    assert all(re.search(r"[一-鿿]", h["title"]) for h in zh)
    # the numbers in the cards are the same in both languages
    num = lambda s: re.findall(r"\d+(?:\.\d+)?%", s)
    assert [num(h["text"]) for h in en] == [num(h["text"]) for h in zh]


def test_risk_points_and_match_components_feed_the_charts(client, mock_id):
    r = client.get("/api/risk", params={"dataset_id": mock_id}).json()
    assert 50 < len(r["points"]) <= 300 and all(0 <= p["p_lapse"] <= 1 for p in r["points"])
    m = client.get("/api/matching/rank", params={"dataset_id": mock_id, "target": "unit:Physics"}).json()
    for c in m["candidates"]:
        assert math.isclose(sum(c["components"].values()), c["score"], rel_tol=1e-6)
