"""Reloadable API provider configuration (edit JSON files, no code changes needed)."""

from __future__ import annotations

import json
from pathlib import Path

from config import (
    BASE_DIR,
    LLM_PROVIDERS_JSON,
    PROVIDERS_JSON,
    TTS_PROVIDERS_JSON,
    VLM_PROVIDERS_JSON,
)

PROVIDER_FILES: dict[str, Path] = {
    "stt": PROVIDERS_JSON,
    "llm": LLM_PROVIDERS_JSON,
    "vlm": VLM_PROVIDERS_JSON,
    "tts": TTS_PROVIDERS_JSON,
}


def provider_file_for(kind: str) -> Path:
    key = str(kind or "").strip().lower()
    if key not in PROVIDER_FILES:
        raise KeyError(f"unknown provider kind: {kind}")
    return PROVIDER_FILES[key]


def load_provider_file(kind: str) -> list[dict]:
    path = provider_file_for(kind)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        providers = raw.get("providers", raw if isinstance(raw, list) else [])
        if isinstance(providers, list):
            return [p for p in providers if isinstance(p, dict)]
    except Exception:
        pass
    return []


def save_provider_file(kind: str, providers: list[dict]) -> None:
    path = provider_file_for(kind)
    payload = {"providers": providers}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def list_provider_summaries() -> list[dict]:
    rows: list[dict] = []
    for kind, path in PROVIDER_FILES.items():
        providers = load_provider_file(kind)
        labels = []
        for item in providers:
            pid = str(item.get("id") or "?")
            label = str(item.get("label") or pid)
            endpoint = str(item.get("endpoint") or "").strip()
            labels.append(f"{pid} ({label})" + (f" -> {endpoint[:48]}..." if len(endpoint) > 48 else (f" -> {endpoint}" if endpoint else "")))
        rows.append(
            {
                "kind": kind,
                "path": str(path.relative_to(BASE_DIR)) if path.is_relative_to(BASE_DIR) else str(path),
                "count": len(providers),
                "providers": labels,
            }
        )
    return rows


def run_provider_info_menu(ui_lang: str) -> None:
    from i18n import t

    while True:
        print("\n" + t(ui_lang, "provider_files_title"))
        for row in list_provider_summaries():
            print(t(ui_lang, "provider_files_kind", kind=row["kind"], path=row["path"], count=row["count"]))
            for line in row["providers"]:
                print(f"    - {line}")
        print(t(ui_lang, "provider_files_hint"))
        print(t(ui_lang, "provider_files_reload_note"))
        print(t(ui_lang, "provider_files_back"))
        choice = input(t(ui_lang, "menu_select")).strip()
        if choice == "1":
            print(t(ui_lang, "provider_files_edit_help"))
        elif choice == "2":
            break
