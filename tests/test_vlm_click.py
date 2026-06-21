import action_executor


class _FakeVLM:
    def __init__(self, coords, enabled=True):
        self._coords = coords
        self.enabled = enabled
        self.llm = object()

    def locate_click(self, target, image_path, ui_lang=None, goal=None):
        x, y = self._coords
        if x is None:
            return None, None, "not_found", ""
        return x, y, "ok", "raw"


def _patch_io(monkeypatch):
    clicks: list[tuple[int, int]] = []
    monkeypatch.setattr(action_executor, "take_screenshot", lambda _v: "fake.png")

    def fake_gui_click(x, y, clicks=1):
        clicks_store.append((x, y))

    clicks_store = clicks
    monkeypatch.setattr(action_executor, "gui_click", fake_gui_click)
    return clicks


def test_vlm_click_success(monkeypatch):
    clicks = _patch_io(monkeypatch)
    vlm = _FakeVLM((120, 340))
    ok, reason = action_executor._vlm_click_fallback(vlm, "Save", "en")
    assert ok
    assert reason is None
    assert clicks == [(120, 340)]


def test_vlm_click_disabled(monkeypatch):
    _patch_io(monkeypatch)
    vlm = _FakeVLM((10, 10), enabled=False)
    ok, reason = action_executor._vlm_click_fallback(vlm, "Save", "en")
    assert not ok
    assert reason == "no_text"


def test_vlm_click_not_found(monkeypatch):
    _patch_io(monkeypatch)
    vlm = _FakeVLM((None, None))
    ok, reason = action_executor._vlm_click_fallback(vlm, "Save", "en")
    assert not ok
    assert reason == "no_text"


def test_vlm_click_none_vlm(monkeypatch):
    _patch_io(monkeypatch)
    ok, reason = action_executor._vlm_click_fallback(None, "Save", "en")
    assert not ok
    assert reason == "no_text"
