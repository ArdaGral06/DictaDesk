import ast
import json
import platform
import re
from pathlib import Path

import requests

from config import (
    LLM_LOCAL_CTX,
    LLM_LOCAL_MAX_TOKENS,
    LLM_LOCAL_MODEL_PATH,
    LLM_LOCAL_TEMPERATURE,
    LLM_LOCAL_THREADS,
    LLM_MODELS_DIR,
    LLM_PROVIDERS_JSON,
)
from i18n import t
from secrets_store import get_entry, set_entry
from agent_memory import format_memory_for_prompt
from actions_manifest import action_names, action_summary_for_prompt, actions_by_safety
from utils import fold_text


ALL_ACTIONS = action_names() | {"none"}
DANGEROUS_ACTIONS = actions_by_safety("dangerous") | actions_by_safety("needs_confirmation")
SAFE_ACTIONS = ALL_ACTIONS - DANGEROUS_ACTIONS - {"none"}


def _allowed_actions_text() -> str:
    return ", ".join(sorted(a for a in ALL_ACTIONS if a != "none"))


def _os_label() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    return "unsupported"


def _router_system_prompt():
    os_name = _os_label()
    os_hint = (
        "This assistant is Windows-only. Prefer app names like 'File Explorer', "
        "'Notepad', and use 'explorer' for the file manager. "
        "If the user says 'Finder', treat it as File Explorer."
    )

    memory = format_memory_for_prompt()
    memory_block = f"\n{memory}" if memory else ""
    manifest = action_summary_for_prompt()
    return (
        "You are a command router for a PC voice assistant. "
        "Convert the user's request into ONE action JSON. "
        "The user may speak Turkish or English (or mixed) — handle both. "
        "Respond in the same language as the user when writing the 'reason'. "
        "Never ask unnecessary questions; make a reasonable assumption and proceed. "
        "Do not repeat yourself. "
        f"Only allowed actions: {_allowed_actions_text()}, none. "
        "Prefer safe actions from the manifest. "
        "Use delete/cmd/powershell/run_code/shutdown/restart/sleep only if the user explicitly asks or confirms execution. "
        "If it can be done in ONE action, output a single action. "
        "Think step-by-step internally but do NOT reveal your reasoning. "
        "Return a JSON object with keys: action, value, reason. "
        "If the user asked for multiple actions, return {\"actions\":[...]} in order. "
        "Reason must be one short sentence. "
        "Hotkey value should be space-separated keys (e.g., 'ctrl shift s', 'alt tab'). "
        "Browser action values: new_tab, close_tab, next_tab, prev_tab, refresh, back, forward, address_bar, downloads, history. "
        "Desktop action values: show, toggle, minimize, snap_left, snap_right, maximize, restore, task_manager, run, file_explorer, copy, paste, cut, undo, redo, select_all, save, refresh, fullscreen, enter, escape, clear_field. "
        "Scroll action values: 'up N' or 'down N' (N number). "
        "Zoom action values: in, out, reset. "
        "Copy/Move/Rename values: 'source -> target'. "
        "Write file values: 'path -> full file content'. Use this when the user asks you to code, create a script, create an HTML game, or write a file. Use run_code only when the user asks to run/execute/test the created code. "
        "Routine values: routine_create uses 'name -> routine command text'; routine_run/list/delete use routine name or empty for list. "
        "List/Open dir values: directory path or empty for Desktop. "
        "Find files value format: 'name=<text>; extension=.pdf; path=downloads; limit=20' (any field optional except name or extension). Largest files value: 'path=downloads; count=10'. Disk usage value: path or empty. "
        "OCR values: image path or 'screen' to capture screen. "
        "GUI actions: gui_click_text uses visible text, gui_click_image uses image path, gui_click uses 'x,y', gui_wait uses seconds. "
        "GUI wait actions: gui_wait_text uses 'text|timeout_sec' (timeout optional), gui_wait_image uses 'path|threshold|timeout'. "
        "GUI mapping: gui_map/gui_click_index are for debugging; do NOT use them unless the user explicitly asks for a map. "
        "If multiple visible elements contain the same text, do not rely on text alone; prefer the element whose UI region and nearby labels match the user intent. "
        "For Discord direct messages, prefer the safe search flow: focus/start Discord, hotkey 'ctrl k', type the person name, hotkey 'enter', then type the message and hotkey 'enter'. Avoid activity/profile panels when a message target is requested. "
        "If the user mentions an app name and GUI actions follow, add a first step: focus with that app name. "
        "Web actions (Playwright): web_open URL, web_search query, youtube_search query, web_click text (or 'css:selector'), web_type text or 'selector -> text', web_press key, web_wait seconds, web_form_fill key=value pairs (use memory for non-sensitive fields; include email/password ONLY if user explicitly provided them). "
        "Native browser actions (no Playwright): browser_open 'browser|url' (browser optional), browser_search 'browser|query'. "
        "If user says 'do not use Playwright' or 'normal browser', use browser_open/browser_search + GUI actions. "
        "Strict ordering: start/open an app before focus or GUI steps; create/write a file before opening it; wait briefly after starting apps or opening pages when UI needs time. Do not repeat a completed start/focus/open step. "
        "If the user says close/quit/exit/terminate/kapat, use action: close. "
        f"Current OS: {os_name}. {os_hint} "
        "If the user mentions a file by name, value can be the filename; the system will search common folders. "
        "If the user gives a path, return the path as value. "
        "For volume, include the number or 'up/down' if specified. "
        "If the request is unclear or unsafe, return action: none. "
        "Return ONLY JSON, no extra text."
        "\nACTION MANIFEST:\n"
        + manifest
        + "\n"
        + memory_block
    )


def _llm_user_prompt(text: str) -> str:
    return f"User request: {text}\nReturn JSON now."


def _build_phi3_prompt(user_text: str, system_prompt: str) -> str:
    return (
        f"<|system|>\n{system_prompt}\n<|end|>\n"
        f"<|user|>\n{user_text}\n<|end|>\n<|assistant|>\n"
    )


def _agent_system_prompt() -> str:
    os_name = _os_label()
    os_hint = "Windows-only. Windows apps: File Explorer, Notepad. Treat 'Finder' as File Explorer."

    memory = format_memory_for_prompt()
    memory_block = f"\n{memory}" if memory else ""
    manifest = action_summary_for_prompt()
    return (
        "You are an autonomous planning agent for a PC voice assistant. "
        "Break the user's goal into the smallest number of steps (max 7). "
        "Never ask unnecessary questions; make a reasonable assumption and proceed. "
        "Do not repeat yourself. "
        f"Each step must be an allowed action only: {_allowed_actions_text()}. "
        "Prefer safe actions from the manifest. "
        "Use delete/cmd/powershell/run_code/shutdown/restart/sleep only if the user explicitly asks or confirms execution. "
        "For coding tasks, use write_file with complete file content; use run_code only if the user asks to run/test it. Do not use cmd/powershell unless the user explicitly asks to run a command. "
        "Each step must be independent; do not reference previous step results in parameters. "
        "If the goal can be done in ONE step, return a single-step plan. "
        f"Current OS: {os_name}. {os_hint} "
        "Output ONLY JSON with keys: goal (short), steps (list), notes (optional). "
        "Each step item has: step (number), action, value, reason, critical (true/false). "
        "Value may be a file name or path when opening files. "
        "Browser action values: new_tab, close_tab, next_tab, prev_tab, refresh, back, forward, address_bar, downloads, history. "
        "Desktop action values: show, toggle, minimize, snap_left, snap_right, maximize, restore, task_manager, run, file_explorer, copy, paste, cut, undo, redo, select_all, save, refresh, fullscreen, enter, escape, clear_field. "
        "Scroll action values: 'up N' or 'down N' (N number). "
        "Zoom action values: in, out, reset. "
        "Copy/Move/Rename values: 'source -> target'. "
        "Write file values: 'path -> full file content'. If the user says create a file and open it, write_file must come before open. "
        "Routine values: routine_create uses 'name -> routine command text'; routine_run/list/delete use routine name or empty for list. "
        "List/Open dir values: directory path or empty for Desktop. "
        "Find files value format: 'name=<text>; extension=.pdf; path=downloads; limit=20' (any field optional except name or extension). Largest files value: 'path=downloads; count=10'. Disk usage value: path or empty. "
        "OCR values: image path or 'screen' to capture screen. "
        "GUI actions: gui_click_text uses visible text, gui_click_image uses image path, gui_click uses 'x,y', gui_wait uses seconds. "
        "GUI wait actions: gui_wait_text uses 'text|timeout_sec' (timeout optional), gui_wait_image uses 'path|threshold|timeout'. "
        "GUI mapping: gui_map/gui_click_index are for debugging; do NOT use them unless the user explicitly asks for a map. "
        "If multiple visible elements contain the same text, do not rely on text alone; prefer the element whose UI region and nearby labels match the user intent. "
        "For Discord direct messages, prefer the safe search flow: focus/start Discord, hotkey 'ctrl k', type the person name, hotkey 'enter', then type the message and hotkey 'enter'. Avoid activity/profile panels when a message target is requested. "
        "If the user mentions an app name and GUI actions follow, add a first step: focus with that app name. "
        "Web actions (Playwright): web_open URL, web_search query, youtube_search query, web_click text (or 'css:selector'), web_type text or 'selector -> text', web_press key, web_wait seconds, web_form_fill key=value pairs (use memory for non-sensitive fields; include email/password ONLY if user explicitly provided them). "
        "Native browser actions (no Playwright): browser_open 'browser|url' (browser optional), browser_search 'browser|query'. "
        "If user says 'do not use Playwright' or 'normal browser', use browser_open/browser_search + GUI actions. "
        "Strict ordering: start/open an app before focus or GUI steps; create/write a file before opening it; wait briefly after starting apps or opening pages when UI needs time. Do not repeat a completed start/focus/open step. "
        "Return ONLY JSON, no extra text."
        "\nACTION MANIFEST:\n"
        + manifest
        + "\n"
        + memory_block
    )


def _agent_user_prompt(goal: str, context: str = "") -> str:
    if context:
        return f"Goal: {goal}\nContext: {context}\nReturn JSON plan now."
    return f"Goal: {goal}\nReturn JSON plan now."


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    candidates = []
    stripped = text.strip()
    if stripped:
        candidates.append(stripped)

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            pass
        match = re.search(r"(\{.*\}|\[.*\])", candidate, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        fixed = candidate
        fixed = re.sub(r"\btrue\b", "True", fixed, flags=re.IGNORECASE)
        fixed = re.sub(r"\bfalse\b", "False", fixed, flags=re.IGNORECASE)
        fixed = re.sub(r"\bnull\b", "None", fixed, flags=re.IGNORECASE)
        try:
            literal = ast.literal_eval(fixed)
            if isinstance(literal, (dict, list)):
                return literal
        except Exception:
            pass

    return _fallback_parse_actions(text)


def _fallback_parse_actions(text: str) -> dict | None:
    if not text:
        return None
    items = []
    matches = list(re.finditer(r"action\s*[:=]\s*\"?([a-z_]+)\"?", text, re.I))
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end]
        action = match.group(1).strip().lower()
        value_match = re.search(
            r"value\s*[:=]\s*\"?(.+?)\"?(?:,|\n|\r|\}|$)", chunk, re.I | re.S
        )
        reason_match = re.search(
            r"reason\s*[:=]\s*\"?(.+?)\"?(?:,|\n|\r|\}|$)", chunk, re.I | re.S
        )
        value = value_match.group(1).strip() if value_match else ""
        reason = reason_match.group(1).strip() if reason_match else ""
        items.append({"action": action, "value": value, "reason": reason})

    if not items:
        action_match = re.search(r"action\s*[:=]\s*\"?([a-z_]+)\"?", text, re.I)
        if not action_match:
            return None
        value_match = re.search(
            r"value\s*[:=]\s*\"?(.+?)\"?(?:,|\n|\r|\}|$)", text, re.I | re.S
        )
        reason_match = re.search(
            r"reason\s*[:=]\s*\"?(.+?)\"?(?:,|\n|\r|\}|$)", text, re.I | re.S
        )
        action = action_match.group(1).strip().lower()
        value = value_match.group(1).strip() if value_match else ""
        reason = reason_match.group(1).strip() if reason_match else ""
        return {"action": action, "value": value, "reason": reason}

    if len(items) == 1:
        return items[0]
    return {"actions": items}


def _extract_plan(payload: object | None) -> tuple[list[dict], str | None, str | None]:
    goal = None
    notes = None
    actions_payload = payload

    if isinstance(payload, dict):
        if isinstance(payload.get("agent"), dict):
            payload = payload.get("agent")
        if isinstance(payload.get("goal"), str):
            goal = payload.get("goal")
        if isinstance(payload.get("task"), str) and not goal:
            goal = payload.get("task")
        if isinstance(payload.get("intent"), str) and not goal:
            goal = payload.get("intent")
        if isinstance(payload.get("notes"), str):
            notes = payload.get("notes")
        if isinstance(payload.get("summary"), str) and not notes:
            notes = payload.get("summary")
        if isinstance(payload.get("explanation"), str) and not notes:
            notes = payload.get("explanation")

        if isinstance(payload.get("actions"), list):
            actions_payload = {"actions": payload.get("actions")}
        elif isinstance(payload.get("steps"), list):
            actions_payload = {"actions": payload.get("steps")}
        elif isinstance(payload.get("plan"), list):
            actions_payload = {"actions": payload.get("plan")}
        elif isinstance(payload.get("commands"), list):
            actions_payload = {"actions": payload.get("commands")}

    actions = validate_actions(actions_payload)
    return actions, goal, notes


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    folded = fold_text(text)
    return re.findall(r"[a-z0-9]+", folded)


def _normalize_phrase(text: str) -> str:
    tokens = _tokenize(text)
    return " ".join(tokens)


def _looks_like_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith(("http://", "https://", "www."))


def _looks_like_path(value: str) -> bool:
    v = (value or "").strip()
    return "\\" in v or "/" in v or re.match(r"^[A-Za-z]:\\", v) is not None


def _normalize_os_action(os_name: str, action: str, value: str) -> tuple[str, str]:
    if not value:
        return action, value
    phrase = _normalize_phrase(value)
    if not phrase:
        return action, value

    if phrase in {"finder", "file explorer", "file manager"}:
        return "open", "explorer"
    if phrase in {"cmd", "command prompt"}:
        return "start", "cmd"
    return action, value


def _fix_actions_from_text(text: str, actions: list[dict]) -> list[dict]:
    if not actions or not text:
        return actions
    tokens = _tokenize(text)
    if not tokens:
        return actions

    close_words = {"close", "quit", "exit", "terminate"}
    delete_words = {"delete", "remove", "uninstall", "erase", "sil", "kaldir"}
    close_prefixes = {"kapat", "cik"}
    delete_prefixes = {"sil", "kaldir"}

    has_close = any(tok in close_words for tok in tokens) or any(
        tok.startswith(p) for tok in tokens for p in close_prefixes
    )
    has_delete = any(tok in delete_words for tok in tokens) or any(
        tok.startswith(p) for tok in tokens for p in delete_prefixes
    )

    if has_close and not has_delete:
        fixed = []
        for item in actions:
            if item.get("action") == "delete":
                updated = dict(item)
                updated["action"] = "close"
                if not updated.get("reason"):
                    updated["reason"] = "User asked to close an app."
                fixed.append(updated)
            else:
                fixed.append(item)
        actions = fixed

    # If user explicitly says not to use Playwright / use normal browser, adapt actions.
    avoid_playwright = False
    avoid_search = False
    if any(tok in tokens for tok in ("playwright", "normal", "browser", "tarayici", "tarayıcı")):
        phrase = fold_text(text)
        if any(
            key in phrase
            for key in (
                "playwright kullanma",
                "playwright kullanma.",
                "playwright istemiyorum",
                "playwright kullanma lütfen",
                "normal tarayici",
                "normal tarayıcı",
                "varsayilan tarayici",
                "varsayılan tarayıcı",
                "default browser",
                "use normal browser",
                "no playwright",
                "without playwright",
            )
        ):
            avoid_playwright = True
    phrase = fold_text(text)
    if any(
        key in phrase
        for key in (
            "acik sayfa",
            "açık sayfa",
            "mevcut sayfa",
            "bu sayfa",
            "current page",
            "this page",
            "current tab",
            "open tab",
            "active tab",
            "chromedaki",
            "chrome'daki",
            "chromedeki",
            "chrome'deki",
            "browserda acik",
            "browserda açık",
            "tarayicida acik",
            "tarayıcıda açık",
        )
    ):
        avoid_playwright = True
        avoid_search = True

    if avoid_playwright:
        browser_name = None
        for name in ("chrome", "edge", "firefox", "brave", "opera"):
            if name in tokens:
                browser_name = name
                break
        adapted = []
        for item in actions:
            action = item.get("action")
            value = item.get("value") or ""
            if action == "web_open":
                updated = dict(item)
                updated["action"] = "browser_open"
                adapted.append(updated)
            elif action == "web_search":
                updated = dict(item)
                updated["action"] = "browser_search"
                adapted.append(updated)
            elif action == "web_click":
                updated = dict(item)
                updated["action"] = "gui_click_text"
                if isinstance(value, str) and value.lower().startswith("css:"):
                    updated["value"] = value[4:].strip()
                elif isinstance(value, str) and value.lower().startswith("text:"):
                    updated["value"] = value[5:].strip()
                adapted.append(updated)
            elif action == "web_type":
                updated = dict(item)
                updated["action"] = "type"
                if "->" in str(value):
                    updated["value"] = str(value).split("->", 1)[1].strip()
                adapted.append(updated)
            elif action == "web_press":
                updated = dict(item)
                updated["action"] = "hotkey"
                adapted.append(updated)
            elif action == "web_wait":
                updated = dict(item)
                updated["action"] = "gui_wait"
                adapted.append(updated)
            elif action == "web_form_fill":
                updated = dict(item)
                updated["action"] = "none"
                updated["reason"] = "Playwright disabled; use normal browser + GUI steps."
                adapted.append(updated)
            else:
                adapted.append(item)
        if browser_name:
            for item in adapted:
                if item.get("action") in ("browser_open", "browser_search"):
                    val = str(item.get("value") or "")
                    if "|" not in val:
                        item["value"] = f"{browser_name}|{val}"
        if avoid_search:
            for item in adapted:
                if item.get("action") in ("browser_open", "browser_search"):
                    item["action"] = "none"
                    item["reason"] = "Use the already-open browser tab."
        actions = adapted

    os_name = _os_label()
    normalized = []
    for item in actions:
        action = item.get("action")
        value = item.get("value") or ""
        if action:
            new_action, new_value = _normalize_os_action(os_name, action, value)
            updated = dict(item)
            updated["action"] = new_action
            updated["value"] = new_value
            normalized.append(updated)
        else:
            normalized.append(item)

    deduped = []
    seen_steps = set()
    for item in normalized:
        key = (item.get("action"), str(item.get("value") or "").strip().lower())
        if key in seen_steps and item.get("action") in {"start", "focus", "open"}:
            continue
        seen_steps.add(key)
        deduped.append(item)
    normalized = deduped

    def _app_key_from_action(action: str | None, val: str) -> str:
        raw = (val or "").strip()
        if not raw:
            return ""
        if action in ("browser_open", "browser_search"):
            if "|" in raw:
                raw = raw.split("|", 1)[0].strip()
            else:
                return ""
        if action == "open":
            if _looks_like_url(raw) or _looks_like_path(raw):
                return ""
        if action == "url_search":
            return ""
        return _normalize_phrase(raw)

    # Ensure "start/open app" happens before "focus app" for the same target.
    launch_indices: dict[str, list[int]] = {}
    for idx, item in enumerate(normalized):
        action = item.get("action")
        if action in ("start", "open", "browser_open", "browser_search"):
            key = _app_key_from_action(action, str(item.get("value") or ""))
            if key:
                launch_indices.setdefault(key, []).append(idx)

    used = set()
    reordered: list[dict] = []
    for idx, item in enumerate(normalized):
        if idx in used:
            continue
        if item.get("action") == "focus":
            key = _app_key_from_action("focus", str(item.get("value") or ""))
            if key:
                for s_idx in launch_indices.get(key, []):
                    if s_idx > idx and s_idx not in used:
                        reordered.append(normalized[s_idx])
                        used.add(s_idx)
            reordered.append(item)
            used.add(idx)
            continue
        reordered.append(item)
        used.add(idx)

    # Ensure cmd/powershell are last-resort steps (run last if present).
    last_resort = []
    ordered = []
    for item in reordered:
        if item.get("action") in ("cmd", "powershell"):
            last_resort.append(item)
        else:
            ordered.append(item)
    if last_resort and ordered:
        ordered = ordered + last_resort
    else:
        ordered = reordered

    def _file_key_for_step(item: dict) -> str:
        action = item.get("action")
        value = str(item.get("value") or "").strip()
        if not value:
            return ""
        if action == "write_file":
            value = re.split(r"\s*(?:->|\|)\s*", value, maxsplit=1)[0].strip()
        if action == "open" and (_looks_like_path(value) or "." in Path(value).name):
            pass
        elif action != "write_file":
            return ""
        return value.lower()

    write_indices = {}
    for idx, item in enumerate(ordered):
        if item.get("action") == "write_file":
            key = _file_key_for_step(item)
            if key:
                write_indices.setdefault(key, idx)
    if write_indices:
        final = []
        used = set()
        for idx, item in enumerate(ordered):
            if idx in used:
                continue
            if item.get("action") == "open":
                key = _file_key_for_step(item)
                w_idx = write_indices.get(key)
                if w_idx is not None and w_idx > idx and w_idx not in used:
                    final.append(ordered[w_idx])
                    used.add(w_idx)
            final.append(item)
            used.add(idx)
        return final
    return ordered


def _normalize_action(value: str | None) -> str | None:
    if not value:
        return None
    action = value.strip().lower()
    aliases = {
        "terminate": "close",
        "quit": "close",
        "exit": "close",
        "url": "open",
        "search": "url_search",
        "poweroff": "shutdown",
        "reboot": "restart",
        "sleep_mode": "sleep",
        "show_desktop": "desktop",
        "desktop_show": "desktop",
        "desktop_toggle": "desktop",
        "open_folder": "open_dir",
        "open_directory": "open_dir",
        "list_folder": "list_dir",
        "list_directory": "list_dir",
        "find_file": "find_files",
        "file_search": "find_files",
        "search_files": "find_files",
        "largest": "largest_files",
        "biggest_files": "largest_files",
        "disk": "disk_usage",
        "storage": "disk_usage",
        "make_dir": "mkdir",
        "create_folder": "mkdir",
        "create_directory": "mkdir",
        "create_file": "write_file",
        "write": "write_file",
        "save_file": "write_file",
        "execute_code": "run_code",
        "run_file": "run_code",
        "run_script": "run_code",
        "create_routine": "routine_create",
        "add_routine": "routine_create",
        "run_routine": "routine_run",
        "start_routine": "routine_run",
        "list_routines": "routine_list",
        "delete_routine": "routine_delete",
        "remove_routine": "routine_delete",
        "unmute": "mute",
    }
    return aliases.get(action, action)


def validate_action(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    action = _normalize_action(payload.get("action"))
    if action not in ALL_ACTIONS:
        return None
    value = payload.get("value")
    reason = payload.get("reason")
    critical = payload.get("critical", True)
    return {"action": action, "value": value, "reason": reason, "critical": bool(critical)}


def validate_actions(payload: object | None) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        if isinstance(payload.get("actions"), list):
            items = []
            for item in payload.get("actions"):
                valid = validate_action(item) if isinstance(item, dict) else None
                if valid:
                    items.append(valid)
            return items
        single = validate_action(payload)
        return [single] if single else []
    if isinstance(payload, list):
        items = []
        for item in payload:
            valid = validate_action(item) if isinstance(item, dict) else None
            if valid:
                items.append(valid)
        return items
    return []


class LLMManager:
    def __init__(self, llm, label: str, enabled: bool = True):
        self.llm = llm
        self.label = label
        self.enabled = enabled
        self.only_mode = False
        self.multi_delay = 0.0
        self.last_plan = {"goal": None, "notes": None}
        self.last_error = ""
        self.last_raw = ""

    def toggle(self):
        self.enabled = not self.enabled

    def toggle_only(self):
        self.only_mode = not self.only_mode

    def status_text(self, ui_lang: str) -> str:
        if self.llm and self.enabled:
            return t(ui_lang, "llm_status_on", name=self.label)
        if self.llm and not self.enabled:
            return t(ui_lang, "llm_status_off", name=self.label)
        return t(ui_lang, "llm_status_missing")

    def suggest_action(self, text: str) -> tuple[list[dict], str]:
        if not self.llm or not self.enabled:
            return [], ""
        self.last_error = ""
        self.last_raw = ""
        raw = self.llm.generate(
            _llm_user_prompt(text),
            system_prompt=_router_system_prompt(),
            raw_user=True,
        )
        self.last_raw = raw or ""
        if not raw and getattr(self.llm, "last_error", ""):
            self.last_error = self.llm.last_error
        actions, goal, notes = _extract_plan(_extract_json(raw))
        actions = _fix_actions_from_text(text, actions)
        self.last_plan = {"goal": goal, "notes": notes}
        return actions, raw

    def plan(self, goal: str, context: str = "") -> tuple[list[dict], str, str | None]:
        if not self.llm or not self.enabled:
            return [], goal, None
        self.last_error = ""
        self.last_raw = ""
        user = _agent_user_prompt(goal, context)
        raw = self.llm.generate(user, system_prompt=_agent_system_prompt(), raw_user=True)
        self.last_raw = raw or ""
        if not raw and getattr(self.llm, "last_error", ""):
            self.last_error = self.llm.last_error
        payload = _extract_json(raw)
        actions, parsed_goal, notes = _extract_plan(payload)
        actions = _fix_actions_from_text(goal, actions)
        if not actions:
            actions, _ = self.suggest_action(goal)
        final_goal = parsed_goal or goal
        self.last_plan = {"goal": final_goal, "notes": notes}
        return actions, final_goal, notes

    def replan(
        self,
        goal: str,
        completed_steps: list[dict],
        failed_step: dict,
        error: str,
    ) -> tuple[list[dict], str, str | None]:
        if not self.llm or not self.enabled:
            return [], goal, None
        summary = "; ".join(
            f"{s.get('action')}:{s.get('value','')}" for s in completed_steps
        )
        context = (
            f"Completed: {summary if summary else 'none'}; "
            f"Failed: {failed_step.get('action')}:{failed_step.get('value','')}; "
            f"Error: {error}"
        )
        return self.plan(goal, context=context)


class LocalLLM:
    def __init__(self, model_path: Path):
        from llama_cpp import Llama

        self.model_path = model_path
        self.llm = Llama(
            model_path=str(model_path),
            n_ctx=LLM_LOCAL_CTX,
            n_threads=LLM_LOCAL_THREADS,
        )
        self.last_error = ""

    def generate(
        self,
        text: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        raw_user: bool = False,
    ) -> str:
        self.last_error = ""
        system_prompt = system_prompt or _router_system_prompt()
        user_text = text if raw_user else _llm_user_prompt(text)
        prompt = _build_phi3_prompt(user_text, system_prompt)
        try:
            result = self.llm(
                prompt,
                max_tokens=LLM_LOCAL_MAX_TOKENS,
                temperature=LLM_LOCAL_TEMPERATURE if temperature is None else temperature,
                stop=["<|end|>"],
            )
            return (result.get("choices") or [{}])[0].get("text", "")
        except Exception as exc:
            self.last_error = str(exc)
            return ""


class ApiLLM:
    def __init__(self, provider: dict, api_key: str, model: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.last_error = ""

    def generate(
        self,
        text: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        raw_user: bool = False,
    ) -> str:
        self.last_error = ""
        endpoint = str(self.provider.get("endpoint", "")).strip()
        if not endpoint or not self.api_key:
            return ""
        headers_tpl = self.provider.get("headers", {})
        headers = {}
        for k, v in headers_tpl.items():
            headers[k] = v.format(api_key=self.api_key)

        user_text = text if raw_user else _llm_user_prompt(text)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt or _router_system_prompt()},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.2 if temperature is None else temperature,
        }
        timeout = int(self.provider.get("timeout_sec", 60))
        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            detail = ""
            try:
                detail = resp.text[:500]
            except Exception:
                detail = ""
            self.last_error = f"{exc}"
            if detail:
                self.last_error = f"{self.last_error} | {detail}"
            return ""

        path = self.provider.get("response_path", [])
        current = data
        for key in path:
            try:
                if isinstance(key, int):
                    current = current[key]
                else:
                    current = current.get(key)
            except Exception:
                return ""
        return current if isinstance(current, str) else ""


def _local_model_path() -> Path | None:
    if LLM_LOCAL_MODEL_PATH:
        path = Path(LLM_LOCAL_MODEL_PATH)
        if path.exists():
            return path
    if LLM_MODELS_DIR.exists():
        for model in LLM_MODELS_DIR.rglob("*.gguf"):
            return model
    return None


def load_llm_providers():
    if not LLM_PROVIDERS_JSON.exists():
        return []
    data = json.loads(LLM_PROVIDERS_JSON.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("providers"), list):
        return data["providers"]
    if isinstance(data, list):
        return data
    return []


def choose_llm(ui_lang):
    while True:
        print("\n" + t(ui_lang, "llm_title"))
        print(t(ui_lang, "llm_off"))
        print(t(ui_lang, "llm_local"))
        print(t(ui_lang, "llm_api"))
        choice = input(t(ui_lang, "llm_select")).strip().lower()

        if choice in ("1", "off", ""):
            return LLMManager(None, t(ui_lang, "llm_label_off"), enabled=False)

        if choice in ("2", "local"):
            model_path = _local_model_path()
            if not model_path:
                print(t(ui_lang, "llm_missing_model"))
                continue
            try:
                llm = LocalLLM(model_path)
            except Exception:
                print(t(ui_lang, "llm_missing_lib"))
                continue
            return LLMManager(llm, t(ui_lang, "llm_label_local"), enabled=True)

        if choice in ("3", "api"):
            providers = load_llm_providers()
            if not providers:
                print(t(ui_lang, "llm_provider_missing"))
                return LLMManager(None, t(ui_lang, "llm_label_api"), enabled=False)

            print("\n" + t(ui_lang, "llm_provider_title"))
            for i, provider in enumerate(providers, start=1):
                label = provider.get("label") or provider.get("id", f"provider_{i}")
                print(f"{i}) {label}")

            select = input(t(ui_lang, "llm_provider_select")).strip().lower()
            provider = None
            if select.isdigit():
                idx = int(select) - 1
                if 0 <= idx < len(providers):
                    provider = providers[idx]
            else:
                for item in providers:
                    if item.get("id", "").lower() == select:
                        provider = item
                        break
            if provider is None:
                provider = providers[0]

            provider_id = provider.get("id", "provider")
            saved = get_entry("llm", provider_id)
            saved_key = saved.get("api_key") if isinstance(saved, dict) else None
            if saved_key:
                api_key = input(t(ui_lang, "llm_api_key_prompt_saved")).strip()
                if not api_key:
                    api_key = saved_key
            else:
                api_key = input(t(ui_lang, "llm_api_key_prompt")).strip()
            if not api_key:
                return LLMManager(None, t(ui_lang, "llm_label_api"), enabled=False)

            model_hint = provider.get("model_hint", "")
            saved_model = saved.get("model") if isinstance(saved, dict) else None
            model_default = saved_model or model_hint
            model = input(t(ui_lang, "llm_model_prompt", default=model_default)).strip()
            if not model:
                model = model_default

            set_entry("llm", provider_id, {"api_key": api_key, "model": model})
            print(t(ui_lang, "api_saved"))
            label = f"{t(ui_lang, 'llm_label_api')} ({provider.get('label', provider_id)})"
            return LLMManager(
                ApiLLM(provider=provider, api_key=api_key, model=model),
                label,
                enabled=True,
            )

        print(t(ui_lang, "invalid_choice"))
