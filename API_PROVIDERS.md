# API Provider Configuration

DictaDesk uses **JSON files** for cloud API endpoints. You can switch providers or update URLs/models **without editing Python code**.

Restart DictaDesk after saving changes.

## Files

| File | Used for | At startup menu |
|------|----------|-----------------|
| `providers.json` | Speech-to-text (STT) | Engine → API |
| `llm_providers.json` | Agent / planner (LLM) | Agent → API |
| `vlm_providers.json` | Vision / screenshot AI (VLM) | VLM → API |
| `tts_providers.json` | Cloud text-to-speech | TTS → API |

Each file contains a `"providers"` array. Every entry needs at least:

- `"id"` — short name (shown in menus)
- `"label"` — display name
- `"endpoint"` — full HTTPS URL (may include `{voice_id}` for TTS)
- `"headers"` — use `{api_key}` placeholder where needed

## API keys (separate from endpoints)

Keys are **not** stored in these JSON files. DictaDesk prompts at first use and saves them via **Windows Credential Manager** (`keyring`) when available, with metadata in `secrets.json`.

To change a key: remove that provider block from `secrets.json` (or clear the Windows credential `DictaDesk`) and restart.

## Switching from Groq to another API

1. Open the relevant `*_providers.json` file.
2. Either edit the `groq` entry’s `endpoint` and `model_hint`, **or** use the built-in `"custom"` entry:
   - Set `"endpoint"` to your provider URL
   - Set `"model_hint"` to the default model name
   - Fill `"headers"` / `"response_path"` to match the provider’s API shape
3. Save the file and restart DictaDesk.
4. At startup, choose API mode and pick **Custom** (or your provider id).

### STT example (`providers.json`)

OpenAI-compatible transcription:

```json
{
  "id": "custom",
  "label": "My STT API",
  "endpoint": "https://api.example.com/v1/audio/transcriptions",
  "model_hint": "whisper-1",
  "headers": { "Authorization": "Bearer {api_key}" },
  "fields": { "file": "file", "model": "model", "language": "language" },
  "response_text_field": "text",
  "timeout_sec": 60
}
```

### LLM / VLM example

OpenAI-style chat completions:

```json
{
  "id": "custom",
  "label": "My LLM",
  "endpoint": "https://api.example.com/v1/chat/completions",
  "model_hint": "your-model-id",
  "max_tokens": 8192,
  "headers": {
    "Authorization": "Bearer {api_key}",
    "Content-Type": "application/json"
  },
  "response_path": ["choices", 0, "message", "content"],
  "timeout_sec": 60
}
```

## In-app help

Main menu → **Settings (5)** → **API provider files (10)** lists current files and provider ids.

## Security

- `keyring` is **required** and installed by `install.bat`.
- Keys prefer Windows Credential Manager; `secrets.json` keeps non-secret fields only when keyring is active.
