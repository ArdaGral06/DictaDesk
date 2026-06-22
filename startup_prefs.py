"""Save and restore STT/TTS/Agent/VLM choices between runs."""

from __future__ import annotations

import json
from pathlib import Path

from config import BASE_DIR, DEFAULT_API_MODEL, DEFAULT_LLM_MODEL, DEFAULT_VLM_MODEL
from api_provider_config import ensure_api_model
from engine import (
    SwitchableTranscriber,
    create_local_transcriber,
    create_vosk_transcriber,
    _whisper_label,
)
from i18n import t
from providers import load_providers, validate_provider
from secrets_store import get_entry
from transcriber import HttpApiTranscriber, LocalTranscriber

STARTUP_PREFS_FILE = BASE_DIR / "startup_prefs.json"


def load_prefs() -> dict | None:
    if not STARTUP_PREFS_FILE.exists():
        return None
    try:
        data = json.loads(STARTUP_PREFS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_prefs(prefs: dict) -> None:
    STARTUP_PREFS_FILE.write_text(
        json.dumps(prefs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _provider_by_id(providers: list[dict], provider_id: str | None) -> dict | None:
    if not providers:
        return None
    if provider_id:
        for item in providers:
            if str(item.get("id", "")).lower() == str(provider_id).lower():
                return item
    return providers[0]


def summarize_prefs(ui_lang: str, prefs: dict) -> list[tuple[str, str]]:
    stt = prefs.get("stt", "whisper")
    stt_labels = {
        "whisper": t(ui_lang, "engine_local_title"),
        "vosk": t(ui_lang, "engine_vosk_title"),
        "api": t(ui_lang, "engine_api_title"),
    }
    tts = prefs.get("tts", "off")
    tts_labels = {
        "off": t(ui_lang, "tts_off_title"),
        "piper": t(ui_lang, "tts_local_title"),
        "api": t(ui_lang, "tts_api_title"),
    }
    llm = prefs.get("llm", "off")
    llm_labels = {
        "off": t(ui_lang, "llm_off_title"),
        "local": t(ui_lang, "llm_local_title"),
        "api": t(ui_lang, "llm_api_title"),
    }
    vlm = prefs.get("vlm", "off")
    vlm_labels = {
        "off": t(ui_lang, "vlm_off_title"),
        "api": t(ui_lang, "vlm_api_title"),
    }
    return [
        (t(ui_lang, "setup_stt_label"), stt_labels.get(stt, stt)),
        (t(ui_lang, "setup_tts_label"), tts_labels.get(tts, tts)),
        (t(ui_lang, "setup_agent_label"), llm_labels.get(llm, llm)),
        (t(ui_lang, "setup_vlm_label"), vlm_labels.get(vlm, vlm)),
    ]


def ask_reuse_prefs(ui_lang: str, prefs: dict) -> bool:
    from ui_terminal import print_banner, print_compact_status, print_option

    print_banner(
        t(ui_lang, "startup_reuse_title"),
        t(ui_lang, "startup_reuse_subtitle"),
    )
    print_compact_status(ui_lang, summarize_prefs(ui_lang, prefs))
    print_option("1", t(ui_lang, "startup_reuse_yes_title"), t(ui_lang, "startup_reuse_yes_desc"))
    print_option("2", t(ui_lang, "startup_reuse_no_title"), t(ui_lang, "startup_reuse_no_desc"))
    choice = input(t(ui_lang, "menu_select")).strip().lower()
    return choice in ("1", "y", "yes", "e", "evet", "")


def build_stt(ui_lang: str, prefs: dict):
    mode = prefs.get("stt", "whisper")
    if mode == "vosk":
        transcriber = create_vosk_transcriber(ui_lang)
        return transcriber or create_local_transcriber(ui_lang)
    if mode == "api":
        providers = load_providers()
        provider = _provider_by_id(providers, prefs.get("stt_provider"))
        if not provider:
            print(t(ui_lang, "startup_prefs_fallback_stt"))
            return create_local_transcriber(ui_lang)
        report = validate_provider(provider)
        if report.get("errors"):
            print(t(ui_lang, "startup_prefs_fallback_stt"))
            return create_local_transcriber(ui_lang)
        provider_id = provider.get("id", "provider")
        saved = get_entry("stt", provider_id)
        api_key = saved.get("api_key") if isinstance(saved, dict) else None
        model = (saved.get("model") if isinstance(saved, dict) else None) or provider.get(
            "model_hint"
        ) or DEFAULT_API_MODEL
        if not api_key:
            print(t(ui_lang, "startup_prefs_api_missing"))
            return create_local_transcriber(ui_lang)
        label = t(
            ui_lang,
            "engine_label_api",
            provider=provider.get("label", provider_id),
            model=model,
        )
        return SwitchableTranscriber(
            ui_lang,
            label,
            lambda: HttpApiTranscriber(provider=provider, api_key=api_key, model=model),
            fallbacks=[(_whisper_label(ui_lang), LocalTranscriber)],
        )
    return create_local_transcriber(ui_lang)


def build_tts(ui_lang: str, prefs: dict):
    from tts_engine import (
        ApiTTS,
        PiperTTS,
        TTSManager,
        _resolve_piper_bin,
        _resolve_piper_model,
        load_tts_providers,
        piper_available,
    )

    label_piper = t(ui_lang, "tts_label_piper")
    label_api = t(ui_lang, "tts_label_api")
    available = piper_available()
    mode = prefs.get("tts", "off")

    if mode == "piper":
        piper_bin = _resolve_piper_bin()
        model_path, config_path = _resolve_piper_model()
        if piper_bin and model_path:
            return TTSManager(
                PiperTTS(piper_bin=piper_bin, model_path=model_path, config_path=config_path),
                label_piper,
                enabled=True,
                available=available,
            )
        print(t(ui_lang, "startup_prefs_fallback_tts"))
        return TTSManager(None, label_piper, enabled=False, available=available)

    if mode == "api":
        providers = load_tts_providers()
        provider = _provider_by_id(providers, prefs.get("tts_provider"))
        if not provider:
            print(t(ui_lang, "startup_prefs_fallback_tts"))
            return TTSManager(None, label_piper, enabled=False, available=available)
        provider_id = provider.get("id", "provider")
        saved = get_entry("tts", provider_id)
        api_key = saved.get("api_key") if isinstance(saved, dict) else None
        if not api_key:
            print(t(ui_lang, "startup_prefs_api_missing"))
            return TTSManager(None, label_piper, enabled=False, available=available)
        voice_id = saved.get("voice_id") if isinstance(saved, dict) else None
        model = saved.get("model") if isinstance(saved, dict) else None
        label = f"{label_api} ({provider.get('label', provider_id)})"
        return TTSManager(
            ApiTTS(provider=provider, api_key=api_key, voice_id=voice_id, model=model),
            label,
            enabled=True,
            available=available,
        )

    return TTSManager(None, label_piper, enabled=False, available=available)


def build_llm(ui_lang: str, prefs: dict):
    from llm_engine import (
        ApiLLM,
        LLMManager,
        LocalLLM,
        _local_model_path,
        load_llm_providers,
    )

    mode = prefs.get("llm", "off")
    if mode == "local":
        model_path = _local_model_path()
        if not model_path:
            print(t(ui_lang, "startup_prefs_fallback_llm"))
            return LLMManager(None, t(ui_lang, "llm_label_off"), enabled=False)
        try:
            llm = LocalLLM(model_path)
            from local_ai_device import llm_device_tag

            device = llm_device_tag(llm.n_gpu_layers, llm.gpu_backend)
            return LLMManager(
                llm, t(ui_lang, "llm_label_local", device=device), enabled=True
            )
        except Exception:
            print(t(ui_lang, "startup_prefs_fallback_llm"))
            return LLMManager(None, t(ui_lang, "llm_label_off"), enabled=False)

    if mode == "api":
        providers = load_llm_providers()
        provider = _provider_by_id(providers, prefs.get("llm_provider"))
        if not provider:
            print(t(ui_lang, "startup_prefs_fallback_llm"))
            return LLMManager(None, t(ui_lang, "llm_label_off"), enabled=False)
        provider_id = provider.get("id", "provider")
        saved = get_entry("llm", provider_id)
        api_key = saved.get("api_key") if isinstance(saved, dict) else None
        model = ensure_api_model(
            "llm",
            provider_id,
            provider,
            saved,
            default=DEFAULT_LLM_MODEL,
            api_key=api_key,
            ui_lang=ui_lang,
        )
        if not api_key or not model:
            print(t(ui_lang, "startup_prefs_api_missing"))
            return LLMManager(None, t(ui_lang, "llm_label_off"), enabled=False)
        label = f"{t(ui_lang, 'llm_label_api')} ({provider.get('label', provider_id)})"
        return LLMManager(
            ApiLLM(provider=provider, api_key=api_key, model=model), label, enabled=True
        )

    return LLMManager(None, t(ui_lang, "llm_label_off"), enabled=False)


def build_vlm(ui_lang: str, prefs: dict):
    from vlm_engine import ApiVLM, VLMManager, load_vlm_providers

    mode = prefs.get("vlm", "off")
    if mode != "api":
        return VLMManager(None, t(ui_lang, "vlm_label_off"), enabled=False)

    providers = load_vlm_providers()
    provider = _provider_by_id(providers, prefs.get("vlm_provider"))
    if not provider:
        print(t(ui_lang, "startup_prefs_fallback_vlm"))
        return VLMManager(None, t(ui_lang, "vlm_label_off"), enabled=False)

    provider_id = provider.get("id", "provider")
    saved_vlm = get_entry("vlm", provider_id)
    saved_llm = get_entry("llm", provider_id)
    api_key = None
    if isinstance(saved_vlm, dict):
        api_key = saved_vlm.get("api_key")
    if not api_key and isinstance(saved_llm, dict):
        api_key = saved_llm.get("api_key")
    model = ensure_api_model(
        "vlm",
        provider_id,
        provider,
        saved_vlm if isinstance(saved_vlm, dict) else {},
        default=DEFAULT_VLM_MODEL,
        api_key=api_key,
        ui_lang=ui_lang,
    )
    if not api_key or not model:
        print(t(ui_lang, "startup_prefs_api_missing"))
        return VLMManager(None, t(ui_lang, "vlm_label_off"), enabled=False)

    label = f"{t(ui_lang, 'vlm_label_api')} ({provider.get('label', provider_id)})"
    return VLMManager(ApiVLM(provider=provider, api_key=api_key, model=model), label, enabled=True)


def apply_startup_prefs(ui_lang: str, prefs: dict):
    return (
        build_stt(ui_lang, prefs),
        build_tts(ui_lang, prefs),
        build_llm(ui_lang, prefs),
        build_vlm(ui_lang, prefs),
    )
