from api_chat_payload import api_format, build_chat_payload


def test_openai_payload():
    provider = {"api_format": "openai", "max_tokens": 1024}
    payload = build_chat_payload(
        provider, "gpt-4o", "sys", "user", max_tokens=512, temperature=0.1
    )
    assert payload["model"] == "gpt-4o"
    assert payload["messages"][0]["role"] == "system"
    assert payload["max_tokens"] == 512


def test_anthropic_payload():
    provider = {"api_format": "anthropic", "max_tokens": 2048}
    payload = build_chat_payload(provider, "claude-opus-4-20250514", "sys", "user")
    assert payload["system"] == "sys"
    assert payload["messages"] == [{"role": "user", "content": "user"}]
    assert "choices" not in payload


def test_default_format_is_openai():
    assert api_format({}) == "openai"
