"""Bilingual guarantees: the two catalogues cannot drift apart, every key the code uses exists, and the same
request in either language returns the same numbers with different text."""
import math
import pathlib
import re

import pytest

from app import i18n, org
from app.ingest import FIELDS
from app.locales import en, zh_TW
from app.mock.generate import IN_KIND_ITEMS
from app.services.risk import FEATURES

ZH = {"Accept-Language": "zh-TW"}
EN = {"Accept-Language": "en"}
APP = pathlib.Path(__file__).resolve().parents[1] / "app"
PLACEHOLDER = re.compile(r"\{(\w+)")


def test_every_english_key_exists_in_chinese_except_singular_forms():
    missing = [k for k in en.M if k not in zh_TW.M and not k.endswith("_one")]
    assert missing == []


def test_chinese_only_keys_are_identifier_translations():
    extra = [k for k in zh_TW.M if k not in en.M and not k.startswith(i18n.IDENTIFIER_PREFIXES)]
    assert extra == []


def test_placeholders_match_between_languages():
    bad = {k: (PLACEHOLDER.findall(en.M[k]), PLACEHOLDER.findall(zh_TW.M[k]))
           for k in en.M if k in zh_TW.M and set(PLACEHOLDER.findall(en.M[k])) != set(PLACEHOLDER.findall(zh_TW.M[k]))}
    assert bad == {}


def test_every_key_used_in_code_exists():
    used = set()
    for f in APP.rglob("*.py"):
        if "locales" in f.parts:
            continue
        s = f.read_text()
        used |= set(re.findall(r'\bt\("([a-zA-Z0-9_.]+)"', s))
        used |= {m for m in re.findall(r'"((?:match|risk|roll|brief)\.[a-z_]+)"', s)}
    used |= {"match.gave_to_project_amt", "match.gave_to_target_amt"}
    used.discard("key")
    assert sorted(k for k in used if k not in en.M) == []


def test_dynamic_key_families_are_complete():
    expected = ([f"band.{i}" for i in range(6)] + [f"tier.{i}" for i in range(4)] + [f"field.{k}" for k in FIELDS]
                + [f"risk.feat.{f}" for f in FEATURES] + [f"group.{g}" for g in org.GROUP_KEYS]
                + [f"class.{c}" for c in org.DONOR_CLASSES + ["unknown"]] + [f"method.{m}" for m in org.METHOD_KEYS]
                + [f"cap.{i}" for i in ("overview", "trends", "methods", "bands", "classes", "purposes", "repeat",
                                         "risk", "matching", "scenario", "roll", "solicited")]
                + ["mock.donor", "mock.corp", "mock.foundation"])
    for cat in (en.M, zh_TW.M):
        assert [k for k in expected if k not in cat] == []


def test_every_domain_identifier_has_a_chinese_name():
    ids = ([f"purpose.{s}" for s in org.PURPOSE_SUBS] + [f"dept.{d}" for d, _, _ in org.DEPARTMENTS]
           + [f"college.{c}" for c in org.COLLEGES] + [f"project.{p['name']}" for p in org.CATALOGUE]
           + [f"item.{i}" for i in IN_KIND_ITEMS])
    assert [k for k in ids if k not in zh_TW.M] == []


def test_brief_template_has_no_hand_typed_digits_in_either_language():
    for cat in (en.M, zh_TW.M):
        static = re.sub(r"\{[^}]*\}", "", cat["brief.draft"])
        assert not re.search(r"\d", static)


def test_language_is_parsed_from_the_header():
    assert i18n.parse_accept_language("zh-TW,zh;q=0.9,en;q=0.8") == "zh-TW"
    assert i18n.parse_accept_language("zh-Hant") == "zh-TW"
    assert i18n.parse_accept_language("en-US,en;q=0.9") == "en"
    assert i18n.parse_accept_language("vi") == "en"          # unsupported -> default
    assert i18n.parse_accept_language(None) == "en"


@pytest.mark.parametrize("path", ["/api/overview", "/api/journey", "/api/risk", "/api/capability", "/api/roll", "/api/meta"])
def test_endpoints_answer_in_the_requested_language(client, mock_id, path):
    en_r = client.get(path, params={"dataset_id": mock_id}, headers=EN)
    zh_r = client.get(path, params={"dataset_id": mock_id}, headers=ZH)
    assert en_r.status_code == zh_r.status_code == 200
    assert en_r.text != zh_r.text
    assert re.search(r"[一-鿿]", zh_r.text)
    assert not re.search(r"[一-鿿]", en_r.text)


def test_numbers_are_identical_in_both_languages(client, mock_id):
    a = client.get("/api/overview", params={"dataset_id": mock_id, "year": 2025}, headers=EN).json()
    b = client.get("/api/overview", params={"dataset_id": mock_id, "year": 2025}, headers=ZH).json()
    assert a["kpis"] == b["kpis"] and a["monthly"] == b["monthly"]
    assert [x["amount"] for x in a["bands"]] == [x["amount"] for x in b["bands"]]
    assert [x["label"] for x in b["bands"]][0] == "1萬(含)以下"          # the staff's own band wording
    assert [x["label"] for x in b["donor_classes"]][:2] == ["校友", "中大之友"]


def test_missing_information_messages_are_translated(client):
    csv = "Creation Date,Actual Amount,Donation Project,Anonymous\n2025-01-05,1000,Campaign: Tree Adoption,No\n"
    r = client.post("/api/upload/preview", files={"file": ("n.csv", csv.encode(), "text/csv")}, headers=ZH).json()
    assert "共 1 列" in r["row_note"]
    mapping = {c["proposed_field"]: c["name"] for c in r["columns"] if c["proposed_field"]}
    out = client.post("/api/upload/confirm", json={"upload_id": r["upload_id"], "name": "n", "mapping": mapping}, headers=ZH).json()
    repeat = next(c for c in out["capability"] if c["id"] == "repeat")
    assert repeat["status"] == "blocked" and "跨年度辨識同一位捐款人" in repeat["reason"]
    j = client.get("/api/journey", params={"dataset_id": out["dataset_id"]}, headers=ZH)
    assert j.status_code == 409 and "僅涵蓋一個年度" in j.json()["detail"]


def test_chinese_brief_is_verified_and_tampering_is_caught(client, mock_id):
    b = client.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship"}, headers=ZH).json()
    assert "物理學系：獎學金" in b["draft_text"] and b["verification"]["verified"]
    assert b["title"].startswith("募款簡報：")
    bad = b["draft_text"].replace("去年共有", "去年共有 777")
    v = client.post(f"/api/briefs/{b['id']}/verify", json={"text": bad}, headers=ZH).json()["verification"]
    assert not v["verified"] and "777" in v["mismatches"]


def test_chinese_roll_masks_anonymous_donors_as_the_staff_do(client, mock_id):
    leak = client.get("/api/roll/leak-test", params={"dataset_id": mock_id}, headers=ZH).json()
    assert leak["passed"] and leak["anonymous_rows"] > 0
    roll = client.get("/api/roll", params={"dataset_id": mock_id}, headers=ZH).json()
    assert roll["stats"]["friends_label"] == "中大之友" and roll["title"] == "捐款芳名錄"
    assert any(e["name"].startswith("模擬捐款人") for s in roll["sections"] for p in s["projects"] for e in p["entries"])
    assert not re.search(r"\bD\d{4}\b", str(roll))


def test_review_labels_are_identifiers_with_translated_text(client, mock_id):
    items = client.get("/api/review", params={"dataset_id": mock_id}, headers=ZH).json()
    assert items and all("proposed_text" in i and "resolved_text" in i for i in items)
    meta = client.get("/api/meta", headers=ZH).json()
    assert {"value": "Student clubs", "label": "學生社團"} in meta["purpose_labels"]
    assert {"value": "alumni", "label": "校友"} in meta["donor_classes"]


def test_matching_targets_keep_english_ids_but_translate_labels(client, mock_id):
    t = client.get("/api/matching/targets", params={"dataset_id": mock_id}, headers=ZH).json()
    sub = next(x for x in t if x["id"] == "sub:Departmental scholarships")
    assert sub["label"] == "院系獎助學金" and sub["kind"] == "purpose"
    r = client.get("/api/matching/rank", params={"dataset_id": mock_id, "target": "unit:Civil Engineering"}, headers=ZH).json()
    assert r["label"] == "土木工程學系" and any(re.search(r"[一-鿿]", e) for c in r["candidates"] for e in c["evidence"])
    assert all(c["donor_class_label"] for c in r["candidates"])


def test_scenario_text_is_translated_but_not_the_numbers(client, mock_id):
    a = client.post("/api/scenario", json={"dataset_id": mock_id}, headers=EN).json()
    b = client.post("/api/scenario", json={"dataset_id": mock_id}, headers=ZH).json()
    assert b["label"] == "敏感度分析，並非預測" and a["label"] != b["label"]
    assert math.isclose(a["baseline"]["expected"], b["baseline"]["expected"])
    assert a["assumptions"] != b["assumptions"]


def test_solicited_view_works_and_translates_its_tiers(client, mock_id):
    """Regression: a loop variable once shadowed the translate function and made this endpoint return 500."""
    a = client.get("/api/extras/solicited", params={"dataset_id": mock_id}, headers=EN)
    b = client.get("/api/extras/solicited", params={"dataset_id": mock_id}, headers=ZH)
    assert a.status_code == b.status_code == 200
    assert [x["tier"] for x in a.json()["tiers"]][0] == "Below NT$500k"
    assert [x["tier"] for x in b.json()["tiers"]][0] == "50萬以下"
    assert [x["solicited_amount"] for x in a.json()["tiers"]] == [x["solicited_amount"] for x in b.json()["tiers"]]
