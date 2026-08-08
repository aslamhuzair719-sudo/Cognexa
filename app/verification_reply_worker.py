"""Background worker that polls IMAP for verification replies and processes them."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from app import config
from app.db import SessionLocal
from app.logging_config import get_logger, setup_logging
from app.services import imap_service
from app.services.audit import write_audit
from app.services.verification_service import (
    complete_verification,
    get_verification_by_public_id,
    VERIFICATION_STATUS_VERIFIED,
    VERIFICATION_STATUS_REJECTED,
)

logger = get_logger(__name__)


def _handle_message(db, item: dict) -> None:
    subject = item.get("subject") or ""
    from_hdr = item.get("from") or ""
    msg = item.get("email_message")
    uid = item.get("num")
    message_id = item.get("message_id")

    logger.info("Processing unread message: subject=%s message_id=%s", subject, message_id)
    verification_public_id = imap_service.extract_verification_id(subject)
    if not verification_public_id:
        logger.warning("Verification ID not found in subject: %s", subject)
        write_audit(
            db,
            action="verification_id_not_found",
            message="No verification id found in reply subject",
            details={"subject": subject, "from": from_hdr},
        )
        # mark seen to avoid repeated logs
        try:
            imap_service.mark_seen(uid)
        except Exception:
            logger.exception("Failed to mark unknown message seen")
        return

    try:
        verification = get_verification_by_public_id(db, verification_public_id)
    except Exception:
        logger.warning("Verification %s not found", verification_public_id)
        write_audit(
            db,
            action="verification_not_found",
            message=f"Verification {verification_public_id} not found",
            details={"verification_id": verification_public_id, "subject": subject, "from": from_hdr},
        )
        imap_service.mark_seen(uid)
        return

    # sender validation: reply must come from exact company_email
    # parse from header to extract address
    from_email = None
    try:
        from email.utils import parseaddr

        from_email = parseaddr(from_hdr)[1]
    except Exception:
        from_email = from_hdr

    if (not from_email) or (from_email.lower() != verification.company_email.lower()):
        logger.warning(
            "Reply sender mismatch for %s: expected=%s got=%s",
            verification.verification_id,
            verification.company_email,
            from_email,
        )
        write_audit(
            db,
            action="invalid_sender",
            message="Reply rejected because sender does not match expected verifier email",
            branch_id=verification.branch_id,
            application_id=verification.application_id,
            details={
                "verification_id": verification.verification_id,
                "expected": verification.company_email,
                "actual": from_email,
                "subject": subject,
            },
        )
        imap_service.mark_seen(uid)
        return

    # prevent duplicate processing when a final status already exists
    if verification.status in {VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_REJECTED}:
        logger.info("Duplicate reply ignored for %s", verification.verification_id)
        write_audit(
            db,
            action="duplicate_reply_ignored",
            message="Duplicate reply ignored",
            branch_id=verification.branch_id,
            application_id=verification.application_id,
            details={"verification_id": verification.verification_id, "from": from_email},
        )
        imap_service.mark_seen(uid)
        return

    # extract first meaningful line from body
    try:
        plain = imap_service.extract_plain_text(msg)
    except Exception:
        plain = ""

    first_line = imap_service.parse_reply_first_meaningful_line(plain)
    normalized = imap_service.normalize_reply_text(first_line)
    logger.info("Reply parsing: extracted=%r normalized=%r", first_line, normalized)
    logger.debug("Reply plain text snippet: %r", plain[:400])

    # determine action
    result: Optional[str] = None
    if normalized == "approved":
        result = VERIFICATION_STATUS_VERIFIED
    elif normalized == "rejected":
        result = VERIFICATION_STATUS_REJECTED
    else:
        result = "manual_review"

    # perform DB updates inside transaction
    try:
        # attach metadata
        verification.response_email = from_email
        verification.reply_subject = subject
        verification.reply_message_id = message_id
        verification.response_message = first_line or ""
        verification.responded_at = datetime.utcnow()
        verification.processed_at = datetime.utcnow()

        if result in {VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_REJECTED}:
            complete_verification(db, verification, result, remarks="Processed via email reply", changed_by=from_email)
            logger.info("Verification %s processed as %s", verification.verification_id, result)
            write_audit(
                db,
                action="verification_reply_processed",
                message=f"Verification {verification.verification_id} processed: {result}",
                branch_id=verification.branch_id,
                application_id=verification.application_id,
                details={
                    "verification_id": verification.verification_id,
                    "result": result,
                    "from": from_email,
                    "subject": subject,
                    "message_id": message_id,
                },
            )
        else:
            # manual review required
            verification.status = "manual_review"
            verification.responded_at = datetime.utcnow()
            verification.processed_at = datetime.utcnow()
            if verification.application:
                verification.application.verification_email_status = "manual_review"
                verification.application.verification_email_confirmed_at = datetime.utcnow()
            if verification.branch_entry:
                verification.branch_entry.verification_email_status = "manual_review"
                verification.branch_entry.verification_email_confirmed_at = datetime.utcnow()
            db.add(verification)
            logger.info("Verification %s marked manual_review", verification.verification_id)
            write_audit(
                db,
                action="manual_review_required",
                message=f"Verification {verification.verification_id} requires manual review",
                branch_id=verification.branch_id,
                application_id=verification.application_id,
                details={
                    "verification_id": verification.verification_id,
                    "from": from_email,
                    "subject": subject,
                    "normalized": normalized,
                },
            )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Database error while processing reply for %s", verification.verification_id)
    except Exception:
        db.rollback()
        logger.exception("Unexpected error while processing reply for %s", verification.verification_id)
    finally:
        try:
            imap_service.mark_seen(uid)
        except Exception:
            logger.exception("Failed to mark processed message seen: %s", uid)


def run_once() -> None:
    db = SessionLocal()
    try:
        messages = imap_service.fetch_unread_messages()
        if not messages:
            logger.debug("IMAP poll completed; no unread messages found.")
            return
        logger.info("IMAP poll found %s unread message(s)", len(messages))
        for item in messages:
            try:
                _handle_message(db, item)
            except Exception:
                logger.exception("Error processing unread message")
    finally:
        db.close()


def run_forever() -> None:
    setup_logging()
    logger.info("Starting verification reply worker, polling every %s seconds", config.IMAP_POLL_INTERVAL_SECONDS)
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Worker loop error")
        time.sleep(max(1, config.IMAP_POLL_INTERVAL_SECONDS))


if __name__ == "__main__":
    run_forever()
