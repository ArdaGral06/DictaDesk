DictaDesk — Vosk Speech Recognition Models (vosk_models/)
===========================================================

This folder is NOT uploaded to GitHub. Download and extract Vosk models yourself.

Purpose
-------
DictaDesk can transcribe microphone input offline using Vosk as an alternative
to Whisper.

Required models
---------------

  Turkish (TR):
    Model : vosk-model-small-tr-0.3
    URL   : https://alphacephei.com/vosk/models
    Path  : vosk_models/tr/vosk-model-small-tr-0.3/
            (must contain conf/, am/, graph/, etc.)

  English (EN):
    Model : vosk-model-small-en-us-0.15
    URL   : https://alphacephei.com/vosk/models
    Path  : vosk_models/en/vosk-model-small-en-us-0.15/

Setup
-----
  1. Download the .zip archives from alphacephei.com/vosk/models.
  2. Extract each archive.
  3. Move the TR model to:
       vosk_models/tr/vosk-model-small-tr-0.3/
  4. Move the EN model to:
       vosk_models/en/vosk-model-small-en-us-0.15/
  5. At startup, select "Local (Vosk TR)" or "Local (Vosk EN)" as the STT engine.

STT options in DictaDesk
------------------------
  1) Local Whisper (faster-whisper — auto-downloads on first run)
  2) Local Vosk (requires models in this folder)
  3) Groq API (requires secrets.json → stt.groq)

Notes
-----
  - Small models are ~40–50 MB each; larger models improve accuracy but use more RAM.
  - Vosk is licensed under Apache 2.0.
  - If the folder structure is wrong, you will see "Vosk model not found".
