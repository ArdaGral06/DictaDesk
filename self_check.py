import platform
import sys

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


def _status_line(ui_lang, name, status, detail=""):
    detail_text = f" {detail}" if detail else ""
    print(t(ui_lang, "self_check_item", name=name, status=status, detail=detail_text))


def run_self_check(ui_lang):
    print("\n" + t(ui_lang, "self_check_title"))

    # System
    os_name = platform.system()
    os_detail = platform.platform()
    os_status = t(ui_lang, "self_check_ok") if os_name.lower() == "windows" else t(ui_lang, "self_check_fail")
    _status_line(ui_lang, t(ui_lang, "self_check_os"), os_status, os_detail)
    py_ver = sys.version.split()[0]
    _status_line(ui_lang, t(ui_lang, "self_check_python"), t(ui_lang, "self_check_ok"), py_ver)

    # Folders
    ensure_dirs()
    dirs_ok = all(d.exists() for d in [TEST_SOUNDS_DIR, RECORDINGS_DIR, TRANSCRIPTS_DIR])
    status = t(ui_lang, "self_check_ok") if dirs_ok else t(ui_lang, "self_check_fail")
    _status_line(ui_lang, t(ui_lang, "self_check_dirs"), status)

    # commands.json
    try:
        load_commands()
        status = t(ui_lang, "self_check_ok")
        detail = str(COMMANDS_JSON)
    except Exception as exc:
        status = t(ui_lang, "self_check_fail")
        detail = str(exc)
    _status_line(ui_lang, t(ui_lang, "self_check_commands"), status, detail)

    # actions_manifest.json
    try:
        from actions_manifest import load_action_manifest

        manifest = load_action_manifest()
        status = t(ui_lang, "self_check_ok") if manifest else t(ui_lang, "self_check_fail")
        detail = f"{ACTION_MANIFEST_JSON} count={len(manifest)}"
    except Exception as exc:
        status = t(ui_lang, "self_check_fail")
        detail = str(exc)
    _status_line(ui_lang, t(ui_lang, "self_check_manifest"), status, detail)

    # providers.json (optional)
    if PROVIDERS_JSON.exists():
        providers = load_providers()
        reports = validate_providers(providers)
        errors = [r for r in reports if r.get("errors")]
        warnings = [r for r in reports if r.get("warnings")]
        if errors:
            status = t(ui_lang, "self_check_fail")
            names = ",".join(r.get("id", "unknown") for r in errors)
            detail = f"errors={len(errors)} ({names})"
        elif warnings:
            status = t(ui_lang, "self_check_warn")
            names = ",".join(r.get("id", "unknown") for r in warnings)
            detail = f"warnings={len(warnings)} ({names})"
        else:
            status = t(ui_lang, "self_check_ok")
            detail = f"count={len(providers)}"
        _status_line(ui_lang, t(ui_lang, "self_check_providers"), status, detail)
    else:
        _status_line(
            ui_lang,
            t(ui_lang, "self_check_providers"),
            t(ui_lang, "self_check_warn"),
            "missing",
        )

    # TTS (Piper)
    if piper_available():
        _status_line(ui_lang, t(ui_lang, "self_check_tts"), t(ui_lang, "self_check_ok"))
    else:
        _status_line(ui_lang, t(ui_lang, "self_check_tts"), t(ui_lang, "self_check_fail"))

    # TTS providers (optional)
    if TTS_PROVIDERS_JSON.exists():
        providers = load_tts_providers()
        status = t(ui_lang, "self_check_ok") if providers else t(ui_lang, "self_check_warn")
        detail = f"count={len(providers)}" if providers else "empty"
        _status_line(ui_lang, t(ui_lang, "self_check_tts_providers"), status, detail)
    else:
        _status_line(
            ui_lang,
            t(ui_lang, "self_check_tts_providers"),
            t(ui_lang, "self_check_warn"),
            "missing",
        )

    # Microphone
    try:
        import sounddevice as sd

        info = sd.query_devices(None, "input")
        name = info.get("name") if isinstance(info, dict) else str(info)
        _status_line(
            ui_lang,
            t(ui_lang, "self_check_audio_device"),
            t(ui_lang, "self_check_ok"),
            name,
        )
    except Exception as exc:
        _status_line(
            ui_lang,
            t(ui_lang, "self_check_audio"),
            t(ui_lang, "self_check_fail"),
            str(exc),
        )

    # VAD sanity
    if VAD_ENABLED:
        ok = 0.0 <= VAD_RMS_THRESHOLD <= 1.0 and VAD_MIN_ACTIVE_FRAMES >= 1
        status = t(ui_lang, "self_check_ok") if ok else t(ui_lang, "self_check_warn")
        detail = f"threshold={VAD_RMS_THRESHOLD}, min_frames={VAD_MIN_ACTIVE_FRAMES}"
        _status_line(ui_lang, t(ui_lang, "self_check_vad"), status, detail)

    # OCR (Tesseract)
    try:
        import pytesseract

        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        pytesseract.get_tesseract_version()
        _status_line(ui_lang, t(ui_lang, "self_check_ocr"), t(ui_lang, "self_check_ok"))
    except Exception as exc:
        _status_line(
            ui_lang, t(ui_lang, "self_check_ocr"), t(ui_lang, "self_check_fail"), str(exc)
        )

    # GUI automation (pyautogui)
    try:
        import pyautogui  # noqa: F401

        _status_line(ui_lang, t(ui_lang, "self_check_gui"), t(ui_lang, "self_check_ok"))
    except Exception as exc:
        _status_line(
            ui_lang,
            t(ui_lang, "self_check_gui"),
            t(ui_lang, "self_check_warn"),
            str(exc),
        )

    # Windows UI Automation
    try:
        import uiautomation  # noqa: F401

        _status_line(ui_lang, t(ui_lang, "self_check_uia"), t(ui_lang, "self_check_ok"))
    except Exception as exc:
        _status_line(ui_lang, t(ui_lang, "self_check_uia"), t(ui_lang, "self_check_warn"), str(exc))

    # GUI helpers used by status popups and robust screenshot/type paths.
    for module_name, label in (
        ("tkinter", "Status popup (Tkinter)"),
        ("mss", "Screenshot backend (mss)"),
        ("pyperclip", "Clipboard typing (pyperclip)"),
    ):
        try:
            __import__(module_name)
            _status_line(ui_lang, label, t(ui_lang, "self_check_ok"))
        except Exception as exc:
            _status_line(ui_lang, label, t(ui_lang, "self_check_warn"), str(exc))

    # Browser automation (Playwright)
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        _status_line(ui_lang, t(ui_lang, "self_check_web"), t(ui_lang, "self_check_ok"))
    except Exception as exc:
        _status_line(
            ui_lang,
            t(ui_lang, "self_check_web"),
            t(ui_lang, "self_check_warn"),
            str(exc),
        )

    # Agent memory
    try:
        load_memory()
        status = t(ui_lang, "self_check_ok")
        detail = str(MEMORY_FILE)
    except Exception as exc:
        status = t(ui_lang, "self_check_fail")
        detail = str(exc)
    _status_line(ui_lang, t(ui_lang, "self_check_memory"), status, detail)

    try:
        DEBUG_REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        _status_line(ui_lang, t(ui_lang, "self_check_debug_replay"), t(ui_lang, "self_check_ok"), str(DEBUG_REPLAY_DIR))
    except Exception as exc:
        _status_line(ui_lang, t(ui_lang, "self_check_debug_replay"), t(ui_lang, "self_check_warn"), str(exc))

    print(t(ui_lang, "self_check_done"))
