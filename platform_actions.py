import os
import platform
import re
import shutil
import subprocess
import time
import datetime
import ctypes
import ctypes.wintypes
from difflib import SequenceMatcher
from PIL import Image
from PIL import ImageDraw
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

import webbrowser

from send2trash import send2trash

from config import (
    APP_ALIASES,
    APP_PROFILES,
    FILE_SEARCH_DIRS,
    FILE_SEARCH_MAX_DEPTH,
    FILE_SEARCH_MAX_FILES,
    OPEN_BLOCKLIST,
    SCREENSHOTS_DIR,
    TESSERACT_CMD,
    OCR_LANG_TR,
    OCR_LANG_EN,
    OCR_LANG_BOTH,
    GUI_MAP_MAX_ITEMS,
    GUI_MAP_DIR,
    GUI_MAP_MIN_CONF,
    GUI_MAP_MIN_AREA,
    GUI_MAP_MAX_AREA,
    GUI_MAP_RECT_MIN_RATIO,
    SCREENSHOT_WAIT_TIMEOUT,
    SCREENSHOT_RETRY_COUNT,
    SCREENSHOT_RETRY_DELAY,
    FOCUS_RECHECK_DELAY,
    FOCUS_ATTEMPTS,
    FOCUS_VERIFY_DELAY,
    FOCUS_POLL_INTERVAL,
    APP_LAUNCH_TIMEOUT,
    APP_LAUNCH_RUNNING_EXTRA_TIMEOUT,
    APP_LAUNCH_SETTLE_SEC,
    WEB_SEARCH_URL_BROWSER,
)
from utils import fold_text
from i18n import t


IS_WINDOWS = platform.system().lower() == "windows"
_DPI_AWARE = False
_LAST_CPU_TIMES = {"idle": None, "kernel": None, "user": None}


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.wintypes.DWORD),
        ("dwHighDateTime", ctypes.wintypes.DWORD),
    ]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.wintypes.DWORD),
        ("dwMemoryLoad", ctypes.wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _filetime_to_int(ft: _FILETIME) -> int:
    return (ft.dwHighDateTime << 32) + ft.dwLowDateTime


def _read_system_times() -> tuple[int, int, int] | None:
    idle = _FILETIME()
    kernel = _FILETIME()
    user = _FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    ):
        return None
    return _filetime_to_int(idle), _filetime_to_int(kernel), _filetime_to_int(user)


def _cpu_usage_percent() -> int | None:
    times = _read_system_times()
    if not times:
        return None
    idle, kernel, user = times
    last = _LAST_CPU_TIMES
    if last["idle"] is None:
        last["idle"], last["kernel"], last["user"] = idle, kernel, user
        return None
    idle_delta = idle - last["idle"]
    kernel_delta = kernel - last["kernel"]
    user_delta = user - last["user"]
    total = kernel_delta + user_delta
    last["idle"], last["kernel"], last["user"] = idle, kernel, user
    if total <= 0:
        return None
    usage = max(0.0, min(100.0, (total - idle_delta) * 100.0 / total))
    return int(round(usage))


def _memory_usage_percent() -> int | None:
    mem = _MEMORYSTATUSEX()
    mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
        return None
    if mem.ullTotalPhys == 0:
        return None
    used = mem.ullTotalPhys - mem.ullAvailPhys
    return int(round(used * 100.0 / mem.ullTotalPhys))


def _init_dpi_awareness():
    global _DPI_AWARE
    if not IS_WINDOWS:
        return
    try:
        # 2 = Per-monitor DPI aware
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        _DPI_AWARE = True
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        _DPI_AWARE = True
    except Exception:
        _DPI_AWARE = False


def _get_scale_factor() -> float:
    if not IS_WINDOWS:
        return 1.0
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            return float(dpi) / 96.0
    except Exception:
        pass
    try:
        scale = ctypes.c_int()
        if ctypes.windll.shcore.GetScaleFactorForDevice(0, ctypes.byref(scale)) == 0:
            return float(scale.value) / 100.0
    except Exception:
        pass
    return 1.0


def _ensure_windows():
    if not IS_WINDOWS:
        raise RuntimeError("windows_only")


def _get_foreground_rect() -> tuple[int, int, int, int] | None:
    if not IS_WINDOWS:
        return None
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        rect = ctypes.wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)) == 0:
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def click_foreground_bottom(offset: int = 80) -> tuple[int, int]:
    rect = _get_foreground_rect()
    if not rect:
        raise ValueError("no_foreground")
    left, top, right, bottom = rect
    x = int((left + right) / 2)
    y = int(bottom - max(10, offset))
    gui_click(x, y, clicks=1)
    return x, y


def _profile_list(profile: dict | None, key: str) -> list[str]:
    if not isinstance(profile, dict):
        return []
    value = profile.get(key)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _contains_phrase(text: str, phrase: str) -> bool:
    text_tokens = _normalize_tokens(text)
    phrase_tokens = _normalize_tokens(phrase)
    if not text_tokens or not phrase_tokens:
        return False
    if len(phrase_tokens) == 1:
        return phrase_tokens[0] in text_tokens
    for idx in range(0, len(text_tokens) - len(phrase_tokens) + 1):
        if text_tokens[idx : idx + len(phrase_tokens)] == phrase_tokens:
            return True
    return False


def _profile_for_key(key: str) -> dict | None:
    if not key:
        return None
    return APP_PROFILES.get(key.lower())


def _find_profile_key(text: str) -> str | None:
    if not text:
        return None
    for key, profile in APP_PROFILES.items():
        candidates = [key] + _profile_list(profile, "aliases") + _profile_list(
            profile, "window_titles"
        )
        if any(_contains_phrase(text, candidate) for candidate in candidates):
            return key
    return None


def _get_app_profile(app_name: str) -> dict | None:
    key = _find_profile_key(app_name)
    if key:
        return _profile_for_key(key)
    raw = (app_name or "").strip().lower()
    return _profile_for_key(raw)


_BROWSER_PROCESS_STEMS = {
    "chrome",
    "msedge",
    "firefox",
    "brave",
    "opera",
    "launcher",
    "vivaldi",
}

APP_TITLE_ALIASES = {
    "vscode": ["visual studio code", "code"],
    "edge": ["microsoft edge", "edge"],
    "notepad++": ["notepad++"],
    "obs": ["obs", "obs studio"],
}


def _is_browser_process_stem(stem: str) -> bool:
    stem = (stem or "").strip().lower()
    return stem in _BROWSER_PROCESS_STEMS


def _is_browser_target(name: str) -> bool:
    return canonical_app_name(name) in {"chrome", "edge", "firefox", "brave", "opera"}


def _title_candidates_for_app(app_name: str) -> list[str]:
    raw = (app_name or "").strip()
    if not raw:
        return []
    candidates: list[str] = [raw]
    profile = _get_app_profile(raw)
    candidates.extend(_profile_list(profile, "aliases"))
    candidates.extend(_profile_list(profile, "window_titles"))
    alias_key = _find_alias_key(raw)
    if alias_key:
        candidates.append(alias_key)
        aliases = APP_ALIASES.get(alias_key)
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, list):
            for candidate in aliases:
                expanded = os.path.expandvars(os.path.expanduser(candidate))
                stem = Path(expanded).stem
                if stem:
                    candidates.append(stem)

    # Common title aliases that are not obvious from executable names.
    for item in APP_TITLE_ALIASES.get(raw.lower(), []):
        candidates.append(item)

    seen = set()
    result = []
    for candidate in candidates:
        normalized = " ".join(_normalize_tokens(candidate))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(candidate)
    return result


def _build_app_tokens(app_name: str) -> list[str]:
    raw = (app_name or "").strip()
    base = Path(raw).stem
    tokens = _filter_app_tokens(_normalize_tokens(base))

    def _alias_keys_from_text(text: str) -> list[str]:
        folded = " ".join(_normalize_tokens(text))
        found = []
        for key in list(APP_PROFILES.keys()) + list(APP_ALIASES.keys()):
            key_l = key.lower()
            profile = APP_PROFILES.get(key_l)
            profile_aliases = _profile_list(profile, "aliases") + _profile_list(
                profile, "window_titles"
            )
            if (
                _contains_phrase(folded, key_l)
                or _contains_phrase(text, key_l)
                or any(_contains_phrase(text, alias) for alias in profile_aliases)
            ):
                found.append(key_l)
        return found

    alias_keys = _alias_keys_from_text(raw)
    if not alias_keys and base.lower() in APP_ALIASES:
        alias_keys = [base.lower()]
    if not alias_keys and base.lower() in APP_PROFILES:
        alias_keys = [base.lower()]

    for key in alias_keys:
        tokens.extend(_filter_app_tokens(_normalize_tokens(key)))
        profile = APP_PROFILES.get(key)
        if profile:
            for candidate in _profile_list(profile, "aliases") + _profile_list(
                profile, "window_titles"
            ):
                tokens.extend(_filter_app_tokens(_normalize_tokens(candidate)))
        aliases = APP_ALIASES.get(key)
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, list):
            for candidate in aliases:
                expanded = os.path.expandvars(os.path.expanduser(candidate))
                stem = Path(expanded).stem
                tokens.extend(_filter_app_tokens(_normalize_tokens(stem)))

    if not tokens:
        tokens = _normalize_tokens(raw)[:1]
    # de-dup
    seen = set()
    result = []
    for t in tokens:
        if t not in seen and len(t) >= 3:
            seen.add(t)
            result.append(t)
    return result


def _process_image_name(pid: int) -> str | None:
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        size = ctypes.wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(handle)
        if not ok:
            return None
        return buf.value
    except Exception:
        return None


def _find_window_for_app(app_name: str) -> int | None:
    _ensure_windows()
    name = canonical_app_name(app_name)
    tokens = _build_app_tokens(name)
    if not tokens:
        return None
    profile = _get_app_profile(name)
    profile_titles = _title_candidates_for_app(name)
    profile_processes = {
        Path(item).stem.lower() for item in _profile_list(profile, "processes")
    }
    title_required_processes = {
        Path(item).stem.lower()
        for item in _profile_list(profile, "title_required_processes")
    }
    user32 = ctypes.windll.user32
    best_hwnd = None
    best_score = 0
    pid_map = None
    target_is_browser = _is_browser_target(name)

    def score_profile_title(text: str) -> int:
        if not text:
            return 0
        score = 0
        for phrase in profile_titles:
            if phrase and _contains_phrase(text, phrase):
                score += max(8, len(" ".join(_normalize_tokens(phrase))) * 2)
        return score

    def score_tokens(text: str) -> int:
        if not text:
            return 0
        text_tokens = _filter_app_tokens(_normalize_tokens(text))
        score = 0
        for tok in tokens:
            if tok in text_tokens:
                score += max(4, len(tok) * 2)
        return score

    def score_process(exe_path: str) -> int:
        exe_stem = Path(exe_path).stem.lower()
        score = 0
        for tok in tokens:
            if tok in exe_stem:
                score += max(4, len(tok) * 2)
        if exe_stem in profile_processes:
            score += 10
        return score

    def process_requires_title(exe_path: str) -> bool:
        stem = Path(exe_path).stem.lower()
        return stem in title_required_processes

    def ensure_pid_map():
        nonlocal pid_map
        if pid_map is not None:
            return pid_map
        pid_map = {}
        try:
            import csv

            out = subprocess.check_output(
                ["tasklist", "/v", "/fo", "csv", "/nh"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            reader = csv.reader(out.splitlines())
            for row in reader:
                if not row or len(row) < 2:
                    continue
                name = row[0]
                pid = row[1]
                title = row[-1] if row else ""
                if pid and pid.isdigit():
                    pid_map[int(pid)] = {"name": name, "title": title}
        except Exception:
            pid_map = {}
        return pid_map

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        title = ""
        try:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = (buf.value or "").strip()
        except Exception:
            title = ""
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_image_name(pid.value)
        title_score = max(score_tokens(title), score_profile_title(title)) if title else 0
        score = 0
        if exe:
            exe_stem = Path(exe).stem.lower()
            proc_score = score_process(exe)
            if (
                title_score
                and proc_score <= 0
                and _is_browser_process_stem(exe_stem)
                and not target_is_browser
            ):
                title_score = 0
            if process_requires_title(exe) and title_score <= 0:
                proc_score = 0
            score = max(proc_score, title_score)
            if proc_score and title_score:
                score += title_score
        else:
            data = ensure_pid_map().get(int(pid.value))
            if data and data.get("name"):
                proc_stem = Path(data["name"]).stem.lower()
                proc_score = score_process(data["name"])
                if (
                    title_score
                    and proc_score <= 0
                    and _is_browser_process_stem(proc_stem)
                    and not target_is_browser
                ):
                    title_score = 0
                if process_requires_title(data["name"]) and title_score <= 0:
                    proc_score = 0
                score = max(score, proc_score)
            if data and data.get("title"):
                mapped_title_score = max(
                    score_tokens(data["title"]), score_profile_title(data["title"])
                )
                score = max(score, int(mapped_title_score * 0.8))
        if title_score:
            score = max(score, int(title_score * 0.9))
        nonlocal best_hwnd, best_score
        if score > best_score:
            best_score = score
            best_hwnd = hwnd
        return True

    user32.EnumWindows(enum_proc, 0)
    if not best_hwnd or best_score < 4:
        return None
    return best_hwnd


def _process_running_tokens(tokens: list[str], profile: dict | None = None) -> bool:
    if not tokens:
        return False
    import csv

    profile_processes = {
        Path(item).stem.lower() for item in _profile_list(profile, "processes")
    }
    profile_titles = _profile_list(profile, "aliases") + _profile_list(
        profile, "window_titles"
    )

    def _match_row(name: str, title: str) -> bool:
        name = (name or "").lower()
        title = (title or "").lower()
        stem = Path(name).stem.lower()
        if stem in profile_processes and (
            stem != "applicationframehost"
            or any(_contains_phrase(title, phrase) for phrase in profile_titles)
        ):
            return True
        for tok in tokens:
            if tok and (tok in stem or tok in title):
                return True
        return False

    # Prefer verbose tasklist with window titles.
    try:
        out = subprocess.check_output(
            ["tasklist", "/v", "/fo", "csv", "/nh"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        reader = csv.reader(out.splitlines())
        for row in reader:
            if not row:
                continue
            name = row[0] if len(row) > 0 else ""
            title = row[-1] if len(row) > 0 else ""
            if _match_row(name, title):
                return True
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["tasklist", "/fo", "csv", "/nh"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        reader = csv.reader(out.splitlines())
        for row in reader:
            if not row:
                continue
            name = row[0] if len(row) > 0 else ""
            if _match_row(name, ""):
                return True
    except Exception:
        return False
    return False


def is_app_window_open(app_name: str) -> bool:
    name = canonical_app_name(app_name)
    hwnd = _find_window_for_app(name)
    return bool(hwnd)


def is_app_running(app_name: str) -> bool:
    name = canonical_app_name(app_name)
    tokens = _build_app_tokens(name)
    return _process_running_tokens(tokens, _get_app_profile(name))


def is_app_open(app_name: str) -> bool:
    return is_app_window_open(app_name) or is_app_running(app_name)


def is_app_focused(app_name: str) -> bool:
    if not IS_WINDOWS:
        return False
    name = canonical_app_name(app_name)
    tokens = _build_app_tokens(name)
    if not tokens:
        return False
    profile = _get_app_profile(name)
    profile_titles = _title_candidates_for_app(name)
    profile_processes = {
        Path(item).stem.lower() for item in _profile_list(profile, "processes")
    }
    title_required_processes = {
        Path(item).stem.lower()
        for item in _profile_list(profile, "title_required_processes")
    }
    user32 = ctypes.windll.user32
    fg = user32.GetForegroundWindow()
    if not fg:
        return False
    title = ""
    length = user32.GetWindowTextLengthW(fg)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(fg, buf, length + 1)
        title = (buf.value or "").strip().lower()
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
    exe = _process_image_name(pid.value)
    exe_stem = Path(exe).stem.lower() if exe else ""
    target_is_browser = _is_browser_target(name)
    title_match = any(_contains_phrase(title, phrase) for phrase in profile_titles)
    process_match = exe_stem in profile_processes or any(
        tok and tok in exe_stem for tok in tokens
    )
    if process_match:
        if exe_stem in title_required_processes:
            return title_match
        return True
    if title_match:
        if _is_browser_process_stem(exe_stem) and not target_is_browser:
            return False
        return True
    for tok in tokens:
        if tok and tok in title:
            if _is_browser_process_stem(exe_stem) and not target_is_browser:
                continue
            return True
        if tok and tok in exe_stem:
            return True
    hwnd = _find_window_for_app(name)
    return bool(hwnd and fg == hwnd)


def get_open_windows(limit: int = 20) -> list[dict]:
    if not IS_WINDOWS:
        return []
    user32 = ctypes.windll.user32
    titles: list[dict] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_proc(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").strip()
        if not title:
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_image_name(pid.value)
        exe_name = Path(exe).name if exe else ""
        titles.append({"title": title, "exe": exe_name})
        if len(titles) >= max(1, limit):
            return False
        return True

    user32.EnumWindows(enum_proc, 0)
    return titles


def get_active_window() -> dict:
    if not IS_WINDOWS:
        return {}
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {}
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = (buf.value or "").strip()
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = _process_image_name(pid.value)
    return {"title": title, "exe": Path(exe).name if exe else ""}


def get_system_stats() -> dict:
    if not IS_WINDOWS:
        return {}
    cpu = _cpu_usage_percent()
    ram = _memory_usage_percent()
    return {"cpu": cpu, "ram": ram}


def get_last_gui_map_summary() -> dict:
    items = _LAST_GUI_MAP.get("items") or []
    path = _LAST_GUI_MAP.get("image") or ""
    return {"count": len(items), "path": path}


def focus_window(app_name: str) -> bool:
    _ensure_windows()
    target = canonical_app_name(app_name or "")
    if not target:
        raise ValueError("missing")
    hwnd = _find_window_for_app(target)
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    current_thread = kernel32.GetCurrentThreadId()
    foreground = user32.GetForegroundWindow()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    )
    attached: list[int] = []
    try:
        for thread_id in {target_thread, foreground_thread}:
            if thread_id and thread_id != current_thread:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetWindowPos(
            hwnd,
            -1,  # HWND_TOPMOST
            0,
            0,
            0,
            0,
            0x0001 | 0x0002 | 0x0040,  # NOMOVE | NOSIZE | SHOWWINDOW
        )
        user32.SetWindowPos(
            hwnd,
            -2,  # HWND_NOTOPMOST
            0,
            0,
            0,
            0,
            0x0001 | 0x0002 | 0x0040,
        )
        user32.SetFocus(hwnd)
        return bool(user32.SetForegroundWindow(hwnd) or user32.GetForegroundWindow() == hwnd)
    finally:
        for thread_id in attached:
            user32.AttachThreadInput(current_thread, thread_id, False)


def wait_for_app_window(app_name: str, timeout: float = 5.0) -> bool:
    name = canonical_app_name(app_name)
    start = time.time()
    while time.time() - start < timeout:
        if _find_window_for_app(name):
            return True
        time.sleep(0.2)
    return False


def _wait_focus_stable(app_name: str, duration: float, poll: float) -> bool:
    if duration <= 0:
        return is_app_focused(app_name)
    deadline = time.time() + duration
    while time.time() < deadline:
        if not is_app_focused(app_name):
            return False
        time.sleep(max(0.05, poll))
    return is_app_focused(app_name)


def ensure_app_focus(
    app_name: str,
    attempts: int = FOCUS_ATTEMPTS,
    delay: float = FOCUS_VERIFY_DELAY,
    settle: float = FOCUS_RECHECK_DELAY,
    wait_window: float = APP_LAUNCH_TIMEOUT,
    ui_lang: str | None = None,
) -> bool:
    _ensure_windows()
    name = canonical_app_name(app_name)
    # Focus is only valid for visible, foreground-capable windows. Some UWP/system
    # apps keep background processes alive without a focusable window.
    if not is_app_window_open(name):
        _log(ui_lang, "focus_trace_wait_window", name=name, seconds=wait_window)
        if not wait_for_app_window(name, timeout=wait_window):
            return False
    total = max(1, attempts)
    for attempt in range(total):
        if not is_app_focused(name):
            _log(
                ui_lang,
                "focus_trace_attempt",
                attempt=attempt + 1,
                total=total,
                name=name,
            )
            focus_window(name)
        time.sleep(delay)
        if not is_app_focused(name):
            time.sleep(delay)
            continue
        if _wait_focus_stable(name, settle, FOCUS_POLL_INTERVAL):
            _log(ui_lang, "focus_trace_stable", name=name)
            return True
        if attempt < total - 1:
            _log(ui_lang, "focus_trace_lost", name=name)
            continue
        _log(ui_lang, "focus_trace_lost", name=name)
        if focus_window(name):
            time.sleep(delay)
            return _wait_focus_stable(name, min(1.0, settle), FOCUS_POLL_INTERVAL)
        time.sleep(delay)
    return is_app_focused(name)


def _crop_image(full_path: str, rect: tuple[int, int, int, int]) -> tuple[str, tuple[int, int]]:
    img = Image.open(full_path)
    left, top, right, bottom = rect
    # Adjust by virtual screen origin (multi-monitor layouts).
    vs_left = vs_top = 0
    try:
        user32 = ctypes.windll.user32
        vs_left = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        vs_top = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
    except Exception:
        vs_left = 0
        vs_top = 0
    left = left - vs_left
    right = right - vs_left
    top = top - vs_top
    bottom = bottom - vs_top
    left = max(0, left)
    top = max(0, top)
    right = min(img.width, right)
    bottom = min(img.height, bottom)
    if right <= left or bottom <= top:
        return full_path, (0, 0)
    cropped = img.crop((left, top, right, bottom))
    cropped_path = str(Path(full_path).with_name(Path(full_path).stem + "_crop.png"))
    cropped.save(cropped_path)
    return cropped_path, (left, top)


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


_init_dpi_awareness()

_LAST_GUI_MAP = {"items": [], "image": None}


def resolve_executable(value: str) -> str:
    value = value.strip()
    if not value:
        return value

    if Path(value).exists():
        return value

    alias_key = _find_alias_key(value)
    if alias_key:
        aliases = APP_ALIASES.get(alias_key)
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, list):
            for candidate in aliases:
                if not candidate:
                    continue
                expanded = os.path.expandvars(os.path.expanduser(candidate))
                if expanded and Path(expanded).exists():
                    return expanded

    aliases = APP_ALIASES.get(value.lower())
    if isinstance(aliases, str):
        aliases = [aliases]
    if isinstance(aliases, list):
        for candidate in aliases:
            if not candidate:
                continue
            expanded = os.path.expandvars(os.path.expanduser(candidate))
            if expanded and Path(expanded).exists():
                return expanded

    which = shutil.which(value)
    if which:
        return which

    return value


def _normalize_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _find_alias_key(text: str) -> str | None:
    if not text:
        return None
    profile_key = _find_profile_key(text)
    if profile_key:
        return profile_key
    folded = " ".join(_normalize_tokens(text))
    raw_lower = text.lower()
    for key, aliases in APP_TITLE_ALIASES.items():
        if any(_contains_phrase(text, alias) for alias in aliases):
            return key
    for key in APP_ALIASES.keys():
        key_l = key.lower()
        if _contains_phrase(folded, key_l) or key_l in raw_lower:
            return key_l
    return None


APP_STOPWORDS = {
    "app",
    "application",
    "program",
    "uygulama",
    "uygulamasi",
    "uygulaması",
    "uygulamayi",
    "uygulamayı",
    "adli",
    "adlı",
    "adinda",
    "adında",
    "adi",
    "adı",
    "player",
    "beta",
    "launcher",
    "update",
    "setup",
    "installer",
    "install",
    "client",
    "game",
    "oyun",
    "open",
    "ac",
    "aç",
    "run",
    "start",
    "close",
    "kapat",
    "exe",
}


def _filter_app_tokens(tokens: list[str]) -> list[str]:
    filtered = [t for t in tokens if t not in APP_STOPWORDS and len(t) > 1]
    return filtered if filtered else tokens


def normalize_app_query(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return raw
    # If looks like a path, do not normalize.
    if re.match(r"^[A-Za-z]:\\", raw) or "\\" in raw or "/" in raw:
        return raw
    tokens = _filter_app_tokens(_normalize_tokens(raw))
    if not tokens:
        return raw
    return " ".join(tokens)


def canonical_app_name(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return raw
    alias_key = _find_alias_key(raw)
    if alias_key:
        return alias_key
    return normalize_app_query(raw)


def _is_blocked_target(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower()
    name = Path(value).name.lower()
    for term in OPEN_BLOCKLIST:
        term = term.lower().strip()
        if not term:
            continue
        if term in lowered or term in name:
            return True
    return False


@lru_cache(maxsize=1)
def _start_menu_entries() -> list[Path]:
    if not IS_WINDOWS:
        return []
    entries: list[Path] = []
    program_data = os.environ.get("ProgramData")
    app_data = os.environ.get("AppData")
    public_dir = os.environ.get("PUBLIC")
    bases = []
    if program_data:
        bases.append(Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if app_data:
        bases.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    bases.append(Path.home() / "Desktop")
    if public_dir:
        bases.append(Path(public_dir) / "Desktop")
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in (".lnk", ".ink", ".exe"):
                entries.append(path)
    return entries


def _search_start_menu_app(query: str) -> Path | None:
    tokens = _filter_app_tokens(_normalize_tokens(query))
    if not tokens:
        return None
    best: tuple[int, int, int, Path] | None = None
    for path in _start_menu_entries():
        name = path.stem.lower()
        name_tokens = _normalize_tokens(name)
        matched = 0
        score = 0
        for tok in tokens:
            if tok in name or tok in name_tokens:
                matched += 1
                score += max(3, len(tok))
                if name.startswith(tok):
                    score += 2
        if matched == 0:
            continue
        if matched == len(tokens):
            score += 4
        cand = (score, matched, -len(name), path)
        if best is None or cand > best:
            best = cand
    if not best:
        return None
    score, matched, _, best_path = best
    if len(tokens) > 1 and matched < 2:
        return None
    if score < 3:
        return None
    return best_path


def _start_menu_search_open(
    query: str, ui_lang: str | None = None, allow_blocked: bool = False
) -> bool:
    if not IS_WINDOWS:
        return False
    if not query:
        return False
    if not allow_blocked and _is_blocked_target(query):
        raise RuntimeError("blocked_target")
    try:
        from pynput.keyboard import Controller, Key
    except Exception:
        return False
    _log(ui_lang, "open_trace_search_ui", target=query)
    controller = Controller()
    controller.press(Key.cmd)
    controller.release(Key.cmd)
    time.sleep(0.3)
    controller.type(query)
    time.sleep(0.2)
    controller.press(Key.enter)
    controller.release(Key.enter)
    return True


def _log(ui_lang: str | None, key: str, **kwargs):
    if not ui_lang:
        return
    try:
        print(t(ui_lang, key, **kwargs))
    except Exception:
        pass


def _wait_for_file(path: str, timeout: float = SCREENSHOT_WAIT_TIMEOUT) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if Path(path).exists():
            return True
        time.sleep(0.05)
    return False


def _wait_for_app_open(name: str, timeout: float = 3.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if is_app_open(name):
            return True
        time.sleep(0.2)
    return False


def _looks_like_path(value: str) -> bool:
    return (
        "/" in value
        or "\\" in value
        or re.match(r"^[A-Za-z]:\\", value) is not None
        or value.startswith(("~/", "./", "../"))
        or "." in Path(value).name
    )


def _format_size(num_bytes: int | float) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0


def _resolve_user_path(path: str | None, default: str = "desktop") -> Path:
    raw = (path or default or "").strip()
    folded = fold_text(raw)
    shortcuts = {
        "": Path.home() / "Desktop",
        "desktop": Path.home() / "Desktop",
        "masaustu": Path.home() / "Desktop",
        "masaustu": Path.home() / "Desktop",
        "home": Path.home(),
        "user": Path.home(),
        "documents": Path.home() / "Documents",
        "belgeler": Path.home() / "Documents",
        "downloads": Path.home() / "Downloads",
        "indirilenler": Path.home() / "Downloads",
        "pictures": Path.home() / "Pictures",
        "resimler": Path.home() / "Pictures",
        "music": Path.home() / "Music",
        "muzik": Path.home() / "Music",
        "videos": Path.home() / "Videos",
        "videolar": Path.home() / "Videos",
        "project": Path(__file__).resolve().parent,
        "proje": Path(__file__).resolve().parent,
    }
    if folded in shortcuts:
        return shortcuts[folded]
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if expanded.is_absolute():
        return expanded
    return Path.home() / expanded


def _search_file_by_name(name: str) -> Path | None:
    target = name.strip()
    if not target:
        return None
    target_lower = target.lower()
    has_ext = "." in Path(target).name
    visited = 0
    for base in FILE_SEARCH_DIRS:
        base = Path(base)
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            try:
                depth = len(Path(root).relative_to(base).parts)
            except Exception:
                depth = 0
            if depth > FILE_SEARCH_MAX_DEPTH:
                dirs[:] = []
                continue
            for fname in files:
                visited += 1
                if visited > FILE_SEARCH_MAX_FILES:
                    return None
                if has_ext:
                    if fname.lower() == target_lower:
                        return Path(root) / fname
                else:
                    if Path(fname).stem.lower() == target_lower:
                        return Path(root) / fname
    return None


def open_target(value: str, ui_lang: str | None = None, allow_blocked: bool = False):
    value = value.strip()
    if not value:
        return
    if not allow_blocked and _is_blocked_target(value):
        raise RuntimeError("blocked_target")
    if is_url(value):
        _log(ui_lang, "open_trace_url", target=value)
        _open_url(value)
        return
    resolved = resolve_executable(value)
    if not allow_blocked and _is_blocked_target(resolved):
        raise RuntimeError("blocked_target")
    if Path(resolved).exists():
        _log(ui_lang, "open_trace_path", target=resolved)
        _open_path(resolved)
        return
    if _looks_like_path(value):
        found = _search_file_by_name(value)
        if found:
            _log(ui_lang, "open_trace_path", target=found)
            _open_path(str(found))
            return
    # If it's not a file/path, try launching as an app name.
    start_app(value, ui_lang=ui_lang, allow_blocked=allow_blocked)


def _open_url(url: str):
    webbrowser.open(url)


def _open_path(path: str):
    _ensure_windows()
    os.startfile(path)


def _profile_start_commands(app_name: str) -> list[str]:
    profile = _get_app_profile(app_name)
    return _profile_list(profile, "start")


def _launch_profile_command(command: str):
    command = os.path.expandvars(os.path.expanduser((command or "").strip()))
    if not command:
        return
    if command.endswith(":"):
        os.startfile(command)
        return
    resolved = resolve_executable(command)
    if Path(resolved).exists():
        os.startfile(resolved)
        return
    subprocess.Popen(command, shell=True)


def start_app_verified(
    value: str,
    ui_lang: str | None = None,
    allow_blocked: bool = False,
    wait_sec: float = APP_LAUNCH_TIMEOUT,
) -> tuple[bool, str]:
    raw_value = (value or "").strip()
    target = canonical_app_name(raw_value)
    _ensure_windows()
    if not target:
        return False, "missing"
    if is_app_window_open(target):
        return True, "already_open"
    alias_key = _find_alias_key(raw_value)
    resolved = resolve_executable(alias_key or raw_value or target)
    if not allow_blocked and (_is_blocked_target(resolved) or _is_blocked_target(target)):
        raise RuntimeError("blocked_target")

    methods: list[tuple[str, callable]] = []
    has_config_path = Path(resolved).exists()
    if has_config_path:
        methods.append(("exe", lambda: os.startfile(resolved)))

    for command in _profile_start_commands(target):
        if not allow_blocked and _is_blocked_target(command):
            raise RuntimeError("blocked_target")
        methods.append(("profile", lambda cmd=command: _launch_profile_command(cmd)))

    candidate = _search_start_menu_app(target)

    if candidate:
        methods.append(("shortcut", lambda: os.startfile(str(candidate))))
    # Prefer Windows search UI after explicit config path and shortcut files.
    if not _looks_like_path(raw_value):
        methods.append(
            (
                "search_ui",
                lambda: _start_menu_search_open(
                    target, ui_lang=ui_lang, allow_blocked=allow_blocked
                ),
            )
        )
    methods.append(("shell", lambda: subprocess.Popen(f'start "" "{resolved}"', shell=True)))

    for method, fn in methods:
        try:
            if is_app_window_open(target):
                time.sleep(APP_LAUNCH_SETTLE_SEC)
                return True, "already_open"
            if method == "exe":
                _log(ui_lang, "open_trace_exe", target=resolved)
            elif method == "profile":
                _log(ui_lang, "open_trace_exe", target=target)
            elif method == "shortcut" and candidate:
                _log(ui_lang, "open_trace_start_menu", target=str(candidate))
            elif method == "shell":
                _log(ui_lang, "open_trace_shell", target=resolved)
            fn()
        except Exception:
            pass
        _log(ui_lang, "app_launch_wait", name=target, seconds=wait_sec)
        if wait_for_app_window(target, timeout=wait_sec):
            time.sleep(APP_LAUNCH_SETTLE_SEC)
            return True, method
        if is_app_running(target):
            _log(
                ui_lang,
                "app_launch_running_wait",
                name=target,
                seconds=APP_LAUNCH_RUNNING_EXTRA_TIMEOUT,
            )
            if wait_for_app_window(target, timeout=APP_LAUNCH_RUNNING_EXTRA_TIMEOUT):
                time.sleep(APP_LAUNCH_SETTLE_SEC)
                return True, method
        time.sleep(0.4)
    return False, "not_found"


def start_app(value: str, ui_lang: str | None = None, allow_blocked: bool = False):
    try:
        start_app_verified(value, ui_lang=ui_lang, allow_blocked=allow_blocked)
    except RuntimeError:
        raise


def close_process(value: str):
    value = value.strip()
    if not value:
        return
    _ensure_windows()
    proc = _process_name(value)

    if proc.isdigit():
        subprocess.Popen(f"taskkill /PID {proc} /T /F", shell=True)
    else:
        subprocess.Popen(f'taskkill /IM "{proc}" /T /F', shell=True)


def _process_name(value: str) -> str:
    if value.isdigit():
        return value
    cleaned = re.sub(
        r"\b(app|application|program|uygulama|uygulamasi|uygulaması|uygulamayi|uygulamayı)\b",
        "",
        value,
        flags=re.IGNORECASE,
    ).strip()
    resolved = resolve_executable(cleaned or value)
    name = Path(resolved).name if resolved else (cleaned or value)
    if not name.lower().endswith(".exe") and IS_WINDOWS:
        name += ".exe"
    return name


def delete_path(value: str):
    value = value.strip()
    if not value:
        return
    if Path(value).exists():
        send2trash(value)


def open_search(query: str):
    query = query.strip()
    if not query:
        return
    url = WEB_SEARCH_URL_BROWSER.format(query=quote_plus(query))
    webbrowser.open(url)


def open_url_in_browser(browser: str | None, url: str):
    if not url:
        return
    target = url.strip()
    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    if not browser:
        webbrowser.open(target)
        return
    name = browser.strip().lower()
    if name in ("default", "system", "normal", "browser"):
        webbrowser.open(target)
        return
    exe = resolve_executable(name)
    if Path(exe).exists():
        try:
            subprocess.Popen([exe, target])
            return
        except Exception:
            pass
    # Fallback: try shell open with browser name.
    try:
        webbrowser.get(name).open(target)
    except Exception:
        webbrowser.open(target)


def type_text(text: str):
    text = text or ""
    if not text:
        return
    from pynput.keyboard import Controller

    # Clipboard paste is faster and more reliable for long, multiline, or non-ASCII text.
    use_clipboard = len(text) > 40 or "\n" in text or any(ord(ch) > 127 for ch in text)
    if use_clipboard:
        try:
            import pyperclip

            old = pyperclip.paste()
            pyperclip.copy(text)
            send_hotkey("ctrl v")
            time.sleep(0.05)
            pyperclip.copy(old)
            return
        except Exception:
            pass
    Controller().type(text)


def send_hotkey(combo: str):
    combo = combo.strip()
    if not combo:
        return
    from pynput.keyboard import Controller, Key

    key_map = {}
    for name in dir(Key):
        if name.startswith("_"):
            continue
        value = getattr(Key, name)
        if isinstance(value, Key):
            key_map[name.lower()] = value

    aliases = {
        "ctrl": "ctrl",
        "control": "ctrl",
        "ctl": "ctrl",
        "alt": "alt",
        "option": "alt",
        "altgr": "alt_gr",
        "shift": "shift",
        "cmd": "cmd",
        "win": "cmd",
        "windows": "cmd",
        "meta": "cmd",
        "super": "cmd",
        "esc": "esc",
        "escape": "esc",
        "enter": "enter",
        "return": "enter",
        "tab": "tab",
        "tb": "tab",
        "space": "space",
        "backspace": "backspace",
        "bksp": "backspace",
        "delete": "delete",
        "del": "delete",
        "insert": "insert",
        "ins": "insert",
        "home": "home",
        "end": "end",
        "pageup": "page_up",
        "pgup": "page_up",
        "pagedown": "page_down",
        "pgdn": "page_down",
        "printscreen": "print_screen",
        "prtsc": "print_screen",
        "capslock": "caps_lock",
        "numlock": "num_lock",
        "scrolllock": "scroll_lock",
        "pause": "pause",
    }

    multi_word = {
        ("page", "up"): "page_up",
        ("page", "down"): "page_down",
        ("print", "screen"): "print_screen",
        ("scroll", "lock"): "scroll_lock",
        ("caps", "lock"): "caps_lock",
        ("num", "lock"): "num_lock",
        ("pause", "break"): "pause",
    }

    tokens = [t for t in re.split(r"[+\s-]+", combo.lower()) if t]
    merged = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens):
            pair = (tokens[i], tokens[i + 1])
            if pair in multi_word:
                merged.append(multi_word[pair])
                i += 2
                continue
        merged.append(tokens[i])
        i += 1
    tokens = merged

    keys = []
    for token in tokens:
        token = aliases.get(token, token)
        if token in key_map:
            keys.append(key_map[token])
            continue
        if token.startswith("f") and token[1:].isdigit():
            fn = f"f{token[1:]}"
            if fn in key_map:
                keys.append(key_map[fn])
                continue
        if len(token) == 1:
            keys.append(token)
            continue
        if token in {"minus", "dash"}:
            keys.append("-")
            continue
        if token in {"equal", "equals"}:
            keys.append("=")
            continue
        if token in {"comma"}:
            keys.append(",")
            continue
        if token in {"dot", "period"}:
            keys.append(".")
            continue
        if token in {"slash"}:
            keys.append("/")
            continue
        if token in {"backslash"}:
            keys.append("\\")
            continue
        if token in {"semicolon"}:
            keys.append(";")
            continue
        if token in {"quote", "apostrophe"}:
            keys.append("'")
            continue
        raise ValueError(f"unknown hotkey: {token}")

    controller = Controller()
    for key in keys:
        controller.press(key)
    for key in reversed(keys):
        controller.release(key)


def media_action(action: str):
    action = (action or "").strip().lower()
    if not action:
        return
    from pynput.keyboard import Controller, Key

    mapping = {
        "play": Key.media_play_pause,
        "pause": Key.media_play_pause,
        "play_pause": Key.media_play_pause,
        "toggle": Key.media_play_pause,
        "next": Key.media_next,
        "next_track": Key.media_next,
        "prev": Key.media_previous,
        "previous": Key.media_previous,
        "previous_track": Key.media_previous,
        "stop": Key.media_stop,
    }
    key = mapping.get(action)
    if not key:
        raise ValueError(f"unknown media action: {action}")

    controller = Controller()
    controller.press(key)
    controller.release(key)


def toggle_mute():
    from pynput.keyboard import Controller, Key

    controller = Controller()
    controller.press(Key.media_volume_mute)
    controller.release(Key.media_volume_mute)


def browser_action(action: str):
    action = (action or "").strip().lower()
    if not action:
        raise ValueError("missing browser action")
    _ensure_windows()
    mod = "ctrl"
    mapping = {
        "new_tab": f"{mod} t",
        "close_tab": f"{mod} w",
        "next_tab": f"{mod} tab",
        "prev_tab": f"{mod} shift tab",
        "refresh": f"{mod} r",
        "address_bar": f"{mod} l",
        "downloads": f"{mod} j",
        "history": f"{mod} h",
    }
    if action in ("back", "forward"):
        combo = "alt left" if action == "back" else "alt right"
        send_hotkey(combo)
        return
    combo = mapping.get(action)
    if not combo:
        raise ValueError(f"unknown browser action: {action}")
    send_hotkey(combo)


def desktop_action(action: str):
    action = (action or "show").strip().lower().replace("-", "_").replace(" ", "_")
    _ensure_windows()
    if action in ("minimize", "minimize_all"):
        send_hotkey("cmd m")
        return
    if action in ("show", "toggle", "desktop", "show_desktop"):
        send_hotkey("cmd d")
        return
    mapping = {
        "snap_left": "cmd left",
        "snap_right": "cmd right",
        "maximize": "cmd up",
        "restore": "cmd down",
        "task_manager": "ctrl shift esc",
        "run": "cmd r",
        "file_explorer": "cmd e",
        "copy": "ctrl c",
        "paste": "ctrl v",
        "cut": "ctrl x",
        "undo": "ctrl z",
        "redo": "ctrl y",
        "select_all": "ctrl a",
        "save": "ctrl s",
        "refresh": "f5",
        "fullscreen": "f11",
        "enter": "enter",
        "escape": "esc",
        "clear_field": "ctrl a backspace",
    }
    combo = mapping.get(action)
    if not combo:
        raise ValueError(f"unknown desktop action: {action}")
    send_hotkey(combo)


def scroll_action(direction: str, amount: int):
    from pynput.mouse import Controller

    direction = (direction or "down").strip().lower()
    amount = int(max(1, amount))
    delta = amount if direction == "down" else -amount
    Controller().scroll(0, delta)


def gui_click(x: int, y: int, clicks: int = 1, button: str = "left"):
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    scale = _get_scale_factor()
    if not _DPI_AWARE and scale and scale != 1.0:
        x = int(x / scale)
        y = int(y / scale)
    pyautogui.click(x=int(x), y=int(y), clicks=int(clicks), button=button)


def gui_wait(seconds: float):
    time.sleep(max(0.0, float(seconds)))


def _ocr_words_from_image(
    image_path: str,
    lang: str | None,
    offset: tuple[int, int] = (0, 0),
    min_conf: float = 40.0,
    psm: int = 6,
):
    import cv2
    import pytesseract
    from pytesseract import Output

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("invalid_image")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Upscale for better OCR on small UI text.
    scale = 2.0
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # If screen is dark (Discord dark mode etc.), invert for OCR.
    if gray.mean() < 110:
        gray = cv2.bitwise_not(gray)
    gray = cv2.medianBlur(gray, 3)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = f"--oem 1 --psm {psm}"
    data = pytesseract.image_to_data(
        thresh, lang=lang, config=config, output_type=Output.DICT
    )
    words = []
    for i, txt in enumerate(data.get("text", [])):
        if not txt or not txt.strip():
            continue
        try:
            conf = float(data.get("conf", [])[i])
        except Exception:
            conf = 0.0
        if conf < float(min_conf):
            continue
        left = int(data["left"][i] / scale) + offset[0]
        top = int(data["top"][i] / scale) + offset[1]
        width = int(data["width"][i] / scale)
        height = int(data["height"][i] / scale)
        words.append(
            {
                "text": txt,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "conf": conf,
            }
        )
    return words


def _dedupe_words(words: list[dict]) -> list[dict]:
    if not words:
        return []
    kept: list[dict] = []
    for w in sorted(words, key=lambda item: item.get("conf", 0.0), reverse=True):
        left = w["left"]
        top = w["top"]
        right = w["left"] + w["width"]
        bottom = w["top"] + w["height"]
        box = (left, top, right, bottom)
        if any(
            _boxes_overlap(
                box,
                (
                    k["left"],
                    k["top"],
                    k["left"] + k["width"],
                    k["top"] + k["height"],
                ),
            )
            > 0.7
            for k in kept
        ):
            continue
        kept.append(w)
    return kept


def _ocr_words_multi(
    image_path: str,
    lang: str | None,
    offset: tuple[int, int] = (0, 0),
    min_conf: float = 0.0,
) -> list[dict]:
    words: list[dict] = []
    for psm in (6, 11, 3):
        try:
            words.extend(
                _ocr_words_from_image(
                    image_path,
                    lang=lang,
                    offset=offset,
                    min_conf=min_conf,
                    psm=psm,
                )
            )
        except Exception:
            continue
    return _dedupe_words(words)


def _filter_map_items(
    items: list[dict],
    rect: tuple[int, int, int, int] | None,
    screen_size: tuple[int, int],
    min_area: int,
    max_area: int,
    min_ratio: float,
) -> list[dict]:
    if not items:
        return []
    screen_w, screen_h = screen_size
    rect_use = None
    if rect:
        left, top, right, bottom = rect
        rect_area = max(0, right - left) * max(0, bottom - top)
        if screen_w > 0 and screen_h > 0 and rect_area >= screen_w * screen_h * min_ratio:
            rect_use = rect
    margin = 8
    filtered: list[dict] = []
    for w in items:
        area = int(w["width"]) * int(w["height"])
        if area < min_area or area > max_area:
            continue
        if rect_use:
            left, top, right, bottom = rect_use
            cx = w["left"] + w["width"] / 2
            cy = w["top"] + w["height"] / 2
            if not (left - margin <= cx <= right + margin and top - margin <= cy <= bottom + margin):
                continue
        filtered.append(w)
    return filtered


def _word_box(word: dict) -> tuple[int, int, int, int]:
    return (
        int(word["left"]),
        int(word["top"]),
        int(word["left"] + word["width"]),
        int(word["top"] + word["height"]),
    )


def _box_region(
    box: tuple[int, int, int, int],
    container_rect: tuple[int, int, int, int] | None,
    screen_size: tuple[int, int] | None = None,
) -> str:
    if container_rect:
        left, top, right, bottom = container_rect
    else:
        width, height = screen_size or (1920, 1080)
        left, top, right, bottom = 0, 0, width, height
    w = max(1, right - left)
    h = max(1, bottom - top)
    cx = ((box[0] + box[2]) / 2 - left) / w
    cy = ((box[1] + box[3]) / 2 - top) / h
    if cy < 0.10:
        return "top_bar"
    if cy > 0.90:
        return "bottom_bar"
    if cx < 0.07:
        return "far_left_nav"
    if cx < 0.23:
        return "left_sidebar"
    if cx < 0.43:
        return "left_list"
    if cx > 0.74:
        return "right_panel"
    return "center_content"


def _nearby_words_text(
    words: list[dict],
    box: tuple[int, int, int, int],
    limit: int = 10,
) -> str:
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    scored: list[tuple[float, str]] = []
    for w in words:
        text = str(w.get("text") or "").strip()
        if not text or text == "[box]":
            continue
        wb = _word_box(w)
        wcx = (wb[0] + wb[2]) / 2
        wcy = (wb[1] + wb[3]) / 2
        dx = abs(wcx - cx)
        dy = abs(wcy - cy)
        if dx > 420 or dy > 90:
            continue
        scored.append((dx + dy * 2, text))
    scored.sort(key=lambda item: item[0])
    return " ".join(text for _score, text in scored[:limit])


def _is_discord_active() -> bool:
    try:
        active = get_active_window()
    except Exception:
        active = {}
    folded = fold_text(f"{active.get('title', '')} {active.get('exe', '')}")
    return "discord" in folded


def _score_text_candidate(
    candidate: dict,
    target_tokens: list[str],
    words: list[dict],
    container_rect: tuple[int, int, int, int] | None,
    screen_size: tuple[int, int] | None,
) -> float:
    score = float(candidate.get("base_score", 0.0))
    box = candidate["box"]
    region = _box_region(box, container_rect, screen_size)
    nearby = fold_text(_nearby_words_text(words, box))
    is_discord = _is_discord_active()

    if region == "center_content":
        score += 18
    elif region == "left_list":
        score += 16
    elif region == "left_sidebar":
        score += 8
    elif region == "far_left_nav":
        score -= 8
    elif region == "top_bar":
        score -= 6
    elif region == "bottom_bar":
        score -= 4
    elif region == "right_panel":
        score -= 6

    if is_discord:
        # In Discord, duplicate names often appear in activity/profile panels.
        # Prefer actionable lists/search results, but do not ban right-panel hits.
        if region in {"left_list", "center_content"}:
            score += 18
        elif region == "right_panel":
            score -= 30
        if any(
            term in nearby
            for term in (
                "message",
                "mesaj",
                "direct",
                "direkt",
                "arkadas",
                "arkadaş",
                "friend",
                "sohbet",
            )
        ):
            score += 18
        if any(
            term in nearby
            for term in (
                "simdi aktif",
                "şimdi aktif",
                "active now",
                "yayinda",
                "yayında",
                "ses kanalinda",
                "ses kanalında",
                "stream",
            )
        ):
            score -= 24

    source_bonus = 0
    for w in candidate.get("words", []):
        if w.get("source") == "uia":
            source_bonus = max(source_bonus, 10)
        control = fold_text(str(w.get("control_type") or ""))
        if any(term in control for term in ("button", "list", "edit", "text")):
            source_bonus = max(source_bonus, 8)
    score += source_bonus

    joined = " ".join(fold_text(str(w.get("text") or "")) for w in candidate.get("words", []))
    if joined == " ".join(target_tokens):
        score += 14
    return score


def _find_text_candidates(words: list[dict], target: str) -> list[dict]:
    target_tokens = [t for t in fold_text(target).split() if t]
    if not target_tokens:
        return []
    ordered_words = sorted(words, key=lambda w: (w["top"], w["left"]))
    tokens = [fold_text(w["text"]) for w in ordered_words]
    n = len(target_tokens)
    candidates: list[dict] = []

    def _token_match(a: str, b: str) -> bool:
        if a == b:
            return True
        if len(a) >= 4 and a in b:
            return True
        if len(b) >= 4 and b in a:
            return True
        return False

    for i in range(len(tokens) - n + 1):
        window = tokens[i : i + n]
        ok = all(_token_match(window[j], target_tokens[j]) for j in range(n))
        if not ok:
            continue
        group = ordered_words[i : i + n]
        conf_sum = sum(float(w.get("conf", 0.0)) for w in group)
        left = min(w["left"] for w in group)
        top = min(w["top"] for w in group)
        right = max(w["left"] + w["width"] for w in group)
        bottom = max(w["top"] + w["height"] for w in group)
        candidates.append(
            {
                "box": (left, top, right, bottom),
                "words": group,
                "base_score": conf_sum + sum(len(t) for t in target_tokens) * 2,
            }
        )

    # fallback: single token fuzzy match
    if not candidates and n == 1:
        target_tok = target_tokens[0]
        for i, tok in enumerate(tokens):
            ratio = SequenceMatcher(a=tok, b=target_tok).ratio()
            if ratio >= 0.82 and len(target_tok) >= 4:
                w = ordered_words[i]
                candidates.append(
                    {
                        "box": _word_box(w),
                        "words": [w],
                        "base_score": float(w.get("conf", 0.0)) * ratio,
                    }
                )
    return candidates


def _find_text_box(
    words: list[dict],
    target: str,
    container_rect: tuple[int, int, int, int] | None = None,
    screen_size: tuple[int, int] | None = None,
):
    target_tokens = [t for t in fold_text(target).split() if t]
    candidates = _find_text_candidates(words, target)
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda item: _score_text_candidate(
            item, target_tokens, words, container_rect, screen_size
        ),
    )
    return best["box"]


def _enrich_map_items(
    words: list[dict],
    container_rect: tuple[int, int, int, int] | None,
    screen_size: tuple[int, int],
) -> list[dict]:
    enriched: list[dict] = []
    for item in words:
        updated = dict(item)
        box = _word_box(updated)
        updated["region"] = _box_region(box, container_rect, screen_size)
        updated["nearby_text"] = _nearby_words_text(words, box, limit=8)
        enriched.append(updated)
    return enriched


def gui_click_text(target: str, ui_lang: str | None = None) -> tuple[int, int]:
    try:
        from uia_automation import click_text as uia_click_text

        clicked = uia_click_text(target)
        if clicked:
            return clicked
    except Exception:
        pass
    last_err = None
    for _ in range(3):
        full_path = take_screenshot(None)
        image_path = full_path
        try:
            screen_size = Image.open(full_path).size
        except Exception:
            screen_size = None
        rect = _get_foreground_rect()
        offset = (0, 0)
        if rect:
            image_path, offset = _crop_image(image_path, rect)
        lang_primary = OCR_LANG_TR if ui_lang == "tr" else OCR_LANG_EN
        lang_combo = OCR_LANG_BOTH
        try:
            words = _ocr_words_from_image(image_path, lang=lang_combo, offset=offset, min_conf=40)
        except Exception:
            words = _ocr_words_from_image(image_path, lang=lang_primary, offset=offset, min_conf=40)
        box = _find_text_box(words, target, container_rect=rect, screen_size=screen_size)
        if box:
            left, top, right, bottom = box
            x = int((left + right) / 2)
            y = int((top + bottom) / 2)
            gui_click(x, y, clicks=1)
            return x, y
        last_err = ValueError("text_not_found")
        time.sleep(0.4)
    raise last_err


def _locate_image_on_screen(path: str, threshold: float = 0.85) -> tuple[int, int] | None:
    import cv2

    if not path or not Path(path).exists():
        raise FileNotFoundError(path)
    screen_path = take_screenshot(None)
    screen = cv2.imread(screen_path, cv2.IMREAD_GRAYSCALE)
    template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if screen is None or template is None:
        raise ValueError("invalid_image")
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val < threshold:
        return None
    h, w = template.shape[:2]
    x = max_loc[0] + w // 2
    y = max_loc[1] + h // 2
    return x, y


def gui_click_image(path: str, threshold: float = 0.85) -> tuple[int, int]:
    last_err = None
    for _ in range(3):
        loc = _locate_image_on_screen(path, threshold=threshold)
        if loc:
            x, y = loc
            gui_click(x, y, clicks=1)
            return x, y
        last_err = ValueError("image_not_found")
        time.sleep(0.4)
    raise last_err


def gui_wait_text(
    target: str,
    timeout_sec: float = 6.0,
    ui_lang: str | None = None,
    interval_sec: float = 0.6,
) -> bool:
    try:
        from uia_automation import wait_text as uia_wait_text

        if uia_wait_text(target, timeout_sec=min(float(timeout_sec), 2.5)):
            return True
    except Exception:
        pass
    deadline = time.time() + max(0.1, timeout_sec)
    while time.time() < deadline:
        full_path = take_screenshot(None)
        image_path = full_path
        try:
            screen_size = Image.open(full_path).size
        except Exception:
            screen_size = None
        rect = _get_foreground_rect()
        offset = (0, 0)
        if rect:
            image_path, offset = _crop_image(image_path, rect)
        lang_primary = OCR_LANG_TR if ui_lang == "tr" else OCR_LANG_EN
        lang_combo = OCR_LANG_BOTH
        try:
            words = _ocr_words_from_image(image_path, lang=lang_combo, offset=offset, min_conf=40)
        except Exception:
            words = _ocr_words_from_image(image_path, lang=lang_primary, offset=offset, min_conf=40)
        box = _find_text_box(words, target, container_rect=rect, screen_size=screen_size)
        if box:
            return True
        time.sleep(max(0.1, interval_sec))
    raise ValueError("text_not_found")


def gui_wait_image(
    path: str,
    threshold: float = 0.85,
    timeout_sec: float = 6.0,
    interval_sec: float = 0.6,
) -> bool:
    deadline = time.time() + max(0.1, timeout_sec)
    while time.time() < deadline:
        loc = _locate_image_on_screen(path, threshold=threshold)
        if loc:
            return True
        time.sleep(max(0.1, interval_sec))
    raise ValueError("image_not_found")


def _boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / float(area_a + area_b - inter)


def _detect_visual_boxes(
    image_path: str, min_area: int = 350, max_area: int = 120000
) -> list[tuple[int, int, int, int]]:
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 60, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        area = w * h
        if area < min_area or area > max_area:
            continue
        aspect = w / float(h + 1)
        if aspect < 0.15 or aspect > 10.0:
            continue
        boxes.append((x, y, x + w, y + h))
    return boxes


def gui_map_text(ui_lang: str | None = None, max_items: int | None = None) -> tuple[str, list[dict]]:
    max_items = max_items or GUI_MAP_MAX_ITEMS
    full_path = take_screenshot(None)
    rect = None
    offset = (0, 0)
    ocr_path = full_path
    lang_primary = OCR_LANG_TR if ui_lang == "tr" else OCR_LANG_EN
    lang_combo = OCR_LANG_BOTH
    try:
        words = _ocr_words_multi(
            ocr_path, lang=lang_combo, offset=offset, min_conf=GUI_MAP_MIN_CONF
        )
    except Exception:
        words = _ocr_words_multi(
            ocr_path, lang=lang_primary, offset=offset, min_conf=GUI_MAP_MIN_CONF
        )

    img = Image.open(full_path).convert("RGB")
    screen_size = (img.width, img.height)
    active_rect = _get_foreground_rect()

    words = _filter_map_items(
        words,
        rect=rect,
        screen_size=screen_size,
        min_area=GUI_MAP_MIN_AREA,
        max_area=GUI_MAP_MAX_AREA,
        min_ratio=GUI_MAP_RECT_MIN_RATIO,
    )
    # sort roughly top->bottom, left->right
    words = sorted(words, key=lambda w: (w["top"], w["left"]))
    if max_items and len(words) > max_items:
        words = words[:max_items]

    # Add Windows UI Automation elements before visual boxes. This gives the agent
    # semantic controls (buttons, edits, tabs) instead of relying only on OCR text.
    try:
        from uia_automation import summarize_foreground

        uia_summary = summarize_foreground(max_depth=4, max_items=120)
        for item in uia_summary.get("items", []):
            rect_item = item.get("rect")
            name = str(item.get("name") or item.get("automation_id") or "").strip()
            if not name or not rect_item:
                continue
            left, top, right, bottom = [int(v) for v in rect_item]
            if right <= left or bottom <= top:
                continue
            words.append(
                {
                    "text": name,
                    "left": left,
                    "top": top,
                    "width": right - left,
                    "height": bottom - top,
                    "conf": 100.0,
                    "source": "uia",
                    "control_type": item.get("control_type", ""),
                }
            )
    except Exception:
        pass
    words = _dedupe_words(words)

    # Add visual (non-text) boxes for images/icons.
    visual_boxes = _detect_visual_boxes(
        full_path, min_area=GUI_MAP_MIN_AREA, max_area=GUI_MAP_MAX_AREA
    )
    text_boxes = [
        (w["left"], w["top"], w["left"] + w["width"], w["top"] + w["height"])
        for w in words
    ]
    visual_items: list[dict] = []
    for box in visual_boxes:
        if any(_boxes_overlap(box, tb) > 0.6 for tb in text_boxes):
            continue
        left, top, right, bottom = box
        visual_items.append(
            {
                "text": "[box]",
                "left": left,
                "top": top,
                "width": right - left,
                "height": bottom - top,
                "conf": 0.0,
            }
        )
    if visual_items:
        remaining = max_items - len(words) if max_items else len(visual_items)
        if remaining > 0:
            words.extend(visual_items[:remaining])
    words = _filter_map_items(
        words,
        rect=rect,
        screen_size=screen_size,
        min_area=GUI_MAP_MIN_AREA,
        max_area=GUI_MAP_MAX_AREA,
        min_ratio=GUI_MAP_RECT_MIN_RATIO,
    )
    words = _enrich_map_items(words, active_rect, screen_size)
    draw = ImageDraw.Draw(img)
    for idx, w in enumerate(words, start=1):
        left = w["left"]
        top = w["top"]
        right = w["left"] + w["width"]
        bottom = w["top"] + w["height"]
        if w.get("source") == "uia":
            color = (0, 255, 120)
        else:
            color = (0, 180, 255) if w.get("text") == "[box]" else (255, 0, 0)
        draw.rectangle([left, top, right, bottom], outline=color, width=2)
        draw.text((left + 2, top + 2), str(idx), fill=(255, 255, 0))

    GUI_MAP_DIR.mkdir(parents=True, exist_ok=True)
    map_name = Path(full_path).stem + "_map.png"
    map_path = str(GUI_MAP_DIR / map_name)
    img.save(map_path)
    _LAST_GUI_MAP["items"] = words
    _LAST_GUI_MAP["image"] = map_path
    return map_path, words


def gui_click_index(index: int) -> tuple[int, int]:
    if not _LAST_GUI_MAP.get("items"):
        raise ValueError("map_empty")
    items = _LAST_GUI_MAP["items"]
    idx = int(index)
    if idx < 1 or idx > len(items):
        raise ValueError("map_index")
    w = items[idx - 1]
    x = int(w["left"] + w["width"] / 2)
    y = int(w["top"] + w["height"] / 2)
    gui_click(x, y, clicks=1)
    return x, y


def _group_words_by_row(words: list[dict], y_tol: int = 12) -> list[dict]:
    rows: list[dict] = []
    for w in sorted(words, key=lambda item: (item["top"], item["left"])):
        placed = False
        for row in rows:
            if abs(w["top"] - row["top"]) <= y_tol:
                row["words"].append(w)
                row["top"] = min(row["top"], w["top"])
                row["bottom"] = max(row["bottom"], w["top"] + w["height"])
                row["left"] = min(row["left"], w["left"])
                row["right"] = max(row["right"], w["left"] + w["width"])
                placed = True
                break
        if not placed:
            rows.append(
                {
                    "top": w["top"],
                    "bottom": w["top"] + w["height"],
                    "left": w["left"],
                    "right": w["left"] + w["width"],
                    "words": [w],
                }
            )
    return rows


def _pick_youtube_result(words: list[dict]) -> tuple[int, int] | None:
    if not words:
        return None
    rows = _group_words_by_row(words)
    for row in rows:
        ordered_words = sorted(row["words"], key=lambda t: t["left"])
        tokens = [fold_text(w["text"]) for w in ordered_words]
        text = " ".join(tokens).strip()
        if len(text) < 8:
            continue
        if row["left"] < 120:
            continue
        if any(tok in ("reklam", "sponsored") for tok in tokens):
            continue
        if any(tok == "ad" for tok in tokens) and len(tokens) <= 2:
            continue
        if any(tok in ("filtreler", "filters", "shorts", "kanallar", "playlists") for tok in tokens):
            continue
        # Skip shorts by detecting very short durations (e.g., 0:15).
        short_hit = False
        for word in ordered_words:
            raw = str(word.get("text", "")).strip()
            if re.match(r"^\d{1,2}:\d{2}$", raw):
                parts = raw.split(":")
                try:
                    mins = int(parts[0])
                    secs = int(parts[1])
                except Exception:
                    continue
                if mins == 0 and secs < 60:
                    short_hit = True
                    break
        if short_hit:
            continue
        x = int((row["left"] + row["right"]) / 2)
        y = int((row["top"] + row["bottom"]) / 2)
        return x, y
    return None


def _scrape_first_youtube_video_url(query: str) -> str | None:
    if not query:
        return None
    try:
        import requests
    except Exception:
        return None
    url = (
        "https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        "&sp=EgIQAQ%3D%3D"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()
        html = resp.text
        seen: set[str] = set()
        for video_id in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
            if video_id in seen:
                continue
            seen.add(video_id)
            if f"/shorts/{video_id}" in html:
                continue
            return f"https://www.youtube.com/watch?v={video_id}"
    except Exception:
        return None
    return None


def open_youtube_first_result(
    query: str, browser: str | None = None, ui_lang: str | None = None
) -> bool:
    if not query:
        return False
    direct_url = _scrape_first_youtube_video_url(query)
    if direct_url:
        open_url_in_browser(browser, direct_url)
        return True
    url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
    open_url_in_browser(browser, url)
    time.sleep(2.5)
    if browser:
        try:
            ensure_app_focus(browser)
        except Exception:
            pass
        time.sleep(0.4)
    try:
        _, words = gui_map_text(ui_lang=ui_lang)
    except Exception:
        return False
    hit = _pick_youtube_result(words)
    if not hit:
        return False
    x, y = hit
    gui_click(x, y, clicks=1)
    return True


def zoom_action(action: str):
    action = (action or "").strip().lower()
    _ensure_windows()
    mod = "ctrl"
    if action in ("in", "zoom_in", "+"):
        send_hotkey(f"{mod} equal")
        return
    if action in ("out", "zoom_out", "-"):
        send_hotkey(f"{mod} minus")
        return
    if action in ("reset", "normal", "100"):
        send_hotkey(f"{mod} 0")
        return
    raise ValueError(f"unknown zoom action: {action}")


def list_dir(path: str | None, limit: int = 50) -> list[str]:
    base = _resolve_user_path(path, default="desktop") if path else Path.home() / "Desktop"
    if base.is_file():
        base = base.parent
    if not base.exists():
        raise FileNotFoundError(str(base))
    items = sorted(base.iterdir(), key=lambda p: p.name.lower())
    names = [p.name + ("/" if p.is_dir() else "") for p in items[:limit]]
    return names


def find_files(
    name: str = "",
    extension: str = "",
    path: str | None = None,
    max_results: int = 20,
) -> list[str]:
    base = _resolve_user_path(path, default="home")
    if not base.exists():
        raise FileNotFoundError(str(base))
    if base.is_file():
        base = base.parent
    query = (name or "").strip().lower()
    ext = (extension or "").strip().lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    if not query and not ext:
        raise ValueError("missing search query")
    results: list[str] = []
    for item in base.rglob("*"):
        try:
            if not item.is_file():
                continue
            if ext and item.suffix.lower() != ext:
                continue
            if query and query not in item.stem.lower() and query not in item.name.lower():
                continue
            results.append(str(item))
            if len(results) >= max(1, int(max_results)):
                break
        except Exception:
            continue
    return results


def largest_files(path: str | None = None, count: int = 10) -> list[str]:
    base = _resolve_user_path(path, default="home")
    if not base.exists():
        raise FileNotFoundError(str(base))
    if base.is_file():
        base = base.parent
    found: list[tuple[int, Path]] = []
    for item in base.rglob("*"):
        try:
            if item.is_file():
                found.append((item.stat().st_size, item))
        except Exception:
            continue
    found.sort(reverse=True, key=lambda pair: pair[0])
    return [f"{_format_size(size)} - {path}" for size, path in found[: max(1, int(count))]]


def disk_usage(path: str | None = None) -> dict:
    target = _resolve_user_path(path, default="home")
    if target.is_file():
        target = target.parent
    usage = shutil.disk_usage(target)
    percent = (usage.used / usage.total * 100.0) if usage.total else 0.0
    return {
        "path": str(target),
        "total": _format_size(usage.total),
        "used": _format_size(usage.used),
        "free": _format_size(usage.free),
        "percent": f"{percent:.1f}%",
    }


def make_dir(path: str):
    target = Path(path)
    if not str(path).strip():
        raise ValueError("missing path")
    target.mkdir(parents=True, exist_ok=True)


def write_file(path: str, content: str):
    if not str(path).strip():
        raise ValueError("missing path")
    target = Path(os.path.expandvars(os.path.expanduser(path)))
    if not target.is_absolute():
        target = Path.home() / "Desktop" / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content or "", encoding="utf-8")


def open_dir(path: str | None):
    base = Path(path) if path else Path.home() / "Desktop"
    if base.is_file():
        base = base.parent
    if not base.exists():
        raise FileNotFoundError(str(base))
    _open_path(str(base))


def copy_path(src: str, dst: str):
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.exists():
        raise FileNotFoundError(str(src_path))
    if dst_path.exists():
        raise FileExistsError(str(dst_path))
    if src_path.is_dir():
        shutil.copytree(src_path, dst_path)
    else:
        shutil.copy2(src_path, dst_path)


def move_path(src: str, dst: str):
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.exists():
        raise FileNotFoundError(str(src_path))
    if dst_path.exists():
        raise FileExistsError(str(dst_path))
    shutil.move(str(src_path), str(dst_path))


def rename_path(src: str, dst: str):
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.exists():
        raise FileNotFoundError(str(src_path))
    if dst_path.exists():
        raise FileExistsError(str(dst_path))
    src_path.rename(dst_path)


def set_volume(percent: int):
    percent = int(max(0, min(100, percent)))
    _ensure_windows()
    _set_volume_windows(percent)


def adjust_volume(delta_percent: int):
    delta_percent = int(delta_percent)
    if delta_percent == 0:
        return
    _ensure_windows()
    _change_volume_windows(delta_percent)


def _set_volume_windows(percent: int):
    from pynput.keyboard import Controller, Key

    controller = Controller()
    # Best-effort: drop volume to minimum, then raise to target.
    for _ in range(60):
        controller.press(Key.media_volume_down)
        controller.release(Key.media_volume_down)
    steps = int(round(percent / 2))
    for _ in range(max(0, steps)):
        controller.press(Key.media_volume_up)
        controller.release(Key.media_volume_up)


def _change_volume_windows(delta_percent: int):
    from pynput.keyboard import Controller, Key

    controller = Controller()
    steps = int(round(abs(delta_percent) / 2))
    key = Key.media_volume_up if delta_percent > 0 else Key.media_volume_down
    for _ in range(max(1, steps)):
        controller.press(key)
        controller.release(key)


def set_brightness(percent: int):
    percent = int(max(0, min(100, percent)))
    _ensure_windows()
    _set_brightness_windows(percent)


def adjust_brightness(delta_percent: int):
    delta_percent = int(delta_percent)
    if delta_percent == 0:
        return
    _ensure_windows()
    current = _get_brightness_windows()
    target = max(0, min(100, current + delta_percent))
    _set_brightness_windows(target)


def _get_brightness_windows() -> int:
    cmd = "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness"
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        nums = re.findall(r"\d+", out)
        if nums:
            return int(nums[0])
    except Exception:
        pass
    return 50


def _set_brightness_windows(percent: int):
    cmd = (
        "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
        f".WmiSetBrightness(1,{percent})"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-Command", cmd])


def lock_system():
    _ensure_windows()
    subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])


def restart_system():
    _ensure_windows()
    subprocess.Popen(["shutdown", "/r", "/t", "0"])


def shutdown_system():
    _ensure_windows()
    subprocess.Popen(["shutdown", "/s", "/t", "0"])


def sleep_system():
    _ensure_windows()
    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])


def take_screenshot(path: str | None = None) -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_windows()
    attempt = 0
    last_err = None
    while attempt < max(1, SCREENSHOT_RETRY_COUNT):
        attempt += 1
        if not path:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = str(SCREENSHOTS_DIR / f"screenshot_{ts}.png")
        try:
            try:
                import mss

                with mss.mss() as sct:
                    shot = sct.grab(sct.monitors[0])
                    img = Image.frombytes("RGB", shot.size, shot.rgb)
            except Exception:
                from PIL import ImageGrab

                img = ImageGrab.grab(all_screens=True)
            img.save(path)
        except Exception as exc:
            last_err = exc
            cmd = (
                "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; "
                "public class DPI { [DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware(); }'; "
                "[DPI]::SetProcessDPIAware() | Out-Null; "
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
                "$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height; "
                "$graphics = [System.Drawing.Graphics]::FromImage($bmp); "
                "$graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size); "
                f"$bmp.Save('{path}');"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=False)
        if _wait_for_file(path):
            return path
        time.sleep(SCREENSHOT_RETRY_DELAY)
        path = None
    raise RuntimeError("screenshot_failed") from last_err


def ocr_text(value: str | None, lang: str | None = None) -> tuple[str, str]:
    import cv2
    import numpy as np
    import pytesseract

    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    target = (value or "").strip()
    if not target or target.lower() in ("screen", "screenshot", "ekran"):
        image_path = take_screenshot(None)
    else:
        image_path = target
        if not Path(image_path).exists():
            raise FileNotFoundError(image_path)

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("invalid_image")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    if gray.mean() < 110:
        gray = cv2.bitwise_not(gray)
    gray = cv2.medianBlur(gray, 3)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    try:
        config = "--oem 1 --psm 6"
        text = (
            pytesseract.image_to_string(thresh, lang=lang, config=config)
            if lang
            else pytesseract.image_to_string(thresh, config=config)
        )
    except Exception:
        if lang:
            text = pytesseract.image_to_string(thresh, config="--oem 1 --psm 6")
        else:
            raise
    cleaned = (text or "").strip()
    return cleaned, image_path
