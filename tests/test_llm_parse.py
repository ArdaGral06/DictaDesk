import json

from llm_engine import _extract_json, _extract_plan, sanitize_planned_actions


def test_extract_json_from_fence():
    raw = 'Here is the plan:\n```json\n{"actions":[{"action":"open","value":"chrome"}]}\n```'
    payload = _extract_json(raw)
    assert payload is not None
    actions, goal, notes = _extract_plan(payload)
    assert len(actions) == 1
    assert actions[0]["action"] == "open"


def test_extract_json_python_literals():
    raw = "{'action': 'focus', 'value': 'notepad'}"
    payload = _extract_json(raw)
    assert payload is not None
    assert payload.get("action") == "focus"


def test_sanitize_removes_hallucinated_cmd():
    actions = [
        {"action": "write_file", "value": "a.txt -> hello"},
        {"action": "cmd", "value": "del /f"},
    ]
    cleaned = sanitize_planned_actions("not defterine yaz", actions)
    assert all(item.get("action") != "cmd" for item in cleaned)


def test_sanitize_keeps_run_code_when_user_asked():
    actions = [{"action": "run_code", "value": "game.py"}]
    cleaned = sanitize_planned_actions("oyunu calistir", actions)
    assert cleaned[0]["action"] == "run_code"
