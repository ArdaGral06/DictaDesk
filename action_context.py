from threading import RLock

_lock = RLock()
_outcomes: dict[str, dict] = {}


def record_action_outcome(
    action: str,
    ok: bool,
    reason: str = "",
    meta: dict | None = None,
) -> None:
    key = str(action or "").strip().lower()
    if not key:
        return
    with _lock:
        _outcomes[key] = {
            "ok": bool(ok),
            "reason": str(reason or ""),
            "meta": dict(meta) if isinstance(meta, dict) else {},
        }


def get_action_outcome(action: str) -> dict | None:
    key = str(action or "").strip().lower()
    with _lock:
        item = _outcomes.get(key)
        return dict(item) if isinstance(item, dict) else None


def clear_action_outcome(action: str) -> None:
    key = str(action or "").strip().lower()
    with _lock:
        _outcomes.pop(key, None)
