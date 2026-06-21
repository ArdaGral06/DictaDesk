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
  "api_format": "openai",
  "max_tokens": 8192,
  "headers": {
    "Authorization": "Bearer {api_key}",
    "Content-Type": "application/json"
  },
  "response_path": ["choices", 0, "message", "content"],
  "timeout_sec": 60
}
```

## Built-in providers (June 2026)

All entries ship ready-made — **no Python changes**. Edit `model_hint` to the exact id from your provider’s docs when they release new models.

### LLM (`llm_providers.json`)

| Provider id | Default `model_hint` | Popular alternatives | API key from |
|-------------|----------------------|----------------------|--------------|
| `groq` | `meta-llama/llama-4-scout-17b-16e-instruct` | Free tier, fast inference | [console.groq.com](https://console.groq.com) |
| `google` | `gemini-2.5-flash` | `gemini-3.1-pro-preview`, `gemini-3.5-flash` | [aistudio.google.com](https://aistudio.google.com) |
| `openai` | `gpt-5.5` | `gpt-5.5-pro`, `gpt-4o` | [platform.openai.com](https://platform.openai.com) |
| `anthropic` | `claude-opus-4-8` | `claude-sonnet-4-6`, `claude-fable-5` | [platform.claude.com](https://platform.claude.com) |
| `xai` | `grok-4.3` | 1M context, vision-capable | [console.x.ai](https://console.x.ai) |
| `deepseek` | `deepseek-v4-flash` | `deepseek-v4-pro` (frontier coding) | [platform.deepseek.com](https://platform.deepseek.com) |
| `mistral` | `mistral-large-latest` | `mistral-small-latest`, `codestral-latest` | [console.mistral.ai](https://console.mistral.ai) |
| `together` | `meta-llama/Llama-4-Scout-17B-16E-Instruct` | Qwen 3, Kimi K2, DeepSeek via Together catalog | [api.together.ai](https://api.together.ai) |
| `fireworks` | `accounts/fireworks/models/deepseek-v3` | Full Fireworks model path from their catalog | [fireworks.ai](https://fireworks.ai) |
| `perplexity` | `sonar-pro` | `sonar`, `sonar-reasoning-pro` (web-aware) | [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api) |
| `openrouter` | `anthropic/claude-opus-4-8` | 100+ models: `google/gemini-3.1-pro-preview`, `x-ai/grok-4.3`, … | [openrouter.ai](https://openrouter.ai) |

Anthropic uses `"api_format": "anthropic"`. All other LLM entries use OpenAI-compatible `"api_format": "openai"`.

Google Gemini uses the [OpenAI-compatible endpoint](https://ai.google.dev/gemini-api/docs/openai) at `generativelanguage.googleapis.com/v1beta/openai/`.

### VLM (`vlm_providers.json`)

Uses OpenAI-style vision payloads (`image_url` in chat messages). Same providers as LLM where vision is supported:

| Provider id | Default `model_hint` | Notes |
|-------------|----------------------|-------|
| `groq` | `meta-llama/llama-4-scout-17b-16e-instruct` | Free tier default |
| `google` | `gemini-2.5-flash` | Strong multimodal; try `gemini-3.1-pro-preview` for hardest tasks |
| `openai` | `gpt-4o` | Also `gpt-5.5` if your account supports vision on that model |
| `xai` | `grok-4.3` | Native video + image input |
| `mistral` | `pixtral-large-latest` | Mistral vision line |
| `together` | `meta-llama/Llama-4-Scout-17B-16E-Instruct` | Pick any vision model from Together catalog |
| `fireworks` | `accounts/fireworks/models/qwen2-vl-72b-instruct` | Edit to match your Fireworks vision model |
| `openrouter` | `google/gemini-2.5-flash` | Route to any vision model on OpenRouter |

### STT (`providers.json`)

OpenAI-compatible multipart `/audio/transcriptions` only:

| Provider id | Default `model_hint` | Notes |
|-------------|----------------------|-------|
| `groq` | `whisper-large-v3-turbo` | Free tier, fast |
| `openai` | `gpt-4o-mini-transcribe` | Also `gpt-4o-transcribe`, `whisper-1` |
| `together` | `openai/whisper-large-v3` | Also NVIDIA Parakeet models on Together |
| `fireworks` | `whisper-v3-turbo` | Also `whisper-v3` |

### TTS (`tts_providers.json`)

| Provider id | Default model / voice | Notes |
|-------------|----------------------|-------|
| `openai` | `gpt-4o-mini-tts` / voice `alloy` | Also `tts-1`, `tts-1-hd`; change voice in JSON or at setup |
| `elevenlabs` | Voice ID required at setup | Multilingual, high quality |
| `together` | `hexgrad/Kokoro-82M` / `af_alloy` | Also `cartesia/sonic-3`, `canopylabs/orpheus-3b-0.1-ft` |

**Setup steps**

1. Open the relevant `*_providers.json` and adjust `"model_hint"` if needed.
2. Restart DictaDesk → setup wizard → pick **API** for that layer (Engine / Agent / VLM / TTS).
3. Choose the provider from the numbered list, paste your API key, then press Enter at the model prompt to accept `model_hint` or type another model id.

**Change model later:** Settings → re-run that layer’s API setup, or edit `secrets.json` / clear the Windows `DictaDesk` credential and restart.

## In-app help

Main menu → **Settings (5)** → **API provider files (10)** lists current files and provider ids.

## Security

- `keyring` is **required** and installed by `install.bat`.
- Keys prefer Windows Credential Manager; `secrets.json` keeps non-secret fields only when keyring is active.
