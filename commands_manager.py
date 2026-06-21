import json

from actions_manifest import load_action_manifest
from config import COMMANDS_JSON
from i18n import safe_lang, t
from ui_terminal import print_menu, print_option, print_section


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


ACTION_CATEGORIES = [
    ("apps", ["start", "open", "close", "focus"]),
    (
        "browser",
        ["browser_open", "browser_search", "youtube_search", "url_search", "browser"],
    ),
    (
        "system",
        [
            "volume",
            "brightness",
            "mute",
            "media",
            "desktop",
            "scroll",
            "zoom",
            "screenshot",
            "lock",
            "restart",
            "shutdown",
            "sleep",
        ],
    ),
    ("input", ["type", "hotkey", "cmd", "powershell"]),
    (
        "files",
        [
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
            "delete",
            "run_code",
        ],
    ),
    ("screen", ["ocr", "gui_map", "gui_click_index", "web_form_fill"]),
    (
        "routines",
        ["routine_create", "routine_run", "routine_list", "routine_delete"],
    ),
]

COMPLEX_VALUE_ACTIONS = {
    "write_file",
    "routine_create",
    "run_code",
    "find_files",
    "largest_files",
    "disk_usage",
    "desktop",
    "copy",
    "move",
    "rename",
    "browser_open",
    "browser_search",
    "browser",
}


def _manifest_lookup():
    return {
        str(item.get("name", "")).strip().lower(): item for item in load_action_manifest()
    }


def _action_description(ui_lang, action_name: str) -> str:
    meta = _manifest_lookup().get(action_name, {})
    if ui_lang == "en":
        return str(meta.get("description_en") or meta.get("description_tr") or action_name)
    return str(meta.get("description_tr") or meta.get("description_en") or action_name)


def _actions_in_category(category_id: str) -> list[str]:
    allowed = set(ACTIONS)
    for cat_id, names in ACTION_CATEGORIES:
        if cat_id == category_id:
            return [name for name in names if name in allowed]
    return []


def _resolve_action_choice(raw: str, options: list[str]) -> str | None:
    value = raw.strip().lower()
    if not value:
        return None
    if value.isdigit():
        idx = int(value) - 1
        if 0 <= idx < len(options):
            return options[idx]
    if value in options:
        return value
    return value if value in ACTIONS else None


def prompt_action(ui_lang, existing=None):
    if existing:
        keep = input(
            t(ui_lang, "action_keep_current", current=existing)
            + " "
            + t(ui_lang, "press_enter_keep")
        ).strip().lower()
        if not keep:
            return existing

    print_menu(
        ui_lang,
        title_key="action_cat_title",
        subtitle_key="action_cat_subtitle",
        items=[
            {
                "num": str(i),
                "title_key": f"action_cat_{cat_id}_title",
                "desc_key": f"action_cat_{cat_id}_desc",
            }
            for i, (cat_id, _) in enumerate(ACTION_CATEGORIES, start=1)
        ],
    )
    cat_choice = input(t(ui_lang, "menu_select")).strip().lower()
    category_id = None
    if cat_choice.isdigit():
        idx = int(cat_choice) - 1
        if 0 <= idx < len(ACTION_CATEGORIES):
            category_id = ACTION_CATEGORIES[idx][0]
    else:
        for cat_id, _ in ACTION_CATEGORIES:
            if cat_id == cat_choice:
                category_id = cat_id
                break
    if not category_id:
        return _resolve_action_choice(cat_choice, [])

    actions = _actions_in_category(category_id)
    if not actions:
        print(t(ui_lang, "invalid_choice"))
        return None

    print_section(t(ui_lang, f"action_cat_{category_id}_title"))
    for i, action_name in enumerate(actions, start=1):
        print_option(str(i), action_name, _action_description(ui_lang, action_name))
    print_option("0", t(ui_lang, "action_cat_back_title"), t(ui_lang, "action_cat_back_desc"))

    pick = input(t(ui_lang, "action_pick_prompt")).strip().lower()
    if pick in ("0", "back", "geri"):
        return prompt_action(ui_lang, existing)
    return _resolve_action_choice(pick, actions)


def prompt_value(ui_lang, existing=None, action=None):
    if action in COMPLEX_VALUE_ACTIONS:
        prompt = t(ui_lang, "enter_value")
    elif action:
        meta = _manifest_lookup().get(action, {})
        params = str(meta.get("parameters") or "-").strip()
        examples = meta.get("examples") or []
        example_text = ", ".join(str(x) for x in examples[:2]) if examples else "-"
        prompt = t(
            ui_lang,
            "action_value_short",
            action=action,
            params=params,
            examples=example_text,
        )
    else:
        prompt = t(ui_lang, "enter_value")
    if existing is not None:
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
        print_menu(
            ui_lang,
            title_key="manager_title",
            subtitle_key="manager_subtitle",
            items=[
                {"num": "1", "title_key": "manager_list_title", "desc_key": "manager_list_desc"},
                {"num": "2", "title_key": "manager_add_title", "desc_key": "manager_add_desc"},
                {"num": "3", "title_key": "manager_edit_title", "desc_key": "manager_edit_desc"},
                {"num": "4", "title_key": "manager_remove_title", "desc_key": "manager_remove_desc"},
                {"num": "5", "title_key": "manager_switch_title", "desc_key": "manager_switch_desc"},
                {"num": "6", "title_key": "manager_back_title", "desc_key": "manager_back_desc"},
            ],
        )
        print(t(ui_lang, "manager_lang", lang=lang.upper()))
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
            value = prompt_value(ui_lang, action=action)
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
            value = prompt_value(ui_lang, current.get("value"), action=action)
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
