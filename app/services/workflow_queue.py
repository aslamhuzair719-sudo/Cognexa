"""Serial queue for workflow branch-entry OCR, extraction, and cross-checks."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.db import SessionLocal
from app.logging_config import get_logger
from app.models import BranchEntry, BranchEntryDocument
from app.services.audit import write_audit
from app.services.document_archive import index_branch_entry
from app.services.queue_eta import (
    DEFAULT_WORKFLOW_SECONDS_PER_DOC,
    InspectableFifo,
    load_workflow_duration_samples,
    progress_marks_doc_done,
)
from app.services.workflow_service import WorkflowService, DOCUMENT_TYPE_LABELS

logger = get_logger(__name__)


class WorkflowQueue(InspectableFifo):
    """FIFO queue — processes one customer workflow (branch entry) at a time."""

    def __init__(self) -> None:
        self.__init_fifo__(
            default_avg=DEFAULT_WORKFLOW_SECONDS_PER_DOC * 3,
            per_doc=True,
            default_per_doc=DEFAULT_WORKFLOW_SECONDS_PER_DOC,
        )
        self._service = WorkflowService()

    def start(self) -> None:
        started = self._start_worker(self._worker, "workflow-queue-worker")
        if not started:
            return
        self.recover_pending()
        self._seed_from_audit()
        logger.info("Workflow queue worker started")

    def enqueue(self, entry_id: uuid.UUID | str, docs_total: Optional[int] = None) -> None:
        key = str(entry_id)
        count = docs_total if docs_total is not None else self._lookup_doc_count(key)
        if not self._enqueue_job(key, count):
            logger.info("Branch entry %s already queued for workflow", key)
            return
        logger.info("Queued branch entry %s for workflow extraction", key)

    def _lookup_doc_count(self, entry_id: str) -> int:
        db = SessionLocal()
        try:
            n = (
                db.query(func.count(BranchEntryDocument.id))
                .filter(BranchEntryDocument.branch_entry_id == entry_id)
                .scalar()
            )
            return max(1, int(n or 1))
        except Exception:
            logger.exception("Failed to count documents for workflow entry %s", entry_id)
            return 3
        finally:
            db.close()

    def recover_pending(self) -> None:
        db = SessionLocal()
        try:
            stuck = (
                db.query(BranchEntry)
                .options(joinedload(BranchEntry.documents))
                .filter(BranchEntry.status.in_(["pending", "analyzing"]))
                .filter(BranchEntry.workflow_type.isnot(None))
                .order_by(BranchEntry.created_at.asc())
                .all()
            )
            for entry in stuck:
                if entry.status == "analyzing":
                    entry.status = "pending"
                self.enqueue(entry.id, docs_total=max(1, len(entry.documents or [])))
            db.commit()
            if stuck:
                logger.info("Recovered %s workflow branch entr(ies) into queue", len(stuck))
        except Exception:
            db.rollback()
            logger.exception("Failed to recover pending workflow entries")
        finally:
            db.close()

    def _seed_from_audit(self) -> None:
        db = SessionLocal()
        try:
            samples = load_workflow_duration_samples(db)
            if samples:
                self.seed_duration_samples(samples)
                logger.info("Seeded workflow duration from %s audit sample(s)", len(samples))
        except Exception:
            logger.exception("Failed to seed workflow duration samples")
        finally:
            db.close()

    def _worker(self) -> None:
        while True:
            job_id, _docs_total = self._dequeue_job()
            recorded = False
            try:
                recorded = self._process(uuid.UUID(job_id))
            except Exception:
                logger.exception("Unhandled workflow worker error for %s", job_id)
            finally:
                self._finish_job(job_id, record=recorded)

    def _process(self, entry_id: uuid.UUID) -> bool:
        db = SessionLocal()
        try:
            entry = (
                db.query(BranchEntry)
                .options(joinedload(BranchEntry.documents))
                .filter(BranchEntry.id == entry_id)
                .first()
            )
            if not entry:
                logger.warning("Queued branch entry %s not found", entry_id)
                return False
            if entry.status in {"completed", "review_required"} and entry.analyzed_at:
                logger.info("Skipping %s — workflow already processed", entry_id)
                return False

            entry.status = "analyzing"
            entry.workflow_meta_json = {
                **(entry.workflow_meta_json or {}),
                "progress": {
                    "stage": "starting",
                    "message": "Starting OCR and field extraction…",
                },
            }
            write_audit(
                db,
                action="workflow_analysis_started",
                message=f"Workflow extraction started for {entry.customer_name}",
                branch_id=entry.branch_id,
                details={"branch_entry_id": str(entry.id), "status": "analyzing"},
            )
            db.commit()

            documents = list(entry.documents or [])
            self.set_current_docs_total(max(1, len(documents)))
            workflow_type = entry.workflow_type or "account_opening"

            def _on_progress(stage: str, message: str) -> None:
                if progress_marks_doc_done(stage, message):
                    self.mark_doc_done()
                session = SessionLocal()
                try:
                    row = session.query(BranchEntry).filter(BranchEntry.id == entry_id).first()
                    if not row:
                        return
                    row.workflow_meta_json = {
                        **(row.workflow_meta_json or {}),
                        "progress": {"stage": stage, "message": message},
                    }
                    session.commit()
                except Exception:
                    session.rollback()
                finally:
                    session.close()

            result = self._service.extract_saved_documents(
                documents,
                workflow_type=workflow_type,
                on_progress=_on_progress,
            )

            enriched_by_id = {
                item["document_id"]: item for item in result.get("documents") or []
            }
            for doc in documents:
                payload = enriched_by_id.get(str(doc.id))
                if not payload:
                    continue
                doc.document_type = payload.get("document_type") or doc.document_type
                doc.extracted_text = payload.get("extracted_text") or doc.extracted_text
                doc.fields_json = payload.get("fields") or doc.fields_json
                doc.summary_json = payload.get("summary") or doc.summary_json

            inferred_name = self._service.infer_customer_name(result.get("documents") or [])
            if inferred_name and (
                not entry.customer_name
                or entry.customer_name.startswith("CUSTOMER-")
            ):
                entry.customer_name = inferred_name

            validation = result.get("validation") or {}
            report = result.get("report") or {}
            rec = str(report.get("recommendation", "")).upper()
            if validation.get("status") == "COMPLETE" and rec not in {"REJECTED"}:
                final_status = "completed"
            else:
                final_status = "review_required"

            entry.status = final_status
            entry.analyzed_at = datetime.utcnow()
            entry.workflow_meta_json = {
                "workflow_type": workflow_type,
                "workflow_group_id": entry.workflow_group_id,
                "validation": validation,
                "cross_document_checks": result.get("cross_document_checks") or [],
                "report": report,
                "sections": result.get("sections") or {},
                "overall_score": report.get("overall_score"),
                "recommendation": report.get("recommendation"),
                "progress": {
                    "stage": "complete",
                    "message": "OCR, LLM extraction, and cross-document validation complete.",
                    "done": True,
                },
            }

            write_audit(
                db,
                action="workflow_analysis_completed",
                message=f"Workflow extraction completed for {entry.customer_name}",
                branch_id=entry.branch_id,
                details={
                    "branch_entry_id": str(entry.id),
                    "status": final_status,
                    "validation": validation.get("status"),
                },
            )
            index_branch_entry(db, entry, document_type_labels=DOCUMENT_TYPE_LABELS)
            db.commit()
            logger.info("Completed workflow processing for %s", entry_id)
            return True
        except Exception as exc:
            db.rollback()
            try:
                entry = db.query(BranchEntry).filter(BranchEntry.id == entry_id).first()
                if entry:
                    entry.status = "failed"
                    entry.workflow_meta_json = {
                        **(entry.workflow_meta_json or {}),
                        "progress": {
                            "stage": "failed",
                            "message": str(exc)[:500],
                            "done": True,
                        },
                        "error": str(exc)[:500],
                    }
                    write_audit(
                        db,
                        action="workflow_analysis_failed",
                        message=f"Workflow extraction failed for {entry.customer_name}",
                        branch_id=entry.branch_id,
                        details={"branch_entry_id": str(entry.id), "error": str(exc)[:500]},
                    )
                    db.commit()
            except Exception:
                db.rollback()
            logger.exception("Workflow processing failed for %s", entry_id)
            return False
        finally:
            db.close()


workflow_queue = WorkflowQueue()
