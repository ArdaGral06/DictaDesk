from api_provider_config import list_provider_summaries, load_provider_file, resolve_api_model


def test_list_provider_summaries():
    rows = list_provider_summaries()
    kinds = {row["kind"] for row in rows}
    assert "stt" in kinds
    assert "llm" in kinds


def test_load_stt_providers():
    providers = load_provider_file("stt")
    assert any(p.get("id") == "groq" for p in providers)


def test_resolve_api_model_uses_hint_when_empty():
    provider = {"model_hint": "meta-llama/llama-4-scout-17b-16e-instruct"}
    model, upgraded = resolve_api_model(provider, {}, default="meta-llama/llama-4-scout-17b-16e-instruct")
    assert upgraded is False
    assert model == "meta-llama/llama-4-scout-17b-16e-instruct"


def test_resolve_api_model_keeps_user_choice():
    provider = {"model_hint": "meta-llama/llama-4-scout-17b-16e-instruct"}
    saved = {"model": "openai/gpt-oss-120b"}
    model, upgraded = resolve_api_model(provider, saved)
    assert upgraded is False
    assert model == "openai/gpt-oss-120b"
