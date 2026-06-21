import threading

from uia_automation import _ensure_uia_com, summarize_foreground


def test_uia_com_init_in_worker_thread():
    result = {}

    def worker():
        result["ready"] = _ensure_uia_com()
        summary = summarize_foreground(max_depth=1, max_items=3)
        result["available"] = summary.get("available")

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert result.get("ready") is True
    assert result.get("available") is True
