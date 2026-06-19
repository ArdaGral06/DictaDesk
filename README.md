# DictaDesk

**DictaDesk** is a Windows voice and text automation assistant. Speak or type commands in **Turkish** or **English** — DictaDesk plans what to do and executes it on your PC: open apps, manage files, control volume, automate browsers, and click on-screen elements.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation Guide](#installation-guide)
- [First Run Walkthrough](#first-run-walkthrough)
- [Optional Components](#optional-components)
- [AI Models](#ai-models)
- [Configuration](#configuration)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Licenses](#licenses)

---

## Features

| Layer | What it does |
|-------|--------------|
| **Speech-to-text** | Converts your voice to text (Whisper, Vosk, or Groq API) |
| **LLM planner** | Understands commands and builds an action plan |
| **VLM** | Reads screenshots to find buttons and UI elements |
| **TTS** | Speaks results aloud (Piper or ElevenLabs) |
| **GUI automation** | Clicks and types using Windows UIA, OCR, and PyAutoGUI |
| **Web automation** | Searches, fills forms, and navigates via Playwright |
| **Custom commands** | Map your own phrases in `commands.json` |
| **Safety** | Confirms dangerous actions before running them |

---

## Requirements

| Item | Details |
|------|---------|
| **OS** | Windows 10 or 11 (64-bit) |
| **Python** | 3.12 ([python.org](https://www.python.org/downloads/)) — check **"Add Python to PATH"** during install |
| **Microphone** | Required for voice commands |
| **Internet** | Required for cloud AI (Groq); optional for fully local setup |
| **Disk space** | ~1 GB minimum (Whisper model); Piper voice model ~15–60 MB |
| **Piper TTS** | **Required** — binary + voice model must be installed before DictaDesk starts |

---

## Installation Guide

Follow these steps in order. Each step builds on the previous one.

### Step 1 — Download DictaDesk

```powershell
git clone https://github.com/ArdaGral06/DictaDesk.git
cd DictaDesk
```

Or download the ZIP from GitHub and extract it.

### Step 2 — Create a virtual environment

Open **PowerShell** in the DictaDesk folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If you get an execution policy error:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate again.

### Step 3 — Install Python dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

This installs Whisper, Playwright bindings, OCR libraries, and everything else DictaDesk needs.

### Step 4 — Install Playwright browser (for web automation)

```powershell
playwright install chromium
```

Skip this only if you will never use browser automation (you can disable it in Settings).

### Step 5 — Install Tesseract OCR (for clicking text on screen)

Tesseract reads text visible on your screen. **DictaDesk uses both English and Turkish OCR**, so you need both language packs.

#### 5a. Install Tesseract

1. Download the Windows installer from [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
2. Run the installer (64-bit).
3. During setup, enable **"Add to PATH"** if offered.
4. Note the install path — usually:
   ```
   C:\Program Files\Tesseract-OCR\
   ```

#### 5b. Add the Turkish language pack

The default installer includes **English** only. Turkish must be added manually:

1. Download `tur.traineddata` from the official tessdata repository:  
   [github.com/tesseract-ocr/tessdata/raw/main/tur.traineddata](https://github.com/tesseract-ocr/tessdata/raw/main/tur.traineddata)
2. Copy the file into the Tesseract `tessdata` folder:
   ```
   C:\Program Files\Tesseract-OCR\tessdata\tur.traineddata
   ```
3. Verify both languages are available — open PowerShell:
   ```powershell
   tesseract --list-langs
   ```
   You should see `eng` and `tur` in the list.

#### 5c. Tell DictaDesk where Tesseract is (if needed)

If `tesseract` is not found automatically, open `config.py` and set:

```python
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Run **Self-check** (main menu option 3) after setup — the OCR line should show OK.

### Step 6 — Install Piper TTS (required)

DictaDesk requires Piper to be installed before it will start. You can disable spoken feedback later in the TTS menu, but the binary and voice model must be present.

#### 6a. Download the voice model

1. Download both files from [rhasspy/piper-voices on Hugging Face](https://huggingface.co/rhasspy/piper-voices) (recommended: `en_US-joe-medium`):
   - `en_US-joe-medium.onnx`
   - `en_US-joe-medium.onnx.json`
2. Place them in:
   ```
   tts_models/piper/en_US-joe-medium.onnx
   tts_models/piper/en_US-joe-medium.onnx.json
   ```

#### 6b. Download the Piper executable

1. Download `piper.exe` for Windows from [Piper releases](https://github.com/rhasspy/piper/releases).
2. Use one of these options:
   - Put `piper.exe` in `DictaDesk/piper/piper.exe`, **or**
   - Add the folder containing `piper.exe` to your system PATH, **or**
   - Set the full path in `config.py`:
     ```python
     PIPER_BIN = r"C:\path\to\piper.exe"
     ```

If Piper is missing, DictaDesk exits with: *"Piper is required. Piper binary and model (.onnx + .onnx.json) not found."*

See `tts_models/MODELS_README.txt` for more details.

### Step 7 — Allow microphone access

Windows **Settings → Privacy & security → Microphone** → enable access for desktop apps.

### Step 8 — Start DictaDesk

```powershell
python voice_control.py
```

---

## First Run Walkthrough

When DictaDesk starts for the first time, it asks a few setup questions. Here is the recommended path for a new user.

### 1. UI language

```
Choose UI language (tr/en): tr
```
Pick `tr` for Turkish or `en` for English.

### 2. Speech-to-text (STT)

| Choice | When to use |
|--------|-------------|
| **1 — Local Whisper** | Easiest start. Downloads ~500 MB on first use. Works offline. **Recommended.** |
| **2 — Local Vosk** | Fully offline, lighter. Requires downloading a model first — see [Vosk models](#vosk-speech-models). |
| **3 — Groq API** | Best accuracy. Free tier at [console.groq.com](https://console.groq.com). Paste your API key when prompted — DictaDesk saves it automatically. |

### 3. Text-to-speech (TTS)

Piper must already be installed (Step 6). At this prompt you choose whether to **use** it:

| Choice | When to use |
|--------|-------------|
| **1 — Off** | No spoken feedback, but Piper is still required to be installed. |
| **2 — Local Piper** | Spoken feedback using your installed Piper model. |
| **3 — ElevenLabs API** | Cloud voice instead of Piper. Requires an ElevenLabs API key. |

### 4. LLM planner (Agent)

| Choice | When to use |
|--------|-------------|
| **1 — Off** | Only custom commands and simple built-in parsers work. Limited. |
| **2 — Local Phi-3.5** | Offline planning. Requires a GGUF model — see [Local LLM](#local-llm). |
| **3 — Groq API** | **Recommended.** Natural language commands. Paste API key when prompted. |

> Get a free Groq API key at [console.groq.com/keys](https://console.groq.com/keys).

### 5. VLM (screen vision)

| Choice | When to use |
|--------|-------------|
| **1 — Off** | Fine if you mostly open apps, adjust volume, etc. |
| **3 — Groq API** | Needed for complex GUI tasks like "click the Sign Up button". Uses the same Groq key. |

### 6. Enter Control mode

From the main menu, select **1 — Control mode**.

- Press **Ctrl+Shift+6** to start recording, speak your command, press again to stop.
- Or type a command and press Enter.

**Try these first commands:**

| Turkish | English | What happens |
|---------|---------|--------------|
| `sesi yükselt` | `volume up` | Raises system volume |
| `notepad aç` | `open notepad` | Opens Notepad |
| `chrome aç` | `open chrome` | Opens Chrome |

Run **Self-check** (menu 3) anytime to verify all components.

---

## Optional Components

### Groq API (cloud AI)

Free tier available. One key works for STT, LLM, and VLM.

1. Create an account at [console.groq.com](https://console.groq.com).
2. Generate an API key.
3. When DictaDesk asks during setup, paste the key and press Enter.
4. Keys are stored locally in `secrets.json` (created automatically on first use).

### Vosk speech models

Only needed if you chose Vosk instead of Whisper.

1. Download from [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models):
   - Turkish: `vosk-model-small-tr-0.3`
   - English: `vosk-model-small-en-us-0.15`
2. Extract to:
   ```
   vosk_models/tr/vosk-model-small-tr-0.3/
   vosk_models/en/vosk-model-small-en-us-0.15/
   ```

See `vosk_models/MODELS_README.txt` for details.

### Local LLM

Only needed for fully offline command planning.

1. Download a Phi-3.5-mini-instruct GGUF file (Q4_K_M recommended) from [Hugging Face](https://huggingface.co/models?search=Phi-3.5-mini-instruct+gguf).
2. Place the `.gguf` file in `llm_models/`.
3. Install the optional dependency:
   ```powershell
   pip install -r requirements-optional.txt
   ```
4. At startup, choose **LLM → 2 — Local Agent**.

See `llm_models/MODELS_README.txt` for details.

---

## AI Models

| Component | Default (easiest) | Offline alternative | Cloud alternative |
|-----------|--------------------|--------------------|-------------------|
| **STT** | Whisper `small` (auto-download) | Vosk TR/EN | Groq Whisper |
| **LLM** | — | Phi-3.5 GGUF | Groq Llama / GPT-OSS |
| **VLM** | — | Not available | Groq Llama Scout |
| **TTS** | Off | Piper | ElevenLabs |

Model files are **not bundled** with DictaDesk due to size. Download instructions are in each model folder's `MODELS_README.txt`.

### Recommended setups

| Profile | STT | LLM | VLM | TTS | Internet |
|---------|-----|-----|-----|-----|----------|
| **Quick start** | Whisper | Groq API | Off | Off | For LLM only |
| **Fully offline** | Whisper or Vosk | Phi-3.5 GGUF | — | Piper | Not needed |
| **Full features** | Groq | Groq | Groq | Piper or ElevenLabs | Required |

---

## Configuration

Most settings are chosen at startup. Advanced options live in these files:

| File | Purpose |
|------|---------|
| `config.py` | Model sizes, Tesseract path, app aliases, timeouts |
| `commands.json` | Your custom voice command phrases |
| `secrets.json` | API keys — created automatically when you enter them at startup |
| `actions_manifest.json` | All supported actions and safety levels |

### API keys

DictaDesk prompts for API keys during first-time setup and saves them to `secrets.json`. You do not need to create this file manually.

To change keys later, delete the relevant section from `secrets.json` and restart — DictaDesk will ask again.

---

## Architecture

```
User (voice / text)
        │
        ▼
   Audio capture + VAD          (audio_io.py)
        │
        ▼
   Speech-to-text              (engine.py / transcriber.py)
        │
        ▼
   Command routing              (commands_manager → heuristics → llm_engine)
        │
        ▼
   Context building             (memory, open windows, UIA, optional VLM)
        │
        ▼
   Action execution             (platform_actions, uia_automation, web_automation)
        │
        ▼
   Verification + error policy  (action_verifier, agent_error_policy)
        │
        ▼
   Feedback                     (ui_popup, tts_engine)
```

### Key modules

| Module | Role |
|--------|------|
| `main.py` / `voice_control.py` | Entry point and main menu |
| `control_mode.py` | Live control loop (`ControlSession`), hotkey, job queue |
| `engine.py` | STT engine selection with automatic fallback |
| `llm_engine.py` | LLM prompts and JSON action parsing |
| `vlm_engine.py` | Screenshot analysis for GUI targeting |
| `platform_actions.py` | Windows automation — apps, files, hotkeys, OCR clicks |
| `web_automation.py` | Playwright browser control |
| `action_verifier.py` | Confirms each action succeeded |
| `i18n.py` | Turkish and English UI strings |

### Command routing order

1. Custom phrase match (`commands.json`)
2. Built-in parsers (volume, brightness, scroll, browser detection)
3. LLM planner (natural language → JSON actions)
4. On failure: skip, retry, replan, or abort

### Control mode hotkey

**Ctrl+Shift+6** — hold Ctrl+Shift, press 6 to toggle recording.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python` not recognized | Reinstall Python with **"Add to PATH"** checked |
| `pip install` fails | Upgrade pip: `python -m pip install --upgrade pip` |
| App exits immediately on start | Run `pip install -r requirements.txt` inside your virtual environment |
| App exits before main menu | Install Piper — see Step 6 (`piper.exe` + `.onnx` model in `tts_models/piper/`) |
| No STT available | Install requirements; Whisper needs `faster-whisper` |
| Whisper very slow first time | Normal — the model is downloading (~500 MB). Wait or use Groq API |
| Microphone not detected | Check Windows microphone privacy settings; run Self-check (menu 3) |
| OCR fails / Turkish text not read | Install Tesseract; add `tur.traineddata` to tessdata folder (see Step 5) |
| `tesseract is not installed` | Set `TESSERACT_CMD` in `config.py` to full path of `tesseract.exe` |
| `eng+tur` OCR error | Both `eng.traineddata` and `tur.traineddata` must exist in tessdata |
| Web automation fails | Run `playwright install chromium` |
| Groq API error | Check your key at [console.groq.com/keys](https://console.groq.com/keys); verify internet connection |
| Piper TTS not working | Verify `piper.exe` path and both `.onnx` + `.json` files in `tts_models/piper/` |
| Local LLM won't load | Run `pip install -r requirements-optional.txt`; place `.gguf` in `llm_models/` |
| Vosk model not found | Follow `vosk_models/MODELS_README.txt` |
| GUI clicks miss the target | Ensure Tesseract is installed; try higher screen scaling awareness; use VLM for complex UIs |
| Permission / access denied | Run PowerShell as Administrator only if launching protected apps |

---

## Licenses

Third-party library licenses: **[THIRD_PARTY.md](THIRD_PARTY.md)**

Project source: **[LICENSE](LICENSE)**

AI models (Whisper, Phi-3.5, Vosk, Piper voices, Groq, ElevenLabs) are subject to their own licenses and terms of service.

---

**DictaDesk** — control your PC with your voice on Windows.
