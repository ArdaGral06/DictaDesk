import ast
import json
import platform
import re
from pathlib import Path

import requests

from config import (
    CODE_PROJECTS_DIR,
    DEFAULT_UI_LANG,
    LLM_CODING_MAX_TOKENS,
    LLM_LOCAL_CTX,
    LLM_LOCAL_MAX_TOKENS,
    LLM_LOCAL_MODEL_PATH,
    LLM_LOCAL_TEMPERATURE,
    LLM_LOCAL_THREADS,
    LLM_MODELS_DIR,
    LLM_PROVIDERS_JSON,
    LLM_ROUTER_MAX_TOKENS,
)
from http_retry import post_with_retry
from i18n import t
from secrets_store import get_entry, set_entry
from agent_memory import format_memory_for_prompt
from actions_manifest import action_names, action_summary_for_prompt, actions_by_safety
from utils import fold_text


ALL_ACTIONS = action_names() | {"none"}
DANGEROUS_ACTIONS = actions_by_safety("dangerous") | actions_by_safety("needs_confirmation")
SAFE_ACTIONS = ALL_ACTIONS - DANGEROUS_ACTIONS - {"none"}

_SYNONYM_GUIDE = (
    "SYNONYM & INTENT GUIDE — Turkish and English phrases map to the SAME action:\n"
    "CLOSE an APP (value = app name): close, quit, exit, terminate, end, kill, stop, "
    "kapat, kapatma, sonlandir, sonlandirma, bitir, kapatir, kapatmak, quit app.\n"
    "SHUTDOWN the PC (no app value): bilgisayari kapat, pc kapat, shut down computer, "
    "power off, turn off pc, kapat bilgisayari, sistemi kapat — NOT the same as closing an app.\n"
    "RESTART PC: restart, reboot, yeniden baslat, bilgisayari yeniden baslat.\n"
    "SLEEP PC: sleep, suspend, uyku, uyku modu, bilgisayari uyut.\n"
    "LOCK screen: lock, kilitle, ekrani kilitle, lock screen.\n"
    "VOLUME up: volume up, louder, ses ac, sesi ac, sesi yukselt, sesi artir, turn up volume.\n"
    "VOLUME down: volume down, quieter, ses kis, sesi kis, sesi azalt, sesi indir.\n"
    "VOLUME set: volume 50, sesi 50 yap, set volume to 30, ses seviyesi 70.\n"
    "MUTE toggle: mute, unmute, sessize al, sesi kapat (audio mute only), sustur.\n"
    "BRIGHTNESS up: brightness up, parlakligi artir, ekrani parlaklastir, daha parlak.\n"
    "BRIGHTNESS down: brightness down, parlakligi azalt, ekrani kis, daha karanlik.\n"
    "BRIGHTNESS set: brightness 50, parlakligi 40 yap, ekran parlakligi 80.\n"
    "OPEN/START app: open, start, launch, run, ac, acmak, baslat, calistir + app name.\n"
    "FOCUS app: focus, bring to front, one getir, uygulamayi one getir + app name.\n"
    "If the user says only 'kapat' with NO target, ask via action none OR close the focused app is NOT supported — prefer none with reason.\n"
    "If both an app name AND close verbs appear, use close with the app name — never shutdown.\n"
)

_CODING_GUIDE = (
    "CODING & GAME DEVELOPMENT MODE — behave like a strong coding LLM:\n"
    "- Produce COMPLETE, runnable source code. Never use placeholders like '// rest of code', '...', or 'TODO implement'.\n"
    "- HTML/CSS/JS games: one self-contained .html file OR split index.html + style.css + game.js under the project folder.\n"
    "- Include a visible game loop, controls (keyboard and/or mouse), score/UI, and clear win/lose or endless gameplay.\n"
    "- For 'clone' requests (e.g. GTA-like): build a simplified 2D playable prototype (canvas top-down/side view), not a full AAA game.\n"
    "- Python scripts: include if __name__ == '__main__' when runnable.\n"
    "- Save paths under Desktop/DictaDeskProjects/<short-project-name>/file.ext unless the user gave an exact path.\n"
    "- write_file value format: relative/path.ext -> FULL file content (real newlines inside JSON strings).\n"
    "- Order: mkdir project folder (if needed) -> write_file(s) -> open .html in browser OR open file path. Do NOT start Notepad++ unless asked.\n"
    "- Use run_code only when the user explicitly asks to run/test/execute a .py or .js file.\n"
    "- For 'open/play/show in browser' HTML games: use open with the .html file path (opens default browser) — NOT start random editors.\n"
    "- Multi-step coding plans are allowed (up to 8 steps): mkdir, multiple write_file, then open/browser_open.\n"
    "- Do not use cmd/powershell to write files; always use write_file with full content.\n"
)


def is_coding_request(text: str) -> bool:
    folded = fold_text(text or "")
    if not folded:
        return False
    keywords = (
        "kod",
        "code",
        "script",
        "html",
        "css",
        "javascript",
        "typescript",
        "python",
        "oyun",
        "game",
        "klon",
        "clone",
        "gelistir",
        "develop",
        "program",
        "uygulama yap",
        "web sitesi",
        "website",
        "flask",
        "react",
        "canvas",
        "gta",
        "dosya olustur",
        "dosya yaz",
        "write file",
        "create file",
        "bana yap",
        "yaz bana",
        "projesi",
        "project",
        "api",
        "sqlite",
        "veritaban",
    )
    return any(key in folded for key in keywords)


def _coding_project_dir(text: str) -> Path:
    slug = re.sub(r"[^a-z0-9-]+", "-", fold_text(text or "")[:56]).strip("-")
    if not slug:
        slug = "project"
    return CODE_PROJECTS_DIR / slug[:40]


def coding_plan_context(text: str) -> str:
    if not is_coding_request(text):
        return ""
    folder = _coding_project_dir(text)
    return (
        f"CODING TASK. Default output folder: {folder}. "
        f"Use write_file with FULL source after '->'. "
        f"Example: game.html -> <!DOCTYPE html>...complete document..."
    )


def _parse_write_file_pair(value: str) -> tuple[str | None, str | None]:
    raw = (value or "").strip()
    if not raw:
        return None, None
    for sep in ("->", "|"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            left = left.strip()
            right = right.strip()
            if left and right is not None:
                return left, right
    return None, None


def _resolve_coding_path(path: str, base_dir: Path) -> str:
    raw = (path or "").strip()
    if not raw:
        return str(base_dir / "output.txt")
    target = Path(raw).expanduser()
    if target.is_absolute():
        return str(target)
    return str(base_dir / target)


def enhance_coding_plan(text: str, actions: list[dict]) -> list[dict]:
    if not actions or not is_coding_request(text):
        return actions

    folded = fold_text(text or "")
    wants_preview = any(
        w in folded
        for w in (
            "oyna",
            "play",
            "ac",
            "open",
            "tarayic",
            "browser",
            "goster",
            "show",
            "calistir",
            "run",
            "test",
            "baslat",
            "launch",
        )
    )
    base_dir = _coding_project_dir(text)
    enhanced: list[dict] = []

    if any(a.get("action") == "write_file" for a in actions) and not any(
        a.get("action") == "mkdir" for a in actions
    ):
        enhanced.append(
            {
                "action": "mkdir",
                "value": str(base_dir),
                "reason": "Create project folder for generated code.",
                "critical": True,
            }
        )

    written_html: list[str] = []
    for item in actions:
        updated = dict(item)
        if updated.get("action") == "write_file":
            path, content = _parse_write_file_pair(str(updated.get("value") or ""))
            if path:
                resolved = _resolve_coding_path(path, base_dir)
                updated["value"] = f"{resolved} -> {content or ''}"
                if Path(resolved).suffix.lower() in (".html", ".htm"):
                    written_html.append(resolved)
        enhanced.append(updated)

    for html_path in written_html:
        if not wants_preview:
            continue
        already = any(
            str(a.get("value") or "").strip().lower() == html_path.lower()
            and a.get("action") in ("open", "browser_open", "run_code")
            for a in enhanced
        )
        if not already:
            enhanced.append(
                {
                    "action": "open",
                    "value": html_path,
                    "reason": "Open the HTML game in the default browser.",
                    "critical": False,
                }
            )

    return enhanced


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
        "Write file values: 'path -> full file content'. Use this when the user asks you to code, create a script, create an HTML game, or write a file. "
        "For coding/game requests output COMPLETE runnable code in write_file — never placeholders. "
        "Save under Desktop/DictaDeskProjects/<project>/ when no exact path is given. "
        "Use run_code only when the user asks to run/execute/test the created code. "
        "Routine values: routine_create uses 'name -> routine command text'; routine_run/list/delete use routine name or empty for list. "
        "List/Open dir values: directory path or empty for Desktop. "
        "Find files value format: 'name=<text>; extension=.pdf; path=downloads; limit=20' (any field optional except name or extension). Largest files value: 'path=downloads; count=10'. Disk usage value: path or empty. "
        "OCR values: image path or 'screen' to capture screen. "
        "GUI actions: gui_click_text uses visible text, gui_click_image uses image path, gui_click uses 'x,y', gui_wait uses seconds. "
        "GUI wait actions: gui_wait_text uses 'text|timeout_sec' (timeout optional), gui_wait_image uses 'path|threshold|timeout'. "
        "GUI mapping: gui_map/gui_click_index are for debugging; do NOT use them unless the user explicitly asks for a map. "
        "If multiple visible elements contain the same text, do not rely on text alone; prefer the element whose UI region and nearby labels match the user intent. "
        "For Discord SERVER + CHANNEL requests (sunucu/kanal/server/channel): first focus Discord, switch to the named server via quick switcher (Ctrl+K + server name), then click the channel in the left channel list (e.g. genel/general), then type the message. Do NOT use DM flow (Ctrl+K person search) for channel requests. "
        "For Discord direct messages only, use: focus Discord, hotkey 'ctrl k', type the person name, hotkey 'enter', type message, hotkey 'enter'. "
        "Never start Notepad++ unless the user explicitly asked for it. After write_file, open the file path — do not start random editors. "
        "Do not add run_code, cmd, powershell, or extra start steps after a coding/write_file task unless the user explicitly asked to run or open a specific app. "
        "If the user mentions an app name and GUI actions follow, add a first step: focus with that app name. "
        "Web actions (Playwright): web_open URL, web_search query, youtube_search query, web_click text (or 'css:selector'), web_type text or 'selector -> text', web_press key, web_wait seconds, web_form_fill key=value pairs (use memory for non-sensitive fields; include email/password ONLY if user explicitly provided them). "
        "Context may include BROWSER_PAGE_JSON / PLAYWRIGHT_PAGE_JSON with page_kind (login/signup/password/checkout/search/form). Match web_form_fill mode to page_kind. "
        "Native browser actions (no Playwright): browser_open 'browser|url' (browser optional), browser_search 'browser|query'. "
        "If user says 'do not use Playwright' or 'normal browser', use browser_open/browser_search + GUI actions. "
        "Strict ordering: start/open an app before focus or GUI steps; create/write a file before opening it; wait briefly after starting apps or opening pages when UI needs time. Do not repeat a completed start/focus/open step. "
        "If the user says close/quit/exit/terminate/kapat/sonlandir/bitir with an APP name, use action: close. "
        "If the user wants to shut down/restart/sleep the PC (bilgisayar/pc/system), use shutdown/restart/sleep — not close. "
        "For volume use action volume with value like 'up 10', 'down 10', or '50'. For brightness use action brightness similarly. "
        "For mute/sessize al use action mute with empty value. "
        f"Current OS: {os_name}. {os_hint} "
        "If the user mentions a file by name, value can be the filename; the system will search common folders. "
        "If the user gives a path, return the path as value. "
        "If the request is unclear or unsafe, return action: none. "
        "Return ONLY JSON, no extra text."
        "\n"
        + _SYNONYM_GUIDE
        + "\nACTION MANIFEST:\n"
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


def _agent_system_prompt(coding: bool = False) -> str:
    os_name = _os_label()
    os_hint = "Windows-only. Windows apps: File Explorer, Notepad. Treat 'Finder' as File Explorer."

    memory = format_memory_for_prompt()
    memory_block = f"\n{memory}" if memory else ""
    manifest = action_summary_for_prompt()
    step_limit = "max 8" if coding else "max 7"
    coding_block = f"\n{_CODING_GUIDE}\n" if coding else ""
    return (
        "You are an autonomous planning agent for a PC voice assistant. "
        f"Break the user's goal into the smallest number of steps ({step_limit}). "
        "Never ask unnecessary questions; make a reasonable assumption and proceed. "
        "Do not repeat yourself. "
        f"Each step must be an allowed action only: {_allowed_actions_text()}. "
        "Prefer safe actions from the manifest. "
        "Use delete/cmd/powershell/run_code/shutdown/restart/sleep only if the user explicitly asks or confirms execution. "
        "For coding/game tasks: write COMPLETE files with write_file; use run_code only if the user asks to run/test code. "
        "Do not use cmd/powershell unless the user explicitly asks to run a command. "
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
        "For Discord SERVER + CHANNEL requests (sunucu/kanal/server/channel): first focus Discord, switch to the named server via quick switcher (Ctrl+K + server name), then click the channel in the left channel list (e.g. genel/general), then type the message. Do NOT use DM flow (Ctrl+K person search) for channel requests. "
        "For Discord direct messages only, use: focus Discord, hotkey 'ctrl k', type the person name, hotkey 'enter', type message, hotkey 'enter'. "
        "Never start Notepad++ unless the user explicitly asked for it. After write_file, open the file path — do not start random editors. "
        "Do not add run_code, cmd, powershell, or extra start steps after a coding/write_file task unless the user explicitly asked to run or open a specific app. "
        "If the user mentions an app name and GUI actions follow, add a first step: focus with that app name. "
        "Web actions (Playwright): web_open URL, web_search query, youtube_search query, web_click text (or 'css:selector'), web_type text or 'selector -> text', web_press key, web_wait seconds, web_form_fill key=value pairs (use memory for non-sensitive fields; include email/password ONLY if user explicitly provided them). "
        "Context may include BROWSER_PAGE_JSON / PLAYWRIGHT_PAGE_JSON with page_kind (login/signup/password/checkout/search/form). Match web_form_fill mode to page_kind. "
        "Native browser actions (no Playwright): browser_open 'browser|url' (browser optional), browser_search 'browser|query'. "
        "If user says 'do not use Playwright' or 'normal browser', use browser_open/browser_search + GUI actions. "
        "Strict ordering: start/open an app before focus or GUI steps; create/write a file before opening it; wait briefly after starting apps or opening pages when UI needs time. Do not repeat a completed start/focus/open step. "
        "If the user says close/quit/exit/terminate/kapat/sonlandir/bitir with an APP name, use action close. "
        "If the user wants to shut down/restart/sleep the PC (bilgisayar/pc/system), use shutdown/restart/sleep — not close. "
        "For volume use action volume with value like 'up 10', 'down 10', or '50'. For brightness use action brightness similarly. "
        "For mute/sessize al use action mute with empty value. "
        "Return ONLY JSON, no extra text."
        "\n"
        + _SYNONYM_GUIDE
        + coding_block
        + "\nACTION MANIFEST:\n"
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


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    folded = fold_text(text or "")
    return any(p in folded for p in phrases)


def _extract_app_target(text: str, skip_tokens: set[str]) -> str:
    import re

    folded = fold_text(text or "")
    tokens = re.findall(r"[a-z0-9]+", folded)
    filler = skip_tokens | {
        "please",
        "lutfen",
        "the",
        "a",
        "an",
        "bir",
        "uygulama",
        "uygulamayi",
        "uygulamasi",
        "app",
        "application",
        "program",
        "window",
        "pencere",
        "bana",
        "benim",
        "icin",
        "for",
        "me",
    }
    kept = [t for t in tokens if t not in filler and len(t) > 1]
    return " ".join(kept).strip()


def infer_quick_actions(text: str) -> list[dict]:
    """High-confidence keyword routing before/alongside the LLM."""
    if not text or not str(text).strip():
        return []

    phrase = fold_text(text)
    tokens = set(_tokenize(text))

    pc_tokens = {
        "bilgisayar",
        "bilgisayari",
        "pc",
        "computer",
        "system",
        "windows",
        "isletim",
        "makine",
        "laptop",
    }
    has_pc = bool(tokens & pc_tokens) or "bilgisayar" in phrase

    if has_pc:
        if _contains_any(
            text,
            (
                "yeniden baslat",
                "restart",
                "reboot",
                "reset pc",
            ),
        ):
            return [{"action": "restart", "value": "", "reason": "Restart the PC.", "critical": True}]
        if _contains_any(
            text,
            (
                "uyku",
                "sleep",
                "suspend",
                "uyut",
            ),
        ):
            return [{"action": "sleep", "value": "", "reason": "Sleep the PC.", "critical": True}]
        if _contains_any(
            text,
            (
                "kapat",
                "shutdown",
                "power off",
                "turn off",
                "shut down",
                "sonlandir",
                "kapatma",
            ),
        ):
            return [{"action": "shutdown", "value": "", "reason": "Shut down the PC.", "critical": True}]

    if _contains_any(
        text,
        (
            "ekrani kilitle",
            "ekran kilitle",
            "lock screen",
            "lock the screen",
            "kilitle",
        ),
    ) and not _contains_any(text, ("unlock", "ac kilidi")):
        return [{"action": "lock", "value": "", "reason": "Lock the screen.", "critical": True}]

    mute_words = {"mute", "sustur", "sessize", "sessiz", "unmute"}
    if tokens & mute_words or _contains_any(
        text,
        ("sessize al", "sesi kapat", "sounds off", "sound off"),
    ):
        return [{"action": "mute", "value": "", "reason": "Toggle mute.", "critical": False}]

    volume_words = {"volume", "ses", "sound", "audio", "sesi", "sesin", "sesli"}
    brightness_words = {"brightness", "parlaklik", "parlakligi", "parlak", "ekran", "screen", "backlight"}
    has_volume = bool(tokens & volume_words) or "ses " in phrase or phrase.startswith("ses")
    has_brightness = bool(tokens & brightness_words) or "parlak" in phrase

    if has_volume and not has_brightness:
        return [
            {
                "action": "volume",
                "value": text.strip(),
                "reason": "Adjust system volume.",
                "critical": False,
            }
        ]
    if has_brightness and not has_volume:
        return [
            {
                "action": "brightness",
                "value": text.strip(),
                "reason": "Adjust screen brightness.",
                "critical": False,
            }
        ]

    close_words = {
        "close",
        "quit",
        "exit",
        "terminate",
        "sonlandir",
        "sonlandirma",
        "bitir",
        "kapat",
        "kapatma",
        "kapatir",
    }
    close_prefixes = ("kapat", "cik", "sonlandir", "bitir")
    has_close = bool(tokens & close_words) or any(
        any(tok.startswith(p) for p in close_prefixes) for tok in tokens
    )
    delete_words = {"delete", "remove", "uninstall", "erase", "sil", "kaldir"}
    has_delete = bool(tokens & delete_words)

    if has_close and not has_delete:
        target = _extract_app_target(text, close_words | delete_words)
        if target and not (tokens & pc_tokens):
            return [
                {
                    "action": "close",
                    "value": target,
                    "reason": f"Close {target}.",
                    "critical": True,
                }
            ]

    return []


def _extract_youtube_query(text: str) -> str:
    folded = fold_text(text or "")
    noise = (
        "youtube",
        "youtu",
        "video",
        "videosu",
        "videosunu",
        "videoyu",
        "izle",
        "watch",
        "play",
        "ac",
        "open",
        "ara",
        "search",
        "bul",
        "bana",
        "lutfen",
        "please",
        "ilk",
        "first",
        "sonuc",
        "result",
        "sonuca",
        "tikla",
        "tıkla",
        "click",
        "cikan",
        "cik",
        "cikani",
        "cikan",
        "rahatsiz",
        "rahatlat",
        "rahatlatici",
    )
    for word in noise:
        folded = re.sub(rf"\b{re.escape(word)}\b", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip(" :,.")
    return folded or (text or "").strip()


def infer_structured_workflow(text: str) -> list[dict]:
    """Deterministic multi-step routes for common complex requests."""
    if not text or not str(text).strip():
        return []

    folded = fold_text(text)

    if "youtube" in folded or "youtu" in folded:
        if any(
            k in folded
            for k in (
                "ara",
                "search",
                "izle",
                "watch",
                "ac",
                "asmr",
                "video",
                "ilk",
                "first",
                "sonuc",
                "result",
                "tikla",
                "click",
                "bul",
                "rahatlat",
            )
        ):
            query = _extract_youtube_query(text)
            if query:
                return [
                    {
                        "action": "youtube_search",
                        "value": query,
                        "reason": "Search YouTube and open the first result.",
                        "critical": True,
                    }
                ]

    create_hints = (
        "olustur",
        "create",
        "yap",
        "klasor",
        "folder",
        "dosya",
        "file",
        "txt",
    )
    if not any(h in folded for h in create_hints):
        return []

    desktop = Path.home() / "Desktop"
    folder_name = None
    folder_patterns = (
        r"(?:masaustu(?:ne|nde|nden)?|desktop(?:\s+named)?).*?(?:adli|adlı|named)?\s*([\w.-]+)\s*(?:adli|adlı|named)?\s*(?:klasor|klasör|folder)",
        r"([\w.-]+)\s+(?:adli|adlı|named)\s+(?:bir\s+)?(?:klasor|klasör|folder)",
        r"(?:klasor|klasör|folder)\s+(?:adli|adlı|named)?\s*([\w.-]+)",
    )
    for pat in folder_patterns:
        match = re.search(pat, text, flags=re.IGNORECASE)
        if match:
            folder_name = match.group(1).strip()
            break

    file_name = None
    match_file = re.search(
        r"([\w.-]+\.(?:txt|html|htm|py|js|css|json|md|bat|ps1))\b",
        text,
        flags=re.IGNORECASE,
    )
    if match_file:
        file_name = match_file.group(1)
    else:
        match_plain = re.search(
            r"([\w.-]+)\s+(?:adli|adlı|named)?\s*(?:dosya|file)",
            text,
            flags=re.IGNORECASE,
        )
        if match_plain and "." not in match_plain.group(1):
            file_name = f"{match_plain.group(1)}.txt"

    content = ""
    for pat in (r'"([^"]+)"', r"'([^']+)'"):
        matches = re.findall(pat, text)
        if matches:
            content = matches[-1].strip()
            break
    if not content and file_name:
        stem = Path(file_name).stem.lower()
        if stem and stem in folded:
            content = stem

    wants_open = any(
        w in folded for w in ("ac", "open", "not defteri", "notepad", "defteri", "ile ac")
    )

    actions: list[dict] = []
    folder_path = desktop / folder_name if folder_name else None

    if folder_name:
        actions.append(
            {
                "action": "mkdir",
                "value": str(folder_path),
                "reason": f"Create folder {folder_name} on Desktop.",
                "critical": True,
            }
        )

    if file_name:
        file_path = (folder_path / file_name) if folder_path else (desktop / file_name)
        actions.append(
            {
                "action": "write_file",
                "value": f"{file_path} -> {content}",
                "reason": f"Create {file_name}.",
                "critical": True,
            }
        )
        if wants_open:
            actions.append(
                {
                    "action": "open",
                    "value": str(file_path),
                    "reason": "Open the created file.",
                    "critical": True,
                }
            )

    return actions


def sanitize_planned_actions(text: str, actions: list[dict]) -> list[dict]:
    """Remove unsafe or unrelated steps the planner may hallucinate."""
    if not actions:
        return actions

    folded = fold_text(text or "")
    run_words = (
        "calistir",
        "run",
        "execute",
        "test et",
        "test it",
        "launch",
        "derle",
        "oyna",
        "play",
    )
    open_words = ("ac", "open", "tarayic", "browser", "goster", "show", "oyna", "play")
    wants_run = any(w in folded for w in run_words)
    wants_open = any(w in folded for w in open_words)
    wants_npp = "notepad++" in folded or "notepad plus" in folded
    has_write = any((item.get("action") or "") == "write_file" for item in actions)
    coding = is_coding_request(text)

    cleaned: list[dict] = []
    for item in actions:
        action = (item.get("action") or "").strip().lower()
        value = item.get("value") or ""
        value_fold = fold_text(value)

        if action == "run_code":
            path = value.strip()
            if path.lower().endswith((".html", ".htm")) and wants_open:
                pass
            elif not wants_run and not (coding and wants_open):
                continue
        if action in {"cmd", "powershell"} and not any(
            w in folded for w in ("cmd", "powershell", "terminal", "komut satiri", "komut")
        ):
            continue
        if action == "start":
            if "notepad++" in value_fold and not wants_npp:
                continue
            if has_write and value_fold not in folded and not wants_open:
                allowed = {"notepad", "not defteri", "chrome", "edge", "firefox", "brave"}
                if value_fold not in allowed and not any(
                    tok in folded for tok in value_fold.split()
                ):
                    continue
        if action == "open" and has_write and wants_open:
            cleaned.append(item)
            continue
        cleaned.append(item)

    return cleaned if cleaned else actions


def _fix_actions_from_text(text: str, actions: list[dict]) -> list[dict]:
    if not actions or not text:
        return actions
    tokens = _tokenize(text)
    if not tokens:
        return actions

    close_words = {
        "close",
        "quit",
        "exit",
        "terminate",
        "end",
        "sonlandir",
        "sonlandirma",
        "bitir",
    }
    delete_words = {"delete", "remove", "uninstall", "erase", "sil", "kaldir"}
    close_prefixes = {"kapat", "cik", "sonlandir", "bitir"}
    delete_prefixes = {"sil", "kaldir"}
    pc_tokens = {
        "bilgisayar",
        "bilgisayari",
        "pc",
        "computer",
        "system",
        "windows",
        "isletim",
        "makine",
    }

    has_pc = any(tok in pc_tokens for tok in tokens) or "bilgisayar" in fold_text(text)
    wants_shutdown = has_pc and (
        bool(tokens & {"kapat", "shutdown", "poweroff", "sonlandir", "kapatma"})
        or _contains_any(text, ("shut down", "power off", "turn off", "kapat bilgisayar"))
    )
    if wants_shutdown and not any(tok in delete_words for tok in tokens):
        return [
            {
                "action": "shutdown",
                "value": "",
                "reason": "User asked to shut down the PC.",
                "critical": True,
            }
        ]

    has_close = any(tok in close_words for tok in tokens) or any(
        tok.startswith(p) for tok in tokens for p in close_prefixes
    )
    has_delete = any(tok in delete_words for tok in tokens) or any(
        tok.startswith(p) for tok in tokens for p in delete_prefixes
    )

    if has_close and not has_delete:
        fixed = []
        for item in actions:
            action_name = item.get("action")
            if action_name == "delete":
                updated = dict(item)
                updated["action"] = "close"
                if not updated.get("reason"):
                    updated["reason"] = "User asked to close an app."
                fixed.append(updated)
            elif action_name in {"open", "focus", "start", "none"} and item.get("value"):
                updated = dict(item)
                updated["action"] = "close"
                if not updated.get("reason"):
                    updated["reason"] = "User asked to close an app."
                fixed.append(updated)
            else:
                fixed.append(item)
        actions = fixed
        if len(actions) == 1 and actions[0].get("action") in {"none", "open", "focus"}:
            target = _extract_app_target(text, close_words | delete_words | pc_tokens)
            if target:
                actions = [
                    {
                        "action": "close",
                        "value": target,
                        "reason": f"Close {target}.",
                        "critical": True,
                    }
                ]

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
        "kapat": "close",
        "sonlandir": "close",
        "bitir": "close",
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
        coding = is_coding_request(text)
        max_tokens = LLM_CODING_MAX_TOKENS if coding else LLM_ROUTER_MAX_TOKENS
        raw = self.llm.generate(
            _llm_user_prompt(text),
            system_prompt=_router_system_prompt(),
            raw_user=True,
            max_tokens=max_tokens,
        )
        self.last_raw = raw or ""
        if not raw and getattr(self.llm, "last_error", ""):
            self.last_error = self.llm.last_error
        actions, goal, notes = _extract_plan(_extract_json(raw))
        actions = _fix_actions_from_text(text, actions)
        actions = enhance_coding_plan(text, actions)
        actions = sanitize_planned_actions(text, actions)
        self.last_plan = {"goal": goal, "notes": notes}
        return actions, raw

    def plan(self, goal: str, context: str = "") -> tuple[list[dict], str, str | None]:
        if not self.llm or not self.enabled:
            return [], goal, None
        self.last_error = ""
        self.last_raw = ""
        coding = is_coding_request(goal)
        if coding and "CODING TASK" not in (context or ""):
            ctx = coding_plan_context(goal)
            context = f"{context}; {ctx}" if context else ctx
        user = _agent_user_prompt(goal, context)
        max_tokens = LLM_CODING_MAX_TOKENS if coding else None
        raw = self.llm.generate(
            user,
            system_prompt=_agent_system_prompt(coding=coding),
            raw_user=True,
            max_tokens=max_tokens,
        )
        self.last_raw = raw or ""
        if not raw and getattr(self.llm, "last_error", ""):
            self.last_error = self.llm.last_error
        payload = _extract_json(raw)
        actions, parsed_goal, notes = _extract_plan(payload)
        actions = _fix_actions_from_text(goal, actions)
        if not actions:
            actions, _ = self.suggest_action(goal)
        else:
            actions = enhance_coding_plan(goal, actions)
            actions = sanitize_planned_actions(goal, actions)
        final_goal = parsed_goal or goal
        self.last_plan = {"goal": final_goal, "notes": notes}
        return actions, final_goal, notes

    def replan(
        self,
        goal: str,
        completed_steps: list[dict],
        failed_step: dict,
        error: str,
        original_text: str = "",
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
        source = (original_text or goal).strip()
        return self.plan(source, context=context)


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
        max_tokens: int | None = None,
    ) -> str:
        self.last_error = ""
        system_prompt = system_prompt or _router_system_prompt()
        user_text = text if raw_user else _llm_user_prompt(text)
        prompt = _build_phi3_prompt(user_text, system_prompt)
        token_limit = max_tokens or LLM_LOCAL_MAX_TOKENS
        try:
            result = self.llm(
                prompt,
                max_tokens=token_limit,
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
        max_tokens: int | None = None,
    ) -> str:
        self.last_error = ""
        endpoint = str(self.provider.get("endpoint", "")).strip()
        if not endpoint or not self.api_key:
            return ""
        from api_budget import check_budget, record_budget_usage

        allowed, block_msg = check_budget("llm", DEFAULT_UI_LANG)
        if not allowed:
            self.last_error = block_msg or "budget_blocked"
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
            "max_tokens": max_tokens or int(self.provider.get("max_tokens", 2048)),
        }
        timeout = int(self.provider.get("timeout_sec", 60))
        try:
            resp = post_with_retry(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            record_budget_usage("llm")
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
