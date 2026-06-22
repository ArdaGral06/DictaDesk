from dataclasses import dataclass
from pathlib import Path

import requests

from http_retry import post_with_retry

from config import (
    API_TIMEOUT_SEC,
    DEFAULT_UI_LANG,
    LOCAL_CPU_THREADS,
    LOCAL_MODEL_SIZE,
    VOSK_MODEL_EN_NAME,
    VOSK_MODEL_EN_DIR,
    VOSK_MODEL_TR_NAME,
    VOSK_MODEL_TR_DIR,
    VOSK_MODELS_DIR,
)


@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    language_probability: float | None = None
    segments: list | None = None


class LocalTranscriber:
    def __init__(self):
        from faster_whisper import WhisperModel

        from local_ai_device import resolve_whisper_settings, whisper_backend_label

        device, compute_type = resolve_whisper_settings()
        self.device = device
        self.compute_type = compute_type
        self.backend = whisper_backend_label(device)
        self.model = WhisperModel(
            LOCAL_MODEL_SIZE,
            device=device,
            compute_type=compute_type,
            cpu_threads=LOCAL_CPU_THREADS,
        )

    def _transcribe_lang(self, audio_path: Path, language: str | None):
        lang = language if language and language != "auto" else None
        segments, info = self.model.transcribe(
            str(audio_path), beam_size=5, language=lang
        )
        segments = list(segments)
        full_text = " ".join(segment.text.strip() for segment in segments).strip()
        return TranscriptionResult(
            text=full_text,
            language=language or getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            segments=segments,
        )

    def _score(self, result: TranscriptionResult) -> float:
        if not result or not result.text:
            return -1e9
        scores = []
        for seg in result.segments or []:
            val = getattr(seg, "avg_logprob", None)
            if val is not None:
                scores.append(val)
        if scores:
            return float(sum(scores) / max(1, len(scores)))
        return float(len(result.text))

    def transcribe(self, audio_path: Path, language: str | None):
        if language in ("tr", "en"):
            return self._transcribe_lang(audio_path, language)
        # Single pass: Whisper auto-detects language (no TR+EN double cost).
        return self._transcribe_lang(audio_path, None)


class HttpApiTranscriber:
    def __init__(self, provider: dict, api_key: str, model: str):
        self.provider = provider
        self.api_key = api_key
        self.model = model

    def _build_headers(self) -> dict:
        headers = {}
        template = self.provider.get("headers", {"Authorization": "Bearer {api_key}"})
        for key, value in template.items():
            if isinstance(value, str):
                headers[key] = value.format(api_key=self.api_key)
        return headers

    def _transcribe_lang(self, audio_path: Path, language: str | None):
        endpoint = str(self.provider.get("endpoint", "")).strip()
        if not endpoint:
            raise RuntimeError("endpoint_missing")
        if not self.api_key:
            raise RuntimeError("api_key_missing")

        from api_budget import check_budget, record_budget_usage

        allowed, block_msg = check_budget("stt", DEFAULT_UI_LANG)
        if not allowed:
            raise RuntimeError(block_msg or "budget_blocked")

        fields = self.provider.get("fields", {}) if isinstance(self.provider, dict) else {}
        file_field = fields.get("file", "file")
        model_field = fields.get("model", "model")
        language_field = fields.get("language", "language")

        headers = self._build_headers()
        data = {model_field: self.model}
        if language_field and language and language != "auto":
            data[language_field] = language

        timeout = int(self.provider.get("timeout_sec", API_TIMEOUT_SEC))

        with open(audio_path, "rb") as f:
            files = {file_field: f}
            resp = post_with_retry(
                endpoint,
                headers=headers,
                files=files,
                data=data,
                timeout=timeout,
            )
        resp.raise_for_status()
        record_budget_usage("stt")

        try:
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError(f"invalid_json: {exc}") from exc

        text_field = self.provider.get("response_text_field", "text")
        segments_field = self.provider.get("response_segments_field", "segments")

        text = ""
        language_out = None
        segments = None
        if isinstance(payload, dict):
            text = payload.get(text_field, "") or payload.get("text", "")
            segments = payload.get(segments_field)
            language_out = payload.get("language")

        return TranscriptionResult(
            text=text or "",
            language=language or language_out,
            language_probability=None,
            segments=segments,
        )

    def _score(self, result: TranscriptionResult) -> float:
        if not result or not result.text:
            return -1e9
        letters = [c for c in result.text if c.isalpha()]
        return float(len(letters))

    def transcribe(self, audio_path: Path, language: str | None):
        if language in ("tr", "en"):
            return self._transcribe_lang(audio_path, language)
        # Single API call; provider detects language when field omitted.
        return self._transcribe_lang(audio_path, None)


class VoskTranscriber:
    def __init__(self, model_dir: Path):
        from vosk import Model

        if not model_dir.exists():
            raise FileNotFoundError(f"vosk_model_missing: {model_dir}")
        self.model = Model(str(model_dir))

    def transcribe(self, audio_path: Path, language: str | None):
        import json
        import soundfile as sf
        import numpy as np
        from vosk import KaldiRecognizer

        data, samplerate = sf.read(str(audio_path), dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        pcm = (mono * 32767).astype(np.int16)

        rec = KaldiRecognizer(self.model, samplerate)
        rec.SetWords(True)

        bytes_data = pcm.tobytes()
        chunk_size = 4000
        for i in range(0, len(bytes_data), chunk_size):
            rec.AcceptWaveform(bytes_data[i : i + chunk_size])

        result = json.loads(rec.FinalResult())
        text = result.get("text", "")
        segments = result.get("result")
        return TranscriptionResult(
            text=text or "",
            language=language,
            language_probability=None,
            segments=segments,
        )


def _looks_like_vosk_model(path: Path) -> bool:
    if not path.exists():
        return False
    # Different Vosk models expose different layouts.
    return (
        (path / "conf").exists()
        or (path / "mfcc.conf").exists()
        or (path / "final.mdl").exists()
    )


def _find_model_dir(base: Path) -> Path | None:
    if _looks_like_vosk_model(base):
        return base
    if base.exists() and base.is_dir():
        for child in base.iterdir():
            if child.is_dir() and _looks_like_vosk_model(child):
                return child
    return None


def find_vosk_model_dir(ui_lang: str) -> Path | None:
    if ui_lang == "tr":
        primary = VOSK_MODEL_TR_DIR
        fallback = VOSK_MODELS_DIR / VOSK_MODEL_TR_NAME
    else:
        primary = VOSK_MODEL_EN_DIR
        fallback = VOSK_MODELS_DIR / VOSK_MODEL_EN_NAME

    found = _find_model_dir(primary)
    if found:
        return found
    return _find_model_dir(fallback)


def get_vosk_model_dir(ui_lang: str) -> Path:
    if ui_lang == "tr":
        primary = VOSK_MODEL_TR_DIR
    else:
        primary = VOSK_MODEL_EN_DIR

    found = find_vosk_model_dir(ui_lang)
    return found if found else primary
