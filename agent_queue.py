import queue
import threading
import time
import uuid
from dataclasses import dataclass


PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"


@dataclass
class AgentJob:
    job_id: str
    text: str
    source: str
    use_commands: bool
    created_at: float
    status: str = PENDING
    result: str | None = None
    error: str = ""
    completed_at: float | None = None


class AgentQueue:
    def __init__(self, handler, cancel_callback=None):
        self._queue = queue.Queue()
        self._pending: list[AgentJob] = []
        self._jobs: dict[str, AgentJob] = {}
        self._history: list[AgentJob] = []
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._handler = handler
        self._current: AgentJob | None = None
        self._cancel_callback = cancel_callback
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def submit(self, text: str, source: str, use_commands: bool) -> AgentJob:
        job = AgentJob(
            job_id=str(uuid.uuid4())[:8],
            text=text,
            source=source,
            use_commands=use_commands,
            created_at=time.time(),
        )
        with self._lock:
            self._pending.append(job)
            self._jobs[job.job_id] = job
        self._queue.put(job)
        return job

    def _worker(self):
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            with self._lock:
                if job.job_id in self._cancelled:
                    self._cancelled.discard(job.job_id)
                    job.status = CANCELLED
                    job.completed_at = time.time()
                    self._history.append(job)
                    self._queue.task_done()
                    continue
            with self._lock:
                self._current = job
                job.status = RUNNING
                self._pending = [j for j in self._pending if j.job_id != job.job_id]
            try:
                result = self._handler(job)
                with self._lock:
                    if job.job_id in self._cancelled:
                        self._cancelled.discard(job.job_id)
                        job.status = CANCELLED
                    else:
                        job.status = COMPLETED
                    job.result = "" if result is None else str(result)
            except Exception as exc:
                with self._lock:
                    job.status = FAILED
                    job.error = str(exc)
            with self._lock:
                job.completed_at = time.time()
                self._history.append(job)
                if len(self._history) > 20:
                    self._history = self._history[-20:]
                self._current = None
            self._queue.task_done()

    def status(self) -> tuple[bool, int]:
        with self._lock:
            current = self._current is not None
            pending = len(self._pending)
        return current, pending

    def snapshot(self) -> tuple[AgentJob | None, list[AgentJob]]:
        with self._lock:
            current = self._current
            pending = list(self._pending)
        return current, pending

    def detailed_snapshot(self) -> tuple[AgentJob | None, list[AgentJob], list[AgentJob]]:
        with self._lock:
            current = self._current
            pending = list(self._pending)
            history = list(self._history[-5:])
        return current, pending, history

    def clear(self):
        with self._lock:
            for job in self._pending:
                job.status = CANCELLED
                job.completed_at = time.time()
                self._history.append(job)
            self._pending.clear()
            self._cancelled.clear()
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    def cancel_current(self) -> bool:
        with self._lock:
            has_current = self._current is not None
            if self._current:
                self._cancelled.add(self._current.job_id)
        if has_current and self._cancel_callback:
            self._cancel_callback()
        return has_current

    def cancel(self, job_id: str) -> bool:
        job_id = (job_id or "").strip()
        if not job_id:
            return False
        with self._lock:
            if self._current and self._current.job_id == job_id:
                current = True
            else:
                current = False
                if any(j.job_id == job_id for j in self._pending):
                    for job in self._pending:
                        if job.job_id == job_id:
                            job.status = CANCELLED
                            job.completed_at = time.time()
                            self._history.append(job)
                            break
                    self._pending = [j for j in self._pending if j.job_id != job_id]
                    self._cancelled.add(job_id)
                    return True
        if current and self._cancel_callback:
            self._cancel_callback()
            return True
        return False

    def stop(self, timeout: float = 15.0):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=max(0.0, timeout))
