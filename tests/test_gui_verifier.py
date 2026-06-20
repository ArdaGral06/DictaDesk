from action_context import record_action_outcome
from gui_verifier import verify_gui_action


def test_gui_not_executed():
    result = verify_gui_action("gui_click_text", "Save")
    assert result["ok"] is False
    assert result["reason"] == "gui_not_executed"


def test_gui_success_from_outcome():
    record_action_outcome("gui_click", True, "gui_action_ok", meta={"x": 10, "y": 20})
    result = verify_gui_action("gui_click", "10,20")
    assert result["ok"] is True
