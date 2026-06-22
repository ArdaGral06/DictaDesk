"""Resolve CPU vs GPU settings for local Whisper (faster-whisper) and LLM (llama-cpp)."""

from __future__ import annotations

import shutil
import subprocess
import sys

import config

_VALID_DEVICES = frozenset({"auto", "cpu", "cuda", "rocm", "vulkan"})


def _normalized_device_mode() -> str:
    mode = (config.LOCAL_AI_DEVICE or "auto").strip().lower()
    return mode if mode in _VALID_DEVICES else "auto"


def nvidia_gpu_present() -> bool:
    if not shutil.which("nvidia-smi"):
        return False
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            ["nvidia-smi"],
            capture_output=True,
            timeout=5,
            creationflags=flags,
        )
        return result.returncode == 0
    except Exception:
        return False


def ctranslate2_rocm_wheel() -> bool:
    try:
        import ctranslate2
        from pathlib import Path

        root = Path(ctranslate2.__file__).resolve().parent.parent
        return (root / "_rocm_sdk_core").is_dir()
    except Exception:
        return False


def ctranslate2_gpu_available() -> bool:
    """CT2 GPU count (NVIDIA CUDA or AMD ROCm wheels both use device='cuda')."""
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def ctranslate2_cuda_available() -> bool:
    return ctranslate2_gpu_available()


def llama_gpu_available() -> bool:
    try:
        import llama_cpp

        if hasattr(llama_cpp, "llama_supports_gpu_offload"):
            return bool(llama_cpp.llama_supports_gpu_offload())
    except Exception:
        return False
    return False


def _whisper_gpu_requested(mode: str) -> bool:
    return mode in {"auto", "cuda", "rocm"}


def _whisper_allows_gpu(mode: str) -> bool:
    if mode == "cpu" or mode == "vulkan":
        return False
    if mode == "cuda":
        return ctranslate2_gpu_available() and nvidia_gpu_present()
    if mode == "rocm":
        return ctranslate2_gpu_available() and (
            ctranslate2_rocm_wheel() or not nvidia_gpu_present()
        )
    # auto
    return ctranslate2_gpu_available()


def whisper_backend_label(ct2_device: str) -> str:
    if ct2_device == "cpu":
        return "cpu"
    if ctranslate2_rocm_wheel() and not nvidia_gpu_present():
        return "rocm"
    if ctranslate2_rocm_wheel() and nvidia_gpu_present():
        return "rocm" if config.LOCAL_AI_DEVICE == "rocm" else "cuda"
    return "cuda"


def resolve_whisper_settings() -> tuple[str, str]:
    """Return (ctranslate2_device, compute_type) for faster-whisper WhisperModel."""
    mode = _normalized_device_mode()
    ct2_device = "cuda" if _whisper_allows_gpu(mode) else "cpu"

    compute_override = (config.LOCAL_COMPUTE_TYPE or "").strip()
    if compute_override:
        compute_type = compute_override
    elif ct2_device == "cuda":
        compute_type = "float16"
    else:
        compute_type = "int8"
    return ct2_device, compute_type


def _detect_llm_backend(mode: str) -> str:
    if mode == "cpu":
        return "cpu"
    if mode == "cuda":
        return "cuda"
    if mode == "rocm":
        return "rocm"
    if mode == "vulkan":
        return "vulkan"
    # auto
    if nvidia_gpu_present():
        return "cuda"
    if ctranslate2_rocm_wheel():
        return "rocm"
    return "vulkan"


def _llm_gpu_requested(mode: str) -> bool:
    return mode != "cpu"


def resolve_llm_settings() -> tuple[int, str]:
    """Return (n_gpu_layers, backend_label) for llama_cpp.Llama."""
    mode = _normalized_device_mode()
    backend = _detect_llm_backend(mode)

    if not _llm_gpu_requested(mode):
        return 0, "cpu"

    explicit = int(config.LLM_LOCAL_N_GPU_LAYERS)
    if explicit >= 0:
        return explicit, backend

    if llama_gpu_available():
        return -1, backend
    return 0, "cpu"


def resolve_llm_gpu_layers() -> int:
    layers, _ = resolve_llm_settings()
    return layers


def llm_device_tag(n_gpu_layers: int, backend: str | None = None) -> str:
    if n_gpu_layers == 0:
        return "cpu"
    if backend in {"cuda", "rocm", "vulkan"}:
        return backend
    if n_gpu_layers < 0:
        return "gpu"
    return f"gpu:{n_gpu_layers}"


def describe_local_ai_device() -> dict:
    ct2_device, whisper_compute = resolve_whisper_settings()
    llm_layers, llm_backend = resolve_llm_settings()
    mode = _normalized_device_mode()
    whisper_label = whisper_backend_label(ct2_device)
    gpu_ok = ctranslate2_gpu_available() or llama_gpu_available()
    return {
        "mode": mode,
        "whisper_device": whisper_label,
        "whisper_ct2_device": ct2_device,
        "whisper_compute": whisper_compute,
        "llm_backend": llm_backend,
        "llm_gpu_layers": llm_layers,
        "nvidia_gpu": nvidia_gpu_present(),
        "ctranslate2_rocm": ctranslate2_rocm_wheel(),
        "ctranslate2_gpu": ctranslate2_gpu_available(),
        "llama_gpu": llama_gpu_available(),
        "gpu_ok": gpu_ok,
    }
