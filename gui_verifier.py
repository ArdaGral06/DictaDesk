from action_context import get_action_outcome
from platform_actions import get_last_gui_map_summary, screen_contains_text


def _target_from_value(action: str, value: str | None, meta: dict) -> str:
    if meta.get("target"):
        return str(meta["target"])
    raw = (value or "").strip()
    if not raw:
        return ""
    if action in {"gui_wait_text", "gui_click_text"} and "|" in raw:
        return raw.split("|", 1)[0].strip()
    return raw


def verify_gui_action(action: str, value: str | None = None, ui_lang: str | None = None) -> dict:
    action = (action or "").strip().lower()
    outcome = get_action_outcome(action)
    if outcome is None:
        return {"ok": False, "reason": "gui_not_executed"}
    if not outcome.get("ok"):
        return {
            "ok": False,
            "reason": outcome.get("reason") or "gui_action_failed",
            "details": outcome.get("meta") or {},
        }
    if action == "gui_map":
        summary = get_last_gui_map_summary()
        count = int(summary.get("count") or 0)
        if count <= 0:
            return {"ok": False, "reason": "map_empty", "details": summary}
    meta = outcome.get("meta") or {}
    if action in {"gui_click_text", "gui_wait_text"}:
        target = _target_from_value(action, value, meta)
        if target and not screen_contains_text(target, ui_lang=ui_lang):
            return {
                "ok": False,
                "reason": "no_text",
                "details": {"target": target, **meta},
            }
    if action == "gui_click_index" and not meta.get("x") and not meta.get("y"):
        return {"ok": False, "reason": "map_index", "details": meta}
    return {"ok": True, "reason": "gui_action_ok", "details": meta}
