DictaDesk — Yerel LLM Modelleri (llm_models/)
==============================================

Bu klasör GitHub'a YUKLENMEZ. Model dosyalarini kendiniz indirip buraya koymaniz gerekir.

Ne icin kullanilir?
------------------
DictaDesk, internet baglantisi olmadan komut planlamak icin yerel bir LLM (Buyuk Dil Modeli)
kullanabilir. Bu mod, llama-cpp-python kutuphanesi ile calisir.

Onerilen model
--------------
  Microsoft Phi-3.5-mini-instruct (GGUF, Q4_K_M veya benzeri kuantize surum)

  Ornek dosya adi:
    Phi-3.5-mini-instruct-Q4_K_M.gguf

  Indirme kaynaklari:
    - Hugging Face: https://huggingface.co/models?search=Phi-3.5-mini-instruct+gguf
    - TheBloke veya bartowski gibi GGUF yayincilarinin repolarini tercih edin.

Kurulum adimlari
----------------
  1. Yukaridaki kaynaktan .gguf dosyasini indirin.
  2. Dosyayi bu klasore kopyalayin:
       llm_models/Phi-3.5-mini-instruct-Q4_K_M.gguf
  3. Opsiyonel: config.py icinde tam yolu belirtin:
       LLM_LOCAL_MODEL_PATH = r"C:\...\llm_models\Phi-3.5-mini-instruct-Q4_K_M.gguf"
     Bos birakirsaniz DictaDesk llm_models/ altindaki ilk .gguf dosyasini otomatik bulur.

  4. llama-cpp-python kurun (yerel LLM icin zorunlu):
       pip install llama-cpp-python

DictaDesk'te secim
------------------
  Baslangicta LLM menusunden "Lokal Agent (Phi-3.5-mini GGUF)" secenegini secin.
  API (Groq vb.) kullanmak istiyorsaniz bu klasore model koymaniz gerekmez;
  bunun yerine secrets.json icinde API anahtari tanimlayin.

Notlar
------
  - GGUF dosyalari genelde 2–4 GB civarindadir; Git LFS veya repo'ya eklemeyin.
  - Yerel LLM yavaş olabilir; hizli planlama icin Groq API onerilir.
  - Lisans: Phi-3.5 Microsoft lisans kosullarina tabidir; ticari kullanim icin lisans metnini okuyun.
