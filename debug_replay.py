import json
from datetime import datetime
from pathlib import Path

from config import DEBUG_REPLAY_DIR


def write_debug_replay(
    *,
    user_command: str,
    plan: list[dict],
    completed_steps: list[dict],
    failed_step: dict,
    error_policy: str,
    error: str,
    verification: dict | None = None,
    uia_summary: dict | None = None,
    vlm_note: str | None = None,
) -> str:
    DEBUG_REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    replay_dir = DEBUG_REPLAY_DIR / f"replay_{ts}"
    replay_dir.mkdir(parents=True, exist_ok=True)

    screenshot_path = ""
    map_summary = {}
    active_window = {}
    open_windows = []
    try:
        from platform_actions import (
            get_active_window,
            get_last_gui_map_summary,
            get_open_windows,
            take_screenshot,
        )

        screenshot_path = take_screenshot(str(replay_dir / "screen.png"))
        map_summary = get_last_gui_map_summary()
        active_window = get_active_window()
        open_windows = get_open_windows(limit=30)
    except Exception as exc:
        map_summary = {"capture_error": str(exc)}

    payload = {
        "user_command": user_command,
        "plan": plan,
        "completed_steps": completed_steps,
        "failed_step": failed_step,
        "error_policy": error_policy,
        "error": error,
        "verification": verification or {},
        "screenshot": screenshot_path,
        "last_gui_map": map_summary,
        "uia_summary": uia_summary or {},
        "vlm_note": vlm_note or "",
        "active_window": active_window,
        "open_windows": open_windows,
    }
    out = replay_dir / "replay.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out)

