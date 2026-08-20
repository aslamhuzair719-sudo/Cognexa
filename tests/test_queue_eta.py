import time
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.services.queue_eta import (
    DEFAULT_PORTAL_SECONDS,
    DurationTracker,
    InspectableFifo,
    eta_payload,
    remaining_seconds,
    samples_from_audit_pairs,
    progress_marks_doc_done,
)


class FifoForTest(InspectableFifo):
    def __init__(self):
        self.__init_fifo__(default_avg=90.0, per_doc=False)


class TestQueueEta(unittest.TestCase):
    def test_fifo_snapshot_order(self):
        q = FifoForTest()
        q._enqueue_job("a1", 4)
        q._enqueue_job("a2", 4)
        q._enqueue_job("a3", 4)
        q._enqueue_job("a1", 4)
        snap = q.snapshot()
        self.assertIsNone(snap["current_id"])
        self.assertEqual([j["id"] for j in snap["pending_jobs"]], ["a1", "a2", "a3"])

        job_id, docs = q._dequeue_job()
        self.assertEqual(job_id, "a1")
        self.assertEqual(docs, 4)
        snap = q.snapshot()
        self.assertEqual(snap["current_id"], "a1")
        self.assertEqual([j["id"] for j in snap["pending_jobs"]], ["a2", "a3"])

    def test_remaining_uses_elapsed_until_docs_done(self):
        started = time.time() - 30
        snap = {
            "current_id": "a1",
            "current_started_at": started,
            "docs_done": 0,
            "docs_total": 4,
            "avg_seconds": 90,
            "pending_jobs": [],
        }
        remaining = remaining_seconds(snap)
        self.assertAlmostEqual(remaining, 60, delta=1.5)

    def test_remaining_uses_docs_fraction(self):
        snap = {
            "current_id": "a1",
            "current_started_at": time.time() - 10,
            "docs_done": 2,
            "docs_total": 4,
            "avg_seconds": 90,
            "pending_jobs": [],
        }
        self.assertAlmostEqual(remaining_seconds(snap), 45, delta=0.5)

    def test_eta_for_three_apps(self):
        started = time.time() - 30
        snap = {
            "current_id": "a1",
            "current_started_at": started,
            "docs_done": 0,
            "docs_total": 4,
            "avg_seconds": 90,
            "pending_jobs": [
                {"id": "a2", "docs_total": 4, "expected_seconds": 90},
                {"id": "a3", "docs_total": 4, "expected_seconds": 90},
            ],
        }
        current = eta_payload("a1", "analyzing", snap)
        self.assertEqual(current["state"], "analyzing")
        self.assertEqual(current["eta_kind"], "remaining")
        self.assertEqual(current["jobs_ahead"], 0)
        self.assertAlmostEqual(current["eta_seconds"], 60, delta=2)

        next_job = eta_payload("a2", "pending", snap)
        self.assertEqual(next_job["state"], "pending")
        self.assertEqual(next_job["position"], 1)
        self.assertEqual(next_job["jobs_ahead"], 1)
        self.assertEqual(next_job["eta_kind"], "until_start")
        self.assertAlmostEqual(next_job["eta_seconds"], 60, delta=2)

        last = eta_payload("a3", "pending", snap)
        self.assertEqual(last["position"], 2)
        self.assertEqual(last["jobs_ahead"], 2)
        self.assertAlmostEqual(last["eta_seconds"], 150, delta=2)

    def test_eta_none_for_completed(self):
        snap = {"current_id": None, "pending_jobs": []}
        self.assertIsNone(eta_payload("a1", "completed", snap))

    def test_duration_tracker_per_doc(self):
        tracker = DurationTracker(default_avg=90, per_doc=True, default_per_doc=25)
        tracker.record(50, 2)
        tracker.record(75, 3)
        self.assertAlmostEqual(tracker.avg_per_doc(), 25.0, places=1)
        self.assertAlmostEqual(tracker.avg_job_seconds(4), 100.0, places=1)

    def test_audit_pair_samples(self):
        t0 = datetime(2026, 8, 20, 12, 0, 0)
        rows = [
            SimpleNamespace(
                action="analysis_started",
                application_id="a1",
                created_at=t0,
            ),
            SimpleNamespace(
                action="analysis_completed",
                application_id="a1",
                created_at=t0 + timedelta(seconds=80),
            ),
        ]
        samples = samples_from_audit_pairs(
            rows,
            started_action="analysis_started",
            completed_action="analysis_completed",
            id_from_row=lambda row: str(row.application_id),
            default_docs=4,
        )
        self.assertEqual(samples, [(80.0, 4)])

    def test_progress_marks_doc_done(self):
        self.assertTrue(
            progress_marks_doc_done("llm", "LLM extraction complete for CNIC front.")
        )
        self.assertFalse(progress_marks_doc_done("ocr", "Parsing CNIC front text with OCR…"))

    def test_default_avg_used_without_samples(self):
        tracker = DurationTracker(default_avg=DEFAULT_PORTAL_SECONDS)
        self.assertEqual(tracker.avg_job_seconds(4), DEFAULT_PORTAL_SECONDS)


if __name__ == "__main__":
    unittest.main()
