import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from pynput import keyboard

from audio_io import Recorder
from commands_manager import match_command
from config import (
    APP_ALIASES,
    LAST_TRANSCRIPT_FILE,
    OCR_LANG_BOTH,
    TRANSCRIPTS_DIR,
    TTS_FAIL_TEXT,
    TTS_SUCCESS_TEXT,
    AUTO_MAP_ENABLED,
    AUTO_MAP_INTERVAL_SEC,
    APP_LAUNCH_TIMEOUT,
)
from engine import get_stt_label
from i18n import t
from llm_engine import DANGEROUS_ACTIONS, infer_quick_actions, _fix_actions_from_text
from platform_actions import (
    adjust_volume,
    adjust_brightness,
    browser_action,
    close_process,
    delete_path,
    desktop_action,
    gui_click,
    gui_click_image,
    gui_click_text,
    gui_click_index,
    gui_wait,
    gui_wait_image,
    gui_wait_text,
    gui_map_text,
    focus_window,
    ensure_app_focus,
    is_app_window_open,
    wait_for_app_window,
    get_open_windows,
    get_active_window,
    get_system_stats,
    get_last_gui_map_summary,
    lock_system,
    find_files,
    largest_files,
    disk_usage,
    list_dir,
    media_action,
    make_dir,
    move_path,
    open_dir,
    open_search,
    open_url_in_browser,
    open_target,
    open_youtube_first_result,
    ocr_text,
    rename_path,
    restart_system,
    scroll_action,
    send_hotkey,
    set_volume,
    set_brightness,
    shutdown_system,
    sleep_system,
    start_app,
    start_app_verified,
    take_screenshot,
    toggle_mute,
    type_text,
    write_file,
    copy_path,
    zoom_action,
    normalize_app_query,
    canonical_app_name,
)
from web_automation import WebAutomation
from ui_popup import show_status_popup
from agent_queue import AgentQueue
from agent_memory import load_memory, update_memory
from automation_settings import AutomationSettings
from action_verifier import verify_action
from debug_replay import write_debug_replay
from agent_error_policy import (
    ERROR_ABORT,
    ERROR_RETRY,
    ERROR_SKIP,
    decide_error_policy,
)
from utils import extract_tail_text, fold_text, parse_int_from_text


def write_transcript(ui_lang, audio_path: Path, result):
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    if result.language and result.language_probability is not None:
        lines.append(
            t(
                ui_lang,
                "detected_language",
                lang=result.language,
                prob=result.language_probability * 100,
            )
        )
        lines.append("-" * 50)
    if result.segments:
        for seg in result.segments:
            try:
                line = f"[{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text}"
            except Exception:
                line = str(seg)
            lines.append(line)
    else:
        lines.append(result.text)

    content = "\n".join(lines) + "\n"
    out_path = TRANSCRIPTS_DIR / f"{audio_path.stem}_transcript.txt"
    out_path.write_text(content, encoding="utf-8")
    LAST_TRANSCRIPT_FILE.write_text(content, encoding="utf-8")
    print(t(ui_lang, "transcript_saved", path=out_path))
    print(t(ui_lang, "last_transcript_saved", path=LAST_TRANSCRIPT_FILE))


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


def _clean_youtube_query(text: str) -> str:
    raw = (text or "").lower()
    # Remove punctuation-like separators
    raw = re.sub(r"[\"'“”‘’.,!?;:()\[\]{}<>]", " ", raw)
    tokens = re.findall(r"[a-z0-9ığüşöç]+", raw, flags=re.IGNORECASE)
    stopwords = {
        # general
        "bana",
        "bir",
        "lütfen",
        "please",
        "the",
        "a",
        "an",
        "and",
        "or",
        # youtube / video
        "youtube",
        "youtubedan",
        "youtubeden",
        "youtube'dan",
        "yt",
        "video",
        "videosu",
        "videosunu",
        "videooo",
        "videoyu",
        "videolar",
        "izle",
        "izlemek",
        "watch",
        "play",
        # open / search
        "aç",
        "ac",
        "open",
        "ara",
        "arama",
        "aramasi",
        "bul",
        # playwright / browser hints
        "playwright",
        "kullanma",
        "kullanmadan",
        "kullanmadan",
        "normal",
        "varsayilan",
        "varsayılan",
        "tarayici",
        "tarayıcı",
        "browser",
        "default",
    }
    cleaned = [t for t in tokens if t and t not in stopwords]
    return " ".join(cleaned).strip()


def _looks_like_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith(("http://", "https://", "www."))


def _looks_like_path(value: str) -> bool:
    v = (value or "").strip()
    return "\\" in v or "/" in v or re.match(r"^[A-Za-z]:\\", v) is not None


def _detect_browser_request(text: str) -> tuple[bool, str | None]:
    phrase = fold_text(text or "")
    avoid_playwright = False
    if any(
        key in phrase
        for key in (
            "playwright kullanma",
            "playwright istemiyorum",
            "normal tarayici",
            "normal tarayıcı",
            "varsayilan tarayici",
            "varsayılan tarayıcı",
            "default browser",
            "normal browser",
            "no playwright",
            "without playwright",
        )
    ):
        avoid_playwright = True
    browser = None
    for name in ("chrome", "edge", "brave", "firefox", "opera"):
        if name in phrase:
            browser = name
            break
    if browser:
        avoid_playwright = True
    return avoid_playwright, browser


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
    memory = load_memory()
    profile = {}
    identity = memory.get("identity", {}) if isinstance(memory, dict) else {}
    for key in ("name", "age", "birthday", "city", "phone", "address", "zip", "username"):
        entry = identity.get(key) if isinstance(identity, dict) else None
        if isinstance(entry, dict):
            val = entry.get("value")
        else:
            val = entry
        if val:
            profile[key] = str(val)
    # fallback to preferences/notes for known keys
    for section_name in ("preferences", "notes"):
        section = memory.get(section_name, {}) if isinstance(memory, dict) else {}
        if not isinstance(section, dict):
            continue
        for key in ("name", "birthday", "city", "phone", "address", "zip", "username"):
            if key in profile:
                continue
            entry = section.get(key)
            if isinstance(entry, dict):
                val = entry.get("value")
            else:
                val = entry
            if val:
                profile[key] = str(val)
    # Provide first/last name from full name if available.
    full_name = profile.get("name")
    if full_name and " " in full_name:
        first, last = full_name.split(" ", 1)
        profile.setdefault("first_name", first.strip())
        profile.setdefault("last_name", last.strip())
    return profile


def _resolve_code_path(raw_path: str) -> Path:
    path = Path((raw_path or "").strip()).expanduser()
    if not path.is_absolute():
        cwd_path = Path.cwd() / path
        desktop_path = Path.home() / "Desktop" / path
        path = cwd_path if cwd_path.exists() else desktop_path
    return path


def _run_code_file(raw_path: str) -> tuple[bool, str]:
    path = _resolve_code_path(raw_path)
    if not path.exists() or not path.is_file():
        return False, "file_missing"
    suffix = path.suffix.lower()
    if suffix == ".py":
        cmd = [sys.executable, str(path)]
    elif suffix in (".js", ".mjs"):
        cmd = ["node", str(path)]
    elif suffix in (".html", ".htm"):
        open_target(str(path))
        return True, "opened_html"
    elif suffix in (".bat", ".cmd"):
        cmd = ["cmd", "/c", str(path)]
    elif suffix == ".ps1":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)]
    else:
        return False, "unsupported_code_type"
    result = subprocess.run(
        cmd,
        cwd=str(path.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if result.returncode != 0:
        return False, f"run_code_failed:{result.returncode}"
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


def execute_action(
    action: str | None,
    value: str | None,
    tail_text: str | None,
    ui_lang: str,
    allow_blocked: bool = False,
    automation: AutomationSettings | None = None,
    web: WebAutomation | None = None,
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
        if not _looks_like_url(payload) and not _looks_like_path(payload):
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
        if not _looks_like_url(payload) and not _looks_like_path(payload):
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
        import subprocess

        subprocess.Popen(payload, shell=True)
    elif action == "powershell":
        if not payload:
            return False, "missing"
        import subprocess

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
        write_file(path, content)
    elif action == "run_code":
        if not payload:
            return False, "missing"
        ok, reason = _run_code_file(payload)
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
        # Auto-generate map for debugging/visibility
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        gui_click_text(payload, ui_lang=ui_lang)
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
        gui_click_image(path, threshold=thresh)
    elif action == "gui_click":
        x, y = _parse_xy(payload)
        if x is None or y is None:
            return False, "missing"
        try:
            gui_map_text(ui_lang=ui_lang)
        except Exception:
            pass
        gui_click(x, y)
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
        gui_wait(seconds)
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
        gui_wait_text(target, timeout_sec=timeout, ui_lang=ui_lang)
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
        gui_wait_image(path, threshold=thresh, timeout_sec=timeout)
    elif action == "gui_map":
        path, items = gui_map_text(ui_lang=ui_lang)
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
        try:
            gui_click_index(idx)
        except ValueError as exc:
            return False, str(exc)
    elif action == "web_open":
        if not payload:
            return False, "missing"
        web.open(payload)
    elif action == "web_search":
        if not payload:
            return False, "missing"
        web.search(payload)
    elif action == "web_form_fill":
        data = _parse_kv_payload(payload)
        profile = _build_profile()
        web.fill_form(data, profile)
    elif action == "web_click":
        if not payload:
            return False, "missing"
        mode, value = _parse_web_click(payload)
        if not value:
            return False, "missing"
        web.click(mode, value)
    elif action == "web_type":
        if not payload:
            return False, "missing"
        selector, text_value = _parse_pair_value(payload)
        if selector and text_value:
            if selector.lower().startswith("css:"):
                selector = selector[4:].strip()
            web.type_text(text_value, selector=selector)
        else:
            web.type_text(payload)
    elif action == "web_press":
        if not payload:
            return False, "missing"
        web.press(payload)
    elif action == "web_wait":
        if not payload:
            return False, "missing"
        try:
            seconds = float(payload)
        except Exception:
            return False, "missing"
        web.wait(seconds)
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
        clean_query = _clean_youtube_query(query or payload)
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
            web.youtube_search(clean_query)
    else:
        return False, "unknown"
    return True, None


class ControlSession:
    def __init__(self, ui_lang, transcriber, commands, tts=None, llm=None, vlm=None, automation=None):
        self.ui_lang = ui_lang
        self.transcriber = transcriber
        self.commands = commands
        self.tts = tts
        self.llm = llm
        self.vlm = vlm
        self.automation = automation or AutomationSettings()
        self.web = WebAutomation()
        self.recorder = Recorder()
        self.recording = False
        self.processing = False
        self.lock = threading.Lock()
        self.confirm_lock = threading.Lock()
        self.pending_confirm = None
        self.cancel_event = threading.Event()
        self.job_queue = AgentQueue(self._run_job, cancel_callback=self.cancel_current)
        self._auto_map_thread = None
        self._auto_map_stop = threading.Event()

    def _build_state_context(self) -> str:
        try:
            windows = get_open_windows(limit=12)
        except Exception:
            windows = []
        try:
            active = get_active_window()
        except Exception:
            active = {}
        try:
            stats = get_system_stats()
        except Exception:
            stats = {}
        win_titles = []
        for item in windows:
            title = item.get("title") or ""
            exe = item.get("exe") or ""
            if title:
                win_titles.append(f"{title} ({exe})" if exe else title)
        active_text = ""
        if active:
            active_text = f"{active.get('title','')} ({active.get('exe','')})".strip()
        cpu = stats.get("cpu")
        ram = stats.get("ram")
        cpu_text = f"{cpu}%" if isinstance(cpu, int) else "unknown"
        ram_text = f"{ram}%" if isinstance(ram, int) else "unknown"
        try:
            from uia_automation import summarize_foreground

            uia_items = summarize_foreground(max_depth=2, max_items=40).get("items", [])
            uia_preview = [
                {
                    "name": item.get("name"),
                    "type": item.get("control_type"),
                    "rect": item.get("rect"),
                    "enabled": item.get("enabled"),
                    "focusable": item.get("focusable"),
                }
                for item in uia_items[:30]
                if item.get("name") or item.get("control_type")
            ]
            uia_context = "; UIA_CONTEXT_JSON: " + json.dumps(
                uia_preview, ensure_ascii=False
            )
        except Exception:
            uia_context = ""
        return (
            f"Current Windows: [{', '.join(win_titles)}]; "
            f"Active: {active_text}; CPU: {cpu_text}; RAM: {ram_text}"
            f"{uia_context}"
        )

    def _observer_context(self, action: str, fail_reason: str) -> str:
        active = get_active_window()
        active_text = f"{active.get('title','')} ({active.get('exe','')})".strip()
        summary = get_last_gui_map_summary()
        count = summary.get("count")
        path = summary.get("path")
        return (
            f"{fail_reason}; Active: {active_text}; "
            f"MapCount: {count}; MapPath: {path}"
        )

    def _request_needs_visual_context(self, text: str) -> bool:
        phrase = fold_text(text or "")
        visual_terms = (
            "tikla",
            "tıkla",
            "bas",
            "buton",
            "ekran",
            "sayfa",
            "form",
            "doldur",
            "sign up",
            "signup",
            "register",
            "kaydol",
            "mesaj",
            "message",
            "dm",
            "gonder",
            "gönder",
            "discord",
            "browser",
            "tarayici",
            "tarayıcı",
        )
        return any(term in phrase for term in visual_terms)

    def _build_visual_context(self, goal: str) -> str:
        try:
            map_path, items = gui_map_text(ui_lang=self.ui_lang)
            ocr_preview = [
                {
                    "text": str(item.get("text", "")),
                    "left": item.get("left"),
                    "top": item.get("top"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                }
                for item in items[:100]
                if str(item.get("text", "")).strip()
            ]
            if not self._vlm_ready():
                return "OCR_SCREEN_MAP_JSON: " + json.dumps(
                    {"map_path": map_path, "items": ocr_preview},
                    ensure_ascii=False,
                )
            observation, raw = self.vlm.observe_screen(
                image_path=map_path,
                goal=goal,
                ocr_items=items,
            )
        except Exception as exc:
            return f"VisualContextError: {exc}"
        if observation:
            return "VLM_SCREEN_OBSERVATION_JSON: " + json.dumps(
                observation, ensure_ascii=False
            )
        if raw:
            return f"VLM_SCREEN_OBSERVATION_RAW: {raw[:1200]}"
        return ""

    def _vlm_observe(self, action: str, value: str, goal: str | None) -> str:
        if not self._vlm_ready():
            return ""
        if not str(action).startswith("gui_"):
            return ""
        try:
            map_path, items = gui_map_text(ui_lang=self.ui_lang)
        except Exception:
            return ""
        observation, raw = self.vlm.observe_screen(
            image_path=map_path,
            goal=goal or value or "",
            ocr_items=items,
        )
        if observation:
            return "VLM_SCREEN_OBSERVATION_JSON: " + json.dumps(
                observation, ensure_ascii=False
            )
        return f"VLM_SCREEN_OBSERVATION_RAW: {raw[:1200]}" if raw else ""

    def _filter_completed_steps(
        self, actions: list[dict], completed_steps: list[dict]
    ) -> list[dict]:
        if not actions or not completed_steps:
            return actions
        completed = {
            (
                str(step.get("action", "")).strip().lower(),
                str(step.get("value", "") or "").strip().lower(),
            )
            for step in completed_steps
            if step.get("action")
        }
        filtered = []
        for item in actions:
            key = (
                str(item.get("action", "")).strip().lower(),
                str(item.get("value", "") or "").strip().lower(),
            )
            if key in completed:
                continue
            filtered.append(item)
        return filtered

    def _start_auto_map(self):
        if not AUTO_MAP_ENABLED:
            return
        if self._auto_map_thread and self._auto_map_thread.is_alive():
            return
        self._auto_map_stop.clear()

        def _loop():
            while not self._auto_map_stop.is_set():
                try:
                    gui_map_text(ui_lang=self.ui_lang)
                except Exception:
                    pass
                # sleep in small steps so we can stop quickly
                steps = max(1, int(AUTO_MAP_INTERVAL_SEC * 10))
                for _ in range(steps):
                    if self._auto_map_stop.is_set():
                        break
                    time.sleep(0.1)

        self._auto_map_thread = threading.Thread(target=_loop, daemon=True)
        self._auto_map_thread.start()

    def _stop_auto_map(self):
        self._auto_map_stop.set()

    def _speak_success(self):
        if self.tts:
            self.tts.speak_async(TTS_SUCCESS_TEXT)

    def _speak_fail(self):
        if self.tts:
            self.tts.speak_async(TTS_FAIL_TEXT)

    def _print_active_models(self):
        stt_label = get_stt_label(self.transcriber)
        tts_status = self.tts.status_text(self.ui_lang) if self.tts else "-"
        llm_status = self.llm.status_text(self.ui_lang) if self.llm else "-"
        vlm_status = self.vlm.status_text(self.ui_lang) if self.vlm else "-"
        print(
            t(
                self.ui_lang,
                "active_models",
                stt=stt_label,
                tts=tts_status,
                llm=llm_status,
                vlm=vlm_status,
            )
        )

    def _planner(self):
        if (
            self.llm
            and getattr(self.llm, "enabled", False)
            and getattr(self.llm, "llm", None)
        ):
            return self.llm
        return None

    def _llm_ready(self) -> bool:
        return self._planner() is not None

    def _vlm_ready(self) -> bool:
        return bool(
            self.vlm
            and getattr(self.vlm, "enabled", False)
            and getattr(self.vlm, "llm", None)
        )

    def _needs_confirmation(self, action: str | None) -> bool:
        return action in DANGEROUS_ACTIONS

    def _await_confirmation(self, action: str, value: str | None) -> bool:
        event = threading.Event()
        with self.confirm_lock:
            self.pending_confirm = {"event": event, "response": None}
        print(t(self.ui_lang, "confirm_danger", action=action, value=value))
        event.wait()
        with self.confirm_lock:
            response = None
            if self.pending_confirm:
                response = self.pending_confirm.get("response")
            self.pending_confirm = None
        return response == "y"

    def handle_input_line(self, line: str) -> bool:
        line = (line or "").strip()
        if self.pending_confirm:
            response = line.lower()
            if response in ("y", "n"):
                with self.confirm_lock:
                    if self.pending_confirm:
                        self.pending_confirm["response"] = response
                        self.pending_confirm["event"].set()
                return False
            print(t(self.ui_lang, "confirm_invalid"))
            return False
        if not line or line.lower() == "exit":
            return True
        lowered = line.lower()
        if lowered in ("queue", "sira", "siradakiler", "status"):
            current, pending = self.job_queue.status()
            if not current and pending == 0:
                print(t(self.ui_lang, "queue_empty"))
            else:
                current_label = (
                    t(self.ui_lang, "queue_current_yes")
                    if current
                    else t(self.ui_lang, "queue_current_no")
                )
                print(
                    t(
                        self.ui_lang,
                        "queue_status",
                        current=current_label,
                        pending=pending,
                    )
                )
                cur_job, pending_jobs, history_jobs = self.job_queue.detailed_snapshot()
                if cur_job:
                    print(
                        t(
                            self.ui_lang,
                            "queue_item_current",
                            id=cur_job.job_id,
                            text=cur_job.text,
                        )
                    )
                for job in pending_jobs:
                    print(
                        t(
                            self.ui_lang,
                            "queue_item_pending",
                            id=job.job_id,
                            text=job.text,
                        )
                    )
                for job in history_jobs:
                    if job.status in ("completed", "failed", "cancelled"):
                        print(
                            t(
                                self.ui_lang,
                                "queue_item_history",
                                id=job.job_id,
                                status=job.status,
                                text=job.text,
                                error=job.error,
                            )
                        )
            return False
        if lowered.startswith("cancel "):
            job_id = lowered.split(" ", 1)[1].strip()
            if self.job_queue.cancel(job_id):
                print(t(self.ui_lang, "queue_cancelled_id", id=job_id))
            else:
                print(t(self.ui_lang, "queue_not_found", id=job_id))
            return False
        if lowered in ("cancel", "iptal"):
            if self.job_queue.cancel_current():
                print(t(self.ui_lang, "queue_cancelled"))
            else:
                print(t(self.ui_lang, "queue_no_current"))
            return False
        if lowered in ("clear", "temizle"):
            self.job_queue.clear()
            print(t(self.ui_lang, "queue_cleared"))
            return False
        planner = self._planner()
        if planner and getattr(planner, "only_mode", False):
            self._enqueue_job(line, source="text", use_commands=False)
            return False
        if not planner and line:
            print(t(self.ui_lang, "llm_only_no_llm"))
        return False

    def cancel_current(self) -> bool:
        current, _ = self.job_queue.status()
        if not current:
            return False
        with self.lock:
            self.cancel_event.set()
        print(t(self.ui_lang, "llm_cancel_requested"))
        return True

    def _handle_llm_request(self, text: str, source_label: str) -> bool:
        planner = self._planner()
        if not planner:
            print(t(self.ui_lang, "llm_only_no_llm"))
            return False

        self.cancel_event.clear()
        print(t(self.ui_lang, "llm_debug_input", source=source_label, text=text))
        context = self._build_state_context()
        if self._request_needs_visual_context(text):
            visual_context = self._build_visual_context(text)
            if visual_context:
                context = f"{context}; {visual_context}"
        try:
            actions, goal, notes = planner.plan(text, context=context)
        except Exception as exc:
            print(t(self.ui_lang, "command_failed", error=f"planner: {exc}"))
            return True
        actions = self._maybe_prepend_focus(text, actions)
        actions = self._reorder_focus_after_start(actions)
        if self.cancel_event.is_set():
            print(t(self.ui_lang, "llm_cancelled"))
            return True
        if goal:
            print(t(self.ui_lang, "agent_goal", goal=goal))
        if notes:
            print(t(self.ui_lang, "agent_notes", notes=notes))
        if not actions:
            if getattr(planner, "last_error", ""):
                print(t(self.ui_lang, "command_failed", error=planner.last_error))
            if getattr(planner, "last_raw", ""):
                print(t(self.ui_lang, "command_failed", error="planner returned empty/invalid JSON"))
            print(t(self.ui_lang, "llm_debug_invalid"))
            print(t(self.ui_lang, "llm_no_action"))
            return False

        print(t(self.ui_lang, "llm_multi_count", count=len(actions)))
        delay = float(getattr(planner, "multi_delay", 0.0) or 0.0)
        replan_attempts = 0
        completed_steps: list[dict] = []
        performed: set[tuple[str, str]] = set()
        retry_counts: dict[tuple[str, str], int] = {}
        idx = 0
        needs_map = any(
            str(item.get("action", "")).startswith("gui_")
            or str(item.get("action", "")).startswith("web_")
            or str(item.get("action", "")) == "youtube_search"
            for item in actions
        )
        if needs_map:
            self._start_auto_map()
        try:
            while idx < len(actions):
                item = actions[idx]
                action = item.get("action")
                value = item.get("value") or ""
                critical = item.get("critical", True)
                if action in (None, "none"):
                    idx += 1
                    continue
                if action in ("start", "focus"):
                    if (action, value) in performed:
                        idx += 1
                        continue
                print(
                    t(
                        self.ui_lang,
                        "llm_action_step",
                        idx=idx + 1,
                        action=action,
                        value=value,
                    )
                )
                reason = item.get("reason")
                if reason:
                    print(t(self.ui_lang, "llm_debug_reason", reason=reason))

                if action == "routine_run":
                    routine_text = _routine_value(value)
                    if not routine_text:
                        ok = False
                        fail_reason = "routine_missing"
                    else:
                        print(t(self.ui_lang, "routine_found", name=value))
                        routine_context = self._build_state_context()
                        routine_actions, _routine_goal, routine_notes = planner.plan(
                            routine_text, context=routine_context
                        )
                        routine_actions = self._maybe_prepend_focus(routine_text, routine_actions)
                        routine_actions = self._reorder_focus_after_start(routine_actions)
                        if routine_notes:
                            print(t(self.ui_lang, "agent_notes", notes=routine_notes))
                        actions = actions[:idx] + routine_actions + actions[idx + 1 :]
                        print(t(self.ui_lang, "llm_multi_count", count=len(actions)))
                        continue

                if self._needs_confirmation(action):
                    confirmed = self._await_confirmation(action, value)
                    if not confirmed:
                        print(t(self.ui_lang, "command_cancelled"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="cancelled")
                        )
                        self._speak_fail()
                        return True

                if self.cancel_event.is_set():
                    print(t(self.ui_lang, "llm_cancelled"))
                    return True

                show_status_popup(
                    t(
                        self.ui_lang,
                        "command_popup_running",
                        action=action,
                        value=value or "",
                    )
                )
                verification = {}
                try:
                    ok, fail_reason = execute_action(
                        action,
                        value,
                        tail_text=None,
                        ui_lang=self.ui_lang,
                        automation=self.automation,
                        web=self.web,
                    )
                except Exception as exc:
                    ok, fail_reason = False, str(exc)
                if ok:
                    verification = verify_action(action, value, web=self.web)
                    if not verification.get("ok", True):
                        ok = False
                        fail_reason = verification.get("reason", "verification_failed")
                if ok:
                    completed_steps.append(item)
                    if action in ("start", "focus"):
                        performed.add((action, value))
                    show_status_popup(t(self.ui_lang, "command_popup_found"))
                    self._speak_success()
                    idx += 1
                    if idx < len(actions) and delay > 0:
                        time.sleep(delay)
                    continue
                else:
                    if fail_reason == "missing":
                        print(t(self.ui_lang, "command_missing"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="missing")
                        )
                    elif fail_reason == "gui_disabled":
                        print(t(self.ui_lang, "automation_gui_disabled"))
                        show_status_popup(
                            t(
                                self.ui_lang,
                                "command_popup_failed",
                                error="gui_disabled",
                            )
                        )
                    elif fail_reason == "web_disabled":
                        print(t(self.ui_lang, "automation_web_disabled"))
                        show_status_popup(
                            t(
                                self.ui_lang,
                                "command_popup_failed",
                                error="web_disabled",
                            )
                        )
                    elif fail_reason == "app_not_open":
                        print(t(self.ui_lang, "app_start_failed", name=value))
                        show_status_popup(
                            t(
                                self.ui_lang,
                                "command_popup_failed",
                                error="app_not_open",
                            )
                        )
                    elif fail_reason == "focus_failed":
                        print(t(self.ui_lang, "focus_failed", name=value))
                        show_status_popup(
                            t(
                                self.ui_lang,
                                "command_popup_failed",
                                error="focus_failed",
                            )
                        )
                    elif fail_reason == "map_empty":
                        print(t(self.ui_lang, "gui_map_empty"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="map_empty")
                        )
                    elif fail_reason == "map_index":
                        print(t(self.ui_lang, "gui_map_index"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="map_index")
                        )
                    elif fail_reason == "no_text":
                        print(t(self.ui_lang, "ocr_empty"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="no_text")
                        )
                    elif fail_reason == "captcha_required":
                        print(t(self.ui_lang, "captcha_required"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="captcha_required")
                        )
                    elif fail_reason == "routine_missing":
                        print(t(self.ui_lang, "command_failed", error="routine_missing"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="routine_missing")
                        )
                    elif fail_reason == "blocked":
                        confirmed = self._await_confirmation(action, value)
                        if confirmed:
                            ok2, reason2 = execute_action(
                                action,
                                value,
                                tail_text=None,
                                ui_lang=self.ui_lang,
                                allow_blocked=True,
                                automation=self.automation,
                                web=self.web,
                            )
                            if ok2:
                                completed_steps.append(item)
                                show_status_popup(t(self.ui_lang, "command_popup_found"))
                                self._speak_success()
                                idx += 1
                                continue
                            print(t(self.ui_lang, "command_failed", error=reason2))
                        print(t(self.ui_lang, "open_blocked"))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="blocked")
                        )
                    else:
                        print(t(self.ui_lang, "unknown_action", action=action))
                        show_status_popup(
                            t(self.ui_lang, "command_popup_failed", error="unknown")
                        )

                retry_key = (
                    str(action or "").strip().lower(),
                    str(value or "").strip().lower(),
                )
                policy = decide_error_policy(
                    action,
                    str(fail_reason),
                    bool(critical),
                    retry_counts.get(retry_key, 0),
                    replan_attempts,
                )
                vlm_note_for_replay = ""
                if str(action).startswith("gui_"):
                    vlm_note_for_replay = self._vlm_observe(action, value, goal)
                try:
                    from uia_automation import summarize_foreground

                    uia_summary = summarize_foreground(max_depth=3, max_items=80)
                except Exception:
                    uia_summary = {}
                try:
                    replay_path = write_debug_replay(
                        user_command=text,
                        plan=actions,
                        completed_steps=completed_steps,
                        failed_step=item,
                        error_policy=policy,
                        error=str(fail_reason),
                        verification=verification,
                        uia_summary=uia_summary,
                        vlm_note=vlm_note_for_replay,
                    )
                    print(t(self.ui_lang, "debug_replay_saved", path=replay_path))
                except Exception:
                    pass
                print(
                    t(
                        self.ui_lang,
                        "agent_error_policy",
                        decision=policy,
                        reason=fail_reason,
                    )
                )
                if policy == ERROR_RETRY:
                    retry_counts[retry_key] = retry_counts.get(retry_key, 0) + 1
                    time.sleep(0.7)
                    continue

                self._speak_fail()
                if policy == ERROR_SKIP:
                    idx += 1
                    continue
                if policy == ERROR_ABORT:
                    return True
                replan_attempts += 1
                print(t(self.ui_lang, "agent_replan", attempt=replan_attempts))
                error_ctx = str(fail_reason)
                if str(action).startswith("gui_"):
                    error_ctx = self._observer_context(action, str(fail_reason))
                    vlm_note = vlm_note_for_replay or self._vlm_observe(action, value, goal)
                    if vlm_note:
                        error_ctx = f"{error_ctx}; {vlm_note}"
                actions, goal, notes = planner.replan(
                    goal, completed_steps, item, error_ctx, original_text=text
                )
                actions = self._filter_completed_steps(actions, completed_steps)
                actions = self._maybe_prepend_focus(text, actions)
                actions = self._reorder_focus_after_start(actions)
                if notes:
                    print(t(self.ui_lang, "agent_notes", notes=notes))
                if not actions:
                    return True
                idx = 0
                print(t(self.ui_lang, "llm_multi_count", count=len(actions)))
                continue

            return True
        finally:
            if needs_map:
                self._stop_auto_map()

    def _start_recording(self):
        self.recorder.start()
        self.recording = True
        show_status_popup(t(self.ui_lang, "status_recording_started"))
        print(t(self.ui_lang, "recording_started"))

    def _stop_recording(self):
        self.recording = False
        out_path = self.recorder.stop_and_save()
        show_status_popup(t(self.ui_lang, "status_recording_stopped"))
        if out_path is None:
            print(t(self.ui_lang, "empty_recording"))
            return
        print(t(self.ui_lang, "recording_stopped", path=out_path))

        self.processing = True
        thread = threading.Thread(
            target=self._process_recording, args=(out_path,), daemon=True
        )
        thread.start()

    def _process_recording(self, audio_path: Path):
        try:
            self._print_active_models()
            result = self.transcriber.transcribe(audio_path, None)
            write_transcript(self.ui_lang, audio_path, result)
            if not result.text:
                print(t(self.ui_lang, "no_text"))
                return
            print(t(self.ui_lang, "detected_text", text=result.text))
            planner = self._planner()
            use_commands = not (planner and getattr(planner, "only_mode", False))
            self._enqueue_job(result.text, source="voice", use_commands=use_commands)
        finally:
            with self.lock:
                self.processing = False

    def _enqueue_job(self, text: str, source: str, use_commands: bool):
        job = self.job_queue.submit(text, source=source, use_commands=use_commands)
        _, pending = self.job_queue.status()
        print(
            t(
                self.ui_lang,
                "queue_added",
                count=pending,
                id=job.job_id,
            )
        )

    def _run_job(self, job):
        self.cancel_event.clear()
        print(
            t(
                self.ui_lang,
                "queue_item_current",
                id=job.job_id,
                text=job.text,
            )
        )
        source_label = (
            t(self.ui_lang, "llm_source_voice")
            if job.source == "voice"
            else t(self.ui_lang, "llm_source_text")
        )
        self._handle_text_request(job.text, source_label, job.use_commands)

    def _extract_discord_request(self, text: str) -> tuple[str, str] | None:
        folded = fold_text(text or "")
        if "discord" not in folded:
            return None
        if not any(
            key in folded for key in ("mesaj", "message", "dm", "gonder", "gönder", "send", "yaz")
        ):
            return None

        msg = None
        import re

        for pattern in (r'"([^"]+)"', r"“([^”]+)”", r"'([^']+)'"):
            matches = re.findall(pattern, text)
            if matches:
                msg = matches[-1].strip()
        if not msg:
            raw_patterns = (
                r"(?:to)\s+[\w.-]{2,64}\s+(?:send|message|dm|write|type)\s+(.+?)$",
                r"(?:send|message|dm|write|type)\s+(.+?)\s+(?:to)\s+[\w.-]{2,64}$",
                r"(?:kişiye|kişisine|kisine|kisisine|kisiye|to)\s+(.+?)\s*(?:yaz|gönder|gonder|send)$",
                r"(?:mesaj(?:ı|i)?|message|dm)\s*(?:olarak)?\s+(.+?)$",
                r"(?:şunu|sunu|bunu)\s+(.+?)\s*(?:yaz|gönder|gonder|send)?$",
            )
            for pattern in raw_patterns:
                m = re.search(pattern, text, flags=re.IGNORECASE)
                if m:
                    msg = m.group(1).strip(" :,.")
                    break
        if msg:
            msg = re.sub(
                r"^(?:şunu|sunu|bunu|mesaj(?:ı|i)?|message|dm)\s+",
                "",
                msg,
                flags=re.IGNORECASE,
            ).strip(" :,.")
            msg = re.sub(
                r"\s+(?:de\s+ve\s+mesaj(?:ı|i)?|ve\s+mesaj(?:ı|i)?|de)$",
                "",
                msg,
                flags=re.IGNORECASE,
            ).strip(" :,.")
        if msg:
            msg = msg.strip()

        target = None
        mention = re.search(r"@([\w.-]{2,64})", text, flags=re.IGNORECASE)
        if mention:
            target = mention.group(1)
        if not target:
            m = re.search(
                r"(?:to|dm)\s+([\w.-]{2,64})",
                text,
                flags=re.IGNORECASE,
            )
            if m:
                target = m.group(1)
        if not target:
            m = re.search(
                r"([\w.-]{2,64})\s*(?:adlı|adli)?\s*(?:kişiye|kişisine|kisine|kisisine|kisiye)",
                text,
                flags=re.IGNORECASE,
            )
            if m:
                target = m.group(1)
        if not target:
            m = re.search(
                r"discord(?:da|de|ta|te)?\s+([\w.-]{2,64})",
                folded,
                flags=re.IGNORECASE,
            )
            if m:
                target = m.group(1)
        if target and fold_text(target) in {"adli", "uygulama", "uygulamada", "application", "app"}:
            target = None
        if not target or not msg:
            return None
        return target.strip("@ "), msg

    def _try_discord_flow(self, text: str) -> bool:
        request = self._extract_discord_request(text)
        if not request:
            return False
        target, message = request
        try:
            if is_app_window_open("discord"):
                ensure_app_focus(
                    "discord",
                    settle=1.0,
                    wait_window=APP_LAUNCH_TIMEOUT,
                    ui_lang=self.ui_lang,
                )
            else:
                ok, _method = start_app_verified("discord", ui_lang=self.ui_lang)
                if not ok:
                    return False
                time.sleep(1.5)
                ensure_app_focus(
                    "discord",
                    settle=1.0,
                    wait_window=APP_LAUNCH_TIMEOUT,
                    ui_lang=self.ui_lang,
                )

            send_hotkey("ctrl k")
            time.sleep(0.5)
            type_text(target)
            time.sleep(0.8)
            send_hotkey("enter")
            time.sleep(1.4)

            type_text(message)
            time.sleep(0.1)
            send_hotkey("enter")
            show_status_popup(t(self.ui_lang, "command_popup_found"))
            self._speak_success()
            return True
        except Exception as exc:
            print(t(self.ui_lang, "command_failed", error=exc))
            show_status_popup(t(self.ui_lang, "command_popup_failed", error=exc))
            self._speak_fail()
            return True

    def _find_routine_request(self, text: str) -> tuple[str, str] | None:
        folded = fold_text(text or "")
        if not folded:
            return None
        trigger_terms = (
            "rutin",
            "routine",
            "mod",
            "mode",
            "baslat",
            "basla",
            "calistir",
            "calistir",
            "gec",
            "geç",
            "start",
            "run",
        )
        for name, entry in _routine_section().items():
            name_folded = fold_text(name)
            if not name_folded or name_folded not in folded:
                continue
            if any(term in folded for term in trigger_terms):
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    return name, str(val)
        return None

    def _maybe_prepend_focus(self, text: str, actions: list[dict]) -> list[dict]:
        if not actions:
            return actions
        if not any(str(item.get("action", "")).startswith("gui_") for item in actions):
            return actions
        if any(item.get("action") == "focus" for item in actions):
            return actions
        text_folded = fold_text(text or "")
        app_name = None
        for name in APP_ALIASES.keys():
            if fold_text(name) in text_folded:
                app_name = name
                break
        if not app_name:
            return actions
        if not is_app_window_open(app_name):
            return actions
        steps = []
        steps.append(
            {
                "action": "focus",
                "value": app_name,
                "reason": "Bring app to front before GUI actions.",
                "critical": True,
            }
        )
        return steps + actions

    def _reorder_focus_after_start(self, actions: list[dict]) -> list[dict]:
        if not actions:
            return actions
        first_start: dict[str, int] = {}
        for idx, item in enumerate(actions):
            action = str(item.get("action", ""))
            value = str(item.get("value", "") or "")
            if action in ("start", "open") and value:
                name = canonical_app_name(value)
                if name and name not in first_start:
                    first_start[name] = idx
        if not first_start:
            return actions
        deferred: dict[str, list[dict]] = {}
        ordered: list[dict] = []
        for idx, item in enumerate(actions):
            action = str(item.get("action", ""))
            value = str(item.get("value", "") or "")
            if action == "focus" and value:
                name = canonical_app_name(value)
                if name in first_start and idx < first_start[name]:
                    deferred.setdefault(name, []).append(item)
                    continue
            ordered.append(item)
            if action in ("start", "open") and value:
                name = canonical_app_name(value)
                if name in deferred:
                    ordered.extend(deferred.pop(name))
        for remaining in deferred.values():
            ordered.extend(remaining)
        return ordered

    def _run_direct_actions(self, actions: list[dict], source_text: str) -> bool:
        if not actions:
            return False
        for item in actions:
            action = item.get("action")
            value = item.get("value") or ""
            if not action or action == "none":
                continue
            if self._needs_confirmation(action):
                if not self._await_confirmation(action, value):
                    print(t(self.ui_lang, "command_cancelled"))
                    show_status_popup(
                        t(self.ui_lang, "command_popup_failed", error="cancelled")
                    )
                    self._speak_fail()
                    return True
            show_status_popup(
                t(
                    self.ui_lang,
                    "command_popup_running",
                    action=action,
                    value=value or "",
                )
            )
            try:
                ok, fail_reason = execute_action(
                    action,
                    value,
                    tail_text=None,
                    ui_lang=self.ui_lang,
                    automation=self.automation,
                    web=self.web,
                )
            except Exception as exc:
                ok, fail_reason = False, str(exc)
            if ok:
                verification = verify_action(action, value, web=self.web)
                if not verification.get("ok", True):
                    ok = False
                    fail_reason = verification.get("reason", "verification_failed")
            if not ok:
                print(t(self.ui_lang, "command_failed", error=fail_reason or "unknown"))
                show_status_popup(
                    t(
                        self.ui_lang,
                        "command_popup_failed",
                        error=fail_reason or "unknown",
                    )
                )
                self._speak_fail()
                return True
        show_status_popup(t(self.ui_lang, "command_popup_found"))
        self._speak_success()
        return True

    def _handle_text_request(self, text: str, source_label: str, use_commands: bool):
        if use_commands:
            match = match_command(text, self.commands)
            if match:
                cmd, matched_phrase = match
                tail_text = extract_tail_text(text, matched_phrase)
                action = cmd.get("action")
                value = cmd.get("value")
                print(
                    t(
                        self.ui_lang,
                        "command_found",
                        phrase=matched_phrase,
                        action=action,
                        value=value,
                    )
                )
                show_status_popup(
                    t(
                        self.ui_lang,
                        "command_popup_running",
                        action=action,
                        value=value or "",
                    )
                )
                needs_map = action in {
                    "gui_click_text",
                    "gui_click_image",
                    "gui_click",
                    "gui_wait",
                    "gui_wait_text",
                    "gui_wait_image",
                    "gui_map",
                    "gui_click_index",
                    "web_open",
                    "web_click",
                    "web_type",
                    "web_press",
                    "web_wait",
                    "web_search",
                    "youtube_search",
                    "web_form_fill",
                }
                if needs_map:
                    self._start_auto_map()
                try:
                    ok, reason = execute_action(
                        action,
                        value,
                        tail_text,
                        self.ui_lang,
                        automation=self.automation,
                        web=self.web,
                    )
                    if not ok:
                        if reason == "missing":
                            print(t(self.ui_lang, "command_missing"))
                            show_status_popup(
                                t(self.ui_lang, "command_popup_failed", error="missing")
                            )
                        elif reason == "gui_disabled":
                            print(t(self.ui_lang, "automation_gui_disabled"))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="gui_disabled",
                                )
                            )
                        elif reason == "web_disabled":
                            print(t(self.ui_lang, "automation_web_disabled"))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="web_disabled",
                                )
                            )
                        elif reason == "app_not_open":
                            print(t(self.ui_lang, "app_start_failed", name=value))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="app_not_open",
                                )
                            )
                        elif reason == "focus_failed":
                            print(t(self.ui_lang, "focus_failed", name=value))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="focus_failed",
                                )
                            )
                        elif reason == "map_empty":
                            print(t(self.ui_lang, "gui_map_empty"))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="map_empty",
                                )
                            )
                        elif reason == "map_index":
                            print(t(self.ui_lang, "gui_map_index"))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="map_index",
                                )
                            )
                        elif reason == "no_text":
                            print(t(self.ui_lang, "ocr_empty"))
                            show_status_popup(
                                t(self.ui_lang, "command_popup_failed", error="no_text")
                            )
                        elif reason == "blocked":
                            print(t(self.ui_lang, "open_blocked"))
                            show_status_popup(
                                t(
                                    self.ui_lang,
                                    "command_popup_failed",
                                    error="blocked",
                                )
                            )
                        else:
                            print(t(self.ui_lang, "unknown_action", action=action))
                            show_status_popup(
                                t(self.ui_lang, "command_popup_failed", error="unknown")
                            )
                        self._speak_fail()
                    else:
                        show_status_popup(t(self.ui_lang, "command_popup_found"))
                        self._speak_success()
                    return
                except Exception as exc:
                    print(t(self.ui_lang, "command_failed", error=exc))
                    show_status_popup(
                        t(self.ui_lang, "command_popup_failed", error=exc)
                    )
                    self._speak_fail()
                    return
                finally:
                    if needs_map:
                        self._stop_auto_map()

        # Weather shortcut: open default browser search directly.
        folded = fold_text(text or "")

        quick_actions = infer_quick_actions(text)
        if quick_actions:
            quick_actions = _fix_actions_from_text(text, quick_actions)
            if self._run_direct_actions(quick_actions, text):
                return

        if "hava durumu" in folded or "weather" in folded:
            open_search(text)
            show_status_popup(t(self.ui_lang, "command_popup_found"))
            return

        # YouTube shortcut: search and open first non-ad result (Playwright unless browser requested).
        if any(key in folded for key in ("youtube", "youtu")) and any(
            key in folded
            for key in (
                "video",
                "izle",
                "watch",
                "aç",
                "ac",
                "ara",
                "search",
                "bul",
                "asmr",
            )
        ):
            query = (
                folded.replace("youtube", "")
                .replace("youtu", "")
                .replace("videosu", "")
                .replace("video", "")
                .replace("izle", "")
                .replace("watch", "")
                .replace("aç", "")
                .replace("ac", "")
                .replace("ara", "")
                .replace("search", "")
                .replace("bul", "")
                .replace("bana", "")
                .replace("lütfen", "")
                .strip()
            )
            if not query:
                query = text
            avoid_pw, browser = _detect_browser_request(text)
            if avoid_pw:
                from urllib.parse import quote_plus
                clean_query = _clean_youtube_query(query)
                ok = open_youtube_first_result(clean_query, browser=browser, ui_lang=self.ui_lang)
                if not ok:
                    url = f"https://www.youtube.com/results?search_query={quote_plus(clean_query or query)}"
                    open_url_in_browser(browser, url)
                show_status_popup(t(self.ui_lang, "command_popup_found"))
            else:
                self._start_auto_map()
                try:
                    self.web.youtube_search(query)
                    show_status_popup(t(self.ui_lang, "command_popup_found"))
                finally:
                    self._stop_auto_map()
            return

        routine = self._find_routine_request(text)
        if routine and self._llm_ready():
            name, routine_text = routine
            print(t(self.ui_lang, "routine_found", name=name))
            self._handle_llm_request(routine_text, source_label)
            return

        if self._try_discord_flow(text):
            return

        handled = False
        if self._llm_ready():
            print(t(self.ui_lang, "llm_fallback"))
            handled = self._handle_llm_request(text, source_label)

        if not handled:
            print(t(self.ui_lang, "command_not_found"))
            show_status_popup(t(self.ui_lang, "command_popup_not_found", text=text))
            self._speak_fail()

    def toggle(self):
        with self.lock:
            if not self.recording:
                self._start_recording()
            else:
                self._stop_recording()

    def shutdown(self):
        self.job_queue.stop()
        try:
            self.web.close()
        except Exception:
            pass


def run_control_mode(ui_lang, transcriber, commands, tts=None, llm=None, vlm=None, automation=None):
    session = ControlSession(ui_lang, transcriber, commands, tts=tts, llm=llm, vlm=vlm, automation=automation)
    pressed = set()
    hotkey_active = {"state": False}
    stop_event = threading.Event()
    input_queue = queue.Queue()

    def is_ctrl(key):
        return key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    def is_shift(key):
        return key in (
            keyboard.Key.shift,
            keyboard.Key.shift_l,
            keyboard.Key.shift_r,
        )

    def is_six(key):
        if isinstance(key, keyboard.KeyCode):
            if key.char in ("6", "^"):
                return True
            if key.vk == 0x36:
                return True
        return False

    def on_press(key):
        pressed.add(key)
        if is_six(key) and not hotkey_active["state"]:
            if any(is_ctrl(k) for k in pressed) and any(is_shift(k) for k in pressed):
                hotkey_active["state"] = True
                session.toggle()

    def on_release(key):
        pressed.discard(key)
        if is_six(key):
            hotkey_active["state"] = False

    def input_worker():
        while not stop_event.is_set():
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                stop_event.set()
                break
            input_queue.put(line)

    print("\n" + t(ui_lang, "control_active"))
    session._print_active_models()
    print(t(ui_lang, "control_hotkey"))
    print(t(ui_lang, "control_background"))
    print(t(ui_lang, "control_queue"))
    print(t(ui_lang, "control_exit"))
    planner = session._planner()
    if planner and getattr(planner, "only_mode", False):
        print(t(ui_lang, "llm_only_tip"))
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    input_thread = threading.Thread(target=input_worker, daemon=True)
    input_thread.start()
    try:
        while not stop_event.is_set():
            try:
                line = input_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            except KeyboardInterrupt:
                if session.cancel_current():
                    continue
                stop_event.set()
                break
            if session.handle_input_line(line):
                stop_event.set()
                break
    except KeyboardInterrupt:
        if not session.cancel_current():
            stop_event.set()
    finally:
        stop_event.set()
        listener.stop()
        session.shutdown()
