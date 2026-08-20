"""Single-worker queue so LLM analysis runs one application at a time."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.db import SessionLocal
from app.logging_config import get_logger
from app.models import Application, ApplicationStatus
from app.schemas.application import ApplicationForm, CnicInfo, EmploymentInfo, PersonalInfo
from app.services.ai_progress import ai_progress
from app.services.application_storage import document_paths_map
from app.services.document_archive import index_application_documents
from app.services.audit import write_audit
from app.services.queue_eta import (
    DEFAULT_PORTAL_SECONDS,
    PORTAL_DOC_COUNT,
    InspectableFifo,
    load_portal_duration_samples,
    progress_marks_doc_done,
)
from app.services.verification_pipeline import VerificationPipeline

logger = get_logger(__name__)


class AnalysisQueue(InspectableFifo):
    """FIFO queue with one background worker (serial LLM usage)."""

    def __init__(self) -> None:
        self.__init_fifo__(default_avg=DEFAULT_PORTAL_SECONDS, per_doc=False)
        self._pipeline = VerificationPipeline()

    def start(self) -> None:
        started = self._start_worker(self._worker, "analysis-queue-worker")
        if not started:
            return
        self.recover_pending()
        self._seed_from_audit()
        logger.info("Analysis queue worker started")

    def enqueue(self, application_id: uuid.UUID | str) -> None:
        key = str(uuid.UUID(str(application_id)))
        if not self._enqueue_job(key, PORTAL_DOC_COUNT):
            logger.info("Application %s already queued", key)
            return
        ai_progress.set(
            key,
            stage="queued",
            message="Waiting in the Cognexa AI queue…",
        )
        logger.info("Queued application %s for AI analysis", key)

    def recover_pending(self) -> None:
        """Re-queue pending apps and any stuck analyzing after restart."""
        db = SessionLocal()
        try:
            stuck = (
                db.query(Application)
                .filter(
                    Application.status.in_(
                        [
                            ApplicationStatus.pending.value,
                            ApplicationStatus.analyzing.value,
                        ]
                    )
                )
                .order_by(Application.created_at.asc())
                .all()
            )
            for app in stuck:
                if app.status == ApplicationStatus.analyzing.value:
                    app.status = ApplicationStatus.pending.value
                self.enqueue(app.id)
            db.commit()
            if stuck:
                logger.info("Recovered %s application(s) into analysis queue", len(stuck))
        except Exception:
            db.rollback()
            logger.exception("Failed to recover pending analyses")
        finally:
            db.close()

    def _seed_from_audit(self) -> None:
        db = SessionLocal()
        try:
            samples = load_portal_duration_samples(db)
            if samples:
                self.seed_duration_samples(samples)
                logger.info("Seeded analysis duration from %s audit sample(s)", len(samples))
        except Exception:
            logger.exception("Failed to seed analysis duration samples")
        finally:
            db.close()

    def _worker(self) -> None:
        while True:
            job_id, _docs_total = self._dequeue_job()
            recorded = False
            try:
                recorded = self._analyze(uuid.UUID(job_id))
            except Exception:
                logger.exception("Unhandled analysis worker error for %s", job_id)
            finally:
                self._finish_job(job_id, record=recorded)

    def _analyze(self, application_id: uuid.UUID) -> bool:
        db = SessionLocal()
        try:
            app = db.query(Application).filter(Application.id == application_id).first()
            if not app:
                logger.warning("Queued application %s not found", application_id)
                return False
            if app.status in (
                ApplicationStatus.accepted.value,
                ApplicationStatus.rejected.value,
            ):
                logger.info("Skipping %s — already decided", application_id)
                return False
            if app.status == ApplicationStatus.completed.value and app.report_json:
                logger.info("Skipping %s — already completed", application_id)
                return False

            app.status = ApplicationStatus.analyzing.value
            write_audit(
                db,
                action="analysis_started",
                message=f"Cognexa AI analysis started for {app.full_name}",
                branch_id=app.branch_id,
                application_id=app.id,
                details={"status": "analyzing"},
            )
            db.commit()
            logger.info("Analyzing application %s", application_id)

            app_key = str(application_id)
            self.set_current_docs_total(PORTAL_DOC_COUNT)

            def _on_progress(stage: str, message: str) -> None:
                if progress_marks_doc_done(stage, message):
                    self.mark_doc_done()
                ai_progress.set(
                    app_key,
                    stage=stage,
                    message=message,
                    done=stage == "complete",
                )

            ai_progress.set(
                app_key,
                stage="starting",
                message="Cognexa AI analysis starting — working…",
            )

            form = ApplicationForm(
                personal=PersonalInfo(
                    full_name=app.full_name,
                    age=app.age or "",
                    email=app.email,
                    mobile_number=app.mobile_number,
                ),
                cnic=CnicInfo(
                    full_name=app.cnic_full_name or app.full_name,
                    father_name=app.father_name,
                    cnic_number=app.cnic_number,
                    date_of_birth=app.date_of_birth,
                    issue_date=app.cnic_issue_date or "",
                    expiry_date=app.cnic_expiry_date or "",
                    country_to_stay=app.country_to_stay or "",
                    gender=app.gender or "",
                ),
                employment=EmploymentInfo(
                    company_name=app.company_name,
                    employee_id=app.employee_id,
                    designation=app.designation or "",
                    monthly_income=app.monthly_income,
                ),
            )
            documents = document_paths_map(app)
            report, extractions = self._pipeline.verify(form, documents, on_progress=_on_progress)

            app = db.query(Application).filter(Application.id == application_id).first()
            if not app:
                return False
            app.report_json = report.model_dump(mode="json")
            app.status = ApplicationStatus.completed.value
            app.analyzed_at = datetime.utcnow()
            index_application_documents(db, app, extractions)
            write_audit(
                db,
                action="analysis_completed",
                message=f"Cognexa AI analysis completed for {app.full_name}",
                branch_id=app.branch_id,
                application_id=app.id,
                details={
                    "status": "completed",
                    "score": report.overall_score,
                    "recommendation": report.recommendation.value
                    if hasattr(report.recommendation, "value")
                    else str(report.recommendation),
                },
            )
            db.commit()
            ai_progress.set(
                app_key,
                stage="complete",
                message="Cognexa AI analysis complete — document parsing and LLM summary done.",
                done=True,
            )
            logger.info("Completed analysis for %s", application_id)
            return True
        except Exception as exc:
            db.rollback()
            try:
                app = db.query(Application).filter(Application.id == application_id).first()
                if app and app.status == ApplicationStatus.analyzing.value:
                    app.status = ApplicationStatus.pending.value
                    write_audit(
                        db,
                        action="analysis_failed",
                        message=f"Cognexa AI analysis failed for {app.full_name}",
                        branch_id=app.branch_id,
                        application_id=app.id,
                        details={"error": str(exc)[:500], "status": "pending"},
                    )
                    db.commit()
            except Exception:
                db.rollback()
            logger.exception("AI analysis failed for %s — returned to pending", application_id)
            return False
        finally:
            db.close()


analysis_queue = AnalysisQueue()
