DictaDesk — Vosk Speech Models (vosk_models/)
================================================

Model files are not included with DictaDesk. Download and extract them here.

Purpose
-------
Offline speech-to-text as an alternative to Whisper.

Required models
---------------

  Turkish:
    Model : vosk-model-small-tr-0.3
    URL   : https://alphacephei.com/vosk/models
    Path  : vosk_models/tr/vosk-model-small-tr-0.3/

  English:
    Model : vosk-model-small-en-us-0.15
    URL   : https://alphacephei.com/vosk/models
    Path  : vosk_models/en/vosk-model-small-en-us-0.15/

Setup
-----
  1. Download the .zip from alphacephei.com/vosk/models.
  2. Extract and copy the TR model to vosk_models/tr/vosk-model-small-tr-0.3/
  3. Extract and copy the EN model to vosk_models/en/vosk-model-small-en-us-0.15/
  4. At startup, choose STT → 2 — Local Vosk.

Notes
-----
  - Small models are ~40–50 MB each.
  - If the folder structure is wrong, you will see "Vosk model not found".

Git / GitHub
------------
Extracted model folders are gitignored. Only this MODELS_README.txt is tracked.
Model klasörleri GitHub'a gitmez. Repoda yalnızca bu açıklama dosyası vardır.
