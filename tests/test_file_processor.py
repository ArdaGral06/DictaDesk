from file_processor import parse_payload, process_file


class _FakeInner:
    def __init__(self):
        self.last_user = None

    def generate(self, user, system_prompt=None, raw_user=False, max_tokens=None):
        self.last_user = user
        return "OZET"


class _FakeLLM:
    def __init__(self):
        self.enabled = True
        self.llm = _FakeInner()


def test_parse_payload_with_action():
    path, action = parse_payload("C:/tmp/a.txt -> summarize")
    assert path == "C:/tmp/a.txt"
    assert action == "summarize"


def test_parse_payload_unknown_action_ignored():
    path, action = parse_payload("C:/tmp/a.txt -> wat")
    assert path == "C:/tmp/a.txt"
    assert action is None


def test_parse_payload_plain_path():
    path, action = parse_payload("C:/tmp/a.txt")
    assert path == "C:/tmp/a.txt"
    assert action is None


def test_process_missing_path():
    ok, reason = process_file("", llm=_FakeLLM())
    assert not ok
    assert reason == "file_path_missing"


def test_process_file_not_found(tmp_path):
    ok, reason = process_file(str(tmp_path / "nope.txt"), llm=_FakeLLM())
    assert not ok
    assert reason == "file_not_found"


def test_process_info_action(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hello world", encoding="utf-8")
    ok, info = process_file(f"{f} -> info", llm=_FakeLLM())
    assert ok
    assert "notes.txt" in info
    assert ".txt" in info


def test_process_extract_text(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("merhaba dunya", encoding="utf-8")
    ok, text = process_file(f"{f} -> extract_text", llm=_FakeLLM())
    assert ok
    assert text == "merhaba dunya"


def test_process_summarize_uses_llm(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("uzun bir metin", encoding="utf-8")
    ok, text = process_file(f"{f} -> summarize", llm=_FakeLLM(), ui_lang="tr")
    assert ok
    assert text == "OZET"


def test_process_summarize_no_llm(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("uzun bir metin", encoding="utf-8")
    ok, reason = process_file(f"{f} -> summarize", llm=None)
    assert not ok
    assert reason == "file_no_llm"


def test_process_unsupported_extension(tmp_path):
    f = tmp_path / "weird.xyz"
    f.write_text("data", encoding="utf-8")
    ok, reason = process_file(str(f), llm=_FakeLLM())
    assert not ok
    assert reason == "file_unsupported"
