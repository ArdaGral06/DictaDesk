import json

from app_logging import get_logger
from config import SECRETS_JSON

logger = get_logger()
SERVICE_NAME = "DictaDesk"
_KEYRING_OK = None


def _keyring_module():
    global _KEYRING_OK
    if _KEYRING_OK is False:
        return None
    try:
        import keyring

        _KEYRING_OK = True
        return keyring
    except Exception:
        _KEYRING_OK = False
        return None


def _default():
    return {"stt": {}, "tts": {}, "llm": {}, "vlm": {}}


def _keyring_key(kind: str, provider_id: str) -> str:
    return f"{kind}:{provider_id}"


def _load_json_file() -> dict:
    if SECRETS_JSON.exists():
        try:
            data = json.loads(SECRETS_JSON.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.warning("secrets.json parse failed: %s", exc)
    return _default()


def _normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        data = _default()
    for kind in ("stt", "tts", "llm", "vlm"):
        if kind not in data or not isinstance(data.get(kind), dict):
            data[kind] = {}
    return data


def _read_keyring_entry(keyring, kind: str, provider_id: str) -> dict:
    stored = keyring.get_password(SERVICE_NAME, _keyring_key(kind, provider_id))
    if not stored:
        return {}
    try:
        parsed = json.loads(stored)
        return parsed if isinstance(parsed, dict) else {"api_key": stored}
    except Exception:
        return {"api_key": stored}


def load_secrets():
    data = _normalize(_load_json_file())
    if not SECRETS_JSON.exists():
        SECRETS_JSON.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return data


def save_secrets(data):
    data = _normalize(data if isinstance(data, dict) else _default())
    SECRETS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_entry(kind: str, provider_id: str) -> dict:
    data = load_secrets()
    entry = data.get(kind, {}).get(provider_id, {})
    if not isinstance(entry, dict):
        entry = {}
    keyring = _keyring_module()
    if keyring:
        secured = _read_keyring_entry(keyring, kind, provider_id)
        if secured:
            return {**entry, **secured}
    return entry


def set_entry(kind: str, provider_id: str, values: dict):
    data = load_secrets()
    if kind not in data or not isinstance(data.get(kind), dict):
        data[kind] = {}
    existing = data[kind].get(provider_id, {})
    if not isinstance(existing, dict):
        existing = {}
    merged = {**existing, **(values or {})}
    api_key = str(merged.get("api_key") or "").strip()
    keyring = _keyring_module()
    if keyring and api_key:
        payload = dict(merged)
        keyring.set_password(
            SERVICE_NAME,
            _keyring_key(kind, provider_id),
            json.dumps(payload, ensure_ascii=False),
        )
        disk_entry = {k: v for k, v in merged.items() if k != "api_key"}
        disk_entry["stored_in_keyring"] = True
        data[kind][provider_id] = disk_entry
    else:
        data[kind][provider_id] = merged
    save_secrets(data)
