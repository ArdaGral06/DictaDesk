import json
import time
from threading import RLock

from config import (
    API_BUDGET_DEFAULT_ENABLED,
    API_BUDGET_DEFAULT_HOURLY_LIMIT,
    API_BUDGET_DEFAULT_SESSION_LIMIT,
    API_BUDGET_JSON,
    DEFAULT_UI_LANG,
)
from i18n import t

_lock = RLock()
_HOUR_SEC = 3600
_SERVICES = ("llm", "stt", "vlm", "tts")

_session_count = 0
_session_by_service = {name: 0 for name in _SERVICES}


def _default_data() -> dict:
    return {
        "enabled": API_BUDGET_DEFAULT_ENABLED,
        "session_limit": API_BUDGET_DEFAULT_SESSION_LIMIT,
        "hourly_limit": API_BUDGET_DEFAULT_HOURLY_LIMIT,
        "usage": {
            "hourly_count": 0,
            "hourly_window_start": time.time(),
            "by_service": {name: 0 for name in _SERVICES},
        },
    }


def ensure_budget_file() -> None:
    if not API_BUDGET_JSON.exists():
        example = API_BUDGET_JSON.with_suffix(".json.example")
        if example.exists():
            API_BUDGET_JSON.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            API_BUDGET_JSON.write_text(
                json.dumps(_default_data(), indent=2), encoding="utf-8"
            )


def _normalize(data: dict) -> dict:
    base = _default_data()
    if not isinstance(data, dict):
        return base
    base["enabled"] = bool(data.get("enabled", base["enabled"]))
    try:
        base["session_limit"] = max(0, int(data.get("session_limit", base["session_limit"])))
    except (TypeError, ValueError):
        pass
    try:
        base["hourly_limit"] = max(0, int(data.get("hourly_limit", base["hourly_limit"])))
    except (TypeError, ValueError):
        pass
    usage = data.get("usage")
    if isinstance(usage, dict):
        try:
            base["usage"]["hourly_count"] = max(0, int(usage.get("hourly_count", 0)))
        except (TypeError, ValueError):
            pass
        try:
            base["usage"]["hourly_window_start"] = float(
                usage.get("hourly_window_start", time.time())
            )
        except (TypeError, ValueError):
            base["usage"]["hourly_window_start"] = time.time()
        by_service = usage.get("by_service")
        if isinstance(by_service, dict):
            for name in _SERVICES:
                try:
                    base["usage"]["by_service"][name] = max(0, int(by_service.get(name, 0)))
                except (TypeError, ValueError):
                    pass
    return base


def _read_budget_unlocked() -> dict:
    ensure_budget_file()
    try:
        raw = json.loads(API_BUDGET_JSON.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return _normalize(raw)


def _write_budget_unlocked(data: dict) -> None:
    ensure_budget_file()
    API_BUDGET_JSON.write_text(
        json.dumps(_normalize(data), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_budget() -> dict:
    with _lock:
        data = _read_budget_unlocked()
        return data


def save_budget(data: dict) -> None:
    with _lock:
        _write_budget_unlocked(data)


def _roll_hourly_window(data: dict) -> None:
    usage = data["usage"]
    now = time.time()
    start = float(usage.get("hourly_window_start", now))
    if now - start >= _HOUR_SEC:
        usage["hourly_count"] = 0
        usage["hourly_window_start"] = now
        usage["by_service"] = {name: 0 for name in _SERVICES}


def _limit_label(limit: int) -> str:
    return str(limit) if limit > 0 else "∞"


def check_budget(service: str, ui_lang: str | None = None) -> tuple[bool, str]:
    lang = ui_lang or DEFAULT_UI_LANG
    svc = str(service or "").strip().lower()
    if svc not in _SERVICES:
        svc = "llm"
    with _lock:
        data = _read_budget_unlocked()
        if not data.get("enabled"):
            return True, ""
        _roll_hourly_window(data)
        _write_budget_unlocked(data)

        session_limit = int(data.get("session_limit", 0))
        hourly_limit = int(data.get("hourly_limit", 0))
        usage = data["usage"]
        hourly_count = int(usage.get("hourly_count", 0))

        if session_limit > 0 and _session_count >= session_limit:
            return False, t(
                lang,
                "budget_blocked_session",
                service=t(lang, f"budget_service_{svc}"),
                used=_session_count,
                limit=session_limit,
            )
        if hourly_limit > 0 and hourly_count >= hourly_limit:
            return False, t(
                lang,
                "budget_blocked_hourly",
                service=t(lang, f"budget_service_{svc}"),
                used=hourly_count,
                limit=hourly_limit,
            )
        return True, ""


def record_budget_usage(service: str) -> None:
    global _session_count, _session_by_service
    svc = str(service or "").strip().lower()
    if svc not in _SERVICES:
        svc = "llm"
    with _lock:
        data = _read_budget_unlocked()
        _roll_hourly_window(data)
        usage = data["usage"]
        usage["hourly_count"] = int(usage.get("hourly_count", 0)) + 1
        by_service = usage.setdefault("by_service", {name: 0 for name in _SERVICES})
        by_service[svc] = int(by_service.get(svc, 0)) + 1
        _write_budget_unlocked(data)
        _session_count += 1
        _session_by_service[svc] = _session_by_service.get(svc, 0) + 1


def reset_budget_usage() -> None:
    global _session_count, _session_by_service
    with _lock:
        data = _read_budget_unlocked()
        data["usage"] = {
            "hourly_count": 0,
            "hourly_window_start": time.time(),
            "by_service": {name: 0 for name in _SERVICES},
        }
        _write_budget_unlocked(data)
        _session_count = 0
        _session_by_service = {name: 0 for name in _SERVICES}


def toggle_budget_enabled() -> bool:
    with _lock:
        data = _read_budget_unlocked()
        data["enabled"] = not bool(data.get("enabled"))
        _write_budget_unlocked(data)
        return bool(data["enabled"])


def set_session_limit(value: int) -> int:
    with _lock:
        data = _read_budget_unlocked()
        data["session_limit"] = max(0, int(value))
        _write_budget_unlocked(data)
        return int(data["session_limit"])


def set_hourly_limit(value: int) -> int:
    with _lock:
        data = _read_budget_unlocked()
        data["hourly_limit"] = max(0, int(value))
        _write_budget_unlocked(data)
        return int(data["hourly_limit"])


def budget_status_text(ui_lang: str) -> str:
    data = load_budget()
    if not data.get("enabled"):
        return t(ui_lang, "toggle_off")
    session_limit = int(data.get("session_limit", 0))
    hourly_limit = int(data.get("hourly_limit", 0))
    usage = data.get("usage", {})
    hourly_count = int(usage.get("hourly_count", 0))
    return t(
        ui_lang,
        "budget_status_on",
        session_used=_session_count,
        session_limit=_limit_label(session_limit),
        hourly_used=hourly_count,
        hourly_limit=_limit_label(hourly_limit),
    )


def budget_usage_lines(ui_lang: str) -> list[str]:
    data = load_budget()
    usage = data.get("usage", {})
    hourly_count = int(usage.get("hourly_count", 0))
    hourly_limit = int(data.get("hourly_limit", 0))
    session_limit = int(data.get("session_limit", 0))
    lines = [
        t(
            ui_lang,
            "budget_usage_session",
            used=_session_count,
            limit=_limit_label(session_limit),
        ),
        t(
            ui_lang,
            "budget_usage_hourly",
            used=hourly_count,
            limit=_limit_label(hourly_limit),
        ),
    ]
    by_service = usage.get("by_service", {})
    if isinstance(by_service, dict):
        for name in _SERVICES:
            session_svc = _session_by_service.get(name, 0)
            hourly_svc = int(by_service.get(name, 0))
            lines.append(
                t(
                    ui_lang,
                    "budget_usage_service",
                    service=t(ui_lang, f"budget_service_{name}"),
                    session=session_svc,
                    hourly=hourly_svc,
                )
            )
    lines.append(t(ui_lang, "budget_path", path=str(API_BUDGET_JSON)))
    return lines


def run_budget_menu(ui_lang: str) -> None:
    while True:
        data = load_budget()
        enabled = bool(data.get("enabled"))
        status = t(ui_lang, "toggle_on") if enabled else t(ui_lang, "toggle_off")
        session_limit = int(data.get("session_limit", 0))
        hourly_limit = int(data.get("hourly_limit", 0))
        print("\n" + t(ui_lang, "budget_title"))
        print(t(ui_lang, "budget_enabled_status", status=status))
        print(
            t(
                ui_lang,
                "budget_limits_status",
                session_limit=_limit_label(session_limit),
                hourly_limit=_limit_label(hourly_limit),
            )
        )
        for line in budget_usage_lines(ui_lang):
            print(line)
        print(t(ui_lang, "budget_toggle"))
        print(t(ui_lang, "budget_set_session"))
        print(t(ui_lang, "budget_set_hourly"))
        print(t(ui_lang, "budget_show_usage"))
        print(t(ui_lang, "budget_reset"))
        print(t(ui_lang, "budget_back"))
        choice = input(t(ui_lang, "menu_select")).strip()
        if choice == "1":
            new_state = toggle_budget_enabled()
            status = t(ui_lang, "toggle_on") if new_state else t(ui_lang, "toggle_off")
            print(t(ui_lang, "budget_toggled", status=status))
        elif choice == "2":
            raw = input(
                t(
                    ui_lang,
                    "budget_limit_prompt",
                    current=_limit_label(session_limit),
                )
            ).strip()
            if not raw:
                continue
            try:
                value = max(0, int(raw))
                set_session_limit(value)
                print(
                    t(
                        ui_lang,
                        "budget_session_updated",
                        limit=_limit_label(value),
                    )
                )
            except ValueError:
                print(t(ui_lang, "settings_delay_invalid"))
        elif choice == "3":
            raw = input(
                t(
                    ui_lang,
                    "budget_limit_prompt",
                    current=_limit_label(hourly_limit),
                )
            ).strip()
            if not raw:
                continue
            try:
                value = max(0, int(raw))
                set_hourly_limit(value)
                print(
                    t(
                        ui_lang,
                        "budget_hourly_updated",
                        limit=_limit_label(value),
                    )
                )
            except ValueError:
                print(t(ui_lang, "settings_delay_invalid"))
        elif choice == "4":
            print("\n" + t(ui_lang, "budget_usage_title"))
            for line in budget_usage_lines(ui_lang):
                print(line)
        elif choice == "5":
            reset_budget_usage()
            print(t(ui_lang, "budget_reset_done"))
        elif choice == "6":
            break
