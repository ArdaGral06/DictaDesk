import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import (
    DEFAULT_SAMPLE_RATE,
    RECORDINGS_DIR,
    SCREENSHOTS_DIR,
    GUI_MAP_DIR,
    TEST_SOUNDS_DIR,
    SUPPORTED_EXTENSIONS,
    TTS_OUTPUT_DIR,
    PIPER_MODELS_DIR,
    LLM_MODELS_DIR,
    DEBUG_REPLAY_DIR,
    TRANSCRIPTS_DIR,
    VAD_ENABLED,
    VAD_MIN_ACTIVE_FRAMES,
    VAD_RMS_THRESHOLD,
    VOSK_MODEL_EN_DIR,
    VOSK_MODEL_TR_DIR,
    VOSK_MODELS_DIR,
    MEMORY_DIR,
)
from i18n import t


def ensure_dirs():
    for d in [
        TEST_SOUNDS_DIR,
        RECORDINGS_DIR,
        TRANSCRIPTS_DIR,
        SCREENSHOTS_DIR,
        GUI_MAP_DIR,
        MEMORY_DIR,
        VOSK_MODELS_DIR,
        VOSK_MODEL_TR_DIR,
        VOSK_MODEL_EN_DIR,
        TTS_OUTPUT_DIR,
        PIPER_MODELS_DIR,
        LLM_MODELS_DIR,
        DEBUG_REPLAY_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def list_audio_files():
    files = [
        p
        for p in TEST_SOUNDS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort(key=lambda p: p.name.lower())
    return files


def choose_audio_file(ui_lang):
    files = list_audio_files()
    if not files:
        print(t(ui_lang, "test_folder_empty"))
        print(t(ui_lang, "test_folder_path", path=TEST_SOUNDS_DIR))
        return None

    print("\n" + t(ui_lang, "audio_files"))
    for i, p in enumerate(files, start=1):
        print(f"{i}. {p.name}")

    while True:
        choice = input(t(ui_lang, "choose_number")).strip().lower()
        if choice in ("q", "quit", "exit", "cik", "çık"):
            return None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return files[idx]
        print(t(ui_lang, "invalid_number"))


def get_input_samplerate():
    try:
        info = sd.query_devices(None, "input")
        return int(info.get("default_samplerate", DEFAULT_SAMPLE_RATE))
    except Exception:
        return DEFAULT_SAMPLE_RATE


def audio_has_speech(audio_path: Path) -> bool:
    if not VAD_ENABLED:
        return True
    try:
        data, samplerate = sf.read(str(audio_path), dtype="float32", always_2d=True)
    except Exception:
        return True
    if data.size == 0:
        return False
    mono = data.mean(axis=1)
    if mono.size == 0:
        return False
    frame_len = max(1, int(samplerate * 0.03))  # ~30ms frames
    active = 0
    for i in range(0, len(mono), frame_len):
        frame = mono[i : i + frame_len]
        if frame.size == 0:
            continue
        rms = float(np.sqrt(np.mean(frame**2)))
        if rms >= VAD_RMS_THRESHOLD:
            active += 1
            if active >= VAD_MIN_ACTIVE_FRAMES:
                return True
    return False


class Recorder:
    def __init__(self):
        self.frames = []
        self.stream = None
        self.samplerate = DEFAULT_SAMPLE_RATE
        self.active_frames = 0
        self.total_frames = 0

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(status)
        self.frames.append(indata.copy())
        if VAD_ENABLED:
            rms = float(np.sqrt(np.mean(indata**2)))
            if rms >= VAD_RMS_THRESHOLD:
                self.active_frames += 1
        self.total_frames += 1

    def start(self):
        self.frames = []
        self.samplerate = get_input_samplerate()
        self.active_frames = 0
        self.total_frames = 0
        self.stream = sd.InputStream(
            samplerate=self.samplerate, channels=1, callback=self._callback
        )
        self.stream.start()

    def stop_and_save(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.frames:
            return None
        if VAD_ENABLED and self.active_frames < VAD_MIN_ACTIVE_FRAMES:
            self.frames = []
            return None

        data = np.concatenate(self.frames, axis=0)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        out_path = RECORDINGS_DIR / f"recording_{timestamp}.wav"
        sf.write(out_path, data, self.samplerate)
        self.frames = []
        return out_path
