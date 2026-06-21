import atexit
import threading
import time
import re
from threading import Event
from urllib.parse import quote_plus

from config import PLAYWRIGHT_HEADLESS, WEB_SEARCH_URL_PLAYWRIGHT, WEB_USER_AGENT
from task_cancel import check_cancelled, sleep_cancellable
from form_automation import (
    FIELD_LABELS,
    fields_for_mode,
    infer_field,
    merge_form_data,
    submit_patterns,
    value_for,
)

_active_instances: list["WebAutomation"] = []
_registry_lock = threading.Lock()


def close_all_web_automation() -> None:
    """Close every live Playwright session before process exit."""
    with _registry_lock:
        instances = list(_active_instances)
    for instance in instances:
        try:
            instance.close()
        except Exception:
            pass


atexit.register(close_all_web_automation)


class WebAutomation:
    def __init__(self):
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._closed = False
        self.last_action = {}
        with _registry_lock:
            _active_instances.append(self)

    def _set_last(self, action: str, ok: bool = True, reason: str = "ok", **extra):
        self.last_action = {"action": action, "ok": ok, "reason": reason, **extra}

    def _detect_captcha(self) -> bool:
        page = self._page
        if page is None:
            return False
        title = ""
        body = ""
        try:
            title = page.title() or ""
        except Exception:
            title = ""
        try:
            body = page.locator("body").inner_text(timeout=1500)[:2500]
        except Exception:
            body = ""
        blob = f"{title} {body}".lower()
        captcha_terms = (
            "captcha",
            "recaptcha",
            "hcaptcha",
            "robot",
            "verify you are human",
            "unusual traffic",
            "are you a robot",
            "insan oldugunuzu",
            "robot olmadiginizi",
        )
        if any(term in blob for term in captcha_terms):
            return True
        try:
            frames = page.frames
            for frame in frames:
                url = (frame.url or "").lower()
                if "recaptcha" in url or "hcaptcha" in url or "captcha" in url:
                    return True
        except Exception:
            pass
        return False

    def _ensure_no_captcha(self, action: str):
        if self._detect_captcha():
            self._set_last(action, ok=False, reason="captcha_required", captcha=True)
            raise RuntimeError("captcha_required")

    def _first_youtube_video_url(self, query: str) -> str | None:
        try:
            import requests
        except Exception:
            return None
        search_url = (
            "https://www.youtube.com/results"
            f"?search_query={quote_plus(query)}"
            "&sp=EgIQAQ%3D%3D"
        )
        headers = {
            "User-Agent": WEB_USER_AGENT,
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        try:
            resp = requests.get(search_url, headers=headers, timeout=8)
            resp.raise_for_status()
            html = resp.text
            seen: set[str] = set()
            for video_id in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
                if video_id in seen:
                    continue
                seen.add(video_id)
                if f"/shorts/{video_id}" in html:
                    continue
                return f"https://www.youtube.com/watch?v={video_id}"
        except Exception:
            return None
        return None

    def _ensure(self):
        if self._closed:
            raise RuntimeError("web_automation_closed")
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(f"playwright_missing: {exc}") from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=PLAYWRIGHT_HEADLESS,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._browser.new_context(
            user_agent=WEB_USER_AGENT,
            locale="en-US",
            timezone_id="UTC",
            viewport={"width": 1280, "height": 720},
        )
        self._page = self._context.new_page()
        # Reduce bot signals a bit.
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        self._page.set_default_timeout(15000)
        self._page.set_default_navigation_timeout(30000)

    def open(self, url: str, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            target = url.strip()
            if target and not target.startswith(("http://", "https://")):
                target = "https://" + target
            check_cancelled(cancel_event)
            self._page.goto(target, wait_until="domcontentloaded")
            self._ensure_no_captcha("web_open")
            self._set_last("web_open", url=self._page.url)

    def search(self, query: str, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            url = WEB_SEARCH_URL_PLAYWRIGHT.format(query=quote_plus(query))
            check_cancelled(cancel_event)
            self._page.goto(url, wait_until="domcontentloaded")
            self._ensure_no_captcha("web_search")
            self._set_last("web_search", url=self._page.url)

    def youtube_search(self, query: str, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            direct_url = self._first_youtube_video_url(query)
            if direct_url:
                check_cancelled(cancel_event)
                self._page.goto(direct_url, wait_until="domcontentloaded")
                self._ensure_no_captcha("youtube_search")
                self._set_last("youtube_search", url=self._page.url)
                return
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            check_cancelled(cancel_event)
            self._page.goto(url, wait_until="domcontentloaded")
            try:
                self._page.wait_for_selector("ytd-video-renderer", timeout=15000)
            except Exception:
                pass
            script = """
            () => {
              const items = Array.from(document.querySelectorAll('ytd-video-renderer'));
              for (const item of items) {
                if (item.closest('ytd-promoted-video-renderer, ytd-display-ad-renderer, ytd-in-feed-ad-layout-renderer, ytd-ad-slot-renderer')) {
                  continue;
                }
                const link = item.querySelector('a#video-title');
                if (link && link.href) {
                  return link.href;
                }
              }
              return null;
            }
            """
            href = self._page.evaluate(script)
            if href:
                self._page.goto(href, wait_until="domcontentloaded")
            else:
                try:
                    self._page.locator("ytd-video-renderer a#video-title").first.click(
                        timeout=8000
                    )
                    self._page.wait_for_load_state("domcontentloaded", timeout=15000)
                except Exception:
                    pass
            check_cancelled(cancel_event)
            self._ensure_no_captcha("youtube_search")
            self._set_last("youtube_search", url=self._page.url)

    def click(self, mode: str, value: str, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            if mode == "css":
                self._page.locator(value).first.click()
            else:
                self._smart_click(value)
            self._ensure_no_captcha("web_click")
            self._set_last("web_click", target=value)

    def type_text(self, text: str, selector: str | None = None, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            if selector:
                self._smart_fill(selector, text)
            else:
                self._page.keyboard.type(text, delay=20)
            self._set_last("web_type", target=selector or "active")

    def press(self, key: str, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            self._page.keyboard.press(key)
            self._set_last("web_press", key=key)

    def wait(self, seconds: float, cancel_event: Event | None = None):
        with self._lock:
            sleep_cancellable(seconds, cancel_event)
            self._set_last("web_wait", seconds=seconds)

    def _smart_click(self, text: str):
        page = self._page
        escaped = re.escape(text)
        partial = re.compile(re.escape(text[: max(3, len(text) // 2)]), re.I)
        candidates = [
            lambda: page.get_by_role("button", name=re.compile(escaped, re.I)).first,
            lambda: page.get_by_role("link", name=re.compile(escaped, re.I)).first,
            lambda: page.get_by_role("menuitem", name=re.compile(escaped, re.I)).first,
            lambda: page.get_by_role("tab", name=re.compile(escaped, re.I)).first,
            lambda: page.get_by_label(text, exact=False).first,
            lambda: page.get_by_placeholder(text, exact=False).first,
            lambda: page.get_by_alt_text(text, exact=False).first,
            lambda: page.get_by_title(text, exact=False).first,
            lambda: page.get_by_text(text, exact=False).first,
            lambda: page.get_by_text(partial).first,
        ]
        last_err = None
        for factory in candidates:
            try:
                loc = factory()
                loc.click(timeout=2500)
                return
            except Exception as exc:
                last_err = exc
        raise last_err or RuntimeError("web_click_failed")

    def _smart_fill(self, selector_or_hint: str, text: str):
        page = self._page
        raw = (selector_or_hint or "").strip()
        selectors = []
        if raw:
            selectors.append(raw)
            if raw.startswith("css:"):
                selectors.insert(0, raw[4:].strip())
        for selector in selectors:
            try:
                page.locator(selector).first.fill(text, timeout=2500)
                return
            except Exception:
                pass
        candidates = [
            lambda: page.get_by_label(raw, exact=False).first,
            lambda: page.get_by_placeholder(raw, exact=False).first,
            lambda: page.get_by_role("textbox", name=re.compile(re.escape(raw), re.I)).first,
            lambda: page.get_by_title(raw, exact=False).first,
        ]
        last_err = None
        for factory in candidates:
            try:
                loc = factory()
                loc.fill(text, timeout=2500)
                return
            except Exception as exc:
                last_err = exc
        raise last_err or RuntimeError("web_type_failed")

    def screenshot(self, path: str):
        with self._lock:
            self._ensure()
            self._page.screenshot(path=path, full_page=True)
            self._set_last("web_screenshot", path=path)

    def fill_form(self, data: dict, profile: dict, cancel_event: Event | None = None):
        with self._lock:
            check_cancelled(cancel_event)
            self._ensure()
            page = self._page
            merged, mode, submit = merge_form_data(data or {}, profile or {})
            allow_sensitive = bool((data or {}).get("email") or (data or {}).get("password"))
            self._ensure_no_captcha("web_form_fill")

            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass

            filled_fields: set[str] = set()

            def fill_field(field: str, value: str) -> bool:
                if field in ("password", "password_confirm"):
                    password_inputs = page.locator("input[type='password']")
                    index = 1 if field == "password_confirm" else 0
                    try:
                        if password_inputs.count() > index:
                            password_inputs.nth(index).fill(value, timeout=1500)
                            return True
                    except Exception:
                        pass
                    autocomplete = (
                        "new-password"
                        if field == "password_confirm"
                        else "current-password"
                    )
                    for auto in (autocomplete, "new-password", "current-password"):
                        try:
                            loc = page.locator(f"input[autocomplete='{auto}']")
                            if loc.count() > index:
                                loc.nth(index).fill(value, timeout=1500)
                                return True
                        except Exception:
                            pass
                labels = FIELD_LABELS.get(field, (field,))
                for label in labels:
                    for factory in (
                        lambda l=label: page.get_by_label(l, exact=False).first,
                        lambda l=label: page.get_by_placeholder(l, exact=False).first,
                        lambda l=label: page.get_by_role(
                            "textbox", name=re.compile(re.escape(l), re.I)
                        ).first,
                    ):
                        try:
                            factory().fill(value, timeout=1500)
                            return True
                        except Exception:
                            pass
                if field == "email":
                    for locator in (
                        page.locator("input[type='email']").first,
                        page.locator("input[autocomplete='email']").first,
                        page.locator("input[name*='mail' i]").first,
                    ):
                        try:
                            locator.fill(value, timeout=1500)
                            return True
                        except Exception:
                            pass
                return False

            for field in fields_for_mode(mode if mode != "auto" else "fill"):
                check_cancelled(cancel_event)
                val = value_for(field, merged, allow_sensitive=allow_sensitive or field in merged)
                if not val:
                    continue
                if fill_field(field, val):
                    filled_fields.add(field)

            inputs = page.locator("input, textarea, select")
            count = inputs.count()
            for i in range(count):
                check_cancelled(cancel_event)
                el = inputs.nth(i)
                try:
                    tag = el.evaluate("el => el.tagName.toLowerCase()")
                except Exception:
                    tag = "input"
                try:
                    itype = (el.get_attribute("type") or "").lower()
                except Exception:
                    itype = ""
                if itype in ("hidden", "submit", "button", "checkbox", "radio", "file", "image"):
                    continue

                attr_name = el.get_attribute("name") or ""
                attr_id = el.get_attribute("id") or ""
                placeholder = el.get_attribute("placeholder") or ""
                aria = el.get_attribute("aria-label") or ""
                label_text = ""
                if attr_id:
                    try:
                        label = page.locator(f"label[for='{attr_id}']").first
                        label_text = label.inner_text(timeout=200) if label else ""
                    except Exception:
                        label_text = ""
                blob = " ".join([attr_name, attr_id, placeholder, aria, label_text, itype]).strip()
                field = infer_field(blob)
                if not field or field in filled_fields:
                    continue
                if mode == "login" and field not in {"email", "password"}:
                    continue
                val = value_for(field, merged, allow_sensitive=allow_sensitive or field in merged)
                if not val:
                    continue
                try:
                    if tag == "select":
                        el.select_option(label=val)
                    else:
                        el.fill(val)
                    filled_fields.add(field)
                except Exception:
                    try:
                        el.click()
                        page.keyboard.type(val, delay=20)
                        filled_fields.add(field)
                    except Exception:
                        pass

            submitted = False
            if submit:
                submitted = self._submit_form(page, mode)
                if submitted:
                    try:
                        self._ensure_no_captcha("web_form_fill")
                    except RuntimeError:
                        self._set_last(
                            "web_form_fill",
                            ok=False,
                            reason="captcha_required",
                            captcha=True,
                            fields=sorted(filled_fields),
                            mode=mode,
                        )
                        raise

            if not filled_fields:
                self._set_last(
                    "web_form_fill",
                    ok=False,
                    reason="no_fields_filled",
                    fields=[],
                    mode=mode,
                )
                raise RuntimeError("no_fields_filled")

            self._ensure_no_captcha("web_form_fill")
            self._set_last(
                "web_form_fill",
                ok=True,
                fields=sorted(filled_fields),
                submitted=submitted,
                mode=mode,
            )

    def _submit_form(self, page, mode: str) -> bool:
        for pattern in submit_patterns(mode):
            for role in ("button", "link"):
                try:
                    page.get_by_role(role, name=re.compile(pattern, re.I)).first.click(timeout=1500)
                    return True
                except Exception:
                    pass
        for text in submit_patterns(mode):
            try:
                page.locator(f"input[type='submit'][value*='{text[:6]}' i]").first.click(timeout=1200)
                return True
            except Exception:
                pass
        try:
            page.locator("button[type='submit'], input[type='submit']").first.click(timeout=1500)
            return True
        except Exception:
            pass
        if mode in {"login", "signup", "auto"}:
            try:
                page.keyboard.press("Enter")
                return True
            except Exception:
                pass
        return False

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            page = self._page
            context = self._context
            browser = self._browser
            playwright = self._playwright
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

        if page is not None:
            try:
                page.goto("about:blank", wait_until="domcontentloaded", timeout=2000)
            except Exception:
                pass
            try:
                page.close()
            except Exception:
                pass
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
            # Give the Node driver a moment to exit cleanly and avoid EPIPE on shutdown.
            sleep_cancellable(0.15)

        with _registry_lock:
            if self in _active_instances:
                _active_instances.remove(self)
