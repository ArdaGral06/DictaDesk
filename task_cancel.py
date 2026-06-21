"""Cooperative cancellation for long-running sync tasks."""

from __future__ import annotations

import time
from threading import Event


class TaskCancelled(RuntimeError):
    """Raised when cancel_event is set during a long operation."""


def check_cancelled(cancel_event: Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise TaskCancelled("cancelled")


def sleep_cancellable(
    seconds: float,
    cancel_event: Event | None = None,
    *,
    step: float = 0.15,
) -> None:
    end = time.monotonic() + max(0.0, float(seconds))
    while time.monotonic() < end:
        check_cancelled(cancel_event)
        remaining = end - time.monotonic()
        time.sleep(min(step, remaining))
