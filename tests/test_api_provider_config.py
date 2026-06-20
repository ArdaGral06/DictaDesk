from api_provider_config import list_provider_summaries, load_provider_file


def test_list_provider_summaries():
    rows = list_provider_summaries()
    kinds = {row["kind"] for row in rows}
    assert "stt" in kinds
    assert "llm" in kinds


def test_load_stt_providers():
    providers = load_provider_file("stt")
    assert any(p.get("id") == "groq" for p in providers)
