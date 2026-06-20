DictaDesk - Piper TTS Models (tts_models/)
=============================================

Voice model files are NOT included in the Git repo (too large).
install.bat downloads them automatically from the official Piper voice repo.

AUTOMATIC SETUP (recommended)
-----------------------------
Run install.bat once. It downloads:
  - en_US-joe-medium.onnx
  - en_US-joe-medium.onnx.json
from https://huggingface.co/rhasspy/piper-voices

Target path after install:
  tts_models/piper/en_US-joe-medium.onnx
  tts_models/piper/en_US-joe-medium.onnx.json

Piper executable (piper.exe) is downloaded separately to piper/piper.exe.
You never run piper.exe yourself — DictaDesk uses it in the background.

MANUAL FALLBACK
---------------
Only if install.bat could not download (no internet, firewall, etc.):

  1. Download .onnx + .onnx.json from https://huggingface.co/rhasspy/piper-voices
  2. Download piper.exe from https://github.com/rhasspy/piper/releases
  3. Place files as shown above and in piper/README.txt

At startup
----------
  TTS -> 1 Off        : no spoken feedback (Piper still must be installed)
  TTS -> 2 Local Piper: spoken feedback using the downloaded model
  TTS -> 3 ElevenLabs : cloud voice (API key required)

Notes
-----
  - For Turkish voices, search piper-voices for tr_TR-* models.
  - .onnx files are typically 10-60 MB.
