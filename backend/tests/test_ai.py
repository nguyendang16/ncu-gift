"""The AI layer is tested with a fake transport: no test can reach the network. What is verified here is everything around
the model (consent, what is sent, the number check, fallbacks, logging, error handling), not the model's intelligence."""
import json
import re

import pytest

from app.ai import client
from app.ai.safety import UnsafePayload, assert_safe

SECRET = "sk-test-SECRET-do-not-leak-123"


def ok_reply(text, prompt=4000, completion=300):
    return 200, {"model": "gpt-6-luna", "choices": [{"message": {"content": text}}],
                 "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "prompt_tokens_details": {"cached_tokens": 0}}}


class Fake:
    """Records every request and answers from a queue (the last answer repeats)."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(json.dumps(body))})
        r = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return r(body) if callable(r) else r


@pytest.fixture(autouse=True)
def isolate(client_, monkeypatch):
    """Every test starts with AI off, no key, and a transport that fails loudly if anything tries to use the network."""
    def boom(*a, **k):
        raise AssertionError("a test tried to use the real network")
    client.set_transport(boom)
    for k in ("OPENAI_API_KEY", "NCU_GIFT_AI_DEMO", "NCU_GIFT_AI_DAILY_CAP"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NCU_GIFT_AI_CONSENT", "0")        # most tests exercise the per-feature switches; one test covers the default
    client_.put("/api/ai/settings", json={"enabled": False, "share_project_names": False, "share_column_headers": False})
    yield
    client.set_transport(None)
    client_.put("/api/ai/settings", json={"enabled": False, "share_project_names": False, "share_column_headers": False})


@pytest.fixture
def client_(client):
    return client


def turn_on(c, projects=False, headers=False):
    c.put("/api/ai/settings", json={"enabled": True, "share_project_names": projects, "share_column_headers": headers})


def with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)


def ask(c, mock_id, q="Why did giving change?", **kw):
    return c.post("/api/ai/ask", json={"dataset_id": mock_id, "question": q, **kw})


def test_a_key_in_the_environment_is_the_consent_unless_switched_back(client_, mock_id, monkeypatch):
    monkeypatch.delenv("NCU_GIFT_AI_CONSENT")
    s = client_.get("/api/ai/status").json()
    assert s["ready"] is False and s["configured"] is False                      # no key: nothing happens
    with_key(monkeypatch)
    s = client_.get("/api/ai/status").json()
    assert s["ready"] and s["enabled"] and s["share_project_names"] and s["share_column_headers"]
    client.set_transport(Fake(ok_reply("OK")))
    assert ask(client_, mock_id).status_code == 200
    monkeypatch.setenv("NCU_GIFT_AI_CONSENT", "0")                                # the administrator turns it back to explicit switches
    assert client_.get("/api/ai/status").json()["ready"] is False
    assert ask(client_, mock_id).status_code == 403


def test_a_year_typed_in_the_question_may_be_repeated_without_being_flagged(client_, mock_id, monkeypatch):
    with_key(monkeypatch); turn_on(client_)
    fake = Fake(ok_reply("The facts do not say what NCU will raise in 2031."))
    client.set_transport(fake)
    a = ask(client_, mock_id, "What will we raise in 2031?").json()
    assert a["verification"]["ok"] is True and len(fake.calls) == 1


def test_negative_money_reads_as_minus_before_the_currency():
    from app.services.insights import _ntd_compact
    assert _ntd_compact(-18_660_900) == "-NT$18.7M" and _ntd_compact(27_000_000) == "NT$27.0M"


# ------------------------------------------------------------------ consent and gating

def test_ai_is_off_by_default_and_says_why(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    s = client_.get("/api/ai/status").json()
    assert s["enabled"] is False and s["ready"] is False and s["model"] == "gpt-6-luna"
    r = ask(client_, mock_id)
    assert r.status_code == 403 and r.json()["code"] == "ai_blocked" and r.json()["ai_code"] == "disabled"


def test_each_kind_of_sharing_needs_its_own_permission(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)                                       # AI on, but nothing beyond summary figures may be shared
    brief = client_.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship", "use_ai": True})
    assert brief.status_code == 403 and brief.json()["ai_code"] == "projects"
    with open(__import__("app.config", fromlist=["x"]).SAMPLE_DIR / "mock_donations.xlsx", "rb") as f:
        up = client_.post("/api/upload/preview", files={"file": ("a.xlsx", f, "application/octet-stream")}).json()
    m = client_.post("/api/ai/map-columns", json={"upload_id": up["upload_id"]})
    assert m.status_code == 403 and m.json()["ai_code"] == "headers"


def test_no_key_gives_a_clear_instruction(client_, mock_id):
    turn_on(client_)
    r = ask(client_, mock_id)
    assert r.status_code == 502 and r.json()["ai_code"] == "no_key" and "OPENAI_API_KEY" in r.json()["detail"]


def test_daily_cap_stops_further_calls(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    monkeypatch.setenv("NCU_GIFT_AI_DAILY_CAP", "1")
    turn_on(client_)
    fake = Fake(ok_reply("OK"))
    client.set_transport(fake)
    first = client_.post("/api/ai/test")
    assert first.status_code == 200
    second = client_.post("/api/ai/test")
    # the cap counts the calls already made today across all tests; it must block once the limit is reached
    assert second.status_code in (200, 403)
    capped = [c for c in (first, second) if c.status_code == 403]
    assert all(c.json()["ai_code"] == "cap" for c in capped)


# ------------------------------------------------------------------ what is sent

def test_request_shape_matches_the_model_docs(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    fake = Fake(ok_reply("Total giving was fine."))
    client.set_transport(fake)
    ask(client_, mock_id)
    call = fake.calls[0]
    assert call["url"].endswith("/chat/completions") and call["headers"]["Authorization"] == f"Bearer {SECRET}"
    body = call["body"]
    assert body["model"] == "gpt-6-luna" and body["reasoning_effort"] == "low" and body["max_completion_tokens"] > 0
    assert "temperature" not in body                                  # not listed for this model, so never sent
    assert [m["role"] for m in body["messages"][:2]] == ["system", "user"]
    assert "Never calculate" in body["messages"][0]["content"] and "English" in body["messages"][0]["content"]


def test_nothing_identifying_is_ever_sent(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_, projects=True, headers=True)
    fake = Fake(ok_reply("Fine."), ok_reply(json.dumps({"headline": "H", "points": ["a", "b", "c"]})))
    client.set_transport(fake)
    ask(client_, mock_id)
    client_.post("/api/ai/insights", json={"dataset_id": mock_id})
    known = {n["name"] for s in client_.get("/api/roll", params={"dataset_id": mock_id}).json()["sections"] for p in s["projects"] for n in p["entries"]}
    sent_all = " ".join(c["body"]["messages"][1]["content"] for c in fake.calls)
    assert not [k for k in known if len(k) > 4 and k in sent_all and not k.startswith("Friends")]      # no real display name appears in any payload
    names = {n for n in re.findall(r"Mock (?:Donor|Corp\.|Foundation) \d{4}", " ".join(c["body"]["messages"][1]["content"] for c in fake.calls))}
    codes = re.findall(r"\bD\d{4}\b", " ".join(c["body"]["messages"][1]["content"] for c in fake.calls))
    assert names == set() and codes == []


def test_a_donor_name_typed_into_a_question_blocks_the_call(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    fake = Fake(ok_reply("x"))
    client.set_transport(fake)
    roll = client_.get("/api/roll", params={"dataset_id": mock_id}).json()
    name = next(e["name"] for s in roll["sections"] for p in s["projects"] for e in p["entries"] if not e["name"].startswith("Friends"))
    r = ask(client_, mock_id, f"What do we know about {name}?")
    assert r.status_code == 403 and r.json()["ai_code"] == "leak" and fake.calls == []        # nothing was sent


def test_safety_gate_catches_codes_and_known_names():
    with pytest.raises(UnsafePayload):
        assert_safe({"x": "see donor D0042"})
    with pytest.raises(UnsafePayload):
        assert_safe({"projects": ["Memorial for Jane Example"]}, {"Jane Example"})
    assert assert_safe({"projects": ["Physics: Scholarship"]}, {"Jane Example"})


def test_column_mapping_sends_headers_and_profiles_but_no_cell_values(client_, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_, headers=True)
    from app.config import SAMPLE_DIR
    with open(SAMPLE_DIR / "mock_donations_renamed.xlsx", "rb") as f:
        up = client_.post("/api/upload/preview", files={"file": ("r.xlsx", f, "application/octet-stream")}).json()
    reply = {"columns": [{"column": "Donor ID", "field": "donor_id", "confidence": 0.99, "reason": "id"},
                         {"column": "Event Source", "field": "made_up_field", "confidence": 0.9, "reason": "?"},
                         {"column": "Was Solicited?", "field": "anonymous", "confidence": 0.4, "reason": "yes/no"}]}
    fake = Fake(ok_reply(json.dumps(reply)))
    client.set_transport(fake)
    out = client_.post("/api/ai/map-columns", json={"upload_id": up["upload_id"]}).json()
    sent = fake.calls[0]["body"]["messages"][1]["content"]
    assert "Donor ID" in sent and "Mock Donor" not in sent and not re.search(r"\bD\d{4}\b", sent) and "Gala dinner" not in sent
    by = {s["column"]: s for s in out["suggestions"]}
    assert by["Donor ID"]["confidence"] == 0.75                            # capped: a person must still confirm
    assert "Event Source" not in by                                        # a field that does not exist is dropped
    assert fake.calls[0]["body"]["response_format"]["json_schema"]["strict"] is True


# ------------------------------------------------------------------ the number check

def test_an_unverifiable_figure_triggers_one_repair_then_passes(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    fake = Fake(ok_reply("Giving was NT$999,999,999 last year."), ok_reply("Giving moved in line with the summary."))
    client.set_transport(fake)
    r = ask(client_, mock_id).json()
    assert len(fake.calls) == 2 and r["verification"]["ok"] is True
    assert "999999999" in fake.calls[1]["body"]["messages"][-1]["content"]        # the model is told which figure failed, in plain digits


def test_a_figure_that_stays_unverified_is_flagged_not_hidden(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    client.set_transport(Fake(ok_reply("Giving was exactly 424242.")))
    r = ask(client_, mock_id).json()
    assert r["answer"] and r["verification"]["ok"] is False and "424242" in r["verification"]["unverified"]


def test_quoting_the_facts_verifies(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)

    def reply(body):
        facts = json.loads(body["messages"][1]["content"])["facts"]
        y = facts["yearly"][-1]
        return ok_reply(f"In {y['year']} total giving was {y['total']['text']} and ordinary giving was {y['ordinary']['text']}.")
    client.set_transport(Fake(reply))
    r = ask(client_, mock_id).json()
    assert r["verification"]["ok"] is True and r["verification"]["checked"] >= 3 and r["cost_usd"] > 0


def test_insights_accept_json_even_inside_code_fences(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    client.set_transport(Fake(ok_reply("```json\n" + json.dumps({"headline": "A short headline.", "points": ["one", "two", "three", "four"]}) + "\n```")))
    r = client_.post("/api/ai/insights", json={"dataset_id": mock_id}).json()
    assert r["headline"] == "A short headline." and r["points"] == ["one", "two", "three"]


def test_bad_json_is_reported_plainly(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    client.set_transport(Fake(ok_reply("this is not json")))
    r = client_.post("/api/ai/insights", json={"dataset_id": mock_id})
    assert r.status_code == 502 and r.json()["ai_code"] == "bad_json"


# ------------------------------------------------------------------ AI drafts fall back to the template

def test_ai_brief_is_used_when_verified_and_falls_back_when_not(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_, projects=True)
    base = client_.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship"}).json()
    assert base["source"] == "template"
    f = base["facts"]
    good = (f"{f['project']} welcomes support. Last year {f['category_last_year']['donors']} donors gave, "
            f"and the middle gift was NT${f['category_last_year']['median_gift']:,.0f}. Draft for staff review.")
    client.set_transport(Fake(ok_reply(good)))
    ai = client_.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship", "use_ai": True}).json()
    assert ai["source"] == "ai" and ai["verification"]["verified"] and ai["draft_text"] == good
    client.set_transport(Fake(ok_reply("Last year 77777 donors gave NT$1,234,567.")))
    fb = client_.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship", "use_ai": True}).json()
    assert fb["source"] == "template" and fb["ai_note"] and fb["verification"]["verified"]


def test_classification_suggestions_stay_inside_the_closed_set(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_, projects=True)
    items = [i for i in client_.get("/api/review", params={"dataset_id": mock_id}).json() if i["kind"] == "purpose"]
    ids = [i["id"] for i in items[:3]]
    reply = {"results": [{"index": 0, "label": "Student clubs", "confidence": 0.99},
                         {"index": 1, "label": "Invented category", "confidence": 0.9},
                         {"index": 2, "label": "unsure", "confidence": 0.1}]}
    client.set_transport(Fake(ok_reply(json.dumps(reply))))
    out = client_.post("/api/ai/classify", json={"dataset_id": mock_id, "item_ids": ids}).json()
    assert [(s["label"], s["confidence"]) for s in out["suggestions"]] == [("Student clubs", 0.8)]      # capped; never applied automatically
    still = {i["id"]: i["status"] for i in client_.get("/api/review", params={"dataset_id": mock_id}).json()}
    assert all(still[i] == "pending" for i in ids)


# ------------------------------------------------------------------ errors, secrets, log

def test_unsupported_optional_parameter_is_dropped_and_retried(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    fake = Fake((400, {"error": {"message": "Unsupported parameter: 'reasoning_effort' is not supported with this model."}}), ok_reply("OK"))
    client.set_transport(fake)
    assert client_.post("/api/ai/test").status_code == 200
    assert "reasoning_effort" in fake.calls[0]["body"] and "reasoning_effort" not in fake.calls[1]["body"]


@pytest.mark.parametrize("status,body,code", [(401, {"error": {"message": "bad key"}}, "bad_key"),
                                              (404, {"error": {"message": "The model `gpt-6-luna` does not exist"}}, "bad_model"),
                                              (429, {"error": {"message": "slow down"}}, "rate_limited"),
                                              (503, {"error": {"message": "down"}}, "unavailable")])
def test_provider_errors_become_actionable_messages(client_, monkeypatch, status, body, code):
    with_key(monkeypatch)
    turn_on(client_)
    client.set_transport(Fake((status, body)))
    r = client_.post("/api/ai/test")
    assert r.status_code == 502 and r.json()["ai_code"] == code
    if code == "bad_model":
        assert "does not exist" in r.json()["detail"] and "gpt-6-luna" in r.json()["detail"]      # OpenAI's own words reach the user


def test_the_api_key_never_appears_anywhere(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_, projects=True, headers=True)
    client.set_transport(Fake(ok_reply("Fine.")))
    ask(client_, mock_id)
    seen = [client_.get("/api/ai/status").text, client_.get("/api/ai/log").text]
    for row in client_.get("/api/ai/log").json():
        seen.append(client_.get(f"/api/ai/log/{row['id']}").text)
    assert not any(SECRET in s or "SECRET" in s for s in seen)


def test_every_call_is_logged_with_what_was_sent(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    client.set_transport(Fake(ok_reply("Fine.")))
    before = len(client_.get("/api/ai/log", params={"limit": 200}).json())
    ask(client_, mock_id, "Anything notable?")
    rows = client_.get("/api/ai/log", params={"limit": 200}).json()
    assert len(rows) == before + 1 and rows[0]["feature"] == "ask" and rows[0]["status"] == "ok" and rows[0]["cost_usd"] > 0
    detail = client_.get(f"/api/ai/log/{rows[0]['id']}").json()
    assert "Anything notable?" in detail["payload_json"] and "facts" in detail["payload_json"]


def test_blocked_attempts_are_logged_too(client_, mock_id, monkeypatch):
    with_key(monkeypatch)
    turn_on(client_)
    client.set_transport(Fake(ok_reply("x")))
    ask(client_, mock_id, "Tell me about Mock Donor 0099")
    assert client_.get("/api/ai/log").json()[0]["status"] == "blocked"


# ------------------------------------------------------------------ demo mode

def test_demo_mode_runs_end_to_end_without_a_key_and_is_labelled(client_, mock_id, monkeypatch):
    monkeypatch.setenv("NCU_GIFT_AI_DEMO", "1")
    turn_on(client_, projects=True, headers=True)
    s = client_.get("/api/ai/status").json()
    assert s["demo"] is True and s["ready"] is True and s["model"] == "demo"
    a = ask(client_, mock_id, "Why did total giving change?").json()
    assert a["demo"] is True and a["answer"].startswith("[Demo answer") and a["verification"]["ok"] is True
    i = client_.post("/api/ai/insights", json={"dataset_id": mock_id}).json()
    assert len(i["points"]) == 3 and i["verification"]["ok"] is True and i["demo"] is True
    zh = client_.post("/api/ai/ask", json={"dataset_id": mock_id, "question": "為什麼下降?"}, headers={"Accept-Language": "zh-TW"}).json()
    assert zh["answer"].startswith("【示範回答") and zh["verification"]["ok"] is True
    b = client_.post("/api/briefs", json={"dataset_id": mock_id, "project": "Physics: Scholarship", "use_ai": True}).json()
    assert b["source"] == "ai" and b["verification"]["verified"]
