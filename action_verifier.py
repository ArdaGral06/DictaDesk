import os
import time
from pathlib import Path

from action_context import get_action_outcome


def _expand_path(path: str | None) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(path or "")))).expanduser()
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


def verify_action(action: str | None, value: str | None, web=None, ui_lang: str | None = None) -> dict:
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
            if value and ("://" in value or "\\" in value or "/" in value or Path(value).suffix):
                target = _expand_path(value)
                if not target.is_absolute():
                    target = Path.home() / "Desktop" / target
                ok = target.exists()
                return {"ok": ok, "reason": "path_exists" if ok else "path_missing"}
            if value and not any(token in value for token in ("://", "\\", "/")) and "." not in Path(value).name:
                app = canonical_app_name(value)
                if app:
                    deadline = time.time() + 3.0
                    while time.time() < deadline:
                        if is_app_window_open(app):
                            return {"ok": True, "reason": "app_window_open"}
                        time.sleep(0.25)
                    return {"ok": False, "reason": "app_not_open"}
            return {"ok": True, "reason": "no_exception"}
        if action == "write_file":
            path, content = _parse_pair(value)
            target = _expand_path(path)
            if path and not target.is_absolute():
                target = Path.home() / "Desktop" / target
            ok = bool(path and target.exists() and target.stat().st_size > 0)
            return {"ok": ok, "reason": "file_exists" if ok else "file_missing"}
        if action == "mkdir":
            target = _expand_path(value)
            if value and not target.is_absolute():
                target = Path.home() / "Desktop" / target
            ok = bool(value and target.is_dir())
            return {"ok": ok, "reason": "dir_exists" if ok else "dir_missing"}
        if action in {"web_open", "web_search", "web_click", "web_type", "web_press", "web_wait", "web_form_fill", "youtube_search"}:
            info = getattr(web, "last_action", {}) if web else {}
            if info and info.get("captcha"):
                return {"ok": False, "reason": "captcha_required", "details": info}
            if info and info.get("ok") is False:
                return {"ok": False, "reason": info.get("reason", "web_action_failed"), "details": info}
            if action == "web_form_fill":
                fields = info.get("fields") if isinstance(info, dict) else None
                if not fields:
                    return {"ok": False, "reason": "no_fields_filled", "details": info}
            if action == "youtube_search":
                url = str((info or {}).get("url") or "")
                ok = ("watch?v=" in url) or ("youtu.be/" in url)
                return {
                    "ok": ok,
                    "reason": "youtube_video_opened" if ok else "youtube_video_not_opened",
                    "details": info,
                }
            return {"ok": True, "reason": "web_action_ok", "details": info}
        if action in {"gui_click_text", "gui_wait_text", "gui_click", "gui_click_image", "gui_wait", "gui_wait_image", "gui_map", "gui_click_index"}:
            from gui_verifier import verify_gui_action

            return verify_gui_action(action, value, ui_lang=ui_lang)
        if action == "run_code":
            outcome = get_action_outcome("run_code")
            if outcome is None:
                return {"ok": False, "reason": "run_code_not_executed"}
            ok = bool(outcome.get("ok"))
            reason = str(outcome.get("reason") or ("process_exit_zero" if ok else "run_code_failed"))
            return {"ok": ok, "reason": reason}
        active = get_active_window()
        return {"ok": True, "reason": "no_exception", "active": active}
    except Exception as exc:
        return {"ok": False, "reason": f"verification_error:{exc}"}
