import json
from pathlib import Path

import dev_agent


class _FakeInner:
    def __init__(self, plan_json, fix_json=None):
        self.plan_json = plan_json
        self.fix_json = fix_json

    def generate(self, user, system_prompt=None, raw_user=False, max_tokens=None, compact=True):
        sp = (system_prompt or "").lower()
        if "debug" in sp or "hata ayikla" in sp:
            return self.fix_json or "{}"
        return self.plan_json


class _FakeLLM:
    def __init__(self, inner, enabled=True):
        self.enabled = enabled
        self.llm = inner


def test_extract_json_plain():
    data = dev_agent.extract_json('{"a": 1, "b": [2, 3]}')
    assert data == {"a": 1, "b": [2, 3]}


def test_extract_json_fenced():
    text = "Here you go:\n```json\n{\"x\": 5}\n```\nthanks"
    assert dev_agent.extract_json(text) == {"x": 5}


def test_extract_json_braces_in_string():
    text = '{"files":[{"path":"a.py","content":"def f(): return {}"}]}'
    data = dev_agent.extract_json(text)
    assert data["files"][0]["path"] == "a.py"


def test_extract_json_none_on_garbage():
    assert dev_agent.extract_json("no json here") is None


def test_write_project_files_blocks_traversal(tmp_path):
    base = tmp_path / "proj"
    written = dev_agent.write_project_files(
        base,
        [
            {"path": "main.py", "content": "print(1)"},
            {"path": "../escape.py", "content": "danger"},
        ],
    )
    assert any(p.endswith("main.py") for p in written)
    assert not (tmp_path / "escape.py").exists()


def test_project_dir_for_uses_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(dev_agent, "CODE_PROJECTS_DIR", tmp_path)
    d = dev_agent.project_dir_for({"folder": "My App!"}, "goal")
    assert d == tmp_path / "my-app"


def test_build_project_no_llm():
    ok, reason = dev_agent.build_project("anything", llm=None)
    assert not ok
    assert reason == "dev_no_llm"


def test_build_project_happy_path_no_run(monkeypatch, tmp_path):
    monkeypatch.setattr(dev_agent, "CODE_PROJECTS_DIR", tmp_path)
    plan = json.dumps(
        {
            "folder": "demo",
            "language": "python",
            "deps": [],
            "run": "",
            "files": [
                {"path": "main.py", "content": "print('hi')"},
                {"path": "pkg/helper.py", "content": "X = 1"},
            ],
        }
    )
    llm = _FakeLLM(_FakeInner(plan))
    ok, info = dev_agent.build_project("demo app", llm=llm, open_folder=False)
    assert ok
    assert (tmp_path / "demo" / "main.py").exists()
    assert (tmp_path / "demo" / "pkg" / "helper.py").exists()


def test_build_project_plan_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(dev_agent, "CODE_PROJECTS_DIR", tmp_path)
    llm = _FakeLLM(_FakeInner("not json"))
    ok, reason = dev_agent.build_project("x", llm=llm, open_folder=False)
    assert not ok
    assert reason == "dev_plan_failed"


def test_build_project_fix_loop(monkeypatch, tmp_path):
    monkeypatch.setattr(dev_agent, "CODE_PROJECTS_DIR", tmp_path)
    plan = json.dumps(
        {
            "folder": "demo",
            "deps": [],
            "run": "main.py",
            "files": [{"path": "main.py", "content": "broken"}],
        }
    )
    fix = json.dumps({"files": [{"path": "main.py", "content": "fixed"}]})
    llm = _FakeLLM(_FakeInner(plan, fix))

    calls = {"n": 0}

    def fake_run_entry(base_dir, entry, cancel_event=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "SyntaxError: boom"
        return True, ""

    monkeypatch.setattr(dev_agent, "run_entry", fake_run_entry)
    ok, info = dev_agent.build_project("demo", llm=llm, open_folder=False)
    assert ok
    assert calls["n"] == 2
    assert (tmp_path / "demo" / "main.py").read_text(encoding="utf-8") == "fixed"
