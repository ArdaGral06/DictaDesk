import time
from difflib import SequenceMatcher

from utils import fold_text


def _import_uia():
    try:
        import uiautomation as auto

        return auto
    except Exception:
        return None


def is_available() -> bool:
    return _import_uia() is not None


def _rect_to_tuple(rect) -> tuple[int, int, int, int] | None:
    if rect is None:
        return None
    for attrs in (
        ("left", "top", "right", "bottom"),
        ("Left", "Top", "Right", "Bottom"),
    ):
        try:
            return tuple(int(getattr(rect, name)) for name in attrs)
        except Exception:
            pass
    try:
        vals = list(rect)
        if len(vals) >= 4:
            return tuple(int(v) for v in vals[:4])
    except Exception:
        return None
    return None


def _element_name(ctrl) -> str:
    for attr in ("Name", "name"):
        try:
            value = getattr(ctrl, attr)
            if value:
                return str(value)
        except Exception:
            pass
    return ""


def _control_type(ctrl) -> str:
    for attr in ("ControlTypeName", "LocalizedControlType", "ClassName"):
        try:
            value = getattr(ctrl, attr)
            if value:
                return str(value)
        except Exception:
            pass
    return ""


def _automation_id(ctrl) -> str:
    for attr in ("AutomationId", "automation_id"):
        try:
            value = getattr(ctrl, attr)
            if value:
                return str(value)
        except Exception:
            pass
    return ""


def _enabled(ctrl) -> bool | None:
    for attr in ("IsEnabled", "Enabled"):
        try:
            return bool(getattr(ctrl, attr))
        except Exception:
            pass
    return None


def _focusable(ctrl) -> bool | None:
    for attr in ("IsKeyboardFocusable", "IsKeyboardFocusableProperty"):
        try:
            return bool(getattr(ctrl, attr))
        except Exception:
            pass
    return None


def _iter_children(ctrl):
    try:
        return list(ctrl.GetChildren())
    except Exception:
        return []


def _score(ctrl, target: str) -> float:
    target_fold = fold_text(target or "")
    if not target_fold:
        return 0.0
    fields = [
        _element_name(ctrl),
        _automation_id(ctrl),
        _control_type(ctrl),
    ]
    best = 0.0
    for field in fields:
        folded = fold_text(field)
        if not folded:
            continue
        if folded == target_fold:
            best = max(best, 1.0)
        elif target_fold in folded or folded in target_fold:
            best = max(best, 0.92)
        else:
            best = max(best, SequenceMatcher(a=folded, b=target_fold).ratio())
    return best


def _walk(root, max_depth: int = 4, max_items: int = 250):
    if root is None:
        return []
    queue = [(root, 0)]
    out = []
    while queue and len(out) < max_items:
        ctrl, depth = queue.pop(0)
        out.append((ctrl, depth))
        if depth >= max_depth:
            continue
        for child in _iter_children(ctrl):
            queue.append((child, depth + 1))
    return out


def foreground_root():
    auto = _import_uia()
    if auto is None:
        return None
    try:
        return auto.GetForegroundControl()
    except Exception:
        return None


def summarize_foreground(max_depth: int = 3, max_items: int = 80) -> dict:
    root = foreground_root()
    if root is None:
        return {"available": is_available(), "items": []}
    items = []
    for ctrl, depth in _walk(root, max_depth=max_depth, max_items=max_items):
        name = _element_name(ctrl).strip()
        ctype = _control_type(ctrl).strip()
        rect = _rect_to_tuple(getattr(ctrl, "BoundingRectangle", None))
        if not name and not ctype:
            continue
        item = {
            "name": name,
            "control_type": ctype,
            "automation_id": _automation_id(ctrl),
            "depth": depth,
            "rect": rect,
            "enabled": _enabled(ctrl),
            "focusable": _focusable(ctrl),
        }
        items.append(item)
    return {"available": True, "items": items}


def _region(rect: tuple[int, int, int, int], root_rect: tuple[int, int, int, int] | None) -> str:
    if root_rect:
        left, top, right, bottom = root_rect
    else:
        left, top, right, bottom = 0, 0, 1920, 1080
    w = max(1, right - left)
    h = max(1, bottom - top)
    cx = ((rect[0] + rect[2]) / 2 - left) / w
    cy = ((rect[1] + rect[3]) / 2 - top) / h
    if cy < 0.10:
        return "top_bar"
    if cy > 0.90:
        return "bottom_bar"
    if cx < 0.07:
        return "far_left_nav"
    if cx < 0.23:
        return "left_sidebar"
    if cx < 0.43:
        return "left_list"
    if cx > 0.74:
        return "right_panel"
    return "center_content"


def _nearby_text(items: list[tuple[object, tuple[int, int, int, int], float]], rect, limit: int = 8) -> str:
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    scored = []
    for ctrl, other, _score_value in items:
        name = _element_name(ctrl).strip()
        if not name:
            continue
        ocx = (other[0] + other[2]) / 2
        ocy = (other[1] + other[3]) / 2
        dx = abs(ocx - cx)
        dy = abs(ocy - cy)
        if dx > 420 or dy > 100:
            continue
        scored.append((dx + dy * 2, name))
    scored.sort(key=lambda item: item[0])
    return " ".join(name for _dist, name in scored[:limit])


def _context_score(ctrl, rect, base_score: float, root_rect, all_items, root_name: str) -> float:
    score = base_score * 100.0
    region = _region(rect, root_rect)
    nearby = fold_text(_nearby_text(all_items, rect))
    root_folded = fold_text(root_name)
    is_discord = "discord" in root_folded
    ctype = fold_text(_control_type(ctrl))

    if region == "center_content":
        score += 18
    elif region == "left_list":
        score += 16
    elif region == "left_sidebar":
        score += 8
    elif region == "right_panel":
        score -= 6
    elif region in {"top_bar", "bottom_bar", "far_left_nav"}:
        score -= 6

    if any(term in ctype for term in ("button", "list", "edit", "text")):
        score += 8

    if is_discord:
        if region in {"left_list", "center_content"}:
            score += 18
        elif region == "right_panel":
            score -= 30
        if any(
            term in nearby
            for term in (
                "message",
                "mesaj",
                "direct",
                "direkt",
                "arkadas",
                "friend",
                "sohbet",
            )
        ):
            score += 18
        if any(
            term in nearby
            for term in (
                "simdi aktif",
                "active now",
                "yayinda",
                "ses kanalinda",
                "stream",
            )
        ):
            score -= 24
    return score


def find_text(target: str, max_depth: int = 5, min_score: float = 0.76):
    root = foreground_root()
    if root is None:
        return None
    root_rect = _rect_to_tuple(getattr(root, "BoundingRectangle", None))
    root_name = _element_name(root)
    all_items = []
    candidates = []
    for ctrl, _depth in _walk(root, max_depth=max_depth, max_items=500):
        rect = _rect_to_tuple(getattr(ctrl, "BoundingRectangle", None))
        if not rect:
            continue
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            continue
        score = _score(ctrl, target)
        all_items.append((ctrl, rect, score))
        if score >= min_score:
            candidates.append((ctrl, rect, score))
    if candidates:
        best = max(
            candidates,
            key=lambda item: _context_score(
                item[0], item[1], item[2], root_rect, all_items, root_name
            ),
        )
        return best[0]
    return None


def click_text(target: str) -> tuple[int, int] | None:
    ctrl = find_text(target)
    if ctrl is None:
        return None
    rect = _rect_to_tuple(getattr(ctrl, "BoundingRectangle", None))
    if not rect:
        return None
    left, top, right, bottom = rect
    x = int((left + right) / 2)
    y = int((top + bottom) / 2)
    try:
        ctrl.SetFocus()
    except Exception:
        pass
    try:
        ctrl.Click()
    except Exception:
        import pyautogui

        pyautogui.click(x=x, y=y)
    return x, y


def wait_text(target: str, timeout_sec: float = 6.0) -> bool:
    end = time.time() + max(0.1, float(timeout_sec))
    while time.time() < end:
        if find_text(target):
            return True
        time.sleep(0.25)
    return False


def fill_native_form(data: dict, profile: dict | None = None) -> dict:
    """Fill visible form fields in the foreground app using UI Automation."""
    from form_automation import (
        fields_for_mode,
        infer_field,
        merge_form_data,
        submit_patterns,
        value_for,
    )

    auto = _import_uia()
    if auto is None:
        return {"ok": False, "reason": "uia_missing", "fields": []}

    merged, mode, submit = merge_form_data(data or {}, profile or {})
    allow_sensitive = bool((data or {}).get("email") or (data or {}).get("password"))
    root = foreground_root()
    if root is None:
        return {"ok": False, "reason": "no_foreground_window", "fields": []}

    filled: set[str] = set()
    target_fields = set(fields_for_mode(mode if mode != "auto" else "fill"))

    for ctrl, _depth in _walk(root, max_depth=8, max_items=400):
        ctype = fold_text(_control_type(ctrl))
        if not any(token in ctype for token in ("edit", "document", "text")):
            continue
        blob = " ".join(filter(None, [_element_name(ctrl), _automation_id(ctrl), ctype]))
        field = infer_field(blob)
        if not field or field in filled:
            continue
        if mode == "login" and field not in {"email", "password"}:
            continue
        if target_fields and field not in target_fields and mode != "login":
            continue
        val = value_for(field, merged, allow_sensitive=allow_sensitive or field in merged)
        if not val:
            continue
        try:
            ctrl.SetFocus()
        except Exception:
            pass
        try:
            pattern = ctrl.GetValuePattern()
            if pattern and pattern.SetValue(val):
                filled.add(field)
                continue
        except Exception:
            pass
        try:
            ctrl.Click()
        except Exception:
            pass
        try:
            auto.SendKeys("{Ctrl}a{Delete}")
            auto.SendKeys(val, interval=0.02)
            filled.add(field)
        except Exception:
            pass

    submitted = False
    if submit:
        from form_automation import submit_text_literals

        for label in submit_text_literals(mode):
            if click_text(label):
                submitted = True
                break
        if not submitted:
            try:
                auto.SendKeys("{Enter}")
                submitted = True
            except Exception:
                pass

    if not filled:
        return {
            "ok": False,
            "reason": "no_fields_filled",
            "fields": [],
            "submitted": submitted,
            "mode": mode,
            "native": True,
        }
    return {
        "ok": True,
        "reason": "ok",
        "fields": sorted(filled),
        "submitted": submitted,
        "mode": mode,
        "native": True,
    }
