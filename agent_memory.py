import json
from datetime import datetime
from pathlib import Path
from threading import RLock

from config import MEMORY_DIR, MEMORY_FILE
from i18n import t

_lock = RLock()
MAX_VALUE_LENGTH = 300
MEMORY_MAX_CHARS = 12000
# LRU cap: keep at most this many entries per category (oldest dropped first).
MEMORY_MAX_ENTRIES_PER_CATEGORY = 40


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty_memory() -> dict:
    return {
        "identity": {},
        "preferences": {},
        "relationships": {},
        "projects": {},
        "wishes": {},
        "notes": {},
        "routines": {},
        "aliases": {},
    }


def _ensure_schema(memory: dict) -> dict:
    if not isinstance(memory, dict):
        return _empty_memory()
    changed = False
    defaults = _empty_memory()
    for key, value in defaults.items():
        if key not in memory or not isinstance(memory.get(key), dict):
            memory[key] = value
            changed = True
    if changed:
        save_memory(memory)
    return memory


def ensure_memory():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text(json.dumps(_empty_memory(), indent=2), encoding="utf-8")


def load_memory() -> dict:
    ensure_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return _empty_memory()
            return _ensure_schema(data)
        except Exception:
            return _empty_memory()


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    ensure_memory()
    with _lock:
        memory = _trim_entries_per_category(memory)
        memory = _trim_to_limit(memory)
        MEMORY_FILE.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _memory_size(memory: dict) -> int:
    return len(json.dumps(memory, ensure_ascii=False))


def _entry_timestamp(entry) -> str:
    # Entries without an 'updated' stamp are treated as oldest (sort first).
    if isinstance(entry, dict):
        return str(entry.get("updated") or "")
    return ""


def _oldest_key(section: dict) -> str | None:
    if not section:
        return None
    return min(section, key=lambda k: _entry_timestamp(section.get(k)))


def _trim_entries_per_category(memory: dict) -> dict:
    """LRU cap: drop oldest entries (by 'updated') beyond the per-category limit."""
    if not isinstance(memory, dict):
        return memory
    for category, section in memory.items():
        if not isinstance(section, dict):
            continue
        while len(section) > MEMORY_MAX_ENTRIES_PER_CATEGORY:
            oldest = _oldest_key(section)
            if oldest is None:
                break
            section.pop(oldest, None)
    return memory


def _trim_to_limit(memory: dict) -> dict:
    if not isinstance(memory, dict) or _memory_size(memory) <= MEMORY_MAX_CHARS:
        return memory
    # Keep identity/preferences as long as possible; trim lower-value entries first.
    # Within each category, drop the oldest (least-recently-updated) entry first (LRU).
    trim_order = (
        "notes",
        "wishes",
        "projects",
        "relationships",
        "aliases",
        "routines",
        "preferences",
        "identity",
    )
    for category in trim_order:
        section = memory.get(category)
        if not isinstance(section, dict):
            continue
        while section and _memory_size(memory) > MEMORY_MAX_CHARS:
            oldest = _oldest_key(section)
            if oldest is None:
                break
            section.pop(oldest, None)
        if _memory_size(memory) <= MEMORY_MAX_CHARS:
            break
    return memory


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            if isinstance(value, dict) and "value" in value:
                new_val = _truncate_value(str(value["value"]))
            else:
                new_val = _truncate_value(str(value))
            existing = target.get(key)
            existing_val = existing.get("value") if isinstance(existing, dict) else existing
            if existing_val != new_val:
                # Bump 'updated' only when the value actually changes (LRU = last write).
                target[key] = {"value": new_val, "updated": _now_iso()}
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
    return memory


def format_memory_for_prompt(memory: dict | None = None) -> str:
    if memory is None:
        memory = load_memory()
    if not memory:
        return ""
    lines = []

    identity = memory.get("identity", {})
    for key in ("name", "age", "birthday", "city"):
        val = identity.get(key, {}).get("value") if isinstance(identity, dict) else None
        if val:
            lines.append(f"{key.title()}: {val}")

    prefs = memory.get("preferences", {})
    if isinstance(prefs, dict):
        for i, (key, entry) in enumerate(prefs.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if isinstance(rels, dict):
        for i, (key, entry) in enumerate(rels.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if isinstance(projects, dict):
        for i, (key, entry) in enumerate(projects.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"Project {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if isinstance(wishes, dict):
        for i, (key, entry) in enumerate(wishes.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"Wish {key.replace('_', ' ').title()}: {val}")

    routines = memory.get("routines", {})
    if isinstance(routines, dict):
        for i, (key, entry) in enumerate(routines.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"Routine {key.replace('_', ' ').title()}: {val}")

    aliases = memory.get("aliases", {})
    if isinstance(aliases, dict):
        for i, (key, entry) in enumerate(aliases.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"Alias {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if isinstance(notes, dict):
        for i, (key, entry) in enumerate(notes.items()):
            if i >= 5:
                break
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{key.replace('_', ' ').title()}: {val}")

    if not lines:
        return ""

    result = "[USER MEMORY]\n" + "\n".join(f"- {line}" for line in lines)
    if len(result) > 800:
        result = result[:797] + "…"
    return result + "\n"


def run_memory_menu(ui_lang: str):
    while True:
        memory = load_memory()
        summary = format_memory_for_prompt(memory)
        print("\n" + t(ui_lang, "memory_title"))
        if summary:
            print(t(ui_lang, "memory_summary"))
            print(summary.strip())
        else:
            print(t(ui_lang, "memory_empty"))
        print(t(ui_lang, "memory_path", path=MEMORY_FILE))
        print(t(ui_lang, "memory_set_pref"))
        print(t(ui_lang, "memory_set_note"))
        print(t(ui_lang, "memory_set_relation"))
        print(t(ui_lang, "memory_set_identity"))
        print(t(ui_lang, "memory_set_routine"))
        print(t(ui_lang, "memory_set_alias"))
        print(t(ui_lang, "memory_back"))
        choice = input(t(ui_lang, "menu_select")).strip()
        if choice == "1":
            key = input(t(ui_lang, "memory_key_prompt")).strip()
            if not key:
                continue
            val = input(t(ui_lang, "memory_value_prompt")).strip()
            if not val:
                continue
            update_memory({"preferences": {key: val}})
            print(t(ui_lang, "memory_saved"))
        elif choice == "2":
            key = input(t(ui_lang, "memory_key_prompt")).strip()
            if not key:
                continue
            val = input(t(ui_lang, "memory_value_prompt")).strip()
            if not val:
                continue
            update_memory({"notes": {key: val}})
            print(t(ui_lang, "memory_saved"))
        elif choice == "3":
            key = input(t(ui_lang, "memory_key_prompt")).strip()
            if not key:
                continue
            val = input(t(ui_lang, "memory_value_prompt")).strip()
            if not val:
                continue
            update_memory({"relationships": {key: val}})
            print(t(ui_lang, "memory_saved"))
        elif choice == "4":
            key = input(t(ui_lang, "memory_key_prompt")).strip()
            if not key:
                continue
            val = input(t(ui_lang, "memory_value_prompt")).strip()
            if not val:
                continue
            update_memory({"identity": {key: val}})
            print(t(ui_lang, "memory_saved"))
        elif choice == "5":
            key = input(t(ui_lang, "memory_key_prompt")).strip()
            if not key:
                continue
            val = input(t(ui_lang, "memory_value_prompt")).strip()
            if not val:
                continue
            update_memory({"routines": {key: val}})
            print(t(ui_lang, "memory_saved"))
        elif choice == "6":
            key = input(t(ui_lang, "memory_key_prompt")).strip()
            if not key:
                continue
            val = input(t(ui_lang, "memory_value_prompt")).strip()
            if not val:
                continue
            update_memory({"aliases": {key: val}})
            print(t(ui_lang, "memory_saved"))
        elif choice == "7":
            break
