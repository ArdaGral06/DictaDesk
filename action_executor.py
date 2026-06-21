import json
import re
import subprocess
import sys
from pathlib import Path
from threading import Event

from action_context import record_action_outcome
from action_parsers import clean_youtube_query, detect_browser_request, looks_like_path, looks_like_url
from agent_memory import load_memory, save_memory, update_memory
from automation_settings import AutomationSettings
from config import APP_LAUNCH_TIMEOUT, CODE_PROJECTS_DIR, OCR_LANG_BOTH
from i18n import t
from platform_actions import (
    adjust_brightness,
    adjust_volume,
    browser_action,
    canonical_app_name,
    close_process,
    copy_path,
    delete_path,
    desktop_action,
    disk_usage,
    ensure_app_focus,
    find_files,
    focus_window,
    gui_click,
    gui_click_image,
    gui_click_index,
    gui_click_text,
    gui_map_text,
    gui_wait,
    gui_wait_image,
    gui_wait_text,
    is_app_window_open,
    largest_files,
    list_dir,
    lock_system,
    make_dir,
    media_action,
    move_path,
    ocr_text,
    open_dir,
    open_search,
    open_target,
    open_url_in_browser,
    open_youtube_first_result,
    rename_path,
    restart_system,
    scroll_action,
    send_hotkey,
    set_brightness,
    set_volume,
    shutdown_system,
    sleep_system,
    start_app_verified,
    take_screenshot,
    toggle_mute,
    type_text,
    wait_for_app_window,
    write_file,
    zoom_action,
)
from form_automation import build_form_profile
from shell_guard import blocked_shell_reason, run_subprocess_cancellable
from task_cancel import TaskCancelled
from utils import fold_text, parse_int_from_text
from web_automation import WebAutomation

def _action_payload(value: str | None, tail: str | None) -> str:
    tail = (tail or "").strip()
    if tail:
        return tail
    return (value or "").strip()


def _parse_level_request(text: str, lang: str) -> tuple[str, int | None]:
    import re

    if not text:
        return "set", None

    folded = fold_text(text)
    tokens = re.findall(r"[a-z0-9]+", folded)

    up_words = {
        "up",
        "increase",
        "raise",
        "louder",
        "brighter",
        "artir",
        "arttir",
        "yukselt",
        "yukari",
        "parlaklastir",
    }
    down_words = {
        "down",
        "decrease",
        "lower",
        "quieter",
        "darker",
        "dim",
        "azalt",
        "kis",
        "indir",
        "asagi",
        "karanlik",
        "kapat",
    }

    mode = "set"
    if any(t in up_words for t in tokens):
        mode = "up"
    elif any(t in down_words for t in tokens):
        mode = "down"

    amount = parse_int_from_text(text, lang)
    if any(t in ("max", "full", "maksimum", "maximum", "loudest") for t in tokens):
        return "set", 100
    if any(t in ("min", "minimum", "lowest", "en dusuk", "endusuk") for t in tokens):
        return "set", 0
    if any(t in ("half", "yarim", "yari", "medium", "orta") for t in tokens):
        return "set", 50

    if mode in ("up", "down") and amount is None:
        amount = 10
    if mode == "set" and amount is None and any(t in up_words for t in tokens):
        mode, amount = "up", 10
    if mode == "set" and amount is None and any(t in down_words for t in tokens):
        mode, amount = "down", 10
    return mode, amount


def _parse_volume_request(text: str, lang: str) -> tuple[str, int | None]:
    return _parse_level_request(text, lang)


def _parse_brightness_request(text: str, lang: str) -> tuple[str, int | None]:
    return _parse_level_request(text, lang)


def _parse_scroll_request(text: str, lang: str) -> tuple[str, int]:
    import re

    folded = fold_text(text or "")
    tokens = re.findall(r"[a-z0-9]+", folded)
    direction = "down"
    if any(t in ("up", "yukari", "yukarı") for t in tokens):
        direction = "up"
    elif any(t in ("down", "asagi", "aşağı") for t in tokens):
        direction = "down"
    amount = parse_int_from_text(text, lang)
    if amount is None:
        amount = 3
    return direction, max(1, amount)


def _normalize_file_content(content: str | None) -> str:
    text = content or ""
    if "\\n" in text and text.count("\n") < 3:
        text = text.replace("\\t", "\t").replace("\\n", "\n").replace('\\"', '"')
    return text


def _parse_pair_value(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    if "->" in text:
        left, right = text.split("->", 1)
    elif "|" in text:
        left, right = text.split("|", 1)
    elif "," in text:
        left, right = text.split(",", 1)
    else:
        return None, None
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None, None
    return left, right


def _parse_xy(text: str) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    parts = [p.strip() for p in re.split(r"[,\s]+", text) if p.strip()]
    if len(parts) < 2:
        return None, None
    try:
        return int(float(parts[0])), int(float(parts[1]))
    except Exception:
        return None, None


def _parse_web_click(text: str) -> tuple[str, str]:
    value = (text or "").strip()
    if value.lower().startswith("css:"):
        return "css", value[4:].strip()
    if value.lower().startswith("text:"):
        return "text", value[5:].strip()
    return "text", value


def _parse_browser_payload(text: str) -> tuple[str | None, str]:
    value = (text or "").strip()
    if "|" in value:
        left, right = value.split("|", 1)
        browser = left.strip()
        target = right.strip()
        return (browser or None), target
    return None, value


def _parse_kv_or_text(text: str) -> dict:
    value = (text or "").strip()
    data: dict[str, str] = {}
    if not value:
        return data
    parts = [p.strip() for p in re.split(r"[;\n]+", value) if p.strip()]
    for part in parts:
        if "=" in part:
            key, val = part.split("=", 1)
        elif ":" in part and re.match(r"^[A-Za-z_ ]{2,20}\s*:", part):
            key, val = part.split(":", 1)
        else:
            continue
        key = key.strip().lower().replace(" ", "_")
        val = val.strip()
        if key and val:
            data[key] = val
    if data:
        return data
    return {"name": value}


def _parse_kv_payload(text: str) -> dict:
    import json
    import re

    raw = (text or "").strip()
    if not raw:
        return {}
    if raw.startswith("{") and raw.endswith("}"):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    pairs = re.split(r"[;|]+", raw)
    out: dict[str, str] = {}
    for item in pairs:
        if not item.strip():
            continue
        if "=" in item:
            key, val = item.split("=", 1)
        elif ":" in item:
            key, val = item.split(":", 1)
        else:
            continue
        key = key.strip().lower()
        val = val.strip()
        if key:
            out[key] = val
    return out


def _build_profile() -> dict:
    return build_form_profile(load_memory())


def _resolve_code_path(raw_path: str) -> Path:
    path = Path((raw_path or "").strip()).expanduser()
    if not path.is_absolute():
        path = (CODE_PROJECTS_DIR / path).resolve()
    else:
        path = path.resolve()
    return path


def _path_under_code_projects(path: Path) -> bool:
    root = CODE_PROJECTS_DIR.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _run_code_file(
    raw_path: str,
    cancel_event: Event | None = None,
) -> tuple[bool, str]:
    path = _resolve_code_path(raw_path)
    if not path.exists() or not path.is_file():
        record_action_outcome("run_code", False, "file_missing")
        return False, "file_missing"
    if not _path_under_code_projects(path):
        record_action_outcome("run_code", False, "path_not_allowed")
        return False, "path_not_allowed"
    suffix = path.suffix.lower()
    if suffix == ".py":
        cmd = [sys.executable, str(path)]
    elif suffix in (".js", ".mjs"):
        cmd = ["node", str(path)]
    elif suffix in (".html", ".htm"):
        open_target(str(path))
        record_action_outcome("run_code", True, "opened_html")
        return True, "opened_html"
    elif suffix in (".bat", ".cmd"):
        cmd = ["cmd", "/c", str(path)]
    elif suffix == ".ps1":
        cmd = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(path),
        ]
    else:
        record_action_outcome("run_code", False, "unsupported_code_type")
        return False, "unsupported_code_type"
    code, stdout, stderr, err = run_subprocess_cancellable(
        cmd,
        cwd=str(path.parent),
        timeout=120.0,
        cancel_event=cancel_event,
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip())
    if err == "cancelled":
        record_action_outcome("run_code", False, "cancelled")
        return False, "cancelled"
    if err == "timeout":
        record_action_outcome("run_code", False, "run_code_failed:timeout")
        return False, "run_code_failed:timeout"
    if err == "start_failed":
        record_action_outcome("run_code", False, "run_code_not_executed")
        return False, "run_code_not_executed"
    if code != 0:
        reason = f"run_code_failed:{code}"
        record_action_outcome("run_code", False, reason)
        return False, reason
    record_action_outcome("run_code", True, "process_exit_zero")
    return True, "process_exit_zero"


def _routine_section() -> dict:
    memory = load_memory()
    section = memory.get("routines", {})
    return section if isinstance(section, dict) else {}


def _routine_value(name: str) -> str | None:
    key_folded = fold_text(name or "")
    if not key_folded:
        return None
    for key, entry in _routine_section().items():
        if fold_text(key) == key_folded:
            val = entry.get("value") if isinstance(entry, dict) else entry
            return str(val) if val else None
    return None


def _map_gui_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "text_not_found" in msg:
        return "no_text"
    if "image_not_found" in msg:
        return "gui_image_not_found"
    if "map_index" in msg or "invalid index" in msg:
        return "map_index"
    return "gui_action_failed"


def _vlm_click_fallback(vlm, target: str, ui_lang: str) -> tuple[bool, str | None]:
    """Last-resort click: ask the VLM to locate the target on a screenshot, then click."""
    if vlm is None or not getattr(vlm, "enabled", False) or getattr(vlm, "llm", None) is None:
        return False, "no_text"
    if not hasattr(vlm, "locate_click"):
        return False, "no_text"
    try:
        shot = take_screenshot(None)
    except Exception:
        return False, "no_text"
    try:
        x, y, _reason, _raw = vlm.locate_click(target, shot, ui_lang=ui_lang)
    except Exception:
        return False, "no_text"
    if x is None or y is None:
        return False, "no_text"
    try:
        gui_click(int(x), int(y), clicks=1)
    except Exception:
        return False, "gui_action_failed"
    record_action_outcome(
        "gui_click_text", True, "gui_action_ok", meta={"x": x, "y": y, "via": "vlm"}
    )
    return True, None


def _run_gui_step(action_name: str, fn, *, meta: dict | None = None) -> tuple[bool, str | None]:
    try:
        result = fn()
        details = dict(meta or {})
        if isinstance(result, tuple) and len(result) >= 2:
            details.setdefault("x", result[0])
            details.setdefault("y", result[1])
        record_action_outcome(action_name, True, "gui_action_ok", meta=details)
        return True, None
    except TaskCancelled:
        record_action_outcome(action_name, False, "cancelled", meta=meta or {})
        return False, "cancelled"
    except ValueError as exc:
        reason = _map_gui_error(exc)
        record_action_outcome(action_name, False, reason, meta=meta or {})
        return False, reason
    except Exception:
        record_action_outcome(action_name, False, "gui_action_failed", meta=meta or {})
        return False, "gui_action_failed"


def execute_action(
    action: str | None,
    value: str | None,
    tail_text: str | None,
    ui_lang: str,
    allow_blocked: bool = False,
    automation: AutomationSettings | None = None,
    web: WebAutomation | None = None,
    cancel_event: Event | None = None,
    llm=None,
    vlm=None,
):
    automation = automation or AutomationSettings()
    gui_actions = {
        "gui_click_text",
        "gui_click_image",
        "gui_click",
        "gui_wait",
        "gui_wait_text",
        "gui_wait_image",
        "gui_map",
        "gui_click_index",
    }
    web_actions = {
        "web_open",
        "web_click",
        "web_type",
        "web_press",
        "web_wait",
        "web_search",
        "youtube_search",
        "web_form_fill",
    }
    if not action:
        return False, "missing"
    if action in gui_actions and not automation.gui_enabled:
        return False, "gui_disabled"
    if action in web_actions and not automation.web_enabled:
        return False, "web_disabled"
    if action in web_actions and web is None:
        web = WebAutomation()
    payload = _action_payload(value, tail_text)
    if action == "start":
        if not payload:
            return False, "missing"
        app_name = canonical_app_name(payload)
        try:
            ok, _method = start_app_verified(
                payload, ui_lang=ui_lang, allow_blocked=allow_blocked
            )
            if not ok:
                return False, "app_not_open"
            if not ensure_app_focus(app_name, ui_lang=ui_lang):
                return False, "focus_failed"
        except RuntimeError as exc:
            if str(exc) == "blocked_target":
                return False, "blocked"
            raise
    elif action == "focus":
        if not payload:
            return False, "missing"
        app_name = canonical_app_name(payload)
        if not is_app_window_open(app_name) and not wait_for_app_window(app_name, timeout=APP_LAUNCH_TIMEOUT):
            return False, "app_not_open"
        if not ensure_app_focus(app_name, ui_lang=ui_lang):
            return False, "focus_failed"
    elif action in ("open", "url"):
        if not payload:
            return False, "missing"
        # If payload is an app name and it's already open, just focus it.
        if not looks_like_url(payload) and not looks_like_path(payload):
            app_name = canonical_app_name(payload)
            if is_app_window_open(app_name):
                if not ensure_app_focus(app_name, ui_lang=ui_lang):
                    return False, "focus_failed"
                return True, None
        try:
            open_target(payload, ui_lang=ui_lang, allow_blocked=allow_blocked)
        except RuntimeError as exc:
            if str(exc) == "blocked_target":
                return False, "blocked"
            raise
        if not looks_like_url(payload) and not looks_like_path(payload):
            app_name = canonical_app_name(payload)
            if not wait_for_app_window(app_name, timeout=APP_LAUNCH_TIMEOUT):
                return False, "app_not_open"
            if not ensure_app_focus(app_name, ui_lang=ui_lang):
                return False, "focus_failed"
    elif action == "close":
        if not payload:
            return False, "missing"
        if not close_process(payload):
            return False, "app_still_open"
    elif action == "delete":
        if not payload:
            return False, "missing"
        delete_path(payload)
    elif action == "cmd":
        if not payload:
            return False, "missing"
        block = blocked_shell_reason(payload)
        if block:
            return False, f"shell_blocked:{block}"
        subprocess.Popen(["cmd", "/c", payload])
    elif action == "powershell":
        if not payload:
            return False, "missing"
        block = blocked_shell_reason(payload)
        if block:
            return False, f"shell_blocked:{block}"
        subprocess.Popen(["powershell", "-NoProfile", "-Command", payload])
    elif action == "type":
        if not payload:
            return False, "missing"
        type_text(payload)
    elif action == "hotkey":
        if not payload:
            return False, "missing"
        send_hotkey(payload)
    elif action == "volume":
        if not payload:
            return False, "missing"
        mode, amount = _parse_volume_request(payload, ui_lang)
        if amount is None:
            return False, "missing"
        if mode == "set":
            set_volume(max(0, min(100, amount)))
        elif mode == "up":
            adjust_volume(abs(amount))
        else:
            adjust_volume(-abs(amount))
    elif action == "brightness":
        if not payload:
            return False, "missing"
        mode, amount = _parse_brightness_request(payload, ui_lang)
        if amount is None:
            return False, "missing"
        if mode == "set":
            set_brightness(max(0, min(100, amount)))
        elif mode == "up":
            adjust_brightness(abs(amount))
        else:
            adjust_brightness(-abs(amount))
    elif action == "browser":
        if not payload:
            return False, "missing"
        browser_action(payload)
    elif action == "desktop":
        desktop_action(payload)
    elif action == "scroll":
        direction, amount = _parse_scroll_request(payload, ui_lang)
        scroll_action(direction, amount)
    elif action == "zoom":
        if not payload:
            return False, "missing"
        zoom_action(payload)
    elif action == "mute":
        toggle_mute()
    elif action == "list_dir":
        items = list_dir(payload or None)
        label = payload if payload else "Desktop"
        print(t(ui_lang, "list_dir_result", path=label, count=len(items)))
        for name in items:
            print(t(ui_lang, "list_dir_item", name=name))
    elif action == "find_files":
        data = _parse_kv_or_text(payload)
        results = find_files(
            name=data.get("name", data.get("query", "")),
            extension=data.get("extension", data.get("ext", "")),
            path=data.get("path", data.get("folder", "")),
            max_results=int(data.get("limit", data.get("max_results", 20)) or 20),
        )
        print(t(ui_lang, "find_files_result", count=len(results)))
        for item in results:
            print(t(ui_lang, "find_files_item", path=item))
    elif action == "largest_files":
        data = _parse_kv_or_text(payload)
        results = largest_files(
            path=data.get("path", data.get("folder", payload or "")),
            count=int(data.get("count", data.get("limit", 10)) or 10),
        )
        print(t(ui_lang, "largest_files_result", count=len(results)))
        for item in results:
            print(t(ui_lang, "largest_files_item", item=item))
    elif action == "disk_usage":
        data = _parse_kv_or_text(payload)
        usage = disk_usage(data.get("path", data.get("folder", payload or "")))
        print(
            t(
                ui_lang,
                "disk_usage_result",
                path=usage["path"],
                total=usage["total"],
                used=usage["used"],
                free=usage["free"],
                percent=usage["percent"],
            )
        )
    elif action == "open_dir":
        open_dir(payload or None)
    elif action == "mkdir":
        if not payload:
            return False, "missing"
        make_dir(payload)
    elif action == "write_file":
        path, content = _parse_pair_value(payload)
        if not path or content is None:
            return False, "missing"
        write_file(path, _normalize_file_content(content))
    elif action == "run_code":
        if not payload:
            return False, "missing"
        ok, reason = _run_code_file(payload, cancel_event=cancel_event)
        if not ok:
            return False, reason
    elif action == "routine_create":
        name, routine_text = _parse_pair_value(payload)
        if not name or not routine_text:
            return False, "missing"
        update_memory({"routines": {name: routine_text}})
        print(t(ui_lang, "routine_saved", name=name))
    elif action == "routine_list":
        routines = _routine_section()
        if not routines:
            print(t(ui_lang, "routine_empty"))
        for name, entry in routines.items():
            val = entry.get("value") if isinstance(entry, dict) else entry
            print(t(ui_lang, "routine_item", name=name, value=val))
    elif action == "routine_delete":
        if not payload:
            return False, "missing"
        memory = load_memory()
        routines = memory.setdefault("routines", {})
        removed = None
        for key in list(routines.keys()):
            if fold_text(key) == fold_text(payload):
                removed = key
                routines.pop(key, None)
                break
        if removed is None:
            return False, "routine_missing"
        from agent_memory import save_memory

        save_memory(memory)
        print(t(ui_lang, "routine_deleted", name=removed))
    elif action == "routine_run":
        if not payload:
            return False, "missing"
        if not _routine_value(payload):
            return False, "routine_missing"
        print(t(ui_lang, "routine_found", name=payload))
    elif action == "copy":
        src, dst = _parse_pair_value(payload)
        if not src or not dst:
            return False, "missing"
        copy_path(src, dst)
    elif action == "move":
        src, dst = _parse_pair_value(payload)
        if not src or not dst:
            return False, "missing"
        move_path(src, dst)
    elif action == "rename":
        src, dst = _parse_pair_value(payload)
        if not src or not dst:
            return False, "missing"
        rename_path(src, dst)
    elif action == "lock":
        lock_system()
    elif action == "restart":
        restart_system()
    elif action == "shutdown":
        shutdown_system()
    elif action == "sleep":
        sleep_system()
    elif action == "screenshot":
        path = take_screenshot(payload or None)
        print(t(ui_lang, "screenshot_saved", path=path))
    elif action == "ocr":
        ocr_lang = OCR_LANG_BOTH
        text, src = ocr_text(payload, lang=ocr_lang)
        print(t(ui_lang, "ocr_source", path=src))
        if text:
            print(t(ui_lang, "ocr_text", text=text))
        else:
            print(t(ui_lang, "ocr_empty"))
            return False, "no_text"
    elif action == "gui_click_text":
        if not payload:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        ok, reason = _run_gui_step(
            "gui_click_text",
            lambda: gui_click_text(payload, ui_lang=ui_lang, cancel_event=cancel_event),
            meta={"target": payload},
        )
        if reason == "cancelled":
            return False, "cancelled"
        if not ok:
            vok, _vreason = _vlm_click_fallback(vlm, payload, ui_lang)
            if vok:
                print(t(ui_lang, "vlm_click_used"))
            else:
                return False, reason
    elif action == "gui_click_image":
        if not payload:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        path, thresh = payload, 0.85
        if "|" in payload:
            left, right = payload.split("|", 1)
            path = left.strip()
            try:
                thresh = float(right.strip())
            except Exception:
                thresh = 0.85
        ok, reason = _run_gui_step(
            "gui_click_image",
            lambda: gui_click_image(path, threshold=thresh),
            meta={"target": path},
        )
        if not ok:
            return False, reason
    elif action == "gui_click":
        x, y = _parse_xy(payload)
        if x is None or y is None:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        ok, reason = _run_gui_step(
            "gui_click",
            lambda: gui_click(x, y),
            meta={"x": x, "y": y},
        )
        if not ok:
            return False, reason
    elif action == "gui_wait":
        if not payload:
            return False, "missing"
        try:
            seconds = float(payload)
        except Exception:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        ok, reason = _run_gui_step(
            "gui_wait",
            lambda: gui_wait(seconds),
            meta={"seconds": seconds},
        )
        if not ok:
            return False, reason
    elif action == "gui_wait_text":
        if not payload:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        target = payload
        timeout = 6.0
        if "|" in payload:
            left, right = payload.split("|", 1)
            target = left.strip()
            try:
                timeout = float(right.strip())
            except Exception:
                timeout = 6.0
        ok, reason = _run_gui_step(
            "gui_wait_text",
            lambda: gui_wait_text(
                target, timeout_sec=timeout, ui_lang=ui_lang, cancel_event=cancel_event
            ),
            meta={"target": target},
        )
        if not ok:
            return False, reason
    elif action == "gui_wait_image":
        if not payload:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        path, thresh, timeout = payload, 0.85, 6.0
        if "|" in payload:
            parts = [p.strip() for p in payload.split("|") if p.strip()]
            if parts:
                path = parts[0]
            if len(parts) > 1:
                try:
                    thresh = float(parts[1])
                except Exception:
                    thresh = 0.85
            if len(parts) > 2:
                try:
                    timeout = float(parts[2])
                except Exception:
                    timeout = 6.0
        ok, reason = _run_gui_step(
            "gui_wait_image",
            lambda: gui_wait_image(path, threshold=thresh, timeout_sec=timeout),
            meta={"target": path},
        )
        if not ok:
            return False, reason
    elif action == "gui_map":
        path, items = gui_map_text(ui_lang=ui_lang)
        if not items:
            record_action_outcome("gui_map", False, "map_empty")
            return False, "map_empty"
        record_action_outcome("gui_map", True, "gui_action_ok", meta={"count": len(items), "path": path})
        print(t(ui_lang, "gui_map_saved", path=path, count=len(items)))
        for idx, item in enumerate(items, start=1):
            print(
                t(
                    ui_lang,
                    "gui_map_item",
                    idx=idx,
                    text=item.get("text", ""),
                    x=item.get("left", 0),
                    y=item.get("top", 0),
                )
            )
    elif action == "gui_click_index":
        if not payload:
            return False, "missing"
        try:
            idx = int(float(payload))
        except Exception:
            return False, "missing"
        ok, reason = _run_gui_step(
            "gui_click_index",
            lambda: gui_click_index(idx),
            meta={"index": idx},
        )
        if not ok:
            return False, reason
    elif action == "web_open":
        if not payload:
            return False, "missing"
        try:
            web.open(payload, cancel_event=cancel_event)
        except TaskCancelled:
            return False, "cancelled"
    elif action == "web_search":
        if not payload:
            return False, "missing"
        try:
            web.search(payload, cancel_event=cancel_event)
        except TaskCancelled:
            return False, "cancelled"
    elif action == "web_form_fill":
        data = _parse_kv_payload(payload)
        profile = _build_profile()
        if automation.web_enabled and web is not None:
            try:
                web.fill_form(data, profile, cancel_event=cancel_event)
            except TaskCancelled:
                return False, "cancelled"
            except RuntimeError as exc:
                reason = str(exc).split(":")[0]
                return False, reason
        elif automation.gui_enabled:
            from uia_automation import fill_native_form

            result = fill_native_form(data, profile)
            if web is not None:
                web.last_action = {"action": "web_form_fill", **result}
            if not result.get("ok"):
                return False, str(result.get("reason") or "form_fill_failed")
        else:
            return False, "web_disabled"
    elif action == "web_click":
        if not payload:
            return False, "missing"
        mode, value = _parse_web_click(payload)
        if not value:
            return False, "missing"
        try:
            web.click(mode, value, cancel_event=cancel_event)
        except TaskCancelled:
            return False, "cancelled"
    elif action == "web_type":
        if not payload:
            return False, "missing"
        selector, text_value = _parse_pair_value(payload)
        try:
            if selector and text_value:
                if selector.lower().startswith("css:"):
                    selector = selector[4:].strip()
                web.type_text(text_value, selector=selector, cancel_event=cancel_event)
            else:
                web.type_text(payload, cancel_event=cancel_event)
        except TaskCancelled:
            return False, "cancelled"
    elif action == "web_press":
        if not payload:
            return False, "missing"
        try:
            web.press(payload, cancel_event=cancel_event)
        except TaskCancelled:
            return False, "cancelled"
    elif action == "web_wait":
        if not payload:
            return False, "missing"
        try:
            seconds = float(payload)
        except Exception:
            return False, "missing"
        try:
            web.wait(seconds, cancel_event=cancel_event)
        except TaskCancelled:
            return False, "cancelled"
    elif action == "browser_open":
        if not payload:
            return False, "missing"
        browser, target = _parse_browser_payload(payload)
        if not target:
            return False, "missing"
        open_url_in_browser(browser, target)
    elif action == "browser_search":
        if not payload:
            return False, "missing"
        from urllib.parse import quote_plus
        from config import WEB_SEARCH_URL_BROWSER

        browser, query = _parse_browser_payload(payload)
        if not query:
            return False, "missing"
        url = WEB_SEARCH_URL_BROWSER.format(query=quote_plus(query))
        open_url_in_browser(browser, url)
    elif action == "media":
        if not payload:
            return False, "missing"
        media_action(payload)
    elif action == "url_search":
        if not payload:
            return False, "missing"
        open_search(payload)
    elif action == "youtube_search":
        if not payload:
            return False, "missing"
        browser, query = _parse_browser_payload(payload)
        clean_query = clean_youtube_query(query or payload)
        if not clean_query:
            clean_query = (query or payload).strip()
        if browser:
            from urllib.parse import quote_plus
            if not open_youtube_first_result(clean_query, browser=browser, ui_lang=ui_lang):
                url = f"https://www.youtube.com/results?search_query={quote_plus(clean_query)}"
                open_url_in_browser(browser, url)
        else:
            if web is None:
                web = WebAutomation()
            try:
                web.youtube_search(clean_query, cancel_event=cancel_event)
            except TaskCancelled:
                return False, "cancelled"
    elif action == "reminder":
        if not payload:
            return False, "missing"
        from reminders import schedule_reminder

        ok, info = schedule_reminder(payload)
        if not ok:
            return False, info
        record_action_outcome("reminder", True, "reminder_set", meta={"when": info})
        print(t(ui_lang, "reminder_set", when=info))
    elif action == "youtube_summarize":
        if not payload:
            return False, "missing"
        from youtube_summary import summarize_youtube

        ok, info = summarize_youtube(payload, llm=llm, ui_lang=ui_lang)
        if not ok:
            return False, info
        print(info)
    elif action == "file_process":
        if not payload:
            return False, "missing"
        from file_processor import process_file

        ok, info = process_file(payload, llm=llm, vlm=vlm, ui_lang=ui_lang)
        if not ok:
            return False, info
        print(info)
    elif action == "dev_project":
        if not payload:
            return False, "missing"
        from dev_agent import build_project

        ok, info = build_project(payload, llm=llm, ui_lang=ui_lang, cancel_event=cancel_event)
        if not ok:
            return False, info
        print(t(ui_lang, "dev_project_done", info=info))
    else:
        return False, "unknown"
    return True, None
