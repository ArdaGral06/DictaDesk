"""Multi-file project generator for the dev_project action.

Loop: plan with the LLM -> write files -> install pip deps -> run the entry file ->
feed any error back to the LLM to fix -> re-run, for a few rounds. Finally open the
project folder (VS Code if available).

All file writes and execution are confined to ``CODE_PROJECTS_DIR`` for safety.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from config import CODE_PROJECTS_DIR
from shell_guard import run_subprocess_cancellable

_MAX_FILE_CONTENT = 60000
_MAX_FILES = 24
_DEFAULT_MAX_FIX_ROUNDS = 2
_RUN_TIMEOUT = 120.0
_INSTALL_TIMEOUT = 240.0
_FIX_CONTENT_PREVIEW = 4000


def extract_json(text: str) -> dict | None:
    """Extract the first JSON object from a possibly fenced LLM response."""
    if not text:
        return None
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[start : i + 1]
                try:
                    data = json.loads(candidate)
                    return data if isinstance(data, dict) else None
                except Exception:
                    return None
    return None


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (text or "").lower()).strip("-")
    return (slug[:40] or "project")


def project_dir_for(plan: dict, goal: str) -> Path:
    name = ""
    if isinstance(plan, dict):
        name = str(plan.get("folder") or "").strip()
    return CODE_PROJECTS_DIR / _slugify(name or goal)


def _generate(inner, user: str, system: str, max_tokens: int) -> str:
    # ApiLLM accepts compact=False (avoid trimming long file/error context); local LLM does not.
    try:
        return inner.generate(
            user, system_prompt=system, raw_user=True, max_tokens=max_tokens, compact=False
        )
    except TypeError:
        return inner.generate(
            user, system_prompt=system, raw_user=True, max_tokens=max_tokens
        )


def _plan_system(ui_lang: str) -> str:
    if ui_lang == "tr":
        return (
            "Sen guclu bir yazilim asistanisin. Kullanicinin istedigi cok dosyali projeyi "
            "uret. SADECE su JSON semasiyla yanit ver, baska metin yazma:\n"
            '{"folder":"kisa-ad","language":"python|node|web","deps":["paket"],'
            '"run":"main.py","files":[{"path":"main.py","content":"TAM kaynak"}]}\n'
            "Kurallar: Eksiksiz, calisabilir kod yaz; placeholder kullanma. "
            "Yollar projeye gore goreli olsun. Sadece pip/npm paketlerini deps'e koy. "
            "Calistirilacak giris dosyasi yoksa run'i bos birak."
        )
    return (
        "You are a strong coding assistant. Build the multi-file project the user wants. "
        "Reply with ONLY this JSON schema, no other text:\n"
        '{"folder":"short-name","language":"python|node|web","deps":["package"],'
        '"run":"main.py","files":[{"path":"main.py","content":"FULL source"}]}\n'
        "Rules: write complete, runnable code; no placeholders. Paths are relative to the "
        "project. Put only pip/npm packages in deps. Leave run empty if there is no entry file."
    )


def _fix_system(ui_lang: str) -> str:
    if ui_lang == "tr":
        return (
            "Sen bir hata ayiklama asistanisin. Hata ciktisina gore dosyalari duzelt. "
            "SADECE su JSON ile yanit ver: "
            '{"files":[{"path":"main.py","content":"DUZELTILMIS tam kaynak"}]}. '
            "Sadece degisen dosyalari dondur, eksiksiz icerikle."
        )
    return (
        "You are a debugging assistant. Fix the files based on the error output. "
        'Reply with ONLY this JSON: {"files":[{"path":"main.py","content":"FIXED full source"}]}. '
        "Return only changed files, with complete content."
    )


def plan_project(inner, goal: str, ui_lang: str = "en") -> dict | None:
    raw = _generate(inner, goal, _plan_system(ui_lang), max_tokens=6000)
    return extract_json(raw)


def _safe_target(base_dir: Path, rel_path: str) -> Path | None:
    candidate = (base_dir / rel_path).resolve()
    try:
        candidate.relative_to(base_dir.resolve())
    except ValueError:
        return None
    return candidate


def write_project_files(base_dir: Path, files: list) -> list[str]:
    written: list[str] = []
    base_dir.mkdir(parents=True, exist_ok=True)
    for item in (files or [])[:_MAX_FILES]:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "").strip().lstrip("/\\")
        content = item.get("content")
        if not rel or content is None:
            continue
        target = _safe_target(base_dir, rel)
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content)[:_MAX_FILE_CONTENT], encoding="utf-8")
        written.append(str(target))
    return written


def install_deps(deps: list, cwd: str, cancel_event=None) -> tuple[bool, str]:
    clean = [str(d).strip() for d in (deps or []) if str(d).strip()]
    if not clean:
        return True, ""
    cmd = [sys.executable, "-m", "pip", "install", *clean]
    code, stdout, stderr, err = run_subprocess_cancellable(
        cmd, cwd=cwd, timeout=_INSTALL_TIMEOUT, cancel_event=cancel_event
    )
    if err or code != 0:
        return False, (stderr or stdout or err or "").strip()
    return True, (stdout or "").strip()


def run_entry(base_dir: Path, entry: str, cancel_event=None) -> tuple[bool, str]:
    entry = (entry or "").strip()
    if not entry:
        return True, ""
    target = _safe_target(base_dir, entry)
    if target is None or not target.exists():
        return False, f"entry not found: {entry}"
    suffix = target.suffix.lower()
    if suffix == ".py":
        cmd = [sys.executable, str(target)]
    elif suffix in (".js", ".mjs"):
        cmd = ["node", str(target)]
    elif suffix in (".html", ".htm"):
        return True, "html"
    else:
        return False, f"unsupported entry: {entry}"
    code, stdout, stderr, err = run_subprocess_cancellable(
        cmd, cwd=str(base_dir), timeout=_RUN_TIMEOUT, cancel_event=cancel_event
    )
    if err == "cancelled":
        return False, "cancelled"
    if code != 0 or err:
        return False, (stderr or stdout or err or "").strip()
    return True, (stdout or "").strip()


def _files_state(base_dir: Path, written: list[str]) -> str:
    parts = []
    for path in written:
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = p.name
        try:
            rel = str(p.relative_to(base_dir))
        except Exception:
            pass
        parts.append(f"=== {rel} ===\n{text[:_FIX_CONTENT_PREVIEW]}")
    return "\n\n".join(parts)


def request_fix(inner, goal: str, files_state: str, error: str, ui_lang: str = "en") -> dict | None:
    user = (
        f"Goal: {goal}\n\nCurrent files:\n{files_state}\n\n"
        f"Error output:\n{error[:4000]}\n\nReturn corrected files as JSON."
    )
    raw = _generate(inner, user, _fix_system(ui_lang), max_tokens=6000)
    return extract_json(raw)


def _open_project(base_dir: Path) -> None:
    try:
        subprocess.Popen(["code", str(base_dir)], shell=True)
        return
    except Exception:
        pass
    try:
        from platform_actions import open_dir

        open_dir(str(base_dir))
    except Exception:
        pass


def build_project(
    goal: str,
    llm=None,
    ui_lang: str = "en",
    cancel_event=None,
    max_fix_rounds: int = _DEFAULT_MAX_FIX_ROUNDS,
    open_folder: bool = True,
) -> tuple[bool, str]:
    """Plan, write, install, run and (if needed) fix a multi-file project."""
    inner = getattr(llm, "llm", None)
    if not llm or not getattr(llm, "enabled", False) or inner is None:
        return False, "dev_no_llm"

    goal = (goal or "").strip()
    if not goal:
        return False, "missing"

    plan = plan_project(inner, goal, ui_lang)
    if not isinstance(plan, dict) or not plan.get("files"):
        return False, "dev_plan_failed"

    base_dir = project_dir_for(plan, goal)
    written = write_project_files(base_dir, plan.get("files"))
    if not written:
        return False, "dev_write_failed"

    notes: list[str] = [f"{len(written)} dosya -> {base_dir}"]

    deps_ok, deps_out = install_deps(plan.get("deps"), str(base_dir), cancel_event)
    if not deps_ok:
        notes.append(f"pip: {deps_out[:200]}")

    entry = str(plan.get("run") or "").strip()
    run_ok, run_out = run_entry(base_dir, entry, cancel_event)
    rounds = 0
    while not run_ok and entry and rounds < max_fix_rounds:
        if cancel_event is not None and cancel_event.is_set():
            break
        rounds += 1
        fix = request_fix(inner, goal, _files_state(base_dir, written), run_out, ui_lang)
        if not isinstance(fix, dict) or not fix.get("files"):
            break
        new_written = write_project_files(base_dir, fix.get("files"))
        for path in new_written:
            if path not in written:
                written.append(path)
        run_ok, run_out = run_entry(base_dir, entry, cancel_event)

    if entry:
        notes.append(
            f"calistirma: {'ok' if run_ok else 'hata'}"
            + (f" ({rounds} duzeltme)" if rounds else "")
        )

    if open_folder:
        _open_project(base_dir)

    return True, "; ".join(notes)
