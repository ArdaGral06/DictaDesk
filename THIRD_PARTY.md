# Third-Party Licenses — DictaDesk

DictaDesk uses the following open-source libraries and external tools.
This document summarizes their licenses for compliance purposes.
For the full license text of each project, visit the linked repositories.

> **Disclaimer:** License summaries here are provided for convenience only.
> Always refer to the upstream project's official license file for legal use.

---

## Python Dependencies (`requirements.txt`)

| Package | Version constraint | License | Project |
|---------|-------------------|---------|---------|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | (see requirements.txt) | MIT | SYSTRAN |
| [numpy](https://github.com/numpy/numpy) | — | BSD-3-Clause | NumPy Developers |
| [pynput](https://github.com/moses-palmer/pynput) | — | LGPL-3.0 (library) / GPL-3.0 (some components) | Moses Palmer |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | — | MIT | Spatial Audio |
| [soundfile](https://github.com/bastibe/python-soundfile) | — | BSD-3-Clause | Bastian Bechtold |
| [requests](https://github.com/psf/requests) | — | Apache-2.0 | Python Software Foundation |
| [send2trash](https://github.com/arsenetar/send2trash) | — | BSD-3-Clause | Arsenetar |
| [vosk](https://github.com/alphacep/vosk-api) | — | Apache-2.0 | Alpha Cephei |
| [piper-tts](https://github.com/rhasspy/piper) | — | MIT | Rhasspy / Michael Jefferson |
| [pathvalidate](https://github.com/thombashi/pathvalidate) | — | MIT | Hiroki Fujimoto |
| [opencv-python](https://github.com/opencv/opencv-python) | — | Apache-2.0 | OpenCV team |
| [pytesseract](https://github.com/madmaze/pytesseract) | — | Apache-2.0 | Mad Maze |
| [Pillow](https://github.com/python-pillow/Pillow) | — | HPND (PIL License) | Pillow contributors |
| [PyAutoGUI](https://github.com/asweigart/pyautogui) | — | BSD-3-Clause | Al Sweigart |
| [playwright](https://github.com/microsoft/playwright-python) | — | Apache-2.0 | Microsoft |
| [mss](https://github.com/BoboTiG/python-mss) | — | MIT | BoboTiG |
| [pyperclip](https://github.com/asweigart/pyperclip) | — | BSD-3-Clause | Al Sweigart |
| [uiautomation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows) | — | Apache-2.0 | Yinkaisheng |

---

## Optional Python Dependencies

| Package | Purpose | License | Project |
|---------|---------|---------|---------|
| [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) | Local LLM inference (Phi-3.5 GGUF) | MIT | Andrei Betlen |
| [llama.cpp](https://github.com/ggerganov/llama.cpp) (bundled by llama-cpp-python) | GGUF model runtime | MIT | Georgi Gerganov et al. |

Install optionally:

```bash
pip install llama-cpp-python
```

---

## External System Tools (not bundled)

| Tool | Purpose | License | Website |
|------|---------|---------|---------|
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Screen text recognition (GUI automation) | Apache-2.0 | https://github.com/tesseract-ocr/tesseract |
| [Piper](https://github.com/rhasspy/piper) (standalone binary, optional) | Offline TTS | MIT | https://github.com/rhasspy/piper |
| [Playwright browsers](https://playwright.dev/) | Web automation runtime | Apache-2.0 | Installed via `playwright install chromium` |

---

## AI Models (downloaded separately — not in this repository)

These models have their own licenses. DictaDesk does **not** redistribute them.

| Model | Use in DictaDesk | Typical license | Source |
|-------|------------------|-----------------|--------|
| OpenAI Whisper (via faster-whisper) | Local STT | MIT | Hugging Face / OpenAI |
| Vosk small TR / EN | Local STT | Apache-2.0 | https://alphacephei.com/vosk/models |
| Microsoft Phi-3.5-mini-instruct (GGUF) | Local LLM planner | Microsoft Phi-3 Model License | Hugging Face |
| Groq Whisper / Llama / Scout (API) | Cloud STT, LLM, VLM | Provider ToS | https://console.groq.com |
| ElevenLabs voices (API) | Cloud TTS | Provider ToS | https://elevenlabs.io |
| Piper voice models (e.g. en_US-joe-medium) | Local TTS | MIT (engine) / per-voice terms | https://github.com/rhasspy/piper |

See `llm_models/MODELS_README.txt`, `vosk_models/MODELS_README.txt`, and
`tts_models/MODELS_README.txt` for download instructions.

---

## Transitive / Runtime Dependencies

The packages above pull in additional libraries at install time (e.g. `ctranslate2`
for faster-whisper, `torch` optional paths, Playwright browser binaries).
Run `pip-licenses` in your virtual environment for a complete transitive list:

```bash
pip install pip-licenses
pip-licenses --format=markdown
```

---

## DictaDesk Project License

Unless a separate `LICENSE` file is added to this repository, the application
source code in this repo is provided as-is. Third-party components remain
under their respective licenses listed above.

---

## Attribution Notes

- **faster-whisper** builds on [CTranslate2](https://github.com/OpenNMT/CTranslate2) (MIT) and OpenAI Whisper (MIT).
- **vosk** is developed by Alpha Cephei Inc.
- **Piper** is part of the Rhasspy ecosystem (MIT).
- **Playwright** browser automation is maintained by Microsoft (Apache-2.0).
- **Windows UI Automation** is accessed via the `uiautomation` Python wrapper; underlying APIs are Microsoft platform components.

If you distribute a build of DictaDesk, ensure compliance with all applicable
licenses, especially LGPL/GPL components (`pynput`) and commercial API terms
(Groq, ElevenLabs).
