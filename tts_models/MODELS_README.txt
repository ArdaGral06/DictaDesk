DictaDesk — Piper TTS Models (tts_models/)
===========================================

Voice model files are not included with DictaDesk. Download them manually.

Purpose
-------
Offline text-to-speech for spoken feedback.

Recommended model (English)
---------------------------
  en_US-joe-medium

  Required files (both):
    - en_US-joe-medium.onnx
    - en_US-joe-medium.onnx.json

  Download:
    https://huggingface.co/rhasspy/piper-voices

  Target path:
    tts_models/piper/en_US-joe-medium.onnx
    tts_models/piper/en_US-joe-medium.onnx.json

Piper executable
----------------
  Download piper.exe from:
    https://github.com/rhasspy/piper/releases

  Place it in your PATH, in DictaDesk/piper/piper.exe, or set PIPER_BIN in config.py.

Setup
-----
  1. Download .onnx and .onnx.json into tts_models/piper/.
  2. Download and configure piper.exe (see above).
  3. At startup, choose TTS → 2 — Local Piper.

Alternative
-----------
  Choose TTS → 1 — Off (no setup needed), or TTS → 3 — ElevenLabs API.

Notes
-----
  - For Turkish voices, search piper-voices for tr_TR-* models.
  - .onnx files are typically 10–60 MB.
