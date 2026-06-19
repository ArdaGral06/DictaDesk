from audio_io import audio_has_speech, choose_audio_file, ensure_dirs
from engine import get_stt_label
from config import DEFAULT_UI_LANG
from engine import choose_engine
from i18n import safe_lang, t


def run_test_mode(ui_lang, transcriber, tts_manager=None):
    audio_path = choose_audio_file(ui_lang)
    if audio_path is None:
        return

    print("\n" + t(ui_lang, "test_processing", name=audio_path.name))
    if not audio_has_speech(audio_path):
        print(t(ui_lang, "vad_no_speech"))
        return
    stt_label = get_stt_label(transcriber)
    tts_status = tts_manager.status_text(ui_lang) if tts_manager else "-"
    print(
        t(ui_lang, "active_models", stt=stt_label, tts=tts_status, llm="-", vlm="-")
    )
    result = transcriber.transcribe(audio_path, None)

    print("-" * 50)
    if result.language and result.language_probability is not None:
        print(
            t(
                ui_lang,
                "detected_language",
                lang=result.language,
                prob=result.language_probability * 100,
            )
        )
        print("-" * 50)
    if result.segments:
        for seg in result.segments:
            try:
                line = f"[{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text}"
            except Exception:
                line = str(seg)
            print(line)
    else:
        print(result.text)

    if result.text:
        print("-" * 50)
        print(t(ui_lang, "detected_text", text=result.text))
    else:
        print(t(ui_lang, "no_text"))


def main():
    ui_lang = safe_lang(
        input(t(DEFAULT_UI_LANG, "choose_ui_language")).strip().lower() or DEFAULT_UI_LANG
    )
    ensure_dirs()
    transcriber = choose_engine(ui_lang)
    run_test_mode(ui_lang, transcriber)


if __name__ == "__main__":
    main()
