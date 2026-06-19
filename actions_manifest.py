import json
from functools import lru_cache

from config import ACTION_MANIFEST_JSON


_FALLBACK_ACTIONS = [
    "start",
    "open",
    "close",
    "focus",
    "browser_open",
    "browser_search",
    "web_open",
    "web_search",
    "web_click",
    "web_type",
    "web_press",
    "web_wait",
    "web_form_fill",
    "youtube_search",
    "type",
    "hotkey",
    "volume",
    "media",
    "brightness",
    "lock",
    "screenshot",
    "browser",
    "desktop",
    "scroll",
    "mute",
    "zoom",
    "list_dir",
    "find_files",
    "largest_files",
    "disk_usage",
    "open_dir",
    "copy",
    "move",
    "rename",
    "mkdir",
    "write_file",
    "run_code",
    "ocr",
    "gui_click_text",
    "gui_click_image",
    "gui_click",
    "gui_wait",
    "gui_wait_text",
    "gui_wait_image",
    "gui_map",
    "gui_click_index",
    "routine_create",
    "routine_run",
    "routine_list",
    "routine_delete",
    "delete",
    "cmd",
    "powershell",
    "shutdown",
    "restart",
    "sleep",
]


@lru_cache(maxsize=1)
def load_action_manifest() -> list[dict]:
    try:
        data = json.loads(ACTION_MANIFEST_JSON.read_text(encoding="utf-8"))
    except Exception:
        data = []
    if not isinstance(data, list):
        data = []
    cleaned = []
    seen = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        cleaned.append(item)
    for name in _FALLBACK_ACTIONS:
        if name not in seen:
            cleaned.append(
                {
                    "name": name,
                    "description_en": name,
                    "description_tr": name,
                    "parameters": "value",
                    "safety": "safe",
                    "verification": "no_exception",
                    "examples": [],
                }
            )
    return cleaned


def action_names() -> set[str]:
    return {str(item.get("name", "")).strip().lower() for item in load_action_manifest()}


def actions_by_safety(safety: str) -> set[str]:
    wanted = safety.strip().lower()
    return {
        str(item.get("name", "")).strip().lower()
        for item in load_action_manifest()
        if str(item.get("safety", "safe")).strip().lower() == wanted
    }


def action_summary_for_prompt() -> str:
    rows = []
    for item in load_action_manifest():
        name = str(item.get("name", "")).strip()
        params = str(item.get("parameters", "value")).strip()
        safety = str(item.get("safety", "safe")).strip()
        desc = str(item.get("description_en") or item.get("description_tr") or "").strip()
        if not name:
            continue
        # Fallback entries are still allowed via the allowed-action list, but they
        # do not need to consume local-model context with duplicate descriptions.
        if desc == name and not item.get("examples"):
            continue
        rows.append(f"- {name}({params}) [{safety}]: {desc}")
    return "\n".join(rows)
