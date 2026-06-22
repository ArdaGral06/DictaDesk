# DictaDesk

**DictaDesk** is a Windows voice and text automation assistant. Speak or type commands in **Turkish** or **English** — DictaDesk plans what to do and executes it on your PC: open apps, manage files, control volume, automate browsers, and click on-screen elements.

> **Note**  
> Built and tested by **one developer** on one machine. Stability may vary on different PCs.  
> Bugs or confusion? Please [open an issue](https://github.com/ArdaGral06/DictaDesk/issues) — feedback is welcome.

---

## Quick setup (start here)

DictaDesk installs itself. **You only run one file.**

| Step | Action |
|------|--------|
| **1** | [Download ZIP](https://github.com/ArdaGral06/DictaDesk) or `git clone`, then extract |
| **2** | Double-click **`install.bat`** — wait for **Setup complete** |
| **3** | Double-click **`start.bat`** every time you use DictaDesk |

`install.bat` does **everything automatically**, with no manual configuration:

- Installs **Python 3.12** if missing (downloaded silently, added to PATH)
- Installs **Tesseract OCR** + Turkish pack (downloaded, added to PATH, written to `config.py`)
- Installs all Python packages, **Piper TTS**, and the **Playwright** browser
- Detects your **GPU** (NVIDIA / AMD / none) and installs **only** the matching local-AI backend — AMD wheels are never downloaded on an NVIDIA-only PC, and vice-versa

> A Windows security (UAC) prompt may appear **once** while Tesseract installs — click **Yes**. That is the only click required.

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
**Verify:** main menu → **3 — Self-check** (checks Tesseract, Turkish OCR pack, and the GPU/CPU backend)

Vosk and cloud TTS are optional extras. Everything required is installed by `install.bat`.

Rare: if automatic Python/Tesseract install is blocked (offline, locked-down PC), see **[Adding Python and Tesseract to PATH](#adding-python-and-tesseract-to-path-windows-10--11)** for the manual fallback.

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
| **Python** | 3.12 — **auto-installed** by `install.bat` if missing |
| **Tesseract OCR** | **Auto-installed** by `install.bat` (download + PATH + Turkish pack) |
| **GPU** | Optional — NVIDIA or AMD auto-detected; the right backend is installed for you |
| **Microphone** | For voice commands |
| **Internet** | Needed during setup (downloads); optional afterwards if fully local |
| **Disk** | ~3–4 GB for default install |
| **Piper** | Installed by `install.bat` (required files; TTS can be Off in menu) |

> The manual PATH guide below is only a **fallback** for locked-down machines where the automatic installer cannot run.

---

## Adding Python and Tesseract to PATH (Windows 10 & 11)

Both tools must be reachable from **Command Prompt** or **PowerShell** (`python --version` and `tesseract --version`). The steps below work the same on **Windows 10** and **Windows 11**.

> **Important difference**  
> - **Python** (python.org installer): can add itself to PATH — check **Add python.exe to PATH** on the **first** setup screen.  
> - **Tesseract** (UB Mannheim `.exe`): **does not** add PATH for you. You install the program, then edit PATH manually in Windows (or set `TESSERACT_CMD` in `config.py` — see Tesseract section).

### Open Environment Variables (same on Windows 10 & 11)

Use **any** of these:

| Method | What to do |
|--------|------------|
| **Start search** | **Win + S** → type **Edit the system environment variables** → open it → **Environment Variables…** |
| **Turkish UI** | **Win + S** → **Sistem ortam değişkenlerini düzenle** → **Ortam Değişkenleri…** |
| **Run dialog** | **Win + R** → type `sysdm.cpl` → Enter → **Advanced** tab → **Environment Variables…** |
| **Settings path** | **Settings → System → About → Advanced system settings** → **Environment Variables…** |

In **Environment Variables**:

- **User variables** → **Path** → affects only your account (enough for DictaDesk).
- **System variables** → **Path** → affects all users (needs admin; fine for Tesseract in `Program Files`).

Select **Path** → **Edit** → **New** → paste a folder path → **OK** on every window.  
Always **close and reopen** Command Prompt / PowerShell after changing PATH.

---

### Python 3.12 — add to PATH during install (recommended)

The official **python.org** installer is the only step where “Add to PATH” is built in:

1. Download **Python 3.12** from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer.
3. On the **very first screen**, at the bottom, check **Add python.exe to PATH**.
4. Click **Install Now**.
5. Close the installer, open a **new** Command Prompt, and verify:

```text
python --version
pip --version
```

You should see `Python 3.12.x`. If not, use **Modify** or manual PATH below.

### Python — already installed without PATH (fix with Modify)

1. Run the **same** Python 3.12 installer again from python.org.
2. Choose **Modify** (not Uninstall).
3. Enable **Add python.exe to PATH**.
4. Finish, then open a **new** terminal and run `python --version`.

### Python — add PATH manually

1. Find your install folder. Typical path:

   `C:\Users\<YourName>\AppData\Local\Programs\Python\Python312`

   Also add the **Scripts** subfolder:

   `C:\Users\<YourName>\AppData\Local\Programs\Python\Python312\Scripts`

   *(Start menu → search **Python 3.12** → right‑click → Open file location → Open file location again.)*

2. Open **Environment Variables** (table above).
3. Select **Path** → **Edit** → **New** → paste the **Python312** folder.
4. **New** again → paste **Python312\Scripts**.
5. **OK** on all windows → **new** terminal → `python --version`.

**Tip:** You can use `py -3.12` if the Python Launcher is installed, but DictaDesk’s `install.bat` works best when `python` is on PATH.

**Microsoft Store alias:** If `python` opens the Store, go to **Settings → Apps → Advanced app settings → App execution aliases** and turn off **python.exe** / **python3.exe**.

---

### Tesseract OCR — install, then add PATH manually (required)

The **[UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)** Windows installer (e.g. `tesseract-ocr-w64-setup-….exe`) walks through language packs and install location. It **does not** show an “Add to PATH” option. After **Finish**, add PATH yourself.

#### 1) Install Tesseract

1. Download the **64-bit** `.exe` from the [UB Mannheim wiki](https://github.com/UB-Mannheim/tesseract/wiki).
2. Run the installer → accept license → choose components (defaults are fine; keep **English** language data).
3. On **Choose install location**, note the folder — almost always:

   `C:\Program Files\Tesseract-OCR`

   Copy this path; you will paste it into PATH in the next step.
4. Click **Install** → **Finish**.
5. Confirm the file exists:

   `C:\Program Files\Tesseract-OCR\tesseract.exe`

   At this point `tesseract --version` in CMD will usually **fail** (“not recognized”) — that is normal until PATH is set.

#### 2) Add Tesseract folder to PATH (Windows 10 & 11)

1. Open **Environment Variables** (see table at top of this section).
2. Under **System variables** (recommended) or **User variables**, select **Path** → **Edit**.
3. Click **New**.
4. Paste **only the folder** (no `\tesseract.exe` at the end):

   `C:\Program Files\Tesseract-OCR`

5. Click **OK** on every dialog (**Edit environment variable** → **Environment Variables** → **System Properties**).
6. **Close all** Command Prompt / PowerShell windows. Open a **new** one.
7. Verify:

```text
tesseract --version
```

You should see `tesseract 5.x…`. If it still fails, reboot once or check the path spelling.

#### 3) Turkish language pack + DictaDesk

1. Run **`install.bat`** — it downloads **`tur.traineddata`** into `tessdata` when Tesseract is detected.
2. Self-check (menu **3**) should report Tesseract OK.

#### Alternative — skip PATH (advanced)

If you cannot edit PATH, set the full path in `config.py`:

```python
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Restart DictaDesk. PATH is still preferred.

#### Optional — `TESSDATA_PREFIX` (only if language data errors)

If OCR reports missing language files but `tessdata` exists:

1. **Environment Variables…** → **System variables** → **New**
2. Name: `TESSDATA_PREFIX`  
   Value: `C:\Program Files\Tesseract-OCR\tessdata`
3. OK → new terminal → run **`install.bat`** again.

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
| **Heavy / offline** (Whisper + local LLM + OCR) | Needs 16 GB+ RAM recommended; **GPU** (NVIDIA or AMD) speeds up Whisper + local LLM |

**Reduce load:** use Groq for STT/LLM, keep VLM off, choose TTS → Off, use Whisper `tiny`/`base` in `config.py` on weak PCs.

### Local AI: CPU or GPU (`config.py`)

| Setting | Values | Effect |
|---------|--------|--------|
| `LOCAL_AI_DEVICE` | `"auto"`, `"cpu"`, `"cuda"`, `"rocm"`, `"vulkan"` | Device/backend for Whisper + local LLM |
| `LOCAL_COMPUTE_TYPE` | `""` (auto), `int8`, `float16`, … | Whisper precision |
| `LLM_LOCAL_N_GPU_LAYERS` | `-1` (auto), `0` (CPU), `N>0` | LLM layers on GPU |

| GPU | Whisper (STT) | Local LLM | Install (examples) |
|-----|---------------|-----------|-------------------|
| **NVIDIA** | Default `pip` + drivers | CUDA wheel | `install.ps1 -WithLocalLlm -WithCuda` |
| **AMD (Windows)** | CTranslate2 ROCm wheel (optional) | Vulkan or HIP wheel | `install.ps1 -WithLocalLlm -WithVulkan` |
| **AMD (Linux)** | CTranslate2 ROCm wheel | ROCm wheel | `install.ps1 -WithLocalLlm -WithRocm` |

- **NVIDIA:** `LOCAL_AI_DEVICE = "cuda"` or `"auto"`.
- **AMD:** `LOCAL_AI_DEVICE = "vulkan"` (LLM on Radeon via Vulkan) or `"rocm"` when ROCm wheels are installed. Whisper on AMD needs the [CTranslate2 ROCm wheel](https://github.com/OpenNMT/CTranslate2/releases) (≥ 4.7.1); `vulkan` mode keeps Whisper on CPU unless ROCm CT2 is present.
- **CPU-only:** `LOCAL_AI_DEVICE = "cpu"`.
- Self-check (menu **3**) shows `whisper=cuda|rocm|cpu` and `llm=cuda|vulkan|rocm|cpu`.

---

## Configuration

| File | Purpose |
|------|---------|
| `commands.json` | Custom voice phrases |
| `providers.json`, `llm_providers.json`, `vlm_providers.json`, `tts_providers.json` | Cloud API endpoints — see **[API_PROVIDERS.md](API_PROVIDERS.md)** |
| `secrets.json` | Provider settings (model name, provider id); **not** the raw API key when keyring is active |
| `config.py` | Advanced: Whisper size, **CPU/GPU** (`LOCAL_AI_DEVICE`), Tesseract path (`TESSERACT_CMD`), timeouts |

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
