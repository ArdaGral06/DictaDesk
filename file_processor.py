"""Process a local file by extension: extract text, summarise, describe or OCR.

Terminal-first: the user supplies a file path (optionally ``path -> action``).
Supported actions: ``summarize`` | ``extract_text`` | ``info`` | ``describe`` | ``ocr``.

Optional dependencies (pypdf, python-docx, pandas/openpyxl) are imported lazily;
when missing, a clear reason code is returned instead of raising.
"""

from __future__ import annotations

from pathlib import Path

_SEPARATORS = ("->", "=>", "|")
_ACTIONS = {"summarize", "extract_text", "info", "describe", "ocr"}
_MAX_TEXT_CHARS = 16000

_TEXT_EXT = {".txt", ".md", ".log", ".rst", ".ini", ".cfg", ".tex"}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".cc", ".h",
    ".hpp", ".cs", ".go", ".rb", ".php", ".rs", ".swift", ".kt", ".sh", ".bat",
    ".ps1", ".sql", ".html", ".css", ".xml", ".yaml", ".yml", ".toml",
}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


def parse_payload(payload: str) -> tuple[str, str | None]:
    """Split ``path -> action`` into (path, action-or-None)."""
    text = (payload or "").strip().strip('"')
    action = None
    for sep in _SEPARATORS:
        if sep in text:
            left, right = text.split(sep, 1)
            text = left.strip().strip('"')
            cand = right.strip().lower()
            if cand in _ACTIONS:
                action = cand
            break
    return text, action


def _read_plain_text(path: Path) -> tuple[str | None, str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace"), ""
    except Exception:
        return None, "file_read_failed"


def _read_pdf(path: Path) -> tuple[str | None, str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return None, "file_dep_pypdf"
    try:
        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts).strip(), ""
    except Exception:
        return None, "file_read_failed"


def _read_docx(path: Path) -> tuple[str | None, str]:
    try:
        import docx
    except Exception:
        return None, "file_dep_docx"
    try:
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs).strip(), ""
    except Exception:
        return None, "file_read_failed"


def _read_tabular(path: Path) -> tuple[str | None, str]:
    try:
        import pandas as pd
    except Exception:
        return None, "file_dep_pandas"
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path)
    except Exception:
        return None, "file_read_failed"
    head = df.head(20).to_string()
    summary = (
        f"Satir: {len(df)}, Sutun: {len(df.columns)}\n"
        f"Sutunlar: {', '.join(map(str, df.columns))}\n\n{head}"
    )
    return summary, ""


def _extract_text(path: Path, ext: str) -> tuple[str | None, str]:
    if ext in _TEXT_EXT or ext in _CODE_EXT or ext == ".json":
        return _read_plain_text(path)
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext in (".csv", ".xlsx", ".xls"):
        return _read_tabular(path)
    return None, "file_unsupported"


def _llm_summary(llm, text: str, ui_lang: str, is_code: bool) -> str | None:
    inner = getattr(llm, "llm", None)
    if not llm or not getattr(llm, "enabled", False) or inner is None:
        return None
    snippet = text[:_MAX_TEXT_CHARS]
    if ui_lang == "tr":
        if is_code:
            system = "Sen bir yazilim asistanisin. Verilen kodun ne yaptigini kisa ve net acikla."
            user = f"Bu kod dosyasini acikla:\n\n{snippet}"
        else:
            system = (
                "Sen yardimci bir asistansin. Belgeyi net ve kisa ozetle: tek cumlelik "
                "genel bakis, ardindan 3-5 madde. Belgenin dilini koru."
            )
            user = f"Bu belgeyi ozetle:\n\n{snippet}"
    else:
        if is_code:
            system = "You are a coding assistant. Explain concisely what the given code does."
            user = f"Explain this code file:\n\n{snippet}"
        else:
            system = (
                "You are a helpful assistant. Summarise the document concisely: a "
                "one-sentence overview then 3-5 bullet points. Match its language."
            )
            user = f"Summarise this document:\n\n{snippet}"
    try:
        out = inner.generate(user, system_prompt=system, raw_user=True, max_tokens=700)
    except Exception:
        return None
    return (out or "").strip() or None


def _describe_image(vlm, path: Path, ui_lang: str) -> str | None:
    inner = getattr(vlm, "llm", None)
    if not vlm or not getattr(vlm, "enabled", False) or inner is None:
        return None
    if ui_lang == "tr":
        prompt = "Bu gorselde ne oldugunu net ve kisa bir sekilde acikla."
    else:
        prompt = "Describe clearly and concisely what is shown in this image."
    try:
        out = inner.generate_with_image(prompt, str(path))
    except Exception:
        return None
    return (out or "").strip() or None


def _ocr_image(path: Path, ui_lang: str) -> tuple[str | None, str]:
    try:
        from config import OCR_LANG_BOTH
        from platform_actions import ocr_text
    except Exception:
        return None, "file_process_failed"
    try:
        text, _src = ocr_text(str(path), lang=OCR_LANG_BOTH)
        return (text or "").strip(), ""
    except Exception:
        return None, "file_ocr_failed"


def _info_string(path: Path) -> str:
    try:
        size = path.stat().st_size
    except Exception:
        size = 0
    if size >= 1024 * 1024:
        size_text = f"{size / (1024 * 1024):.1f} MB"
    elif size >= 1024:
        size_text = f"{size / 1024:.1f} KB"
    else:
        size_text = f"{size} B"
    return f"{path.name} | {path.suffix.lower() or '-'} | {size_text}"


def process_file(payload: str, llm=None, vlm=None, ui_lang: str = "en") -> tuple[bool, str]:
    """Dispatch a file to the right handler. Returns (ok, text-or-reason)."""
    raw = (payload or "").strip()
    if not raw:
        return False, "file_path_missing"
    path_text, action = parse_payload(raw)
    if not path_text:
        return False, "file_path_missing"
    path = Path(path_text).expanduser()
    if not path.exists() or not path.is_file():
        return False, "file_not_found"

    ext = path.suffix.lower()
    is_image = ext in _IMAGE_EXT
    is_code = ext in _CODE_EXT

    if action is None:
        action = "describe" if is_image else "summarize"

    if action == "info":
        return True, _info_string(path)

    if is_image:
        if action == "ocr":
            text, reason = _ocr_image(path, ui_lang)
            if reason:
                return False, reason
            return (True, text) if text else (False, "file_ocr_empty")
        # default for images: describe
        desc = _describe_image(vlm, path, ui_lang)
        if desc:
            return True, desc
        if not vlm or not getattr(vlm, "enabled", False):
            return False, "file_no_vlm"
        return False, "file_process_failed"

    text, reason = _extract_text(path, ext)
    if reason:
        return False, reason
    if not text:
        return False, "file_empty"

    if action in ("extract_text", "ocr"):
        return True, text[:_MAX_TEXT_CHARS]

    # summarize (or code explanation)
    summary = _llm_summary(llm, text, ui_lang, is_code)
    if summary:
        return True, summary
    if not llm or not getattr(llm, "enabled", False):
        return False, "file_no_llm"
    return False, "file_process_failed"
