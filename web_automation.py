import threading
import time
import re
from urllib.parse import quote_plus

from config import WEB_SEARCH_URL_PLAYWRIGHT, WEB_USER_AGENT
import random
import string


class WebAutomation:
    def __init__(self):
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self.last_action = {}

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
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(f"playwright_missing: {exc}") from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=False,
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

    def open(self, url: str):
        with self._lock:
            self._ensure()
            target = url.strip()
            if target and not target.startswith(("http://", "https://")):
                target = "https://" + target
            self._page.goto(target, wait_until="domcontentloaded")
            self._ensure_no_captcha("web_open")
            self._set_last("web_open", url=self._page.url)

    def search(self, query: str):
        with self._lock:
            self._ensure()
            url = WEB_SEARCH_URL_PLAYWRIGHT.format(query=quote_plus(query))
            self._page.goto(url, wait_until="domcontentloaded")
            self._ensure_no_captcha("web_search")
            self._set_last("web_search", url=self._page.url)

    def youtube_search(self, query: str):
        with self._lock:
            self._ensure()
            direct_url = self._first_youtube_video_url(query)
            if direct_url:
                self._page.goto(direct_url, wait_until="domcontentloaded")
                self._ensure_no_captcha("youtube_search")
                self._set_last("youtube_search", url=self._page.url)
                return
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
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
            self._ensure_no_captcha("youtube_search")
            self._set_last("youtube_search", url=self._page.url)

    def click(self, mode: str, value: str):
        with self._lock:
            self._ensure()
            if mode == "css":
                self._page.locator(value).first.click()
            else:
                self._smart_click(value)
            self._ensure_no_captcha("web_click")
            self._set_last("web_click", target=value)

    def type_text(self, text: str, selector: str | None = None):
        with self._lock:
            self._ensure()
            if selector:
                self._smart_fill(selector, text)
            else:
                self._page.keyboard.type(text, delay=20)
            self._set_last("web_type", target=selector or "active")

    def press(self, key: str):
        with self._lock:
            self._ensure()
            self._page.keyboard.press(key)
            self._set_last("web_press", key=key)

    def wait(self, seconds: float):
        with self._lock:
            time.sleep(max(0.0, seconds))
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

    def fill_form(self, data: dict, profile: dict):
        with self._lock:
            self._ensure()
            page = self._page
            data = data or {}
            profile = profile or {}
            self._ensure_no_captcha("web_form_fill")

            allow_email = "email" in data
            allow_password = "password" in data
            # Merge profile, then override with explicit data
            combined = dict(profile)
            for key, val in data.items():
                combined[key] = val

            submit = False
            if isinstance(combined.get("submit"), str):
                submit = combined.get("submit").lower() in ("1", "true", "yes", "y")
            elif isinstance(combined.get("submit"), bool):
                submit = combined.get("submit")

            def guess_value(field: str) -> str | None:
                field = field.lower()
                if field in ("name", "full_name"):
                    return random.choice(["Alex Johnson", "Taylor Smith", "Jordan Lee"])
                if field == "first_name":
                    return random.choice(["Alex", "Taylor", "Jordan", "Casey"])
                if field == "last_name":
                    return random.choice(["Johnson", "Smith", "Lee", "Brown"])
                if field == "username":
                    return "user" + str(random.randint(1000, 9999))
                if field == "city":
                    return random.choice(["Istanbul", "Ankara", "Izmir"])
                if field == "phone":
                    return "05" + str(random.randint(100000000, 999999999))
                if field == "address":
                    return f"{random.randint(10, 999)} Main Street"
                if field == "zip":
                    return str(random.randint(10000, 99999))
                if field == "birthday":
                    return "01/01/1995"
                if field == "age":
                    return "25"
                return None

            def value_for(field: str) -> str | None:
                if field in ("email", "password") and not (
                    (field == "email" and allow_email) or (field == "password" and allow_password)
                ):
                    return None
                val = combined.get(field)
                if val:
                    return str(val)
                return guess_value(field)

            def infer_field(text: str) -> str | None:
                t = (text or "").lower()
                if not t:
                    return None
                if "email" in t or "e-mail" in t:
                    return "email"
                if "password" in t or "pass" in t:
                    return "password"
                if "first" in t and "name" in t:
                    return "first_name"
                if "last" in t and "name" in t:
                    return "last_name"
                if "full" in t and "name" in t:
                    return "name"
                if "user" in t and "name" in t:
                    return "username"
                if t.strip() == "name":
                    return "name"
                if "phone" in t or "mobile" in t or "tel" in t:
                    return "phone"
                if "city" in t:
                    return "city"
                if "address" in t or "street" in t:
                    return "address"
                if "zip" in t or "postal" in t:
                    return "zip"
                if "birth" in t or "dob" in t:
                    return "birthday"
                if "age" in t:
                    return "age"
                return None

            def fill_dom_first(field: str, value: str) -> bool:
                labels = {
                    "email": ("email", "e-mail"),
                    "password": ("password", "pass"),
                    "first_name": ("first name", "ad"),
                    "last_name": ("last name", "soyad"),
                    "name": ("name", "full name", "ad soyad"),
                    "username": ("username", "user name", "kullanici adi"),
                    "phone": ("phone", "mobile", "telefon"),
                    "city": ("city", "sehir"),
                    "address": ("address", "street", "adres"),
                    "zip": ("zip", "postal"),
                    "birthday": ("birthday", "birth", "dob"),
                    "age": ("age", "yas"),
                }.get(field, (field,))
                for label in labels:
                    for factory in (
                        lambda l=label: page.get_by_label(l, exact=False).first,
                        lambda l=label: page.get_by_placeholder(l, exact=False).first,
                        lambda l=label: page.get_by_role("textbox", name=re.compile(re.escape(l), re.I)).first,
                    ):
                        try:
                            factory().fill(value, timeout=1200)
                            return True
                        except Exception:
                            pass
                return False

            filled_fields: set[str] = set()
            for field in (
                "email",
                "password",
                "first_name",
                "last_name",
                "name",
                "username",
                "phone",
                "city",
                "address",
                "zip",
                "birthday",
                "age",
            ):
                value = value_for(field)
                if value and fill_dom_first(field, value):
                    filled_fields.add(field)

            inputs = page.locator("input, textarea, select")
            count = inputs.count()
            for i in range(count):
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
                blob = " ".join([attr_name, attr_id, placeholder, aria, label_text]).strip()
                field = infer_field(blob)
                if not field:
                    continue
                if field in filled_fields:
                    continue
                value = value_for(field)
                if not value:
                    continue
                try:
                    if tag == "select":
                        el.select_option(label=value)
                    else:
                        el.fill(value)
                except Exception:
                    try:
                        el.click()
                        page.keyboard.type(value, delay=20)
                    except Exception:
                        pass

            if submit:
                try:
                    page.locator("button[type='submit'], input[type='submit']").first.click()
                    self._ensure_no_captcha("web_form_fill")
                    self._set_last("web_form_fill", fields=sorted(filled_fields), submitted=True)
                    return
                except Exception:
                    pass
                for text in ("sign up", "register", "create account", "submit", "continue"):
                    try:
                        page.get_by_text(text, exact=False).first.click()
                        self._ensure_no_captcha("web_form_fill")
                        self._set_last("web_form_fill", fields=sorted(filled_fields), submitted=True)
                        return
                    except Exception:
                        pass
            self._ensure_no_captcha("web_form_fill")
            self._set_last("web_form_fill", fields=sorted(filled_fields))

    def close(self):
        with self._lock:
            try:
                if self._page:
                    self._page.close()
            except Exception:
                pass
            try:
                if self._context:
                    self._context.close()
            except Exception:
                pass
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass
            try:
                if self._playwright:
                    self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None
