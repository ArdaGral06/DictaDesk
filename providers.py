import json

from config import PROVIDERS_JSON


def _default_providers():
    return {
        "providers": [
            {
                "id": "groq",
                "label": "Groq",
                "endpoint": "https://api.groq.com/openai/v1/audio/transcriptions",
                "model_hint": "whisper-large-v3-turbo",
                "headers": {"Authorization": "Bearer {api_key}"},
                "fields": {"file": "file", "model": "model", "language": "language"},
                "response_text_field": "text",
                "response_segments_field": "segments",
                "timeout_sec": 60,
            },
            {
                "id": "custom",
                "label": "Custom (edit providers.json)",
                "endpoint": "",
                "model_hint": "",
                "headers": {"Authorization": "Bearer {api_key}"},
                "fields": {"file": "file", "model": "model", "language": "language"},
                "response_text_field": "text",
                "response_segments_field": "segments",
                "timeout_sec": 60,
            },
        ]
    }


def load_providers():
    if PROVIDERS_JSON.exists():
        try:
            raw = json.loads(PROVIDERS_JSON.read_text(encoding="utf-8"))
            providers = raw.get("providers", [])
            if isinstance(providers, list) and providers:
                return providers
        except Exception:
            pass

    defaults = _default_providers()
    PROVIDERS_JSON.write_text(
        json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return defaults["providers"]


def validate_provider(provider: dict) -> dict:
    errors = []
    warnings = []

    if not isinstance(provider, dict):
        return {"errors": ["provider_not_dict"], "warnings": warnings}

    provider_id = provider.get("id")
    if not provider_id or not isinstance(provider_id, str):
        errors.append("missing_id")

    label = provider.get("label")
    if not label or not isinstance(label, str):
        warnings.append("missing_label")

    endpoint = provider.get("endpoint")
    if not endpoint or not isinstance(endpoint, str):
        if provider_id == "custom":
            warnings.append("missing_endpoint")
        else:
            errors.append("missing_endpoint")
    elif not endpoint.lower().startswith("http"):
        warnings.append("endpoint_not_http")

    headers = provider.get("headers", {})
    if not isinstance(headers, dict):
        warnings.append("headers_not_dict")
    else:
        uses_key = any(
            isinstance(v, str) and "{api_key}" in v for v in headers.values()
        )
        if not uses_key:
            warnings.append("headers_no_api_key")

    fields = provider.get("fields", {})
    if not isinstance(fields, dict):
        errors.append("fields_not_dict")
    else:
        if not fields.get("file"):
            errors.append("missing_file_field")
        if not fields.get("model"):
            errors.append("missing_model_field")
        if not fields.get("language"):
            warnings.append("missing_language_field")

    text_field = provider.get("response_text_field")
    if not text_field:
        warnings.append("missing_text_field")

    timeout = provider.get("timeout_sec")
    if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
        warnings.append("bad_timeout")

    return {"errors": errors, "warnings": warnings}


def validate_providers(providers: list) -> list:
    seen = set()
    results = []
    for provider in providers:
        report = validate_provider(provider)
        provider_id = provider.get("id") if isinstance(provider, dict) else None
        if provider_id:
            if provider_id in seen:
                report["errors"].append("duplicate_id")
            seen.add(provider_id)
        report["id"] = provider_id or "unknown"
        report["label"] = (
            provider.get("label") if isinstance(provider, dict) else "unknown"
        )
        results.append(report)
    return results
