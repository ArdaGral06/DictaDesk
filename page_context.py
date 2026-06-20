"""Browser/window page awareness for LLM planning and form automation."""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from utils import fold_text

BROWSER_EXES = frozenset(
    {
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "vivaldi.exe",
        "iexplore.exe",
    }
)

BROWSER_SUFFIXES = (
    " - google chrome",
    " - microsoft edge",
    " - mozilla firefox",
    " - brave",
    " - opera",
    " - vivaldi",
    " — google chrome",
    " — microsoft edge",
)

PAGE_KIND_HINTS: dict[str, tuple[str, ...]] = {
    "login": (
        "sign in",
        "log in",
        "login",
        "giris yap",
        "giriş yap",
        "giris",
        "giriş",
        "oturum ac",
        "oturum aç",
        "authenticate",
        "welcome back",
        "hesaba gir",
    ),
    "signup": (
        "sign up",
        "signup",
        "register",
        "registration",
        "create account",
        "kayit ol",
        "kayıt ol",
        "kaydol",
        "hesap olustur",
        "hesap oluştur",
        "join now",
        "new account",
    ),
    "password": (
        "reset password",
        "forgot password",
        "change password",
        "set password",
        "create password",
        "sifre sifirla",
        "şifre sıfırla",
        "sifremi unuttum",
        "şifremi unuttum",
        "sifrenizi ayarlayin",
        "şifrenizi ayarlayın",
        "sifre belirle",
        "şifre belirle",
        "new password",
        "password recovery",
    ),
    "checkout": (
        "checkout",
        "payment",
        "billing",
        "odeme",
        "ödeme",
        "sepet",
        "cart",
        "siparis",
        "sipariş",
    ),
    "search": (
        "search results",
        "results for",
        "arama sonuclari",
        "arama sonuçları",
        "google search",
    ),
    "form": (
        "contact form",
        "application form",
        "survey",
        "form",
        "basvuru",
        "başvuru",
        "iletisim",
        "iletişim",
    ),
    "captcha": (
        "captcha",
        "recaptcha",
        "hcaptcha",
        "robot",
        "verify you are human",
        "insan oldugunuzu",
    ),
    "error": (
        "404",
        "not found",
        "error",
        "bulunamadi",
        "bulunamadı",
        "access denied",
        "forbidden",
    ),
}


def is_browser_exe(exe: str) -> bool:
    return fold_text(exe or "") in BROWSER_EXES


def parse_browser_title(title: str, exe: str = "") -> dict[str, str]:
    raw = (title or "").strip()
    if not raw:
        return {}
    lowered = raw.lower()
    for suffix in BROWSER_SUFFIXES:
        if lowered.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
            lowered = raw.lower()
            break

    parts = [part.strip() for part in re.split(r"\s[-–—|]\s", raw) if part.strip()]
    if not parts:
        return {"page_title": title, "site": "", "browser": _browser_name(exe)}

    if len(parts) == 1:
        return {
            "page_title": parts[0],
            "site": parts[0],
            "browser": _browser_name(exe),
        }

    # Common: "Sign in - Google Accounts" or "Video title - YouTube"
    page_title = parts[0]
    site = parts[1] if len(parts) > 1 else parts[0]
    if len(parts) > 2 and fold_text(parts[-1]) in {"profile 1", "profile 2", "personal"}:
        site = parts[-2]
    return {
        "page_title": page_title,
        "site": site,
        "browser": _browser_name(exe),
        "breadcrumbs": " > ".join(parts),
    }


def _browser_name(exe: str) -> str:
    mapping = {
        "chrome.exe": "Chrome",
        "msedge.exe": "Edge",
        "firefox.exe": "Firefox",
        "brave.exe": "Brave",
        "opera.exe": "Opera",
        "vivaldi.exe": "Vivaldi",
    }
    return mapping.get(fold_text(exe or ""), _exe_stem(exe))


def _exe_stem(exe: str) -> str:
    name = (exe or "").strip()
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name or "browser"


def classify_page_kind(
    *,
    title: str = "",
    url: str = "",
    headings: list[str] | None = None,
) -> str:
    blob = fold_text(" ".join([title, url, *(headings or [])]))
    if not blob:
        return "unknown"
    for kind in ("captcha", "error", "login", "signup", "password", "checkout", "search", "form"):
        if any(hint in blob for hint in PAGE_KIND_HINTS[kind]):
            return kind
    path = fold_text(urlparse(url or "").path or "")
    if any(token in path for token in ("/login", "/signin", "/giris", "/auth")):
        return "login"
    if any(token in path for token in ("/signup", "/register", "/kayit", "/join")):
        return "signup"
    if any(token in path for token in ("/reset", "/forgot", "/password")):
        return "password"
    if path in {"", "/"}:
        return "home"
    return "unknown"


def describe_page_kind(kind: str, ui_lang: str = "tr") -> str:
    labels_tr = {
        "login": "giris / login sayfasi",
        "signup": "kayit / signup sayfasi",
        "password": "sifre belirleme / sifirlama sayfasi",
        "checkout": "odeme / sepet sayfasi",
        "search": "arama sonuclari sayfasi",
        "form": "form sayfasi",
        "captcha": "captcha / dogrulama sayfasi",
        "error": "hata sayfasi",
        "home": "ana sayfa",
        "unknown": "genel web sayfasi",
    }
    labels_en = {
        "login": "login / sign-in page",
        "signup": "sign-up / registration page",
        "password": "password set/reset page",
        "checkout": "checkout / payment page",
        "search": "search results page",
        "form": "form page",
        "captcha": "captcha / verification page",
        "error": "error page",
        "home": "home page",
        "unknown": "general web page",
    }
    table = labels_tr if ui_lang == "tr" else labels_en
    return table.get(kind, kind)


def get_playwright_page_snapshot(web: Any | None) -> dict[str, Any]:
    if web is None:
        return {}
    page = getattr(web, "_page", None)
    if page is None:
        last = getattr(web, "last_action", {}) or {}
        if last.get("url"):
            return {"url": last.get("url"), "source": "playwright_last_action"}
        return {}
    try:
        url = page.url or ""
    except Exception:
        url = ""
    try:
        title = page.title() or ""
    except Exception:
        title = ""
    headings: list[str] = []
    try:
        headings = page.evaluate(
            """() => Array.from(document.querySelectorAll('h1,h2,[role=heading]'))
            .map(el => (el.innerText || el.textContent || '').trim())
            .filter(Boolean).slice(0, 6)"""
        )
    except Exception:
        headings = []
    kind = classify_page_kind(title=title, url=url, headings=headings)
    host = urlparse(url).netloc if url else ""
    return {
        "source": "playwright",
        "url": url,
        "title": title,
        "host": host,
        "headings": headings,
        "page_kind": kind,
        "page_kind_label": describe_page_kind(kind),
    }


def build_active_browser_context(active: dict | None, ui_lang: str = "tr") -> dict[str, Any]:
    active = active or {}
    title = str(active.get("title") or "")
    exe = str(active.get("exe") or "")
    if not is_browser_exe(exe):
        return {}
    parsed = parse_browser_title(title, exe)
    kind = classify_page_kind(title=title, url="", headings=[parsed.get("page_title", "")])
    return {
        "source": "native_browser",
        "browser": parsed.get("browser") or _browser_name(exe),
        "window_title": title,
        "page_title": parsed.get("page_title", ""),
        "site": parsed.get("site", ""),
        "breadcrumbs": parsed.get("breadcrumbs", ""),
        "page_kind": kind,
        "page_kind_label": describe_page_kind(kind, ui_lang),
    }


def format_page_context_for_llm(
    *,
    active: dict | None = None,
    web: Any | None = None,
    ui_lang: str = "tr",
) -> str:
    chunks: list[str] = []
    pw = get_playwright_page_snapshot(web)
    if pw:
        chunks.append(
            "PLAYWRIGHT_PAGE_JSON: "
            + json.dumps(
                {
                    "url": pw.get("url"),
                    "title": pw.get("title"),
                    "host": pw.get("host"),
                    "headings": pw.get("headings"),
                    "page_kind": pw.get("page_kind"),
                    "page_kind_label": pw.get("page_kind_label"),
                },
                ensure_ascii=False,
            )
        )
    native = build_active_browser_context(active, ui_lang=ui_lang)
    if native:
        chunks.append(
            "BROWSER_PAGE_JSON: "
            + json.dumps(
                {
                    "browser": native.get("browser"),
                    "page_title": native.get("page_title"),
                    "site": native.get("site"),
                    "window_title": native.get("window_title"),
                    "page_kind": native.get("page_kind"),
                    "page_kind_label": native.get("page_kind_label"),
                },
                ensure_ascii=False,
            )
        )
    if not chunks:
        return ""
    hint = (
        "Use PAGE context to choose login vs signup vs password-reset actions and the correct form fields."
        if ui_lang != "tr"
        else "PAGE baglamina gore login / kayit / sifre sayfasi ayrimini ve dogru form alanlarini sec."
    )
    return "; ".join(chunks) + f"; PAGE_HINT: {hint}"
