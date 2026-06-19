# Security — DictaDesk

This document helps you avoid leaking private data when using or publishing DictaDesk.

---

## Files that must stay local

| File / folder | Contains |
|---------------|----------|
| `secrets.json` | Groq, ElevenLabs, and other API keys |
| `memory/long_term.json` | User preferences, notes, routines |
| `recordings/` | Microphone audio |
| `transcripts/` | Speech transcription output |
| `screenshots/`, `mappedscreenshots/` | Desktop screenshots |
| `debug_replays/` | Execution debug dumps |
| `last_transcript.txt` | Latest transcription text |
| `llm_models/*.gguf` | Local LLM weights |
| `vosk_models/**` | Vosk STT models |
| `tts_models/**` | Piper TTS models |

All of the above are listed in `.gitignore`.

---

## Pre-push checklist

Run from the project root before every `git push`:

```powershell
# 1. Confirm secrets are ignored
git check-ignore -v secrets.json
# Expected: .gitignore:2:secrets.json

# 2. Confirm no secrets in staged files
git diff --cached | Select-String -Pattern "gsk_|sk-[a-zA-Z0-9]{20,}|xi-api-key"

# 3. Confirm secrets never entered git history
git log --all --full-history -- secrets.json
# Expected: no output

# 4. Review what will be pushed
git status
git diff --stat origin/main
```

If `secrets.json` was ever committed, **rotate all API keys immediately** and use `git filter-repo` or BFG Repo-Cleaner to purge history before pushing again.

---

## Setting up secrets safely

1. Copy the template:
   ```powershell
   copy secrets.json.example secrets.json
   ```
2. Edit `secrets.json` locally only.
3. Never paste real API keys into issues, README, or chat logs.
4. Rotate keys at [Groq Console](https://console.groq.com) if a key may have been exposed.

---

## What is safe to commit

- Source code (`.py`)
- Provider schema JSON (`providers.json`, `llm_providers.json`, etc.) — endpoints only, no keys
- `secrets.json.example` — placeholder values only
- `commands.json` — your custom phrases (review for personal info before committing)
- `MODELS_README.txt` and folder `README.txt` placeholders

---

## Runtime data hygiene

DictaDesk may write sensitive data during normal use:

- Voice recordings in `recordings/`
- Transcripts in `transcripts/`
- Screenshots during VLM/OCR in `screenshots/`

These directories are gitignored. Do not manually `git add` files from them.

---

## Reporting security issues

If you discover a vulnerability, please open a private security advisory on GitHub rather than a public issue.
