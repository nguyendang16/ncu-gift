"""The analyst agent, tested against a fake model. What is verified: the tool loop, that donor tables never reach the model,
that a made-up figure is caught and repaired once, that bad tool calls cannot crash anything, and the step cap."""
import json
import re

import pytest

from app.ai import agent, client

KEY = "sk-test-agent-123"


def usage():
    return {"prompt_tokens": 2000, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 0}}


def say(text):
    return 200, {"model": "gpt-6-luna", "choices": [{"message": {"role": "assistant", "content": text}}], "usage": usage()}


def call(*calls):
    tcs = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
    return 200, {"model": "gpt-6-luna", "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": tcs}}], "usage": usage()}


class Fake:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, headers, body, timeout):
        self.calls.append(json.loads(json.dumps(body)))
        r = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return r(body) if callable(r) else r


def tool_results(body):
    return [json.loads(m["content"]) for m in body["messages"] if m.get("role") == "tool"]


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.delenv("NCU_GIFT_AI_DEMO", raising=False)
    monkeypatch.delenv("NCU_GIFT_AI_CONSENT", raising=False)
    yield
    client.set_transport(None)


def ask(c, mock_id, q="Who should we call first?", lang="en", **kw):
    return c.post("/api/ai/agent", json={"dataset_id": mock_id, "question": q, **kw}, headers={"Accept-Language": lang})


def test_the_model_picks_tools_the_app_runs_them_and_donor_tables_stay_out_of_the_model(client, mock_id):
    def final(body):
        r = tool_results(body)
        return say(f"Total giving was {r[0]['total']['text']} [1]. I listed 5 donors [2]; the list is below.")
    fake = Fake(call(("giving_overview", {}), ("at_risk_donors", {"count": 5})), final)
    from app.ai.client import set_transport
    set_transport(fake)
    r = ask(client, mock_id)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["verification"]["ok"] is True and [s["tool"] for s in out["steps"]] == ["giving_overview", "at_risk_donors"]
    assert out["steps"][1]["table"] and len(out["steps"][1]["table"]["rows"]) == 5          # drawn by the app
    seen = json.dumps(fake.calls)
    assert not re.search(r"\bD\d{4}\b|USER_\d+", seen)                                      # no donor code in anything sent
    assert all("tools" in b and b["reasoning_effort"] == "none" for b in fake.calls)       # function calling needs reasoning "none"
    assert fake.calls[-1]["messages"][-1]["role"] == "tool"


def test_an_invented_figure_is_caught_and_the_answer_is_repaired_once(client, mock_id):
    def good(body):
        return say(f"Total giving was {tool_results(body)[0]['total']['text']} [1].")
    from app.ai.client import set_transport
    fake = Fake(call(("giving_overview", {})), say("Total giving was NT$999.9M [1]."), good)
    # the third reply is only used if the second call asks for a repair; the loop returns the first text answer then verifies
    set_transport(fake)
    out = ask(client, mock_id).json()
    assert out["verification"]["ok"] is True and "999.9" not in out["answer"]
    assert len(fake.calls) == 3


def test_a_number_the_person_typed_may_be_repeated(client, mock_id):
    from app.ai.client import set_transport
    set_transport(Fake(say("The tools cannot say what will be raised in 2031.")))
    out = ask(client, mock_id, "What will we raise in 2031?").json()
    assert out["verification"]["ok"] is True and out["steps"] == []


def test_unknown_tools_bad_targets_and_bad_arguments_do_not_crash(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("delete_everything", {}), ("find_prospects", {"target_id": "sub:Not a thing"}), ("giving_overview", {"year": "banana"})),
                say("Only the overview worked."))
    set_transport(fake)
    out = ask(client, mock_id).json()
    assert [s["ok"] for s in out["steps"]] == [False, False, True]
    msgs = tool_results(fake.calls[1])
    assert msgs[0]["error"] and "unknown target_id" in msgs[1]["error"]


def test_scenario_arguments_are_clamped_and_linked_to_the_strategy_page(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("run_scenario", {"first_time_retention_uplift_pts": 500, "new_donor_inflow_multiplier": 9, "major_gift_ntd": -5})), say("Done."))
    set_transport(fake)
    step = ask(client, mock_id, "What if we keep far more first-time donors?").json()["steps"][0]
    assert "r1=20" in step["link"] and "mult=1.5" in step["link"] and "gift=0" in step["link"]
    res = tool_results(fake.calls[1])[0]
    assert res["settings"]["first_time_retention_uplift_points"] == 20 and "sensitivity" in res["kind"].lower()


def test_a_citation_to_a_source_that_does_not_exist_is_flagged(client, mock_id):
    from app.ai.client import set_transport
    def bad(body):
        return say(f"Total giving was {tool_results(body)[0]['total']['text']} [7].")
    set_transport(Fake(call(("giving_overview", {})), bad, bad))
    out = ask(client, mock_id).json()
    assert out["verification"]["ok"] is False and "[7]" in out["verification"]["unverified"]


def test_the_loop_stops_after_the_step_cap(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("giving_by_year", {})))
    set_transport(fake)
    r = ask(client, mock_id)
    assert r.status_code == 502 and len(fake.calls) == agent.MAX_STEPS
    assert fake.calls[-1]["tool_choice"] == "none"


def test_a_tool_result_with_a_donor_identifier_is_never_sent(client, mock_id, monkeypatch):
    from app.ai.client import set_transport
    def leaky(c, a):
        return agent.ToolOut({"note": "ask USER_55 about it"}, "x")
    monkeypatch.setitem(agent.IMPL, "giving_overview", leaky)
    fake = Fake(call(("giving_overview", {})), say("never reached"))
    set_transport(fake)
    r = ask(client, mock_id)
    assert r.status_code == 403 and len(fake.calls) == 1


def test_demo_mode_works_without_a_key_in_both_languages(client, mock_id, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("NCU_GIFT_AI_DEMO", "1")
    en = ask(client, mock_id, "Who is most at risk of stopping?").json()
    assert en["demo"] is True and en["steps"][0]["tool"] == "at_risk_donors" and en["steps"][0]["table"] and en["verification"]["ok"]
    zh = ask(client, mock_id, "如果提高續捐率會怎樣？", lang="zh-TW").json()
    assert zh["steps"][0]["tool"] == "run_scenario" and zh["answer"].startswith("【示範") and zh["steps"][0]["link"].startswith("/strategy?")


def test_no_key_means_no_agent(client, mock_id, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    assert ask(client, mock_id).status_code in (403, 502)


# ------------------------------------------------------------------ conversations, planning, feature finder, actions

def tool_msgs(fake, i=-1):
    return [json.loads(m["content"]) for m in fake.calls[i]["messages"] if m.get("role") == "tool"]


def test_conversations_are_saved_continued_reopened_and_deleted(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("giving_by_year", {})), say("There are three years of data."), say("Still three years."))
    set_transport(fake)
    first = ask(client, mock_id, "How many years of data are there?").json()
    cid = first["conversation_id"]
    assert cid
    second = ask(client, mock_id, "And is that enough?", conversation_id=cid).json()
    assert second["conversation_id"] == cid
    sent = json.dumps(fake.calls[-1]["messages"])
    assert "How many years of data are there?" in sent and "There are three years of data." in sent          # the follow-up sees the earlier turn
    rows = client.get("/api/ai/conversations").json()
    mine = next(r for r in rows if r["id"] == cid)
    assert mine["n_messages"] == 4 and mine["title"].startswith("How many years")
    full = client.get(f"/api/ai/conversations/{cid}").json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant", "user", "assistant"]
    assert full["messages"][1]["steps"][0]["tool"] == "giving_by_year" and full["messages"][1]["verification"]["ok"] is True
    assert client.delete(f"/api/ai/conversations/{cid}").json()["deleted"] == 1
    assert client.get(f"/api/ai/conversations/{cid}").status_code == 404
    ask(client, mock_id, "Another one")
    assert client.delete("/api/ai/conversations").json()["deleted"] >= 1 and client.get("/api/ai/conversations").json() == []


def test_a_goal_gets_levers_gifts_a_balanced_plan_and_concrete_next_actions(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("plan_to_raise", {"target_ntd": 1_000_000})), lambda body: say(f"The goal is {tool_results(body)[0]['goal']['extra_ordinary_giving']['text']} extra [1]."))
    set_transport(fake)
    out = ask(client, mock_id, "I want to raise about NT$1M").json()
    assert out["verification"]["ok"] and out["steps"][0]["ok"]
    res = tool_msgs(fake)[0]
    assert {x["lever"] for x in res["levers_each_on_its_own"]} == {"first_time_retention_uplift_pts", "repeat_retention_uplift_pts", "new_donor_inflow_multiplier", "recurring_conversion_pct"}
    assert res["balanced_effort"]["adds_about"]["value"] >= 1_000_000 * 0.99 and res["typical_gifts"]["extra_gifts_needed_at_median"] >= 1
    assert 1 <= len(res["concrete_next_actions"]) <= 4 and all(len(a["steps"]) == 3 for a in res["concrete_next_actions"])
    step = out["steps"][0]
    assert step["table"] and len(step["table"]["columns"]) == 4
    assert any(l["to"].startswith("/strategy?r1=") for l in step["links"]) and any(l["to"] == "/risk" for l in step["links"])
    assert not re.search(r"\bD\d{4}\b", json.dumps(fake.calls))


def test_the_goal_can_be_for_one_purpose_and_is_clamped(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("plan_to_raise", {"target_ntd": 5, "focus_target_id": "sub:Student clubs"})), say("Done."))
    set_transport(fake)
    out = ask(client, mock_id, "Raise a little for student clubs").json()
    res = tool_msgs(fake)[0]
    assert res["goal"]["extra_ordinary_giving"]["value"] == 100_000                                   # lowest allowed goal
    assert res["focus"]["gifts_last_year"] >= 1 and "organisation-wide" in res["levers_scope"]
    assert any(l["to"].startswith("/matching?target=") for l in out["steps"][0]["links"])


def test_where_is_it_returns_open_buttons_and_numbered_how_to_lists_are_not_flagged(client, mock_id):
    from app.ai.client import set_transport
    fake = Fake(call(("find_feature", {"query": "who might stop giving"})),
                say("Open At-risk donors.\n1. Start at the top of the list.\n2. Read the reason on each row."))
    set_transport(fake)
    out = ask(client, mock_id, "Where can I see who might stop giving?").json()
    assert out["steps"][0]["links"][0]["to"] == "/risk" and len(out["steps"][0]["links"]) <= 3
    assert out["verification"]["ok"] is True                                                               # "1." and "2." are list numbering, not figures
    assert tool_msgs(fake)[0]["pages"][0]["id"] == "risk"


def test_every_data_tool_points_to_the_page_where_the_person_can_see_it_for_themselves(client, mock_id):
    from app.ai.client import set_transport
    set_transport(Fake(call(("concentration", {}), ("donor_retention", {}), ("why_total_changed", {}), ("monthly_pattern", {})), say("ok")))
    links = [s["links"][0]["to"] for s in ask(client, mock_id, "overview of everything").json()["steps"]]
    assert links == ["/#concentration", "/journey", "/#change", "/#when"]


def test_feature_search_and_routes():
    from app.ai import guide
    assert guide.search("how do I upload an excel file")[0] == "data_upload"
    assert guide.search("who should we phone")[0] == "risk"
    assert guide.route("strategy", r1=5) == "/strategy?r1=5" and guide.route("data_upload") == "/data?tab=upload"
    assert guide.route("overview") == "/" and guide.route("bridge") == "/#change"
    assert len(guide.search("")) == len(guide.FEATURES)


def insights_reply(actions):
    obs = [{"key": k, "text": "x"} for k in ("compare", "base", "concentration", "accounts")]
    return say(json.dumps({"observations": obs, "recommendations": ["a", "b", "c"], "actions": actions}))


def test_the_overview_actions_keep_the_models_choice_and_use_the_playbook_for_steps(client, mock_id):
    from app.ai.client import set_transport
    set_transport(Fake(insights_reply([{"candidate_id": "recurring", "why": "Recurring plans steady the income.", "now": "It is the easiest start."},
                                         {"candidate_id": "not_a_candidate", "why": "x", "now": "y"}])))
    r = client.post("/api/ai/insights", json={"dataset_id": mock_id, "exceptional_threshold": 10_000_000}).json()
    ids = [a["candidate_id"] for a in r["actions"]]
    assert ids[0] == "recurring" and "not_a_candidate" not in ids and len(ids) == len(set(ids)) and 3 <= len(ids) <= 4          # the gap is filled from the playbook
    first = r["actions"][0]
    assert first["why"] == "Recurring plans steady the income." and first["now"] == "It is the easiest start." and len(first["steps"]) == 3
    assert first["expected_effect"].startswith("If ") and first["measure"].startswith("Success looks like") and first["link"]["to"] == "/strategy"
    assert r["verification"]["ok"] is True


def test_without_a_usable_reply_the_actions_still_come_from_the_playbook_in_both_languages(client, mock_id):
    from app.ai.client import set_transport
    for lang, marker in (("en", "Success looks like"), ("zh-TW", "成功的樣子")):
        set_transport(Fake(insights_reply([])))
        r = client.post("/api/ai/insights", json={"dataset_id": mock_id, "exceptional_threshold": 10_000_000}, headers={"Accept-Language": lang}).json()
        assert len(r["actions"]) >= 3 and all(marker in a["measure"] and len(a["steps"]) == 3 for a in r["actions"])
        assert r["verification"]["ok"] is True
