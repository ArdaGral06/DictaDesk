import json

from config import SECRETS_JSON


def _default():
    return {"stt": {}, "tts": {}, "llm": {}, "vlm": {}}


def load_secrets():
    if SECRETS_JSON.exists():
        try:
            data = json.loads(SECRETS_JSON.read_text(encoding="utf-8"))
        except Exception:
            data = _default()
    else:
        data = _default()
        SECRETS_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if not isinstance(data, dict):
        data = _default()
    if "stt" not in data or not isinstance(data.get("stt"), dict):
        data["stt"] = {}
    if "tts" not in data or not isinstance(data.get("tts"), dict):
        data["tts"] = {}
    if "llm" not in data or not isinstance(data.get("llm"), dict):
        data["llm"] = {}
    if "vlm" not in data or not isinstance(data.get("vlm"), dict):
        data["vlm"] = {}
    return data


def save_secrets(data):
    SECRETS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_entry(kind: str, provider_id: str) -> dict:
    data = load_secrets()
    return data.get(kind, {}).get(provider_id, {})


def set_entry(kind: str, provider_id: str, values: dict):
    data = load_secrets()
    if kind not in data or not isinstance(data.get(kind), dict):
        data[kind] = {}
    existing = data[kind].get(provider_id, {})
    if not isinstance(existing, dict):
        existing = {}
    existing.update(values)
    data[kind][provider_id] = existing
    save_secrets(data)
