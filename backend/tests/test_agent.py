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
