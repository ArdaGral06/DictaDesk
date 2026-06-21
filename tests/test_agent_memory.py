import agent_memory


def _use_tmp_memory(monkeypatch, tmp_path):
    mem_dir = tmp_path / "memory"
    mem_file = mem_dir / "long_term.json"
    monkeypatch.setattr(agent_memory, "MEMORY_DIR", mem_dir)
    monkeypatch.setattr(agent_memory, "MEMORY_FILE", mem_file)
    return mem_file


def test_new_categories_present():
    mem = agent_memory._empty_memory()
    assert "projects" in mem
    assert "wishes" in mem


def test_recursive_update_adds_timestamp():
    target = {}
    changed = agent_memory._recursive_update(target, {"name": "Ada"})
    assert changed
    assert target["name"]["value"] == "Ada"
    assert target["name"]["updated"]


def test_recursive_update_no_change_when_value_same():
    target = {}
    agent_memory._recursive_update(target, {"name": "Ada"})
    stamp = target["name"]["updated"]
    changed = agent_memory._recursive_update(target, {"name": "Ada"})
    assert not changed
    assert target["name"]["updated"] == stamp


def test_oldest_key_uses_timestamp():
    section = {
        "a": {"value": "1", "updated": "2026-01-01T00:00:00"},
        "b": {"value": "2", "updated": "2025-01-01T00:00:00"},
    }
    assert agent_memory._oldest_key(section) == "b"


def test_entry_without_timestamp_is_oldest():
    section = {
        "new": {"value": "1", "updated": "2026-01-01T00:00:00"},
        "legacy": {"value": "2"},
    }
    assert agent_memory._oldest_key(section) == "legacy"


def test_trim_entries_per_category(monkeypatch):
    monkeypatch.setattr(agent_memory, "MEMORY_MAX_ENTRIES_PER_CATEGORY", 2)
    memory = {
        "notes": {
            "n1": {"value": "1", "updated": "2026-01-01T00:00:00"},
            "n2": {"value": "2", "updated": "2026-01-02T00:00:00"},
            "n3": {"value": "3", "updated": "2026-01-03T00:00:00"},
        }
    }
    agent_memory._trim_entries_per_category(memory)
    assert set(memory["notes"]) == {"n2", "n3"}


def test_update_memory_roundtrip(monkeypatch, tmp_path):
    _use_tmp_memory(monkeypatch, tmp_path)
    agent_memory.update_memory({"preferences": {"tema": "koyu"}})
    loaded = agent_memory.load_memory()
    assert loaded["preferences"]["tema"]["value"] == "koyu"
    assert loaded["preferences"]["tema"]["updated"]
