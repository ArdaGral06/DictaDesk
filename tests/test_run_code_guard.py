from pathlib import Path

from action_executor import _path_under_code_projects, _resolve_code_path


def test_run_code_path_must_be_under_projects(tmp_path, monkeypatch):
    projects = tmp_path / "DictaDeskProjects"
    monkeypatch.setattr(
        "action_executor.CODE_PROJECTS_DIR",
        projects,
        raising=False,
    )
    allowed = projects / "game.py"
    allowed.parent.mkdir(parents=True, exist_ok=True)
    allowed.write_text("print('ok')", encoding="utf-8")
    outside = tmp_path / "evil.py"
    outside.write_text("print('no')", encoding="utf-8")

    assert _path_under_code_projects(allowed.resolve()) is True
    assert _path_under_code_projects(outside.resolve()) is False
    assert _resolve_code_path("game.py") == allowed.resolve()
