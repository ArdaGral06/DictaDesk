DictaDesk — Local LLM Models (llm_models/)
============================================

This folder is NOT uploaded to GitHub. Download model files yourself.

Purpose
-------
DictaDesk can plan commands offline using a local Large Language Model via
llama-cpp-python.

Recommended model
-----------------
  Microsoft Phi-3.5-mini-instruct (GGUF, Q4_K_M or similar quantized build)

  Example filename:
    Phi-3.5-mini-instruct-Q4_K_M.gguf

  Download sources:
    - Hugging Face: https://huggingface.co/models?search=Phi-3.5-mini-instruct+gguf
    - GGUF publishers such as TheBloke or bartowski

Setup
-----
  1. Download the .gguf file.
  2. Place it in this folder, e.g.:
       llm_models/Phi-3.5-mini-instruct-Q4_K_M.gguf
  3. Optional — set the full path in config.py:
       LLM_LOCAL_MODEL_PATH = r"C:\path\to\llm_models\Phi-3.5-mini-instruct-Q4_K_M.gguf"
     If left empty, DictaDesk auto-detects the first .gguf file here.

  4. Install the optional dependency:
       pip install llama-cpp-python

Selecting in DictaDesk
----------------------
  At startup, choose "Local Agent (Phi-3.5-mini GGUF)" in the LLM menu.
  For cloud planning instead, skip this folder and configure secrets.json.

Notes
-----
  - GGUF files are typically 2–4 GB — do not add them to git or Git LFS in this repo.
  - Local LLM inference can be slow; Groq API is faster for planning.
  - Phi-3.5 is subject to Microsoft's model license — review before commercial use.
