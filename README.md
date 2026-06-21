# DictaDesk

**DictaDesk** is a Windows voice and text automation assistant. Speak or type commands in **Turkish** or **English** — DictaDesk plans what to do and executes it on your PC: open apps, manage files, control volume, automate browsers, and click on-screen elements.

> **Note**  
> Built and tested by **one developer** on one machine. Stability may vary on different PCs.  
> Bugs or confusion? Please [open an issue](https://github.com/ArdaGral06/DictaDesk/issues) — feedback is welcome.

---

## Quick setup (start here)

| Step | Action |
|------|--------|
| **0** | [Download ZIP](https://github.com/ArdaGral06/DictaDesk) or `git clone`, then extract |
| **1** | Install **Python 3.12** from [python.org](https://www.python.org/downloads/) — check **Add Python to PATH** |
| **2** | Install **Tesseract OCR** (required) — [UB Mannheim Windows installer](https://github.com/UB-Mannheim/tesseract/wiki). During setup, enable **Add to PATH** if offered. DictaDesk uses OCR to read on-screen text (Turkish + English) for clicks and GUI automation. |
| **3** | Double-click **`install.bat`** — wait for **Setup complete**. This also fetches the **Turkish OCR language pack** if Tesseract is installed. |
| **4** | Double-click **`start.bat`** every time you use DictaDesk |

**Beginner guides:** **`GETTING_STARTED.txt`** (English) · **`GETTING_STARTED_TR.txt`** (Turkish)

**First-run menu (recommended):**

| Prompt | Choose |
|--------|--------|
| UI language | `tr` or `en` |
| STT | **1 — Whisper** or **3 — Groq API** (free key) |
| TTS | **1 — Off** (Piper is installed; you skip spoken feedback) |
| LLM | **3 — Groq API** — key from [console.groq.com/keys](https://console.groq.com/keys) |
| VLM | **1 — Off** (enable later for vision-based clicks) |

Then: main menu → **1 — Control mode** → **Ctrl+Shift+6** to record, speak, press again to stop.

**Try:** `sesi yükselt` / `volume up` · `notepad aç` / `open notepad` · `chrome'da ara` / GUI text clicks  
**Verify:** main menu → **3 — Self-check** (checks Tesseract + Turkish OCR pack)

Local LLM, Vosk, and cloud TTS are optional extras. Tesseract is **required** for full DictaDesk functionality.

PATH not working after install? See **[Adding Python and Tesseract to PATH](#adding-python-and-tesseract-to-path-windows-10--11)** below.

---

## Features

| Layer | What it does |
|-------|--------------|
| **Speech-to-text** | Whisper, Vosk, or cloud API |
| **LLM planner** | Natural-language commands → action plan |
| **VLM** | Screenshot analysis for GUI targeting |
| **TTS** | Spoken feedback (Piper or cloud) |
| **GUI automation** | UIA, OCR, PyAutoGUI |
| **Web automation** | Playwright browser control |
| **Custom commands** | Your phrases in `commands.json` |
| **Safety** | Confirms dangerous actions first |

---

## Requirements

| Item | Details |
|------|---------|
| **OS** | Windows 10 or 11 (64-bit) |
| **Python** | 3.12 — **Add to PATH** during install |
| **Tesseract OCR** | **Required** — screen text recognition (TR + EN). [Install guide](https://github.com/UB-Mannheim/tesseract/wiki) |
| **Microphone** | For voice commands |
| **Internet** | For cloud AI; optional if fully local |
| **Disk** | ~3–4 GB for default install |
| **Piper** | Installed by `install.bat` (required files; TTS can be Off in menu) |

---

## Adding Python and Tesseract to PATH (Windows 10 & 11)

Both tools must be reachable from **Command Prompt** or **PowerShell** (`python --version` and `tesseract --version`). Steps are the same on Windows 10 and 11.

### Python 3.12 — recommended (during install)

1. Download **Python 3.12** from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer.
3. On the **first screen**, check **Add python.exe to PATH** (bottom of the window).
4. Click **Install Now** (or **Customize installation** if you prefer, but keep PATH checked).
5. Close the installer, **open a new** Command Prompt, and verify:

```text
python --version
pip --version
```

You should see `Python 3.12.x`. If not, use the manual method below.

### Python — already installed without PATH (fix with Modify)

1. Run the **same** Python 3.12 installer again from python.org.
2. Choose **Modify** (not Uninstall).
3. Enable **Add python.exe to PATH**.
4. Finish, then open a **new** terminal and run `python --version`.

### Python — add PATH manually

1. Find your install folder. Typical path:

   `C:\Users\<YourName>\AppData\Local\Programs\Python\Python312`

   Also note the **Scripts** subfolder:

   `C:\Users\<YourName>\AppData\Local\Programs\Python\Python312\Scripts`

   *(Start menu → search **Python 3.12** → right‑click → Open file location → Open file location again to find the folder.)*

2. Press **Win + S**, search **Edit the system environment variables**, open it.
3. Click **Environment Variables…**
4. Under **User variables** (your account) or **System variables** (all users), select **Path** → **Edit**.
5. Click **New** and add the **Python312** folder path.
6. Click **New** again and add the **Python312\Scripts** folder path.
7. Click **OK** on every window.
8. **Close and reopen** Command Prompt / PowerShell, then run `python --version`.

**Tip:** On Windows you can also use `py -3.12` if the [Python Launcher](https://docs.python.org/3/using/windows.html) is installed, even when `python` is not on PATH. DictaDesk’s `install.bat` still works best when `python` is on PATH.

**Store Python alias:** If `python` opens the Microsoft Store instead, go to **Settings → Apps → Advanced app settings → App execution aliases** and turn off **python.exe** / **python3.exe** aliases, then retry.

---

### Tesseract OCR — during install (UB Mannheim)

1. Download the Windows installer from **[UB Mannheim Tesseract wiki](https://github.com/UB-Mannheim/tesseract/wiki)** (64-bit `.exe`).
2. Run the installer.
3. Note the install folder — default is usually:

   `C:\Program Files\Tesseract-OCR`

4. If the installer offers **Add to PATH** or **Add to system PATH**, enable it.
5. Finish install, open a **new** Command Prompt, and verify:

```text
tesseract --version
```

6. Run **`install.bat`** again so DictaDesk can download **`tur.traineddata`** (Turkish) into the `tessdata` folder.

### Tesseract — add PATH manually

1. Confirm `tesseract.exe` exists, e.g.:

   `C:\Program Files\Tesseract-OCR\tesseract.exe`

2. **Win + S** → **Edit the system environment variables** → **Environment Variables…**
3. Under **System variables** (recommended for Tesseract) or **User variables**, select **Path** → **Edit**.
4. Click **New** and paste the folder path only (not the `.exe` file):

   `C:\Program Files\Tesseract-OCR`

5. Click **OK** on all dialogs.
6. Open a **new** Command Prompt and run:

```text
tesseract --version
```

### Tesseract — optional `TESSDATA_PREFIX` (if language files are not found)

Only needed if OCR says language data is missing and files are in the default `tessdata` folder:

1. **Environment Variables…** → **System variables** → **New**
2. Variable name: `TESSDATA_PREFIX`
3. Variable value: `C:\Program Files\Tesseract-OCR\tessdata`
4. OK, new terminal, run **`install.bat`** once more for Turkish/English packs.

### Verify both before DictaDesk

```text
python --version
tesseract --version
```

Then run **`install.bat`**, then **`start.bat`**. Main menu → **3 — Self-check** should report Tesseract OK.

---

## Performance tips

| Setup | Impact |
|-------|--------|
| **Light** (Groq STT + Groq LLM, VLM/TTS off) | Very low — best for most PCs |
| **Balanced** (local Whisper + Groq LLM) | Short CPU spike while transcribing |
| **Heavy / offline** (Whisper + local LLM + OCR) | Needs 16 GB+ RAM recommended |

**Reduce load:** use Groq for STT/LLM, keep VLM off, choose TTS → Off, use Whisper `tiny`/`base` in `config.py` on weak PCs.

---

## Configuration

| File | Purpose |
|------|---------|
| `commands.json` | Custom voice phrases |
| `providers.json`, `llm_providers.json`, `vlm_providers.json`, `tts_providers.json` | Cloud API endpoints — see **[API_PROVIDERS.md](API_PROVIDERS.md)** |
| `secrets.json` | Provider settings (model name, provider id); **not** the raw API key when keyring is active |
| `config.py` | Advanced: Whisper size, Tesseract path (`TESSERACT_CMD`), timeouts |

### API keys — Windows Credential Manager

`install.bat` installs **`keyring`**. When possible, API keys are stored in **Windows Credential Manager**, not in plain text in the repo.

**Open Credential Manager (Windows 10 & 11):**

| Language | How to open |
|----------|-------------|
| **English UI** | **Win + S** → type **Credential Manager** → open **Credential Manager** → **Windows Credentials** |
| **Turkish UI** | **Win + S** → **Kimlik Bilgileri Yöneticisi** → **Windows Kimlik Bilgileri** |

Or: **Control Panel** → **User Accounts** → **Credential Manager** → **Windows Credentials**.

**DictaDesk entries** look like service names, for example:

- `llm:groq` — Agent / LLM (Groq)
- `stt:groq` — speech-to-text
- `vlm:groq` — vision
- `tts:elevenlabs` — cloud TTS

**Change an API key (recommended):**

1. Open **Windows Credentials** as above.
2. Find the **DictaDesk** entry for the service you use (e.g. `llm:groq`).
3. Click the entry → **Edit** (or **Düzenle** in Turkish).
4. In the **Password** field you will see JSON, for example:

   `{"api_key": "gsk_...", "model": "meta-llama/llama-4-scout-17b-16e-instruct"}`

5. Replace the `api_key` value. Keep `"model"` if present.
6. Save → **restart DictaDesk**.

**Reset and enter again in the app:**

1. Delete that **DictaDesk** credential entry in Credential Manager, **or** remove the matching block from `secrets.json`.
2. Restart DictaDesk → choose API mode → paste the new key when prompted.

**Change provider or model (no key change):** edit `*_providers.json` or use **Settings → API provider files (10)**. See **[API_PROVIDERS.md](API_PROVIDERS.md)**. Restart after saving.

Other cloud providers (OpenAI, Anthropic, Google Gemini, DeepSeek, …) are preconfigured in `llm_providers.json` — no Python code changes needed.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python` not found | Reinstall Python 3.12 with **Add to PATH** |
| Setup / venv missing | Run **`install.bat`** or **`start.bat`** |
| Piper missing | Re-run **`install.bat`** with internet |
| Tesseract missing / OCR fails | Install [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki), then run **`install.bat`** again for Turkish pack |
| No speech recognition | Run Self-check (menu 3); install requirements in `.venv` |
| Whisper slow first time | First download ~500 MB — wait, or use Groq STT |
| `eng+tur` OCR error | Both `eng.traineddata` and `tur.traineddata` must exist — re-run **`install.bat`** after Tesseract install |
| Groq / API errors | Check key and internet; see **API_PROVIDERS.md** |
| PC slow during commands | Switch STT/LLM to Groq API; disable VLM |

More detail: **GETTING_STARTED.txt** / **GETTING_STARTED_TR.txt**

---

## What this README covers (and what moved elsewhere)

**Still in this README**

| Section | Contents |
|---------|----------|
| **Quick setup** | Download → Python → Tesseract → `install.bat` → `start.bat` + first-run menu |
| **Requirements** | OS, Python, Tesseract, disk, Piper |
| **PATH guide** | Python & Tesseract on Windows 10/11 (installer + manual) |
| **Performance tips** | Light / balanced / heavy setups (short) |
| **Configuration** | Config files + **Credential Manager** step-by-step |
| **Troubleshooting** | Common fixes |
| **Licenses** | Links to LICENSE / THIRD_PARTY |

**Removed from README** (to keep GitHub page short — details live in other files)

| Old README section | Where to look now |
|--------------------|-------------------|
| Long **System Resource Usage** (RAM/CPU per model, disk breakdown) | **Performance tips** above + `config.py` (`LOCAL_MODEL_SIZE`) |
| **Installation Guide** (manual venv, pip, Playwright steps) | **`install.bat`** / **GETTING_STARTED.txt** |
| **Architecture** (module diagram, `desk_platform/_impl.py`) | Source code; not needed for end users |
| **AI Models** tables (Whisper sizes, Groq model list) | **`API_PROVIDERS.md`**, `llm_models/MODELS_README.txt`, `vosk_models/` |
| **Optional Components** (Vosk, local LLM walkthrough) | Model folder READMEs + in-app setup wizard |
| Duplicate **Quick Install** / Piper FAQ | Quick setup + GETTING_STARTED guides |
| Table of contents (long anchor list) | Section headers above |

---

## Licenses

Third-party libraries: **[THIRD_PARTY.md](THIRD_PARTY.md)** · Project: **[LICENSE](LICENSE)**

AI models and cloud services have their own terms (Whisper, Groq, OpenAI, etc.).
