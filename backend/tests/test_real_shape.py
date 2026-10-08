"""The real ledger arrives as a workbook with one sheet per year, Chinese headers, pseudonymised names instead of donor IDs,
extra non-ledger sheets, and a separate project table kept by the staff. These tests build a synthetic workbook of that
shape (no real data in the repo) and check that the system copes with it."""
import io

import pandas as pd
import pytest

from app import reference as ref_mod
from app.db import SessionLocal
from app.models import AnnualProject, ProjectRef, RefMeta

COLS = ["ID", "模式", "成立日期", "姓名", "幣別", "捐款內容", "真實金額", "捐助項目", "身份", "匿名", "捐助方式"]


def row(i, who, date, amount, project, cls="校友", method="電匯(國內外)", mode="單次捐款", anon="否"):
    return [i, mode, date, who, "台幣", amount, amount, project, cls, anon, method]


def ledger_book() -> bytes:
    y23 = [row(1, "USER_1", "2023-03-01", 5000, "安心就學支持計畫"), row(2, "USER_2", "2023-04-01", 800000, "校務基金"),
           row(3, "USER_3", "2023-05-01", 20000, "電機系：新實驗室設備", method="WebATM")]
    y24 = [row(4, "USER_1", "2024-03-01", 6000, "安心就學支持計畫"), row(5, "USER_3", "2024-06-01", 1000000, "校務基金", cls="中大之友"),
           row(6, "USER_9", "2024-07-01", 30000, "學務處：新生獎學金"), row(7, "USER_4", "2024-08-01", 500, "樹木認養", method="線上刷卡")]
    y25 = [row(8, "USER_1", "2025-03-01", 7000, "安心就學支持計畫"), row(9, "USER_5", "2025-04-01", 50000, "電機系：新實驗室設備", anon="是"),
           row(10, "USER_6", "2025-05-01", 9000, "某個沒有登記的專案"), row(11, "USER_2", "2025-06-01", 1000000, "校務基金", cls="中大之友")]
    out = io.BytesIO()
    with pd.ExcelWriter(out) as w:
        for name, rows in (("2025", y25), ("2024", y24), ("2023", y23)):
            pd.DataFrame(rows, columns=COLS).to_excel(w, sheet_name=name, index=False)
        pd.DataFrame({"國立中央大學捐款芳名錄": ["(2026年)", "現金捐款"], "Unnamed: 1": [1, 2]}).to_excel(w, sheet_name="芳名錄_成品", index=False)
        pd.DataFrame({"項目": ["捐款總收入"], "筆數": [None], "備註說明": ["要自動生成圖表"]}).to_excel(w, sheet_name="需求", index=False)
    return out.getvalue()


def reference_book() -> bytes:
    table = pd.DataFrame({"網站-芳名錄": ["安心就學支持計畫", "校務基金", "電機系：新實驗室設備", "電機系：舊實驗室", "學務處：陳先生紀念獎學金", "學務處：校慶活動"],
                          "計畫流水號": [1, 2, 3, 4, 5, 6], "代號": ["P1", "A01", "C1", "C2", "B1", "B2"],
                          "分類": ["專案2025", "校務基金", "院系教學研究-資-電", "院系教學研究-資-電", "獎助學金(全校性)-學務處", "行政單位-學務處"],
                          "提撥管理費": [0, 1, 0.1, 0.1, 0, 0.1]})
    annual = pd.DataFrame({"2025年專案": ["安心就學支持計畫", "校務基金"], "2024年專案": ["安心就學支持計畫", "樹木認養"], "2023年專案": ["安心就學支持計畫", None]})
    out = io.BytesIO()
    with pd.ExcelWriter(out) as w:
        table.to_excel(w, sheet_name="院系、提撥比例", index=False)
        annual.to_excel(w, sheet_name="專案紀錄", index=False)
    return out.getvalue()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture()
def loaded(client):
    """Reference table + ledger loaded as a new dataset; the reference is removed again afterwards."""
    r = client.post("/api/reference", files={"file": ("ref.xlsx", reference_book(), XLSX)})
    assert r.status_code == 200, r.text
    p = client.post("/api/upload/preview", files={"file": ("real.xlsx", ledger_book(), XLSX)}).json()
    mapping = {c["proposed_field"]: c["name"] for c in p["columns"] if c["proposed_field"]}
    out = client.post("/api/upload/confirm", json={"upload_id": p["upload_id"], "name": "real-shape", "mapping": mapping}).json()
    yield p, out
    with SessionLocal() as s:
        for m in (ProjectRef, AnnualProject, RefMeta):
            s.query(m).delete()
        s.commit()


def groups(client, ds, year):
    o = client.get("/api/overview", params={"dataset_id": ds, "year": year, "exceptional_threshold": 10**9}).json()
    return {g["label"]: g["amount"] for g in o["purpose_groups"]}, o


def test_non_ledger_sheets_are_skipped_and_donors_are_identified_by_name(loaded):
    p, out = loaded
    assert "芳名錄_成品" in p["row_note"] and "需求" in p["row_note"] and "identified by name" in p["row_note"]
    assert p["n_rows"] == 11 and out["n_rows"] == 11
    cap = {c["id"]: c for c in out["capability"]}
    assert cap["repeat"]["status"] == "caveat" and "name" in cap["repeat"]["reason"]


def test_the_sheet_name_is_the_report_year_and_repeat_donors_are_found(client, loaded):
    _, out = loaded
    j = client.get("/api/journey", params={"dataset_id": out["dataset_id"]}).json()
    assert [y["year"] for y in j["years"]] == [2023, 2024, 2025]
    assert j["years"][2]["retained"] >= 1                    # USER_1 gave in 2024 and 2025


def test_the_staff_table_decides_the_category_and_the_year(client, loaded):
    _, out = loaded
    ds = out["dataset_id"]
    g25, _ = groups(client, ds, 2025)
    assert g25["Annual campaigns"] == 7000                    # listed as a 2025 campaign
    assert g25["University fund"] == 1_000_000                # the fund stays the fund even though the campaign list names it
    g24, _ = groups(client, ds, 2024)
    assert g24["Annual campaigns"] == 6000 + 500             # campaign list for 2024 (tree adoption has no table row: it is an annual-list name)
    g23, _ = groups(client, ds, 2023)
    assert g23["Annual campaigns"] == 5000                    # tagged 2025 in the table, but in the 2023 list: proposed, same amount counted


def test_names_the_table_lacks_get_a_proposal_from_the_same_office_and_wait_for_a_person(client, loaded):
    _, out = loaded
    ds = out["dataset_id"]
    review = {r["raw_value"]: r for r in client.get("/api/review", params={"dataset_id": ds}).json()}
    assert "學務處：新生獎學金" in review and review["學務處：新生獎學金"]["proposed_label"] == "University-wide scholarships"
    assert review["學務處：新生獎學金"]["confidence"] < 0.8
    assert "某個沒有登記的專案" in review and review["某個沒有登記的專案"]["proposed_label"] is None
    n = client.post("/api/review/accept-suggestions", json={"dataset_id": ds}).json()["accepted"]
    assert n >= 1
    after = {r["raw_value"]: r["status"] for r in client.get("/api/review", params={"dataset_id": ds}).json()}
    assert after["學務處：新生獎學金"] == "resolved" and after["某個沒有登記的專案"] == "pending"


def test_gift_bands_follow_the_staffs_labels_and_atm_is_its_own_method(client, loaded):
    _, out = loaded
    _, o = groups(client, out["dataset_id"], 2025)
    last = o["bands"][-1]
    assert last["count"] == 1 and last["amount"] == 1_000_000     # exactly NT$1,000,000 is "100萬(含)以上"
    o23 = client.get("/api/overview", params={"dataset_id": out["dataset_id"], "year": 2023, "exceptional_threshold": 10**9}).json()
    assert any(m["label"] == "ATM transfer" for m in o23["methods"])


def test_the_table_is_replaced_not_stacked_and_must_look_like_a_table(client):
    r = client.post("/api/reference", files={"file": ("x.xlsx", ledger_book(), XLSX)})
    assert r.status_code == 400
    ok = client.post("/api/reference", files={"file": ("ref.xlsx", reference_book(), XLSX)}).json()
    again = client.post("/api/reference", files={"file": ("ref.xlsx", reference_book(), XLSX)}).json()
    assert ok["n_projects"] == again["n_projects"] == 6 and again["annual_by_year"] == {"2023": 1, "2024": 2, "2025": 2}
    with SessionLocal() as s:
        for m in (ProjectRef, AnnualProject, RefMeta):
            s.query(m).delete()
        s.commit()


def test_reference_key_ignores_width_spacing_and_case():
    assert ref_mod.ref_key("學務處：  ABC") == ref_mod.ref_key("學務處:abc")
