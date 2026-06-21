import io
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import requests
import sounddevice as sd
import soundfile as sf

from config import (
    DEFAULT_UI_LANG,
    PIPER_BIN,
    PIPER_MODEL_PATH,
    PIPER_MODELS_DIR,
    PIPER_SPEAKER,
    TTS_OUTPUT_DIR,
    TTS_PROVIDERS_JSON,
)
from http_retry import post_with_retry
from i18n import t
from ui_terminal import print_wizard
from secrets_store import get_entry, set_entry


class BaseTTS:
    def speak(self, text: str):
        raise NotImplementedError

    def speak_async(self, text: str):
        thread = threading.Thread(target=self.speak, args=(text,), daemon=True)
        thread.start()


class TTSManager:
    def __init__(self, tts: BaseTTS | None, label: str, enabled: bool, available: bool):
        self.tts = tts
        self.label = label
        self.enabled = enabled
        self.available = available

    def toggle(self):
        self.enabled = not self.enabled

    def speak_async(self, text: str):
        if self.enabled and self.tts:
            self.tts.speak_async(text)

    def status_text(self, ui_lang: str) -> str:
        if self.tts and self.enabled:
            return t(ui_lang, "tts_status_on", name=self.label)
        if self.tts and not self.enabled:
            return t(ui_lang, "tts_status_off", name=self.label)
        if self.available:
            return t(ui_lang, "tts_status_off_available", name=self.label)
        return t(ui_lang, "tts_status_missing")


def _play_wav_bytes(data: bytes) -> bool:
    try:
        with io.BytesIO(data) as bio:
            audio, sr = sf.read(bio, dtype="float32")
        sd.play(audio, sr)
        sd.wait()
        return True
    except Exception:
        return False


def _play_wav_file(path: Path) -> bool:
    try:
        audio, sr = sf.read(str(path), dtype="float32")
        sd.play(audio, sr)
        sd.wait()
        return True
    except Exception:
        return False


def _open_file(path: Path):
    os.startfile(path)  # type: ignore[attr-defined]


def _resolve_piper_bin() -> Path | None:
    if PIPER_BIN:
        candidate = Path(PIPER_BIN)
        if candidate.exists():
            return candidate
    which = shutil.which("piper")
    if which:
        return Path(which)
    local = Path(__file__).resolve().parent / "piper" / "piper.exe"
    if local.exists():
        return local
    return None


def piper_available() -> bool:
    if not _resolve_piper_bin():
        return False
    model_path, config_path = _resolve_piper_model()
    return model_path is not None and config_path is not None


def require_piper(ui_lang: str) -> bool:
    if piper_available():
        return True
    print(t(ui_lang, "tts_piper_required"))
    return False


def _resolve_piper_model() -> tuple[Path | None, Path | None]:
    if PIPER_MODEL_PATH:
        model = Path(PIPER_MODEL_PATH)
        if model.exists():
            cfg = Path(str(model) + ".json")
            if cfg.exists():
                return model, cfg
    if PIPER_MODELS_DIR.exists():
        for model in PIPER_MODELS_DIR.rglob("*.onnx"):
            cfg = Path(str(model) + ".json")
            if cfg.exists():
                return model, cfg
    return None, None


class PiperTTS(BaseTTS):
    def __init__(self, piper_bin: Path, model_path: Path, config_path: Path | None):
        self.piper_bin = piper_bin
        self.model_path = model_path
        self.config_path = config_path

    def speak(self, text: str):
        if not text:
            return
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = TTS_OUTPUT_DIR / f"tts_{timestamp}.wav"
        cmd = [str(self.piper_bin), "--model", str(self.model_path), "--output_file", str(out_path)]
        if self.config_path:
            cmd += ["--config", str(self.config_path)]
        if PIPER_SPEAKER:
            cmd += ["--speaker", str(PIPER_SPEAKER)]
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            if not _play_wav_file(out_path):
                _open_file(out_path)
        except Exception:
            return


class ApiTTS(BaseTTS):
    def __init__(self, provider: dict, api_key: str, voice_id: str | None, model: str | None):
        self.provider = provider
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model

    def _format(self, value, **kwargs):
        if isinstance(value, str):
            return value.format(**kwargs)
        if isinstance(value, dict):
            return {k: self._format(v, **kwargs) for k, v in value.items()}
        if isinstance(value, list):
            return [self._format(v, **kwargs) for v in value]
        return value

    def speak(self, text: str):
        if not text:
            return
        endpoint = str(self.provider.get("endpoint", "")).strip()
        if not endpoint:
            return
        if "{voice_id}" in endpoint and not self.voice_id:
            return

        from api_budget import check_budget, record_budget_usage

        allowed, block_msg = check_budget("tts", DEFAULT_UI_LANG)
        if not allowed:
            return

        endpoint = endpoint.format(voice_id=self.voice_id or "")
        headers_tpl = self.provider.get("headers", {})
        headers = self._format(headers_tpl, api_key=self.api_key, voice_id=self.voice_id or "", model=self.model or "", text=text)

        payload_tpl = self.provider.get("json", {})
        payload = self._format(payload_tpl, text=text, model=self.model or "", voice_id=self.voice_id or "")

        model_field = self.provider.get("model_field")
        if model_field and self.model:
            payload[model_field] = self.model

        query_tpl = self.provider.get("query", {})
        query = self._format(query_tpl, text=text, model=self.model or "", voice_id=self.voice_id or "")

        timeout = int(self.provider.get("timeout_sec", 30))
        try:
            resp = post_with_retry(
                endpoint, headers=headers, json=payload, params=query, timeout=timeout
            )
            resp.raise_for_status()
            record_budget_usage("tts")
        except Exception:
            return

        content = resp.content
        if not content:
            return
        response_format = str(self.provider.get("response_format", "wav")).lower()
        if response_format == "wav":
            if not _play_wav_bytes(content):
                out_path = TTS_OUTPUT_DIR / f"tts_{time.strftime('%Y%m%d_%H%M%S')}.wav"
                out_path.write_bytes(content)
                _open_file(out_path)
        else:
            out_path = TTS_OUTPUT_DIR / f"tts_{time.strftime('%Y%m%d_%H%M%S')}.{response_format}"
            out_path.write_bytes(content)
            _open_file(out_path)


def load_tts_providers():
    if not TTS_PROVIDERS_JSON.exists():
        return []
    data = json.loads(TTS_PROVIDERS_JSON.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("providers"), list):
        return data["providers"]
    if isinstance(data, list):
        return data
    return []


def choose_tts(ui_lang, prefs_out: dict | None = None):
    label_piper = t(ui_lang, "tts_label_piper")
    label_api = t(ui_lang, "tts_label_api")
    available = piper_available()

    print_wizard(
        ui_lang,
        title_key="tts_title",
        subtitle_key="tts_subtitle",
        options=[
            ("1", "tts_off_title", "tts_off_desc"),
            ("2", "tts_local_title", "tts_local_desc"),
            ("3", "tts_api_title", "tts_api_desc"),
        ],
    )
    choice = input(t(ui_lang, "tts_select")).strip().lower()

    if choice in ("2", "local", "piper"):
        piper_bin = _resolve_piper_bin()
        if not piper_bin:
            print(t(ui_lang, "tts_piper_missing_bin"))
            if prefs_out is not None:
                prefs_out["tts"] = "off"
                prefs_out.pop("tts_provider", None)
            return TTSManager(None, label_piper, enabled=False, available=available)
        model_path, config_path = _resolve_piper_model()
        if not model_path:
            print(t(ui_lang, "tts_piper_missing_model"))
            if prefs_out is not None:
                prefs_out["tts"] = "off"
                prefs_out.pop("tts_provider", None)
            return TTSManager(None, label_piper, enabled=False, available=available)
        if prefs_out is not None:
            prefs_out["tts"] = "piper"
            prefs_out.pop("tts_provider", None)
        return TTSManager(
            PiperTTS(piper_bin=piper_bin, model_path=model_path, config_path=config_path),
            label_piper,
            enabled=True,
            available=available,
        )

    if choice in ("3", "api"):
        providers = load_tts_providers()
        if not providers:
            print(t(ui_lang, "tts_provider_missing"))
            return TTSManager(None, label_piper, enabled=False, available=available)

        print("\n" + t(ui_lang, "tts_provider_title"))
        for i, provider in enumerate(providers, start=1):
            label = provider.get("label") or provider.get("id", f"provider_{i}")
            print(f"{i}) {label}")

        select = input(t(ui_lang, "tts_provider_select")).strip().lower()
        provider = None
        if select.isdigit():
            idx = int(select) - 1
            if 0 <= idx < len(providers):
                provider = providers[idx]
        else:
            for item in providers:
                if item.get("id", "").lower() == select:
                    provider = item
                    break
        if provider is None:
            provider = providers[0]

        provider_id = provider.get("id", "provider")
        saved = get_entry("tts", provider_id)
        saved_key = saved.get("api_key") if isinstance(saved, dict) else None
        if saved_key:
            api_key = input(t(ui_lang, "tts_api_key_prompt_saved")).strip()
            if not api_key:
                api_key = saved_key
        else:
            api_key = input(t(ui_lang, "tts_api_key_prompt")).strip()
        if not api_key:
            return TTSManager(None, label_piper, enabled=False, available=available)

        voice_id = None
        endpoint = str(provider.get("endpoint", ""))
        if "{voice_id}" in endpoint:
            saved_voice = saved.get("voice_id") if isinstance(saved, dict) else None
            voice_id = input(t(ui_lang, "tts_voice_prompt_saved", default=saved_voice or "")).strip()
            if not voice_id and saved_voice:
                voice_id = saved_voice
            if not voice_id:
                return TTSManager(None, label_piper, enabled=False, available=available)

        saved_model = saved.get("model") if isinstance(saved, dict) else None
        model = input(t(ui_lang, "tts_model_prompt_saved", default=saved_model or "")).strip()
        if not model and saved_model:
            model = saved_model

        set_entry("tts", provider_id, {"api_key": api_key, "voice_id": voice_id, "model": model})
        print(t(ui_lang, "api_saved"))
        if prefs_out is not None:
            prefs_out["tts"] = "api"
            prefs_out["tts_provider"] = provider_id

        label = f"{label_api} ({provider.get('label', provider.get('id', 'api'))})"
        return TTSManager(
            ApiTTS(provider=provider, api_key=api_key, voice_id=voice_id, model=model),
            label,
            enabled=True,
            available=available,
        )

    if prefs_out is not None:
        prefs_out["tts"] = "off"
        prefs_out.pop("tts_provider", None)
    return TTSManager(None, label_piper, enabled=False, available=available)
