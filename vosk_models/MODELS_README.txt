DictaDesk — Vosk Konusma Tanima Modelleri (vosk_models/)
=========================================================

Bu klasör GitHub'a YUKLENMEZ. Vosk model arsivlerini kendiniz indirip acmaniz gerekir.

Ne icin kullanilir?
------------------
DictaDesk, mikrofon kaydini metne cevirmek (STT) icin Vosk kullanabilir.
Whisper'a alternatif olarak tamamen cevrimdisi calisir.

Gerekli modeller
----------------

  Turkce (TR):
    Model adi : vosk-model-small-tr-0.3
    Indirme   : https://alphacephei.com/vosk/models
    Hedef yol : vosk_models/tr/vosk-model-small-tr-0.3/
                (icinde conf/, am/, graph/ vb. klasorler olmali)

  Ingilizce (EN):
    Model adi : vosk-model-small-en-us-0.15
    Indirme   : https://alphacephei.com/vosk/models
    Hedef yol : vosk_models/en/vosk-model-small-en-us-0.15/

Kurulum adimlari
----------------
  1. alphacephei.com/vosk/models adresinden ilgili .zip dosyalarini indirin.
  2. Zip dosyalarini acin.
  3. TR modelini su klasore tasiyin/kopyalayin:
       vosk_models/tr/vosk-model-small-tr-0.3/
  4. EN modelini su klasore tasiyin/kopyalayin:
       vosk_models/en/vosk-model-small-en-us-0.15/
  5. DictaDesk baslatildiginda STT menusunden "Lokal (Vosk TR)" veya
     "Lokal (Vosk EN)" secenegini secin.

DictaDesk'te secim
------------------
  Ana menu > Sistem kontrol modu oncesi STT motoru secimi:
    - 1) Lokal Whisper (faster-whisper, model otomatik indirilir)
    - 2) Lokal Vosk (bu klasordeki modeller gerekli)
    - 3) API (Groq Whisper — secrets.json gerekir)

Notlar
------
  - Small modeller ~40–50 MB civarindadir; buyuk modeller daha iyi tanir ama daha agirdir.
  - Vosk Apache 2.0 lisanslidir.
  - Model klasor yapisi bozulursa "Vosk modeli bulunamadi" hatasi alirsiniz.
