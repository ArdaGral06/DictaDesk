"""Regression tests for path resolution, verifier, and routing fixes."""

import action_verifier
import llm_engine
from desk_platform import _impl


# --- Bug: unsupported operand type(s) for &: 'list' and 'set' (lock/shutdown) ---

def test_fix_actions_from_text_shutdown_no_crash():
    actions = [{"action": "shutdown", "value": ""}]
    # Must not raise TypeError (list & set).
    result = llm_engine._fix_actions_from_text("bilgisayari kapat", actions)
    assert isinstance(result, list)


def test_fix_actions_from_text_lock_no_crash():
    actions = [{"action": "lock", "value": ""}]
    result = llm_engine._fix_actions_from_text("bilgisayari kilitle", actions)
    assert isinstance(result, list)


# --- Bug: write_file verifier did not expand %username% / env vars ---

def test_write_file_verifier_expands_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DDESK_TESTDIR", str(tmp_path))
    f = tmp_path / "hello.py"
    f.write_text("print('hi')", encoding="utf-8")
    value = "%DDESK_TESTDIR%\\hello.py -> print('hi')"
    res = action_verifier.verify_action("write_file", value)
    assert res["ok"] is True
    assert res["reason"] == "file_exists"


# --- Bug: open_dir/list_dir/make_dir path resolution ---

def test_resolve_existing_dir_shortcut(monkeypatch, tmp_path):
    monkeypatch.setattr(_impl.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Desktop").mkdir(parents=True)
    resolved = _impl._resolve_existing_dir("Desktop")
    assert resolved == tmp_path / "Desktop"


def test_resolve_existing_dir_relative_under_desktop(monkeypatch, tmp_path):
    monkeypatch.setattr(_impl.Path, "home", classmethod(lambda cls: tmp_path))
    target = tmp_path / "Desktop" / "minecraftbot"
    target.mkdir(parents=True)
    resolved = _impl._resolve_existing_dir("minecraftbot")
    assert resolved == target


def test_make_dir_relative_goes_under_desktop(monkeypatch, tmp_path):
    monkeypatch.setattr(_impl.Path, "home", classmethod(lambda cls: tmp_path))
    (tmp_path / "Desktop").mkdir(parents=True)
    _impl.make_dir("DictaDeskTest")
    assert (tmp_path / "Desktop" / "DictaDeskTest").is_dir()


# --- Bug: copy/rename of bare filename did not resolve under Desktop ---

def test_resolve_file_arg_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(_impl.Path, "home", classmethod(lambda cls: tmp_path))
    resolved = _impl._resolve_file_arg("test.txt")
    assert resolved == tmp_path / "Desktop" / "test.txt"


def test_copy_path_bare_names(monkeypatch, tmp_path):
    monkeypatch.setattr(_impl.Path, "home", classmethod(lambda cls: tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir(parents=True)
    (desktop / "test.txt").write_text("merhaba", encoding="utf-8")
    _impl.copy_path("test.txt", "test2.txt")
    assert (desktop / "test2.txt").read_text(encoding="utf-8") == "merhaba"


# --- Bug: youtube URL + "ozetle" routed to youtube_search instead of summarize ---

def test_youtube_url_summarize_routes_to_summarize():
    text = "https://www.youtube.com/watch?v=7GbxDQJXmvw videosunu ozetle"
    actions = llm_engine.infer_structured_workflow(text)
    assert actions
    assert actions[0]["action"] == "youtube_summarize"
    assert "7GbxDQJXmvw" in actions[0]["value"]


def test_youtube_search_still_routes_to_search():
    actions = llm_engine.infer_structured_workflow("youtube'da relaxing music ara")
    assert actions
    assert actions[0]["action"] == "youtube_search"
