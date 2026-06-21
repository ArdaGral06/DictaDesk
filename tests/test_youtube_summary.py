import youtube_summary
from youtube_summary import extract_video_id, summarize_youtube


class _FakeInner:
    def generate(self, user, system_prompt=None, raw_user=False, max_tokens=None):
        return "OZET METNI"


class _FakeLLM:
    enabled = True
    llm = _FakeInner()


def test_extract_video_id_from_watch_url():
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_from_short_url():
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_from_bare_id():
    assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_extract_video_id_from_query_is_none():
    assert extract_video_id("python tutorial") is None


def test_summarize_happy_path(monkeypatch):
    monkeypatch.setattr(youtube_summary, "_YTApi", object())
    monkeypatch.setattr(youtube_summary, "get_transcript", lambda vid: "lorem ipsum")
    monkeypatch.setattr(youtube_summary, "_save_summary", lambda s, u: None)
    ok, text = summarize_youtube("https://youtu.be/dQw4w9WgXcQ", llm=_FakeLLM(), ui_lang="tr")
    assert ok
    assert text == "OZET METNI"


def test_summarize_no_api(monkeypatch):
    monkeypatch.setattr(youtube_summary, "_YTApi", None)
    ok, reason = summarize_youtube("dQw4w9WgXcQ", llm=_FakeLLM())
    assert not ok
    assert reason == "youtube_no_api"


def test_summarize_no_transcript(monkeypatch):
    monkeypatch.setattr(youtube_summary, "_YTApi", object())
    monkeypatch.setattr(youtube_summary, "get_transcript", lambda vid: None)
    ok, reason = summarize_youtube("dQw4w9WgXcQ", llm=_FakeLLM())
    assert not ok
    assert reason == "youtube_no_transcript"


def test_summarize_no_video(monkeypatch):
    monkeypatch.setattr(youtube_summary, "_YTApi", object())
    monkeypatch.setattr(youtube_summary, "_scrape_first_video_id", lambda q: None)
    ok, reason = summarize_youtube("some search query", llm=_FakeLLM())
    assert not ok
    assert reason == "youtube_no_video"
