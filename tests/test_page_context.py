from form_automation import infer_field
from page_context import (
    build_active_browser_context,
    classify_page_kind,
    parse_browser_title,
)


def test_password_label_variants():
    assert infer_field("Şifrenizi girin") == "password"
    assert infer_field("Set your password") == "password"
    assert infer_field("Şifrenizi tekrar girin") == "password_confirm"
    assert infer_field("Confirm password") == "password_confirm"


def test_parse_browser_title_chrome():
    parsed = parse_browser_title("Sign in - Google Accounts - Google Chrome", "chrome.exe")
    assert parsed["page_title"] == "Sign in"
    assert parsed["site"] == "Google Accounts"
    assert parsed["browser"] == "Chrome"


def test_classify_login_page():
    kind = classify_page_kind(title="Sign in - Google Accounts - Google Chrome")
    assert kind == "login"


def test_classify_password_reset_page():
    kind = classify_page_kind(title="Şifrenizi ayarlayın - Microsoft account")
    assert kind == "password"


def test_build_active_browser_context():
    ctx = build_active_browser_context(
        {"title": "Kayıt ol - Discord - Google Chrome", "exe": "chrome.exe"},
        ui_lang="tr",
    )
    assert ctx["browser"] == "Chrome"
    assert ctx["page_kind"] in {"signup", "login", "unknown", "form"}
