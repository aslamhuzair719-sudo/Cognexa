"""Global FIFO snapshots and wait-time estimates for LLM analysis queues."""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

MIN_REMAINING_SECONDS = 15.0
DEFAULT_PORTAL_SECONDS = 90.0
DEFAULT_WORKFLOW_SECONDS_PER_DOC = 25.0
PORTAL_DOC_COUNT = 4
SAMPLE_WINDOW = 20
MAX_SAMPLE_SECONDS = 1800.0
MIN_SAMPLE_SECONDS = 5.0


class DurationTracker:
    """Rolling average of recent job durations."""

    def __init__(
        self,
        *,
        default_avg: float,
        per_doc: bool = False,
        default_per_doc: float = DEFAULT_WORKFLOW_SECONDS_PER_DOC,
        sample_window: int = SAMPLE_WINDOW,
    ) -> None:
        self.default_avg = default_avg
        self.per_doc = per_doc
        self.default_per_doc = default_per_doc
        self.samples: deque[Tuple[float, int]] = deque(maxlen=sample_window)

    def record(self, seconds: float, docs: int = 1) -> None:
        if seconds < MIN_SAMPLE_SECONDS or seconds > MAX_SAMPLE_SECONDS:
            return
        self.samples.append((float(seconds), max(1, int(docs))))

    def avg_per_doc(self) -> float:
        if not self.samples:
            return self.default_per_doc
        total_s = sum(item[0] for item in self.samples)
        total_d = sum(item[1] for item in self.samples)
        if total_d <= 0:
            return self.default_per_doc
        return total_s / total_d

    def avg_job_seconds(self, docs: int) -> float:
        count = max(1, int(docs or 1))
        if self.per_doc:
            return self.avg_per_doc() * count
        if not self.samples:
            return self.default_avg
        return sum(item[0] for item in self.samples) / len(self.samples)


class InspectableFifo:
    """Thread-safe FIFO that can be snapshotted for ETA (replaces queue.Queue)."""

    def __init_fifo__(
        self,
        *,
        default_avg: float,
        per_doc: bool = False,
        default_per_doc: float = DEFAULT_WORKFLOW_SECONDS_PER_DOC,
    ) -> None:
        self._pending: deque[Tuple[str, int]] = deque()
        self._queued: set[str] = set()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._current_id: Optional[str] = None
        self._current_started_at: Optional[float] = None
        self._docs_done = 0
        self._docs_total = 1
        self._durations = DurationTracker(
            default_avg=default_avg,
            per_doc=per_doc,
            default_per_doc=default_per_doc,
        )
        self._thread: Optional[threading.Thread] = None
        self._started = False

    def _start_worker(self, target, name: str) -> bool:
        with self._lock:
            if self._started:
                return False
            self._started = True
            self._thread = threading.Thread(target=target, name=name, daemon=True)
            self._thread.start()
            return True

    def _enqueue_job(self, job_id: str, docs_total: int) -> bool:
        key = str(job_id)
        with self._cv:
            if key in self._queued:
                return False
            self._queued.add(key)
            self._pending.append((key, max(1, int(docs_total or 1))))
            self._cv.notify()
            return True

    def _dequeue_job(self) -> Tuple[str, int]:
        with self._cv:
            while not self._pending:
                self._cv.wait()
            job_id, docs_total = self._pending.popleft()
            self._current_id = job_id
            self._current_started_at = time.time()
            self._docs_done = 0
            self._docs_total = max(1, int(docs_total or 1))
            return job_id, self._docs_total

    def _finish_job(self, job_id: str, *, record: bool) -> None:
        key = str(job_id)
        with self._lock:
            started = self._current_started_at
            docs = self._docs_total
            if record and started:
                self._durations.record(time.time() - started, docs)
            self._queued.discard(key)
            if self._current_id == key:
                self._current_id = None
                self._current_started_at = None
                self._docs_done = 0

    def mark_doc_done(self) -> None:
        with self._lock:
            if self._docs_done < self._docs_total:
                self._docs_done += 1

    def set_current_docs_total(self, docs_total: int) -> None:
        with self._lock:
            self._docs_total = max(1, int(docs_total or 1))

    def seed_duration_samples(self, samples: Iterable[Tuple[float, int]]) -> None:
        with self._lock:
            for seconds, docs in samples:
                self._durations.record(seconds, docs)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            pending_jobs = []
            for job_id, docs in self._pending:
                pending_jobs.append(
                    {
                        "id": job_id,
                        "docs_total": docs,
                        "expected_seconds": self._durations.avg_job_seconds(docs),
                    }
                )
            current_docs = self._docs_total or 1
            return {
                "current_id": self._current_id,
                "current_started_at": self._current_started_at,
                "docs_done": self._docs_done,
                "docs_total": self._docs_total,
                "avg_seconds": self._durations.avg_job_seconds(current_docs),
                "pending_jobs": pending_jobs,
            }


def remaining_seconds(
    snapshot: Dict[str, Any],
    *,
    min_remaining: float = MIN_REMAINING_SECONDS,
) -> float:
    """Estimated seconds left on the job currently being analyzed."""
    if not snapshot.get("current_id"):
        return 0.0
    expected = float(snapshot.get("avg_seconds") or DEFAULT_PORTAL_SECONDS)
    started = snapshot.get("current_started_at")
    elapsed = max(0.0, time.time() - float(started)) if started else 0.0
    docs_done = int(snapshot.get("docs_done") or 0)
    docs_total = int(snapshot.get("docs_total") or 0)
    if docs_done > 0 and docs_total > 0:
        frac_left = max(0.0, (docs_total - docs_done) / float(docs_total))
        remaining = expected * frac_left
    else:
        remaining = expected - elapsed
    if remaining <= 0:
        return min_remaining
    return max(min_remaining, remaining)


def eta_payload(
    item_id: str,
    status: Optional[str],
    snapshot: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Queue wait payload for one application or workflow entry."""
    key = str(item_id)
    status_value = (status or "").strip().lower()
    if status_value not in {"pending", "analyzing"}:
        return None

    current_id = snapshot.get("current_id")
    pending_jobs: List[Dict[str, Any]] = list(snapshot.get("pending_jobs") or [])
    pending_ids = [str(job.get("id")) for job in pending_jobs]

    if current_id == key:
        remaining = remaining_seconds(snapshot)
        return {
            "state": "analyzing",
            "position": 0,
            "jobs_ahead": 0,
            "eta_seconds": int(round(remaining)),
            "eta_kind": "remaining",
        }

    if key not in pending_ids:
        return None

    idx = pending_ids.index(key)
    jobs_ahead = (1 if current_id else 0) + idx
    waiting_on_current = remaining_seconds(snapshot) if current_id else 0.0
    expected_ahead = sum(
        float(job.get("expected_seconds") or 0) for job in pending_jobs[:idx]
    )
    eta = max(0.0, waiting_on_current + expected_ahead)
    return {
        "state": "pending",
        "position": idx + 1,
        "jobs_ahead": jobs_ahead,
        "eta_seconds": int(round(eta)),
        "eta_kind": "until_start",
    }


def _seconds_between(start: datetime, end: datetime) -> Optional[float]:
    try:
        return (end - start).total_seconds()
    except Exception:
        return None


def samples_from_audit_pairs(
    rows: Iterable[Any],
    *,
    started_action: str,
    completed_action: str,
    id_from_row,
    default_docs: int,
) -> List[Tuple[float, int]]:
    """Pair started/completed audit rows in chronological order."""
    started_at: Dict[str, datetime] = {}
    samples: List[Tuple[float, int]] = []
    chronological = sorted(rows, key=lambda row: row.created_at or datetime.min)
    for row in chronological:
        key = id_from_row(row)
        if not key:
            continue
        if row.action == started_action:
            started_at[key] = row.created_at
        elif row.action == completed_action:
            start = started_at.pop(key, None)
            if not start or not row.created_at:
                continue
            seconds = _seconds_between(start, row.created_at)
            if seconds is None:
                continue
            samples.append((seconds, default_docs))
    return samples[-SAMPLE_WINDOW:]


def load_portal_duration_samples(db) -> List[Tuple[float, int]]:
    from app.models import AuditLog

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.in_(["analysis_started", "analysis_completed"]))
        .order_by(AuditLog.created_at.desc())
        .limit(80)
        .all()
    )
    return samples_from_audit_pairs(
        rows,
        started_action="analysis_started",
        completed_action="analysis_completed",
        id_from_row=lambda row: str(row.application_id) if row.application_id else None,
        default_docs=PORTAL_DOC_COUNT,
    )


def load_workflow_duration_samples(db) -> List[Tuple[float, int]]:
    from app.models import AuditLog

    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.action.in_(
                ["workflow_analysis_started", "workflow_analysis_completed"]
            )
        )
        .order_by(AuditLog.created_at.desc())
        .limit(80)
        .all()
    )

    def _entry_id(row) -> Optional[str]:
        details = row.details or {}
        value = details.get("branch_entry_id")
        return str(value) if value else None

    return samples_from_audit_pairs(
        rows,
        started_action="workflow_analysis_started",
        completed_action="workflow_analysis_completed",
        id_from_row=_entry_id,
        default_docs=3,
    )


def progress_marks_doc_done(stage: str, message: str) -> bool:
    text = f"{stage} {message}".lower()
    return "extraction complete" in text or "finished processing" in text
