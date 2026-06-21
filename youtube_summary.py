"""Fetch a YouTube transcript and summarise it with the active LLM.

Accepts either a YouTube URL/ID or a free-text search query. Falls back to a
lightweight HTML scrape to resolve the first non-Shorts result for a query.
The summary is saved under the project's ``transcripts/`` directory.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

try:
    import requests as _requests
except Exception:  # pragma: no cover - optional dependency
    _requests = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi as _YTApi
except Exception:  # pragma: no cover - optional dependency
    _YTApi = None

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_LANG_PRIORITY = ["tr", "en", "de", "fr", "es", "it", "pt", "ru", "ja", "ko", "ar", "zh"]
_MAX_TRANSCRIPT_CHARS = 16000


def extract_video_id(text: str) -> str | None:
    """Return an 11-char YouTube video id from a URL or bare id, else None."""
    if not text:
        return None
    text = text.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return text
    m = re.search(
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", text
    )
    return m.group(1) if m else None


def _scrape_first_video_id(query: str) -> str | None:
    if _requests is None:
        return None
    url = (
        "https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}&sp=EgIQAQ%3D%3D"
    )
    try:
        html = _requests.get(url, headers=_HEADERS, timeout=10).text
    except Exception:
        return None
    seen: set[str] = set()
    for vid in re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html):
        if vid in seen:
            continue
        seen.add(vid)
        if f"/shorts/{vid}" in html:
            continue
        return vid
    return None


def _snippets_to_text(fetched) -> str:
    parts: list[str] = []
    try:
        items = getattr(fetched, "snippets", None) or fetched
        for entry in items:
            if isinstance(entry, dict):
                parts.append(str(entry.get("text", "")))
            else:
                parts.append(str(getattr(entry, "text", "")))
    except Exception:
        return ""
    return " ".join(p for p in parts if p).strip()


def get_transcript(video_id: str) -> str | None:
    """Fetch a transcript across the several youtube-transcript-api versions."""
    if _YTApi is None:
        return None
    # Newer instance API (>= 1.0)
    try:
        api = _YTApi()
        fetched = api.fetch(video_id, languages=_LANG_PRIORITY)
        text = _snippets_to_text(fetched)
        if text:
            return text
    except Exception:
        pass
    # Classic static API
    try:
        fetched = _YTApi.get_transcript(video_id, languages=_LANG_PRIORITY)
        text = _snippets_to_text(fetched)
        if text:
            return text
    except Exception:
        pass
    # list_transcripts fallback
    try:
        listing = _YTApi.list_transcripts(video_id)
        transcript = None
        try:
            transcript = listing.find_manually_created_transcript(_LANG_PRIORITY)
        except Exception:
            try:
                transcript = listing.find_generated_transcript(_LANG_PRIORITY)
            except Exception:
                for tr in listing:
                    transcript = tr
                    break
        if transcript is not None:
            return _snippets_to_text(transcript.fetch())
    except Exception:
        pass
    return None


def _llm_summary(llm, transcript: str, ui_lang: str) -> str | None:
    inner = getattr(llm, "llm", None)
    if not llm or not getattr(llm, "enabled", False) or inner is None:
        return None
    snippet = transcript[:_MAX_TRANSCRIPT_CHARS]
    if ui_lang == "tr":
        system = (
            "Sen yardimci bir asistansin. YouTube video transkriptlerini net ve "
            "kisa ozetle. Once tek cumlelik genel bakis, ardindan 3-5 madde halinde "
            "ana noktalar. Transkriptin dilini koru."
        )
        user = f"Su YouTube video transkriptini ozetle:\n\n{snippet}"
    else:
        system = (
            "You are a helpful assistant. Summarise YouTube transcripts clearly and "
            "concisely: a one-sentence overview, then 3-5 key bullet points. Match "
            "the transcript language."
        )
        user = f"Summarise this YouTube video transcript:\n\n{snippet}"
    try:
        out = inner.generate(user, system_prompt=system, raw_user=True, max_tokens=700)
    except Exception:
        return None
    return (out or "").strip() or None


def _save_summary(summary: str, video_url: str) -> str | None:
    try:
        from config import TRANSCRIPTS_DIR

        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = TRANSCRIPTS_DIR / f"youtube_summary_{ts}.txt"
        header = (
            "DictaDesk - YouTube Ozet\n"
            f"URL : {video_url}\n"
            f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"{'-' * 40}\n\n"
        )
        path.write_text(header + summary, encoding="utf-8")
        return str(path)
    except Exception:
        return None


def summarize_youtube(payload: str, llm=None, ui_lang: str = "en") -> tuple[bool, str]:
    """Resolve, transcribe and summarise a video. Returns (ok, text-or-reason)."""
    if _YTApi is None:
        return False, "youtube_no_api"
    text = (payload or "").strip()
    if not text:
        return False, "youtube_bad_input"

    video_id = extract_video_id(text)
    if not video_id:
        video_id = _scrape_first_video_id(text)
    if not video_id:
        return False, "youtube_no_video"

    transcript = get_transcript(video_id)
    if not transcript:
        return False, "youtube_no_transcript"

    summary = _llm_summary(llm, transcript, ui_lang)
    if not summary:
        if not llm or not getattr(llm, "enabled", False):
            return False, "youtube_no_llm"
        return False, "youtube_summarize_failed"

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    saved = _save_summary(summary, video_url)
    if saved:
        return True, f"{summary}\n\n({saved})"
    return True, summary
