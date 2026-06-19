import json

from config import COMMANDS_JSON
from i18n import t, safe_lang


def normalize_commands_data(data):
    if isinstance(data, dict) and "commands" in data:
        data = data["commands"]

    if isinstance(data, list):
        return {"tr": data, "en": []}

    if isinstance(data, dict):
        tr_cmds = data.get("tr", [])
        en_cmds = data.get("en", [])
        if not isinstance(tr_cmds, list):
            tr_cmds = []
        if not isinstance(en_cmds, list):
            en_cmds = []
        return {"tr": tr_cmds, "en": en_cmds}

    return {"tr": [], "en": []}


def default_commands():
    return {
        "commands": {
            "tr": [],
            "en": [],
        }
    }


def load_commands():
    if COMMANDS_JSON.exists():
        raw = json.loads(COMMANDS_JSON.read_text(encoding="utf-8"))
        commands = normalize_commands_data(raw)
        normalized = {"commands": commands}
        if raw != normalized:
            COMMANDS_JSON.write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return commands

    defaults = default_commands()
    COMMANDS_JSON.write_text(
        json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return defaults["commands"]


def save_commands(all_commands):
    COMMANDS_JSON.write_text(
        json.dumps({"commands": all_commands}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_phrases(cmd):
    phrases = []
    if isinstance(cmd.get("phrase"), str):
        phrases.append(cmd["phrase"])
    if isinstance(cmd.get("phrases"), list):
        for item in cmd["phrases"]:
            if isinstance(item, str):
                phrases.append(item)
    return [p.strip() for p in phrases if p.strip()]


def format_command_line(index, cmd):
    phrases = extract_phrases(cmd)
    phrase_text = " | ".join(phrases) if phrases else "-"
    action = cmd.get("action", "-")
    value = cmd.get("value", "-")
    return f"{index}. [{action}] {phrase_text} -> {value}"


def match_command(text: str, commands):
    from utils import normalize_text

    norm_text = normalize_text(text)
    matches = []
    for cmd in commands:
        phrases = extract_phrases(cmd)
        for phrase in phrases:
            norm_phrase = normalize_text(phrase)
            if norm_phrase and norm_phrase in norm_text:
                matches.append((len(norm_phrase), cmd, phrase))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0], reverse=True)
    _, cmd, matched_phrase = matches[0]
    return cmd, matched_phrase


def get_commands_for_lang(all_commands, lang):
    lang = safe_lang(lang)
    return all_commands.get(lang, [])


def choose_manager_language(ui_lang):
    default_lang = safe_lang(ui_lang)
    choice = input(
        t(ui_lang, "manager_choose_lang", default=default_lang.upper())
    ).strip().lower()
    if choice in ("2", "en", "english"):
        return "en"
    if choice in ("1", "tr", "turkce", "türkçe", "turkish", ""):
        return "tr"
    return default_lang


def prompt_phrases(ui_lang, action, existing_phrases=None):
    prompt = t(ui_lang, "enter_phrases")
    if existing_phrases:
        prompt = f"{prompt} {t(ui_lang, 'press_enter_keep')}"
    elif action:
        prompt = f"{prompt} {t(ui_lang, 'press_enter_default', default=action)}"
    value = input(prompt).strip()
    if not value:
        if existing_phrases is not None:
            return existing_phrases
        if action:
            return [action]
        return None
    phrases = [p.strip() for p in value.split(",") if p.strip()]
    if not phrases:
        return None
    return phrases


ACTIONS_ALLOW_EMPTY_VALUE = {
    "type",
    "volume",
    "url_search",
    "youtube_search",
    "hotkey",
    "media",
    "brightness",
    "lock",
    "restart",
    "shutdown",
    "sleep",
    "screenshot",
    "mute",
    "desktop",
    "scroll",
    "list_dir",
    "find_files",
    "largest_files",
    "disk_usage",
    "open_dir",
    "gui_map",
    "routine_list",
}
ACTIONS = [
    "start",
    "open",
    "close",
    "focus",
    "browser_open",
    "browser_search",
    "youtube_search",
    "delete",
    "cmd",
    "powershell",
    "type",
    "hotkey",
    "volume",
    "media",
    "url_search",
    "youtube_search",
    "brightness",
    "lock",
    "restart",
    "shutdown",
    "sleep",
    "screenshot",
    "mute",
    "desktop",
    "scroll",
    "browser",
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
    "gui_map",
    "gui_click_index",
    "web_form_fill",
    "routine_create",
    "routine_run",
    "routine_list",
    "routine_delete",
]


def prompt_action(ui_lang, existing=None):
    prompt = t(ui_lang, "enter_action")
    if existing:
        prompt = f"{prompt} {t(ui_lang, 'press_enter_keep')}"
    value = input(prompt).strip().lower()
    if not value and existing:
        return existing
    mapping = {
        "1": "start",
        "2": "open",
        "3": "close",
        "4": "focus",
        "5": "browser_open",
        "6": "browser_search",
        "7": "youtube_search",
        "8": "delete",
        "9": "cmd",
        "10": "powershell",
        "11": "type",
        "12": "hotkey",
        "13": "volume",
        "14": "media",
        "15": "url_search",
        "16": "brightness",
        "17": "lock",
        "18": "restart",
        "19": "shutdown",
        "20": "sleep",
        "21": "screenshot",
        "22": "mute",
        "23": "desktop",
        "24": "scroll",
        "25": "browser",
        "26": "zoom",
        "27": "list_dir",
        "28": "open_dir",
        "29": "find_files",
        "30": "largest_files",
        "31": "disk_usage",
        "32": "copy",
        "33": "move",
        "34": "rename",
        "35": "mkdir",
        "36": "write_file",
        "37": "run_code",
        "38": "ocr",
        "39": "gui_map",
        "40": "gui_click_index",
        "41": "web_form_fill",
        "42": "routine_create",
        "43": "routine_run",
        "44": "routine_list",
        "45": "routine_delete",
        "start": "start",
        "open": "open",
        "close": "close",
        "focus": "focus",
        "browser_open": "browser_open",
        "browser_search": "browser_search",
        "youtube_search": "youtube_search",
        "delete": "delete",
        "cmd": "cmd",
        "powershell": "powershell",
        "type": "type",
        "hotkey": "hotkey",
        "volume": "volume",
        "media": "media",
        "url_search": "url_search",
        "youtube_search": "youtube_search",
        "brightness": "brightness",
        "lock": "lock",
        "restart": "restart",
        "shutdown": "shutdown",
        "sleep": "sleep",
        "screenshot": "screenshot",
        "mute": "mute",
        "desktop": "desktop",
        "scroll": "scroll",
        "browser": "browser",
        "zoom": "zoom",
        "list_dir": "list_dir",
        "find_files": "find_files",
        "largest_files": "largest_files",
        "disk_usage": "disk_usage",
        "open_dir": "open_dir",
        "copy": "copy",
        "move": "move",
        "rename": "rename",
        "mkdir": "mkdir",
        "write_file": "write_file",
        "run_code": "run_code",
        "ocr": "ocr",
        "gui_map": "gui_map",
        "gui_click_index": "gui_click_index",
        "web_form_fill": "web_form_fill",
        "routine_create": "routine_create",
        "routine_run": "routine_run",
        "routine_list": "routine_list",
        "routine_delete": "routine_delete",
    }
    return mapping.get(value) or (value if value in ACTIONS else None)


def prompt_value(ui_lang, existing=None):
    prompt = t(ui_lang, "enter_value")
    if existing:
        prompt = f"{prompt} {t(ui_lang, 'press_enter_keep')}"
    value = input(prompt).strip()
    if not value and existing is not None:
        return existing
    return value if value else None


def build_command(phrases, action, value):
    cmd = {"action": action, "value": value}
    if len(phrases) == 1:
        cmd["phrase"] = phrases[0]
    else:
        cmd["phrases"] = phrases
    return cmd


def manage_commands(ui_lang, all_commands):
    lang = choose_manager_language(ui_lang)
    if lang not in all_commands:
        all_commands[lang] = []

    while True:
        print("\n" + t(ui_lang, "manager_title"))
        print(t(ui_lang, "manager_lang", lang=lang.upper()))
        print(t(ui_lang, "manager_list"))
        print(t(ui_lang, "manager_add"))
        print(t(ui_lang, "manager_edit"))
        print(t(ui_lang, "manager_remove"))
        print(t(ui_lang, "manager_switch"))
        print(t(ui_lang, "manager_back"))
        choice = input(t(ui_lang, "menu_select")).strip()

        commands = all_commands.get(lang, [])

        if choice == "1":
            if not commands:
                print(t(ui_lang, "command_list_empty"))
                continue
            for i, cmd in enumerate(commands, start=1):
                print(format_command_line(i, cmd))
        elif choice == "2":
            action = prompt_action(ui_lang)
            if not action:
                print(t(ui_lang, "command_cancelled"))
                continue
            phrases = prompt_phrases(ui_lang, action)
            value = prompt_value(ui_lang)
            if not phrases or not action or (not value and action not in ACTIONS_ALLOW_EMPTY_VALUE):
                print(t(ui_lang, "command_cancelled"))
                continue
            commands.append(build_command(phrases, action, value))
            all_commands[lang] = commands
            save_commands(all_commands)
            print(t(ui_lang, "command_added"))
        elif choice == "3":
            if not commands:
                print(t(ui_lang, "command_list_empty"))
                continue
            for i, cmd in enumerate(commands, start=1):
                print(format_command_line(i, cmd))
            idx = input(t(ui_lang, "command_index_prompt")).strip()
            if not idx.isdigit() or not (1 <= int(idx) <= len(commands)):
                print(t(ui_lang, "command_invalid_index"))
                continue
            index = int(idx) - 1
            current = commands[index]
            action = prompt_action(ui_lang, current.get("action"))
            if not action:
                print(t(ui_lang, "command_cancelled"))
                continue
            existing_phrases = extract_phrases(current)
            phrases = prompt_phrases(ui_lang, action, existing_phrases)
            value = prompt_value(ui_lang, current.get("value"))
            if not phrases or not action or (not value and action not in ACTIONS_ALLOW_EMPTY_VALUE):
                print(t(ui_lang, "command_cancelled"))
                continue
            commands[index] = build_command(phrases, action, value)
            all_commands[lang] = commands
            save_commands(all_commands)
            print(t(ui_lang, "command_updated"))
        elif choice == "4":
            if not commands:
                print(t(ui_lang, "command_list_empty"))
                continue
            for i, cmd in enumerate(commands, start=1):
                print(format_command_line(i, cmd))
            idx = input(t(ui_lang, "command_index_prompt")).strip()
            if not idx.isdigit() or not (1 <= int(idx) <= len(commands)):
                print(t(ui_lang, "command_invalid_index"))
                continue
            commands.pop(int(idx) - 1)
            all_commands[lang] = commands
            save_commands(all_commands)
            print(t(ui_lang, "command_removed"))
        elif choice == "5":
            lang = choose_manager_language(ui_lang)
            if lang not in all_commands:
                all_commands[lang] = []
        elif choice == "6":
            break
        else:
            print(t(ui_lang, "invalid_choice"))
