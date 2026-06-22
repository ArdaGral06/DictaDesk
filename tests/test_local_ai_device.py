import config
import local_ai_device as lad


def test_whisper_cpu_mode(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "cpu")
    monkeypatch.setattr(config, "LOCAL_COMPUTE_TYPE", "")
    device, compute = lad.resolve_whisper_settings()
    assert device == "cpu"
    assert compute == "int8"


def test_whisper_cuda_mode_without_gpu(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "cuda")
    monkeypatch.setattr(config, "LOCAL_COMPUTE_TYPE", "")
    monkeypatch.setattr(lad, "ctranslate2_gpu_available", lambda: False)
    monkeypatch.setattr(lad, "nvidia_gpu_present", lambda: True)
    device, compute = lad.resolve_whisper_settings()
    assert device == "cpu"
    assert compute == "int8"


def test_whisper_cuda_mode_with_nvidia_gpu(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "cuda")
    monkeypatch.setattr(config, "LOCAL_COMPUTE_TYPE", "")
    monkeypatch.setattr(lad, "ctranslate2_gpu_available", lambda: True)
    monkeypatch.setattr(lad, "nvidia_gpu_present", lambda: True)
    device, compute = lad.resolve_whisper_settings()
    assert device == "cuda"
    assert compute == "float16"


def test_whisper_rocm_mode_with_amd_wheel(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "rocm")
    monkeypatch.setattr(config, "LOCAL_COMPUTE_TYPE", "")
    monkeypatch.setattr(lad, "ctranslate2_gpu_available", lambda: True)
    monkeypatch.setattr(lad, "ctranslate2_rocm_wheel", lambda: True)
    monkeypatch.setattr(lad, "nvidia_gpu_present", lambda: False)
    device, compute = lad.resolve_whisper_settings()
    assert device == "cuda"
    assert compute == "float16"
    assert lad.whisper_backend_label(device) == "rocm"


def test_whisper_vulkan_mode_uses_cpu(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "vulkan")
    monkeypatch.setattr(lad, "ctranslate2_gpu_available", lambda: True)
    device, compute = lad.resolve_whisper_settings()
    assert device == "cpu"
    assert compute == "int8"


def test_whisper_auto_picks_gpu_when_available(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "auto")
    monkeypatch.setattr(lad, "ctranslate2_gpu_available", lambda: True)
    device, _ = lad.resolve_whisper_settings()
    assert device == "cuda"


def test_whisper_compute_type_override(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "cpu")
    monkeypatch.setattr(config, "LOCAL_COMPUTE_TYPE", "int8_float16")
    _, compute = lad.resolve_whisper_settings()
    assert compute == "int8_float16"


def test_llm_cpu_mode(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "cpu")
    monkeypatch.setattr(config, "LLM_LOCAL_N_GPU_LAYERS", -1)
    layers, backend = lad.resolve_llm_settings()
    assert layers == 0
    assert backend == "cpu"


def test_llm_explicit_layers(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "auto")
    monkeypatch.setattr(config, "LLM_LOCAL_N_GPU_LAYERS", 12)
    layers, _backend = lad.resolve_llm_settings()
    assert layers == 12


def test_llm_vulkan_mode(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "vulkan")
    monkeypatch.setattr(config, "LLM_LOCAL_N_GPU_LAYERS", -1)
    monkeypatch.setattr(lad, "llama_gpu_available", lambda: True)
    layers, backend = lad.resolve_llm_settings()
    assert layers == -1
    assert backend == "vulkan"


def test_llm_auto_gpu_when_available(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_AI_DEVICE", "auto")
    monkeypatch.setattr(config, "LLM_LOCAL_N_GPU_LAYERS", -1)
    monkeypatch.setattr(lad, "llama_gpu_available", lambda: True)
    monkeypatch.setattr(lad, "nvidia_gpu_present", lambda: False)
    monkeypatch.setattr(lad, "ctranslate2_rocm_wheel", lambda: False)
    layers, backend = lad.resolve_llm_settings()
    assert layers == -1
    assert backend == "vulkan"


def test_llm_device_tag():
    assert lad.llm_device_tag(0) == "cpu"
    assert lad.llm_device_tag(-1, "vulkan") == "vulkan"
    assert lad.llm_device_tag(-1, "rocm") == "rocm"
    assert lad.llm_device_tag(8, "cuda") == "cuda"
