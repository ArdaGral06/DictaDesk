import json
from pathlib import Path

import pytest

import api_budget


@pytest.fixture
def budget_file(tmp_path, monkeypatch):
    path = tmp_path / "api_budget.json"
    monkeypatch.setattr(api_budget, "API_BUDGET_JSON", path)
    api_budget._session_count = 0
    api_budget._session_by_service = {name: 0 for name in api_budget._SERVICES}
    return path


def test_budget_disabled_allows_calls(budget_file):
    data = api_budget._default_data()
    data["enabled"] = False
    budget_file.write_text(json.dumps(data), encoding="utf-8")
    ok, msg = api_budget.check_budget("llm", "en")
    assert ok is True
    assert msg == ""


def test_budget_blocks_session_limit(budget_file):
    data = api_budget._default_data()
    data["enabled"] = True
    data["session_limit"] = 1
    budget_file.write_text(json.dumps(data), encoding="utf-8")
    api_budget.reset_budget_usage()
    api_budget.record_budget_usage("llm")
    ok, msg = api_budget.check_budget("llm", "tr")
    assert ok is False
    assert "oturum" in msg.lower() or "session" in msg.lower()


def test_toggle_budget(budget_file):
    budget_file.write_text(json.dumps(api_budget._default_data()), encoding="utf-8")
    assert api_budget.toggle_budget_enabled() is True
    loaded = api_budget.load_budget()
    assert loaded["enabled"] is True
