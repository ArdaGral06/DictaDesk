DictaDesk — Piper TTS Models (tts_models/)
===========================================

This folder is NOT uploaded to GitHub. Download Piper voice model files yourself.

Purpose
-------
DictaDesk can speak action results aloud using Piper, a fast offline TTS engine.

Recommended model (English)
---------------------------
  en_US-joe-medium

  Required files (both):
    - en_US-joe-medium.onnx
    - en_US-joe-medium.onnx.json

  Download:
    - Piper: https://github.com/rhasspy/piper/blob/master/README.md
    - Hugging Face: rhasspy/piper-voices repository

  Target path:
    tts_models/piper/en_US-joe-medium.onnx
    tts_models/piper/en_US-joe-medium.onnx.json

Setup
-----
  1. Download both files.
  2. Copy them into tts_models/piper/.
  3. Install Piper:
       pip install piper-tts
     Or download piper.exe separately and set PIPER_BIN in config.py.
  4. At startup, select "Local (Piper)" in the TTS menu.

Alternative: API TTS
--------------------
  Skip local models and use ElevenLabs instead.
  Configure secrets.json → tts.elevenlabs (see secrets.json.example).

TTS options in DictaDesk
-------------------------
  1) Off
  2) Local (Piper) — requires model files in this folder
  3) API (ElevenLabs) — requires secrets.json

Notes
-----
  - .onnx files are typically 10–60 MB — do not commit them to git.
  - For Turkish voices, search piper-voices for tr_TR-* models.
  - Piper engine is MIT-licensed; individual voice models may have separate terms.
