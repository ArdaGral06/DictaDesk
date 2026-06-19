DictaDesk — Piper TTS Modelleri (tts_models/)
==============================================

Bu klasör GitHub'a YUKLENMEZ. Piper ses sentez model dosyalarini kendiniz indirmeniz gerekir.

Ne icin kullanilir?
------------------
DictaDesk, islem sonuclarini sesli geri bildirim (TTS) olarak okuyabilir.
Piper tamamen cevrimdisi, hizli ve hafif bir TTS motorudur.

Onerilen model (Ingilizce)
--------------------------
  en_US-joe-medium

  Gerekli dosyalar (ikisi birlikte):
    - en_US-joe-medium.onnx
    - en_US-joe-medium.onnx.json

  Indirme:
    - Piper ses modelleri: https://github.com/rhasspy/piper/blob/master/README.md
    - Hugging Face rhasspy/piper-voices deposu

  Hedef yol:
    tts_models/piper/en_US-joe-medium.onnx
    tts_models/piper/en_US-joe-medium.onnx.json

Kurulum adimlari
----------------
  1. .onnx ve .onnx.json dosyalarini indirin.
  2. tts_models/piper/ klasorune kopyalayin.
  3. Piper'i kurun:
       pip install piper-tts
     veya ayri piper.exe indirip config.py icinde PIPER_BIN yolunu belirtin.
  4. DictaDesk baslatildiginda TTS menusunden "Lokal (Piper)" secin.

Alternatif: API TTS
-----------------
  Yerel model istemiyorsaniz ElevenLabs API kullanabilirsiniz.
  secrets.json icinde tts.elevenlabs anahtarini tanimlayin (bkz. secrets.json.example).

DictaDesk'te secim
------------------
  TTS menusu:
    - 1) Kapali
    - 2) Lokal (Piper) — bu klasordeki model gerekli
    - 3) API (ElevenLabs) — secrets.json gerekir

Notlar
------
  - .onnx dosyalari ~10–60 MB arasi olabilir; repo'ya eklemeyin.
  - Turkce Piper sesi icin tr_TR-* modellerine bakin (piper-voices listesinde).
  - Piper MIT lisanslidir; ses modeli lisanslari modele gore degisebilir.
