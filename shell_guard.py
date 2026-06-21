"""Block destructive shell patterns; helpers for cancellable subprocess runs."""

from __future__ import annotations

import re
import subprocess
import time
from threading import Event

_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bformat\s+[a-z]:", re.I), "format_drive"),
    (re.compile(r"\bdel\s+/[sfq]", re.I), "mass_delete_cmd"),
    (re.compile(r"\brmdir\s+/[sq]", re.I), "mass_delete_cmd"),
    (re.compile(r"remove-item\s+.*-recurse", re.I), "mass_delete_ps"),
    (re.compile(r"clear-content\s+-path\s+[a-z]:\\", re.I), "wipe_drive"),
    (re.compile(r"invoke-webrequest.*\|\s*iex", re.I), "remote_code_exec"),
    (re.compile(r"downloadstring.*\|\s*iex", re.I), "remote_code_exec"),
    (re.compile(r"\bshutdown\s+/[srf]", re.I), "system_shutdown"),
    (re.compile(r"stop-computer\b", re.I), "system_shutdown"),
    (re.compile(r"restart-computer\b", re.I), "system_restart"),
    (re.compile(r"\bbcdedit\b", re.I), "boot_config"),
    (re.compile(r"reg\s+delete\s+", re.I), "registry_delete"),
    (re.compile(r"remove-item\s+.*registry", re.I), "registry_delete"),
]


def blocked_shell_reason(payload: str) -> str | None:
    text = (payload or "").strip()
    if not text:
        return None
    for pattern, reason in _BLOCKED_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def run_subprocess_cancellable(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: float = 120.0,
    cancel_event: Event | None = None,
    capture_output: bool = True,
) -> tuple[int | None, str, str, str | None]:
    """
    Run a subprocess; poll for cancel/timeout.
    Returns (returncode, stdout, stderr, error_reason).
    error_reason is set for cancelled/timeout/start_failed.
    """
    kwargs: dict = {
        "cwd": cwd,
        "text": True,
    }
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except Exception as exc:
        return None, "", str(exc), "start_failed"

    deadline = time.monotonic() + timeout
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3.0)
            return None, "", "", "cancelled"
        if time.monotonic() >= deadline:
            proc.kill()
            proc.wait(timeout=3.0)
            return None, "", "", "timeout"
        time.sleep(0.15)

    stdout = proc.stdout.read() if proc.stdout else ""
    stderr = proc.stderr.read() if proc.stderr else ""
    return proc.returncode, stdout or "", stderr or "", None
