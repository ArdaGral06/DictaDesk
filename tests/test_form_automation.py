from form_automation import (
    infer_field,
    merge_form_data,
    parse_form_options,
    parse_form_voice_request,
)


def test_infer_field_turkish():
    assert infer_field("E-posta adresi") == "email"
    assert infer_field("Sifre") == "password"
    assert infer_field("Şifrenizi ayarlayın") == "password"
    assert infer_field("Enter your password") == "password"
    assert infer_field("Şifre tekrar") == "password_confirm"
    assert infer_field("Kullanici adi") == "username"


def test_parse_form_options_login():
    data, mode, submit = parse_form_options(
        {"mode": "login", "email": "a@b.com", "password": "secret"}
    )
    assert mode == "login"
    assert submit is True
    assert data["email"] == "a@b.com"


def test_merge_form_data_uses_profile_email():
    merged, mode, submit = merge_form_data(
        {"password": "secret", "login": "true"},
        {"email": "user@example.com", "name": "Ali"},
    )
    assert merged["email"] == "user@example.com"
    assert merged["password"] == "secret"
    assert mode == "login"
    assert submit is True


def test_parse_form_voice_request_login():
    text = 'siteye giris yap email=user@test.com sifre=abc123'
    data = parse_form_voice_request(text)
    assert data is not None
    assert data.get("mode") == "login"
    assert data.get("email") == "user@test.com"
    assert data.get("password") == "abc123"
