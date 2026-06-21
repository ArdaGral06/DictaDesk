"""Build chat request payloads for OpenAI-compatible and Anthropic APIs."""

from __future__ import annotations


def api_format(provider: dict) -> str:
    return str(provider.get("api_format") or "openai").strip().lower()


def build_chat_payload(
    provider: dict,
    model: str,
    system_prompt: str,
    user_text: str,
    *,
    max_tokens: int | None = None,
    temperature: float = 0.2,
) -> dict:
    token_limit = max_tokens or int(provider.get("max_tokens", 2048))
    fmt = api_format(provider)
    if fmt == "anthropic":
        return {
            "model": model,
            "max_tokens": token_limit,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_text}],
        }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
        "max_tokens": token_limit,
    }
