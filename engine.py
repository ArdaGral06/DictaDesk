from config import DEFAULT_API_MODEL, LOCAL_MODEL_SIZE
from i18n import t
from ui_terminal import print_wizard
from providers import load_providers, validate_provider
from secrets_store import get_entry, set_entry
from transcriber import (
    HttpApiTranscriber,
    LocalTranscriber,
    TranscriptionResult,
    VoskTranscriber,
    find_vosk_model_dir,
    get_vosk_model_dir,
)


class SwitchableTranscriber:
    def __init__(self, ui_lang, primary_label, primary_factory, fallbacks=None):
        self.ui_lang = ui_lang
        self.current_label = primary_label
        self.current = primary_factory()
        self.fallbacks = fallbacks or []

    def _try_fallbacks(self):
        for label, factory in self.fallbacks:
            try:
                self.current = factory()
                self.current_label = label
                print(t(self.ui_lang, "engine_switched", name=label))
                return True
            except Exception:
                print(t(self.ui_lang, "engine_fallback_failed", name=label))
        return False

    def transcribe(self, audio_path, language):
        try:
            result = self.current.transcribe(audio_path, language)
            if result and getattr(result, "text", ""):
                return result
            if self._try_fallbacks():
                try:
                    return self.current.transcribe(audio_path, language)
                except Exception as exc2:
                    print(t(self.ui_lang, "engine_failed", error=exc2))
            return result
        except Exception as exc:
            if self._try_fallbacks():
                try:
                    return self.current.transcribe(audio_path, language)
                except Exception as exc2:
                    print(t(self.ui_lang, "engine_failed", error=exc2))
            else:
                print(t(self.ui_lang, "engine_failed", error=exc))
        return TranscriptionResult(text="")


def choose_engine(ui_lang, prefs_out: dict | None = None):
    while True:
        print_wizard(
            ui_lang,
            title_key="engine_title",
            subtitle_key="engine_subtitle",
            options=[
                ("1", "engine_local_title", "engine_local_desc"),
                ("2", "engine_vosk_title", "engine_vosk_desc"),
                ("3", "engine_api_title", "engine_api_desc"),
            ],
        )
        choice = input(t(ui_lang, "engine_select")).strip().lower()
        if choice in ("2", "vosk"):
            transcriber = create_vosk_transcriber(ui_lang)
            if transcriber is None:
                continue
            if prefs_out is not None:
                prefs_out["stt"] = "vosk"
                prefs_out.pop("stt_provider", None)
            return transcriber
        if choice in ("3", "api"):
            transcriber = create_api_transcriber(ui_lang, prefs_out)
            if transcriber is None:
                continue
            return transcriber
        transcriber = create_local_transcriber(ui_lang)
        if transcriber is None:
            continue
        if prefs_out is not None:
            prefs_out["stt"] = "whisper"
            prefs_out.pop("stt_provider", None)
        return transcriber


def create_api_transcriber(ui_lang, prefs_out: dict | None = None):
    providers = load_providers()
    if not providers:
        print(t(ui_lang, "provider_missing"))
        return create_local_transcriber(ui_lang)

    print("\n" + t(ui_lang, "provider_title"))
    for i, provider in enumerate(providers, start=1):
        label = provider.get("label") or provider.get("id", f"provider_{i}")
        print(f"{i}) {label}")

    choice = input(t(ui_lang, "provider_select")).strip().lower()
    provider = None
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(providers):
            provider = providers[idx]
    else:
        for item in providers:
            if item.get("id", "").lower() == choice:
                provider = item
                break
    if provider is None:
        provider = providers[0]

    report = validate_provider(provider)
    if report.get("errors"):
        reasons = ", ".join(report["errors"])
        print(t(ui_lang, "provider_invalid", name=provider.get("id", "provider"), reason=reasons))
        return create_local_transcriber(ui_lang)
    if report.get("warnings"):
        reasons = ", ".join(report["warnings"])
        print(t(ui_lang, "provider_warning", name=provider.get("id", "provider"), reason=reasons))

    provider_id = provider.get("id", "provider")
    saved = get_entry("stt", provider_id)
    saved_key = saved.get("api_key") if isinstance(saved, dict) else None
    if saved_key:
        api_key = input(t(ui_lang, "api_key_prompt_saved")).strip()
        if not api_key:
            api_key = saved_key
    else:
        api_key = input(t(ui_lang, "api_key_prompt")).strip()
    if not api_key:
        print(t(ui_lang, "api_failed"))
        return create_local_transcriber(ui_lang)

    model_hint = provider.get("model_hint") or DEFAULT_API_MODEL
    saved_model = saved.get("model") if isinstance(saved, dict) else None
    model_default = saved_model or model_hint
    model = input(t(ui_lang, "api_model_prompt", default=model_default)).strip()
    if not model:
        model = model_default

    set_entry("stt", provider_id, {"api_key": api_key, "model": model})
    print(t(ui_lang, "api_saved"))
    if prefs_out is not None:
        prefs_out["stt"] = "api"
        prefs_out["stt_provider"] = provider_id

    try:
        label = t(ui_lang, "engine_label_api", provider=provider.get("label", provider.get("id", "api")), model=model)
        return SwitchableTranscriber(
            ui_lang,
            label,
            lambda: HttpApiTranscriber(provider=provider, api_key=api_key, model=model),
            fallbacks=[(_whisper_label(ui_lang), LocalTranscriber)],
        )
    except Exception:
        print(t(ui_lang, "api_failed"))
        return create_local_transcriber(ui_lang)


def create_vosk_transcriber(ui_lang):
    model_dir = find_vosk_model_dir(ui_lang)
    if model_dir is None:
        expected = get_vosk_model_dir(ui_lang)
        print(t(ui_lang, "vosk_missing_model", path=expected))
        return None
    try:
        label = _vosk_label(ui_lang)
        fallbacks = []
        if _whisper_available():
            fallbacks.append((_whisper_label(ui_lang), LocalTranscriber))
        return SwitchableTranscriber(
            ui_lang,
            label,
            lambda: VoskTranscriber(model_dir=model_dir),
            fallbacks=fallbacks,
        )
    except Exception:
        print(t(ui_lang, "engine_init_failed", name=_vosk_label(ui_lang)))
        return None


def _whisper_label(ui_lang):
    return t(ui_lang, "engine_label_whisper", size=LOCAL_MODEL_SIZE)


def _vosk_label(ui_lang):
    return t(ui_lang, "engine_label_vosk_tr" if ui_lang == "tr" else "engine_label_vosk_en")


def _whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except Exception:
        return False


def stt_available(ui_lang: str) -> bool:
    return _whisper_available() or find_vosk_model_dir(ui_lang) is not None


def get_stt_label(transcriber) -> str:
    return getattr(transcriber, "current_label", "unknown")


def create_local_transcriber(ui_lang):
    label = _whisper_label(ui_lang)
    fallbacks = []
    vosk_dir = find_vosk_model_dir(ui_lang)
    if vosk_dir is not None:
        fallbacks.append((_vosk_label(ui_lang), lambda: VoskTranscriber(model_dir=vosk_dir)))
    try:
        return SwitchableTranscriber(ui_lang, label, LocalTranscriber, fallbacks=fallbacks)
    except Exception:
        print(t(ui_lang, "engine_init_failed", name=label))
        return None
