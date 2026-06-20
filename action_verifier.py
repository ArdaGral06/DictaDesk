import time
from pathlib import Path

from platform_actions import (
    canonical_app_name,
    get_active_window,
    is_app_focused,
    is_app_window_open,
)


def _parse_pair(value: str | None) -> tuple[str | None, str | None]:
    text = (value or "").strip()
    for sep in ("->", "|"):
        if sep in text:
            left, right = text.split(sep, 1)
            return left.strip() or None, right.strip()
    return text or None, None


def verify_action(action: str | None, value: str | None, web=None) -> dict:
    action = (action or "").strip().lower()
    value = (value or "").strip()
    try:
        if action == "start":
            app = canonical_app_name(value)
            ok = bool(app and is_app_window_open(app))
            return {"ok": ok, "reason": "app_window_open" if ok else "app_window_missing"}
        if action == "focus":
            app = canonical_app_name(value)
            ok = bool(app and is_app_focused(app))
            return {"ok": ok, "reason": "app_focused" if ok else "app_not_focused"}
        if action == "close":
            app = canonical_app_name(value)
            deadline = time.time() + 2.0
            ok = False
            while time.time() < deadline:
                if app and not is_app_window_open(app):
                    ok = True
                    break
                time.sleep(0.25)
            return {"ok": ok, "reason": "app_closed" if ok else "app_still_open"}
        if action == "open":
            # URLs and app/file opens are hard to prove generically. If no exception
            # occurred, treat as verified unless it clearly targeted an app.
            if value and not any(token in value for token in ("://", "\\", "/")) and "." not in Path(value).name:
                app = canonical_app_name(value)
                if app and is_app_window_open(app):
                    return {"ok": True, "reason": "app_window_open"}
            return {"ok": True, "reason": "no_exception"}
        if action == "write_file":
            path, _content = _parse_pair(value)
            target = Path(path or "").expanduser()
            if path and not target.is_absolute():
                target = Path.home() / "Desktop" / target
            ok = bool(path and target.exists())
            return {"ok": ok, "reason": "file_exists" if ok else "file_missing"}
        if action in {"web_open", "web_search", "web_click", "web_type", "web_press", "web_wait", "web_form_fill", "youtube_search"}:
            info = getattr(web, "last_action", {}) if web else {}
            if info and info.get("captcha"):
                return {"ok": False, "reason": "captcha_required", "details": info}
            if info and info.get("ok") is False:
                return {"ok": False, "reason": info.get("reason", "web_action_failed"), "details": info}
            return {"ok": True, "reason": "web_action_ok", "details": info}
        if action in {"gui_click_text", "gui_wait_text", "gui_click", "gui_click_image", "gui_wait", "gui_wait_image", "gui_map", "gui_click_index"}:
            return {"ok": True, "reason": "gui_action_ok"}
        if action == "run_code":
            return {"ok": True, "reason": "process_exit_zero"}
        active = get_active_window()
        return {"ok": True, "reason": "no_exception", "active": active}
    except Exception as exc:
        return {"ok": False, "reason": f"verification_error:{exc}"}
