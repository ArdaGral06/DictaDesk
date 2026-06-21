import threading

import pytest

from task_cancel import TaskCancelled, check_cancelled, sleep_cancellable


def test_sleep_cancellable_raises_when_cancelled():
    event = threading.Event()
    event.set()
    with pytest.raises(TaskCancelled):
        sleep_cancellable(1.0, event)


def test_check_cancelled_no_event():
    check_cancelled(None)
