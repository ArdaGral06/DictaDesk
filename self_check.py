import platform
import sys
from dataclasses import dataclass

from audio_io import ensure_dirs
from commands_manager import load_commands
from config import (
    ACTION_MANIFEST_JSON,
    COMMANDS_JSON,
    DEBUG_REPLAY_DIR,
    MEMORY_FILE,
    PROVIDERS_JSON,
    RECORDINGS_DIR,
    TEST_SOUNDS_DIR,
    TRANSCRIPTS_DIR,
    TTS_PROVIDERS_JSON,
    VAD_ENABLED,
    VAD_MIN_ACTIVE_FRAMES,
    VAD_RMS_THRESHOLD,
    TESSERACT_CMD,
)
from agent_memory import load_memory
from i18n import t
from providers import load_providers, validate_providers
from tts_engine import load_tts_providers, piper_available
from ui_terminal import print_banner, print_section


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""


def _status_line(ui_lang, name, status, detail=""):
    detail_text = f" {detail}" if detail else ""
    print(t(ui_lang, "self_check_item", name=name, status=status, detail=detail_text))


def _print_group(ui_lang, group_key: str, results: list[CheckResult]) -> None:
    print_section(t(ui_lang, group_key))
    for item in results:
        status_label = t(ui_lang, f"self_check_{item.status}")
        _status_line(ui_lang, item.name, status_label, item.detail)


def _collect_core(ui_lang) -> list[CheckResult]:
    rows: list[CheckResult] = []

    os_name = platform.system()
    os_detail = platform.platform()
    os_status = "ok" if os_name.lower() == "windows" else "fail"
    rows.append(CheckResult(t(ui_lang, "self_check_os"), os_status, os_detail))

    py_ver = sys.version.split()[0]
    rows.append(CheckResult(t(ui_lang, "self_check_python"), "ok", py_ver))

    ensure_dirs()
    dirs_ok = all(d.exists() for d in [TEST_SOUNDS_DIR, RECORDINGS_DIR, TRANSCRIPTS_DIR])
    rows.append(
        CheckResult(
            t(ui_lang, "self_check_dirs"),
            "ok" if dirs_ok else "fail",
        )
    )

    try:
        load_commands()
        rows.append(CheckResult(t(ui_lang, "self_check_commands"), "ok", str(COMMANDS_JSON)))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_commands"), "fail", str(exc)))

    try:
        from actions_manifest import load_action_manifest

        manifest = load_action_manifest()
        status = "ok" if manifest else "fail"
        rows.append(
            CheckResult(
                t(ui_lang, "self_check_manifest"),
                status,
                f"{ACTION_MANIFEST_JSON} count={len(manifest)}",
            )
        )
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_manifest"), "fail", str(exc)))

    try:
        import keyring
        from importlib.metadata import PackageNotFoundError, version

        try:
            detail = f"v{version('keyring')}"
        except PackageNotFoundError:
            detail = "installed"
        rows.append(CheckResult(t(ui_lang, "self_check_keyring"), "ok", detail))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_keyring"), "fail", str(exc)))

    try:
        from app_logging import LOG_DIR, setup_logging

        setup_logging()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rows.append(CheckResult(t(ui_lang, "self_check_logging"), "ok", str(LOG_DIR)))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_logging"), "warn", str(exc)))

    try:
        from api_budget import load_budget

        budget = load_budget()
        enabled = budget.get("enabled")
        rows.append(
            CheckResult(t(ui_lang, "self_check_api_budget"), "ok", f"enabled={enabled}")
        )
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_api_budget"), "warn", str(exc)))

    return rows


def _collect_voice(ui_lang) -> list[CheckResult]:
    rows: list[CheckResult] = []

    try:
        import sounddevice as sd

        info = sd.query_devices(None, "input")
        name = info.get("name") if isinstance(info, dict) else str(info)
        rows.append(CheckResult(t(ui_lang, "self_check_audio_device"), "ok", name))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_audio"), "fail", str(exc)))

    if VAD_ENABLED:
        ok = 0.0 <= VAD_RMS_THRESHOLD <= 1.0 and VAD_MIN_ACTIVE_FRAMES >= 1
        detail = f"threshold={VAD_RMS_THRESHOLD}, min_frames={VAD_MIN_ACTIVE_FRAMES}"
        rows.append(
            CheckResult(t(ui_lang, "self_check_vad"), "ok" if ok else "warn", detail)
        )

    if piper_available():
        rows.append(CheckResult(t(ui_lang, "self_check_tts"), "ok"))
    else:
        rows.append(CheckResult(t(ui_lang, "self_check_tts"), "fail"))

    if TTS_PROVIDERS_JSON.exists():
        providers = load_tts_providers()
        status = "ok" if providers else "warn"
        detail = f"count={len(providers)}" if providers else "empty"
        rows.append(CheckResult(t(ui_lang, "self_check_tts_providers"), status, detail))
    else:
        rows.append(
            CheckResult(t(ui_lang, "self_check_tts_providers"), "warn", "missing")
        )

    return rows


def _collect_ai(ui_lang) -> list[CheckResult]:
    rows: list[CheckResult] = []

    if PROVIDERS_JSON.exists():
        providers = load_providers()
        reports = validate_providers(providers)
        errors = [r for r in reports if r.get("errors")]
        warnings = [r for r in reports if r.get("warnings")]
        if errors:
            names = ",".join(r.get("id", "unknown") for r in errors)
            rows.append(
                CheckResult(
                    t(ui_lang, "self_check_providers"),
                    "fail",
                    f"errors={len(errors)} ({names})",
                )
            )
        elif warnings:
            names = ",".join(r.get("id", "unknown") for r in warnings)
            rows.append(
                CheckResult(
                    t(ui_lang, "self_check_providers"),
                    "warn",
                    f"warnings={len(warnings)} ({names})",
                )
            )
        else:
            rows.append(
                CheckResult(
                    t(ui_lang, "self_check_providers"),
                    "ok",
                    f"count={len(providers)}",
                )
            )
    else:
        rows.append(
            CheckResult(t(ui_lang, "self_check_providers"), "warn", "missing")
        )

    try:
        load_memory()
        rows.append(CheckResult(t(ui_lang, "self_check_memory"), "ok", str(MEMORY_FILE)))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_memory"), "fail", str(exc)))

    return rows


def _collect_automation(ui_lang) -> list[CheckResult]:
    rows: list[CheckResult] = []

    try:
        import pytesseract

        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        pytesseract.get_tesseract_version()
        rows.append(CheckResult(t(ui_lang, "self_check_ocr"), "ok"))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_ocr"), "fail", str(exc)))

    try:
        import pyautogui  # noqa: F401

        rows.append(CheckResult(t(ui_lang, "self_check_gui"), "ok"))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_gui"), "warn", str(exc)))

    try:
        import uiautomation  # noqa: F401

        rows.append(CheckResult(t(ui_lang, "self_check_uia"), "ok"))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_uia"), "warn", str(exc)))

    for module_name, label_key in (
        ("tkinter", "self_check_tkinter"),
        ("mss", "self_check_mss"),
        ("pyperclip", "self_check_pyperclip"),
    ):
        try:
            __import__(module_name)
            rows.append(CheckResult(t(ui_lang, label_key), "ok"))
        except Exception as exc:
            rows.append(CheckResult(t(ui_lang, label_key), "warn", str(exc)))

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        rows.append(CheckResult(t(ui_lang, "self_check_web"), "ok"))
    except Exception as exc:
        rows.append(CheckResult(t(ui_lang, "self_check_web"), "warn", str(exc)))

    return rows


def _collect_storage(ui_lang) -> list[CheckResult]:
    rows: list[CheckResult] = []
    try:
        DEBUG_REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        rows.append(
            CheckResult(
                t(ui_lang, "self_check_debug_replay"),
                "ok",
                str(DEBUG_REPLAY_DIR),
            )
        )
    except Exception as exc:
        rows.append(
            CheckResult(t(ui_lang, "self_check_debug_replay"), "warn", str(exc))
        )
    return rows


def run_self_check(ui_lang):
    print_banner(t(ui_lang, "self_check_title"), t(ui_lang, "self_check_subtitle"))

    groups = [
        ("self_check_group_core", _collect_core(ui_lang)),
        ("self_check_group_voice", _collect_voice(ui_lang)),
        ("self_check_group_ai", _collect_ai(ui_lang)),
        ("self_check_group_automation", _collect_automation(ui_lang)),
        ("self_check_group_storage", _collect_storage(ui_lang)),
    ]

    all_results: list[CheckResult] = []
    for group_key, results in groups:
        _print_group(ui_lang, group_key, results)
        all_results.extend(results)

    ok_count = sum(1 for r in all_results if r.status == "ok")
    warn_count = sum(1 for r in all_results if r.status == "warn")
    fail_count = sum(1 for r in all_results if r.status == "fail")
    print(
        t(
            ui_lang,
            "self_check_summary",
            ok=ok_count,
            warn=warn_count,
            fail=fail_count,
        )
    )
    print(t(ui_lang, "self_check_done"))
