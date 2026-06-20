from failure_ui import failure_console_message, is_known_failure
from i18n import fail_reason_text


def test_fail_reason_translation_tr():
    text = fail_reason_text("tr", "gui_disabled")
    assert "GUI" in text


def test_run_code_failed_includes_exit_code():
    text = fail_reason_text("en", "run_code_failed:1")
    assert "1" in text


def test_known_failure_detection():
    assert is_known_failure("captcha_required")
    assert is_known_failure("run_code_failed:2")


def test_failure_console_message_missing():
    msg = failure_console_message("en", "missing")
    assert msg
