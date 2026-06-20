"""Runtime data folders — created automatically; contents stay out of git."""

from pathlib import Path

from config import (
    BASE_DIR,
    DEBUG_REPLAY_DIR,
    GUI_MAP_DIR,
    LLM_MODELS_DIR,
    MEMORY_DIR,
    PIPER_MODELS_DIR,
    RECORDINGS_DIR,
    SCREENSHOTS_DIR,
    TEST_SOUNDS_DIR,
    TRANSCRIPTS_DIR,
    TTS_OUTPUT_DIR,
    VOSK_MODEL_EN_DIR,
    VOSK_MODEL_TR_DIR,
    VOSK_MODELS_DIR,
)

# Log dir lives in app_logging to avoid import cycles at module load.
_LOG_DIR: Path | None = None


def _log_dir() -> Path:
    global _LOG_DIR
    if _LOG_DIR is None:
        from app_logging import LOG_DIR

        _LOG_DIR = LOG_DIR
    return _LOG_DIR


def runtime_data_dirs() -> list[Path]:
    """All project-local folders that hold user/runtime data (not source code)."""
    return [
        TEST_SOUNDS_DIR,
        RECORDINGS_DIR,
        TRANSCRIPTS_DIR,
        SCREENSHOTS_DIR,
        GUI_MAP_DIR,
        MEMORY_DIR,
        VOSK_MODELS_DIR,
        VOSK_MODEL_TR_DIR,
        VOSK_MODEL_EN_DIR,
        TTS_OUTPUT_DIR,
        PIPER_MODELS_DIR,
        LLM_MODELS_DIR,
        DEBUG_REPLAY_DIR,
        _log_dir(),
        BASE_DIR / "piper",
    ]


def ensure_runtime_dirs() -> None:
    for d in runtime_data_dirs():
        d.mkdir(parents=True, exist_ok=True)
