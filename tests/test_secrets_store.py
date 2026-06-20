import json

import secrets_store


def test_set_entry_without_keyring(monkeypatch, tmp_path):
    path = tmp_path / "secrets.json"
    monkeypatch.setattr(secrets_store, "SECRETS_JSON", path)
    monkeypatch.setattr(secrets_store, "_KEYRING_OK", False)
    monkeypatch.setattr(secrets_store, "_keyring_module", lambda: None)
    secrets_store.set_entry("llm", "groq", {"api_key": "abc123", "model": "test"})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["llm"]["groq"]["api_key"] == "abc123"
    entry = secrets_store.get_entry("llm", "groq")
    assert entry["api_key"] == "abc123"
