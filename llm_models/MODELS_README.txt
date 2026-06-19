DictaDesk — Local LLM Models (llm_models/)
============================================

Model files are not included with DictaDesk. Download and place them here manually.

Purpose
-------
Offline command planning using a local Large Language Model via llama-cpp-python.

Recommended model
-----------------
  Microsoft Phi-3.5-mini-instruct (GGUF, Q4_K_M or similar)

  Example filename:
    Phi-3.5-mini-instruct-Q4_K_M.gguf

  Download:
    https://huggingface.co/models?search=Phi-3.5-mini-instruct+gguf

Setup
-----
  1. Download the .gguf file.
  2. Place it in this folder:
       llm_models/Phi-3.5-mini-instruct-Q4_K_M.gguf
  3. Optional — set full path in config.py:
       LLM_LOCAL_MODEL_PATH = r"C:\path\to\model.gguf"
     If left empty, DictaDesk finds the first .gguf file here automatically.

  4. Install the optional dependency:
       pip install -r requirements-optional.txt

  5. At startup, choose LLM → 2 — Local Agent (Phi-3.5-mini GGUF).

Notes
-----
  - Files are typically 2–4 GB.
  - Local inference can be slow; Groq API is faster for planning.
  - Review Microsoft's Phi-3 license before commercial use.
