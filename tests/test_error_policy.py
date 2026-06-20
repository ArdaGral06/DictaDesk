from agent_error_policy import ERROR_ABORT, ERROR_REPLAN, ERROR_RETRY, ERROR_SKIP, decide_error_policy


def test_non_critical_skips():
    assert decide_error_policy("open", "timeout", False, 0, 0) == ERROR_SKIP


def test_gui_disabled_aborts():
    assert decide_error_policy("gui_click", "gui_disabled", True, 0, 0) == ERROR_ABORT


def test_transient_retries_once():
    assert decide_error_policy("type", "network timeout", True, 0, 0) == ERROR_RETRY
    assert decide_error_policy("type", "network timeout", True, 1, 0) == ERROR_REPLAN


def test_replan_cap_aborts():
    assert decide_error_policy("start", "app_not_open", True, 0, 2) == ERROR_ABORT
