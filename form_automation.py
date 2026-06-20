"""Shared form/login field matching for Playwright and native UIA fills."""
from __future__ import annotations

import re
from typing import Any

from utils import fold_text

ALL_FIELDS = (
    "email",
    "password",
    "password_confirm",
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
)

FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "email": (
        "email",
        "e-mail",
        "eposta",
        "e-posta",
        "e mail",
        "mail",
        "correo",
        "email address",
        "e-posta adresi",
        "eposta adresi",
    ),
    "password": (
        "password",
        "pass",
        "passwd",
        "sifre",
        "şifre",
        "parola",
        "parolaniz",
        "parolanız",
        "sifreniz",
        "şifreniz",
        "sifrenizi girin",
        "şifrenizi girin",
        "sifrenizi ayarlayin",
        "şifrenizi ayarlayın",
        "sifre belirleyin",
        "şifre belirleyin",
        "sifre belirle",
        "şifre belirle",
        "yeni sifre",
        "yeni şifre",
        "sifre olustur",
        "şifre oluştur",
        "enter your password",
        "enter password",
        "your password",
        "set your password",
        "set password",
        "create password",
        "choose a password",
        "choose password",
        "type your password",
        "current password",
        "new password",
    ),
    "password_confirm": (
        "confirm password",
        "password confirm",
        "password again",
        "re-enter password",
        "reenter password",
        "repeat password",
        "verify password",
        "sifre tekrar",
        "şifre tekrar",
        "sifreyi tekrar",
        "şifreyi tekrar",
        "sifrenizi tekrar",
        "şifrenizi tekrar",
        "sifre onay",
        "şifre onay",
        "parola tekrar",
        "confirm your password",
    ),
    "first_name": ("first name", "firstname", "ad", "given name"),
    "last_name": ("last name", "lastname", "soyad", "surname", "family name"),
    "name": ("name", "full name", "ad soyad", "isim", "tam ad"),
    "username": ("username", "user name", "kullanici adi", "kullanıcı adı", "nick"),
    "phone": ("phone", "mobile", "telefon", "tel", "gsm"),
    "city": ("city", "sehir", "şehir", "town"),
    "address": ("address", "street", "adres", "cadde"),
    "zip": ("zip", "postal", "posta kodu", "postcode"),
    "birthday": ("birthday", "birth", "dob", "dogum", "doğum"),
    "age": ("age", "yas", "yaş"),
}

LOGIN_SUBMIT_LABELS = (
    r"^log\s*in$",
    r"^login$",
    r"^sign\s*in$",
    r"^giri[sş]$",
    r"^giri[sş]\s*yap$",
    r"^oturum\s*a[cç]$",
    r"^devam$",
    r"^continue$",
    r"^submit$",
    r"^enter$",
)

SIGNUP_SUBMIT_LABELS = (
    r"^sign\s*up$",
    r"^register$",
    r"^create\s*account$",
    r"^kaydol$",
    r"^kayit\s*ol$",
    r"^kayıt\s*ol$",
    r"^hesap\s*olustur$",
    r"^hesap\s*oluştur$",
    r"^submit$",
    r"^devam$",
)

GENERIC_SUBMIT_LABELS = LOGIN_SUBMIT_LABELS + SIGNUP_SUBMIT_LABELS + (
    r"^continue$",
    r"^next$",
    r"^ileri$",
    r"^tamam$",
    r"^ok$",
)

SUBMIT_TEXT_LITERALS: dict[str, tuple[str, ...]] = {
    "login": (
        "log in",
        "login",
        "sign in",
        "giriş",
        "giris",
        "giriş yap",
        "giris yap",
        "oturum aç",
        "oturum ac",
        "devam",
        "submit",
    ),
    "signup": (
        "sign up",
        "register",
        "create account",
        "kaydol",
        "kayıt ol",
        "kayit ol",
        "hesap oluştur",
        "hesap olustur",
        "devam",
        "submit",
    ),
    "auto": (
        "log in",
        "login",
        "sign in",
        "sign up",
        "register",
        "giriş",
        "giris",
        "kaydol",
        "devam",
        "submit",
        "continue",
        "tamam",
    ),
    "fill": (
        "submit",
        "devam",
        "continue",
        "kaydet",
        "save",
        "tamam",
    ),
}


def submit_text_literals(mode: str) -> tuple[str, ...]:
    if mode == "login":
        return SUBMIT_TEXT_LITERALS["login"]
    if mode == "signup":
        return SUBMIT_TEXT_LITERALS["signup"]
    if mode == "fill":
        return SUBMIT_TEXT_LITERALS["fill"]
    return SUBMIT_TEXT_LITERALS["auto"]


def build_form_profile(memory: dict | None) -> dict[str, str]:
    profile: dict[str, str] = {}
    if not isinstance(memory, dict):
        return profile
    identity = memory.get("identity", {})
    if isinstance(identity, dict):
        for key in ALL_FIELDS + ("email",):
            entry = identity.get(key)
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                profile[key] = str(val)
    for section_name in ("preferences", "notes"):
        section = memory.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for key in ALL_FIELDS + ("email",):
            if key in profile:
                continue
            entry = section.get(key)
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                profile[key] = str(val)
    full_name = profile.get("name")
    if full_name and " " in full_name:
        first, last = full_name.split(" ", 1)
        profile.setdefault("first_name", first.strip())
        profile.setdefault("last_name", last.strip())
    return profile


def infer_field(text: str) -> str | None:
    folded = fold_text(text or "")
    if not folded:
        return None
    if any(term in folded for term in ("email", "eposta", "e-posta", "e mail", "e-mail", "mail address")):
        return "email"
    if any(
        term in folded
        for term in (
            "confirm password",
            "password confirm",
            "password again",
            "re-enter password",
            "repeat password",
            "verify password",
            "sifre tekrar",
            "şifre tekrar",
            "sifreyi tekrar",
            "şifreyi tekrar",
            "sifrenizi tekrar",
            "şifrenizi tekrar",
            "sifre onay",
            "şifre onay",
            "parola tekrar",
        )
    ):
        return "password_confirm"
    if any(
        term in folded
        for term in (
            "password",
            "sifre",
            "şifre",
            "parola",
            "passwd",
            "sifrenizi girin",
            "şifrenizi girin",
            "sifrenizi ayarlayin",
            "şifrenizi ayarlayın",
            "sifre belirleyin",
            "şifre belirleyin",
            "sifre belirle",
            "şifre belirle",
            "yeni sifre",
            "yeni şifre",
            "enter your password",
            "enter password",
            "set your password",
            "set password",
            "create password",
            "choose a password",
            "choose password",
            "type your password",
            "current password",
            "new password",
            "sifreniz",
            "şifreniz",
            "parolaniz",
            "parolanız",
        )
    ):
        return "password"
    if "first" in folded and "name" in folded:
        return "first_name"
    if "last" in folded and "name" in folded:
        return "last_name"
    if ("full" in folded and "name" in folded) or folded.strip() in {"name", "isim", "ad soyad"}:
        return "name"
    if ("user" in folded and "name" in folded) or any(
        term in folded for term in ("kullanici adi", "kullanıcı adı", "kullanici", "nickname")
    ):
        return "username"
    if any(term in folded for term in ("phone", "mobile", "telefon", "gsm")) or re.search(
        r"\btel\b", folded
    ):
        return "phone"
    if any(term in folded for term in ("city", "sehir", "town")):
        return "city"
    if any(term in folded for term in ("address", "street", "cadde")) or re.search(
        r"\badres\b", folded
    ):
        return "address"
    if any(term in folded for term in ("zip", "postal", "postcode")) or re.search(
        r"posta\s*kodu", folded
    ):
        return "zip"
    if any(term in folded for term in ("birth", "dob", "dogum")):
        return "birthday"
    if re.search(r"\bage\b", folded):
        return "age"
    return None


def fields_for_mode(mode: str) -> tuple[str, ...]:
    if mode == "login":
        return ("email", "password")
    if mode == "signup":
        return ("email", "password", "password_confirm", "first_name", "last_name", "name", "username")
    return ALL_FIELDS


def submit_patterns(mode: str) -> tuple[str, ...]:
    if mode == "login":
        return LOGIN_SUBMIT_LABELS
    if mode == "signup":
        return SIGNUP_SUBMIT_LABELS
    return GENERIC_SUBMIT_LABELS


def parse_form_options(data: dict[str, Any]) -> tuple[dict[str, str], str, bool]:
    """Return cleaned data, mode (auto/login/signup/fill), submit flag."""
    cleaned = {str(k).lower(): str(v) for k, v in (data or {}).items() if v is not None}
    mode = "auto"
    submit = False

    raw_mode = cleaned.pop("mode", "").strip().lower()
    if raw_mode in {"login", "signup", "fill", "register"}:
        mode = "signup" if raw_mode == "register" else raw_mode

    for key in ("login", "signin", "sign_in", "giris", "giriş"):
        if key in cleaned and str(cleaned.pop(key)).lower() in ("1", "true", "yes", "y", "on"):
            mode = "login"
            submit = True

    for key in ("signup", "register", "kayit", "kayıt", "kaydol"):
        if key in cleaned and str(cleaned.pop(key)).lower() in ("1", "true", "yes", "y", "on"):
            mode = "signup"
            submit = True

    if "submit" in cleaned:
        submit = str(cleaned.pop("submit")).lower() in ("1", "true", "yes", "y", "on")

    if mode == "login" and not submit:
        submit = True
    if mode == "auto":
        has_login_fields = "email" in cleaned or "password" in cleaned
        if has_login_fields and len(cleaned) <= 3:
            mode = "login"
            submit = True

    return cleaned, mode, submit


def merge_form_data(
    data: dict[str, Any],
    profile: dict[str, str],
) -> tuple[dict[str, str], str, bool]:
    explicit, mode, submit = parse_form_options(data)
    combined = dict(profile or {})
    combined.update(explicit)
    allow_email = "email" in explicit
    allow_password = "password" in explicit
    merged: dict[str, str] = {}
    for key, val in combined.items():
        if key in {"mode", "submit", "login", "signup"}:
            continue
        if key == "email" and not allow_email and key not in profile:
            continue
        if key == "password" and not allow_password:
            continue
        if val:
            merged[key] = str(val)
    if mode == "auto" and {"email", "password"} <= set(merged.keys()):
        mode = "login"
        submit = submit or True
    return merged, mode, submit


def guess_value(field: str) -> str | None:
    import random

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


def value_for(field: str, merged: dict[str, str], *, allow_sensitive: bool) -> str | None:
    if field == "password_confirm":
        confirm = merged.get("password_confirm") or merged.get("password")
        return str(confirm) if confirm else None
    if field in ("email", "password") and not allow_sensitive:
        if field not in merged:
            return None
    val = merged.get(field)
    if val:
        return str(val)
    if field in ("email", "password"):
        return None
    return guess_value(field)


def parse_form_voice_request(text: str) -> dict[str, str] | None:
    """Detect simple login/signup voice commands with inline credentials."""
    folded = fold_text(text or "")
    if not folded:
        return None
    login_words = (
        "giris yap",
        "giriş yap",
        "oturum ac",
        "oturum aç",
        "login",
        "log in",
        "sign in",
        "giris",
        "giriş",
    )
    signup_words = ("kaydol", "kayit ol", "kayıt ol", "sign up", "signup", "register", "hesap olustur")
    form_words = ("form", "formu", "doldur", "fill", "kayit", "kayıt")

    is_login = any(w in folded for w in login_words)
    is_signup = any(w in folded for w in signup_words)
    is_form = any(w in folded for w in form_words)
    if not is_login and not is_signup and not is_form:
        return None

    data: dict[str, str] = {}
    if is_login:
        data["mode"] = "login"
        data["submit"] = "true"
    elif is_signup:
        data["mode"] = "signup"
        data["submit"] = "true"

    email_match = re.search(
        r"(?:email|e[\s-]?posta|mail)\s*(?:=|:)?\s*([^\s;]+@[^\s;]+)",
        text,
        flags=re.I,
    )
    if not email_match:
        email_match = re.search(r"([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})", text, flags=re.I)
    if email_match:
        data["email"] = email_match.group(1).strip()

    pwd_match = re.search(
        r"(?:sifre|şifre|password|parola)\s*(?:=|:)?\s*([^\s;\"']+)",
        text,
        flags=re.I,
    )
    if pwd_match:
        data["password"] = pwd_match.group(1).strip()

    for pattern in (r'"([^"]+)"', r"'([^']+)'"):
        matches = re.findall(pattern, text)
        if matches and "password" not in data and is_login:
            data["password"] = matches[-1].strip()

    if is_login and ("email" in data or "password" in data):
        return data
    if is_signup or is_form:
        return data if data else {"mode": "signup" if is_signup else "fill", "submit": "true"}
    return None
