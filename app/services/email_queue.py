"""Background worker for sending verification emails asynchronously."""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import joinedload

from app.db import SessionLocal
from app.logging_config import get_logger
from app.models import BranchEntry, Verification
from app import config
from app.services.verification_service import (
    get_verification_by_public_id,
    send_verification_message,
    VERIFICATION_STATUS_PENDING,
    VERIFICATION_STATUS_CANCELED,
    MAX_EMAIL_RETRIES,
    _write_history,
    _write_verification_audit,
)

logger = get_logger(__name__)

MAX_RETRY_DELAY_SECONDS = 8


class VerificationEmailQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._worker,
            name="verification-email-queue",
            daemon=True,
        )
        self._thread.start()
        self.recover_pending()
        logger.info("Verification email queue started")

    def recover_pending(self) -> None:
        db = SessionLocal()
        try:
            rows = (
                db.query(Verification.verification_id)
                .filter(Verification.status == VERIFICATION_STATUS_PENDING)
                .all()
            )
            for (public_id,) in rows:
                self.enqueue(public_id)
            if rows:
                logger.info("Recovered %s pending verification(s) into email queue", len(rows))
        except Exception:
            logger.exception("Failed to recover pending verification emails")
        finally:
            db.close()

    def enqueue(self, public_verification_id: str) -> None:
        self._queue.put(public_verification_id)
        logger.info("Queued verification %s for email delivery", public_verification_id)

    def _worker(self) -> None:
        while True:
            public_id = self._queue.get()
            try:
                self._deliver(public_id)
            except Exception:
                logger.exception("Unexpected error while delivering verification email %s", public_id)
            finally:
                self._queue.task_done()

    def _deliver(self, public_id: str) -> None:
        db = SessionLocal()
        try:
            verification = (
                db.query(Verification)
                .options(
                    joinedload(Verification.application),
                    joinedload(Verification.branch_entry).joinedload(BranchEntry.documents),
                )
                .filter(Verification.verification_id == public_id)
                .first()
            )
            if not verification:
                logger.warning("Verification %s not found in queue", public_id)
                return
            if verification.status != VERIFICATION_STATUS_PENDING:
                logger.info(
                    "Skipping delivery for verification %s because status is %s",
                    public_id,
                    verification.status,
                )
                return
            try:
                send_verification_message(verification)
                verification.sent_at = datetime.utcnow()
                verification.failure_reason = None
                verification.updated_at = datetime.utcnow()
                if verification.application:
                    verification.application.verification_email_status = "sent"
                    verification.application.verification_email_last_error = None
                    verification.application.verification_email_sent_at = datetime.utcnow()
                if verification.branch_entry:
                    verification.branch_entry.verification_email_status = "sent"
                    verification.branch_entry.verification_email_last_error = None
                    verification.branch_entry.verification_email_sent_at = datetime.utcnow()
                _write_verification_audit(
                    db,
                    action="verification_delivered",
                    message=f"Verification email delivered for {public_id}.",
                    branch_id=verification.branch_id,
                    user_id=verification.created_by,
                    username=None,
                    application_id=verification.application_id,
                    details={
                        "verification_id": public_id,
                        "status": VERIFICATION_STATUS_PENDING,
                    },
                )
                db.commit()
                logger.info("Verification email delivered for %s", public_id)
            except Exception as exc:
                verification.retry_count += 1
                verification.failure_reason = f"{type(exc).__name__}: {exc}"
                if verification.application:
                    verification.application.verification_email_last_error = str(exc)
                if verification.branch_entry:
                    verification.branch_entry.verification_email_last_error = str(exc)
                if verification.retry_count < MAX_EMAIL_RETRIES:
                    db.commit()
                    backoff = min(2 ** verification.retry_count, config.SMTP_RETRY_BACKOFF_MAX)
                    logger.warning(
                        "Verification %s failed to send (%s). Retrying %s/%s after %s seconds.",
                        public_id,
                        exc,
                        verification.retry_count,
                        MAX_EMAIL_RETRIES,
                        backoff,
                    )
                    time.sleep(backoff)
                    self.enqueue(public_id)
                else:
                    previous_status = verification.status
                    verification.status = VERIFICATION_STATUS_CANCELED
                    verification.canceled_at = datetime.utcnow()
                    verification.updated_at = datetime.utcnow()
                    if verification.application:
                        verification.application.verification_email_status = "failed"
                        verification.application.verification_email_last_error = str(exc)
                    if verification.branch_entry:
                        verification.branch_entry.verification_email_status = "failed"
                        verification.branch_entry.verification_email_last_error = str(exc)
                    _write_history(
                        db,
                        verification,
                        old_status=previous_status,
                        new_status=VERIFICATION_STATUS_CANCELED,
                        remarks=str(exc),
                        changed_by="system",
                    )
                    _write_verification_audit(
                        db,
                        action="verification_delivery_failed",
                        message=f"Verification {public_id} canceled after retries.",
                        branch_id=verification.branch_id,
                        user_id=verification.created_by,
                        username=None,
                        application_id=verification.application_id,
                        details={
                            "verification_id": public_id,
                            "status": VERIFICATION_STATUS_CANCELED,
                            "error": str(exc),
                        },
                    )
                    db.commit()
                    logger.error(
                        "Verification %s canceled after %s retries: %s",
                        public_id,
                        verification.retry_count,
                        exc,
                    )
        finally:
            db.close()


email_queue = VerificationEmailQueue()
