"""
jobs.py — in-process ingest job store + single-worker executor (Fase 3).

Why threads in-process and not Celery/RQ/SQS: this app deploys as a single
instance (Render web service, one process). An in-process ThreadPoolExecutor
with max_workers=1 gives exactly what the demo needs — the request returns
immediately (202 + job_id), reindexes are serialized (one at a time, replacing
the old lock-as-queue behavior), and there is zero infrastructure to operate.
The trade-off is explicit: jobs die with the process (no persistence, no
retries) and the queue cannot span multiple instances. The upgrade path when
either matters is an external broker (Celery/RQ/SQS) behind the same JobStore
interface; that cost is deliberately not paid today.

States: queued → extracting → embedding → indexing → done | failed.
Retention: the newest MAX_JOBS jobs; older ones expire (job fetch → 404).

Tests call configure(run_inline=True) so submitted work runs synchronously in
the caller's thread (no sleeping/polling), and reset_jobs() between tests.
"""

import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

JOB_STATES = ("queued", "extracting", "embedding", "indexing", "done", "failed")
TERMINAL_STATES = ("done", "failed")
MAX_JOBS = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Thread-safe in-memory job registry with bounded retention."""

    def __init__(self, max_jobs: int = MAX_JOBS):
        self._jobs: "OrderedDict[str, dict]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def create(self, workspace: str) -> dict:
        job = {
            "id": uuid.uuid4().hex[:12],
            "workspace": workspace,
            "state": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "error": None,
            "result": None,
        }
        with self._lock:
            self._jobs[job["id"]] = job
            while len(self._jobs) > self._max_jobs:
                self._jobs.popitem(last=False)
        return dict(job)

    def update(
        self,
        job_id: str,
        state: Optional[str] = None,
        error: Optional[dict] = None,
        result: Optional[dict] = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:  # expired out of retention mid-run; nothing to record
                return
            if state is not None:
                if state not in JOB_STATES:
                    raise ValueError(f"Unknown job state {state!r}")
                job["state"] = state
            if error is not None:
                job["error"] = error
            if result is not None:
                job["result"] = result
            job["updated_at"] = _now()

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self, workspace: Optional[str] = None) -> list:
        """Jobs newest-first, optionally filtered by workspace."""
        with self._lock:
            jobs = [dict(j) for j in self._jobs.values()]
        if workspace is not None:
            jobs = [j for j in jobs if j["workspace"] == workspace]
        return list(reversed(jobs))

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


_store = JobStore()
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()
_run_inline = False


def get_store() -> JobStore:
    return _store


def configure(run_inline: bool) -> None:
    """Tests: run_inline=True executes submitted work synchronously."""
    global _run_inline
    _run_inline = run_inline


def submit(fn: Callable[[], None]) -> None:
    """Run `fn` on the single ingest worker (or inline under tests).

    max_workers=1 is the serialization mechanism: two concurrent uploads
    queue behind each other instead of racing the reindex.
    """
    if _run_inline:
        fn()
        return
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="qt-ingest"
            )
        _executor.submit(fn)


def reset_jobs() -> None:
    """Tests: drop all recorded jobs (does not touch the executor)."""
    _store.clear()
