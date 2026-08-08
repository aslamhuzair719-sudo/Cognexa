"""High-level company verification domain logic."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    Application,
    BranchEntry,
    Verification,
    VerificationHistory,
)
from app.services.audit import write_audit
from app.services.application_storage import resolve_document_path
from app.services.branch_entry_storage import resolve_branch_entry_path
from app.services.email_service import (
    VerificationEmailError,
    compose_verification_email,
    is_smtp_configured,
    send_verification_email,
    validate_verification_target,
)

logger = get_logger(__name__)

VERIFICATION_STATUS_PENDING = "pending_verification"
VERIFICATION_STATUS_CANCELED = "canceled"
VERIFICATION_STATUS_VERIFIED = "verified"
VERIFICATION_STATUS_REJECTED = "rejected"
VERIFICATION_STATUS_BOUNCED = "bounced"

SUPPORTED_DOCUMENT_TYPES = {"payslip", "bank_statement"}
MAX_EMAIL_RETRIES = 3


def _now() -> datetime:
    return datetime.utcnow()


def _new_public_verification_id() -> str:
    return f"VER-{uuid.uuid4().hex[:16]}"


def validate_company_email(email: str) -> str:
    return validate_verification_target(email)


def _application_email_payload(application: Application) -> dict:
    return {
        "applicant_name": application.full_name,
        "cnic_number": application.cnic_number,
        "company_name": application.company_name,
        "employee_id": application.employee_id,
        "branch_name": application.branch.name if application.branch else "",
        "request_date": _now().isoformat(),
    }


def _branch_entry_email_payload(entry: BranchEntry) -> dict:
    return {
        "applicant_name": entry.customer_name,
        "cnic_number": None,
        "company_name": None,
        "employee_id": None,
        "branch_name": entry.branch.name if entry.branch else "",
        "request_date": _now().isoformat(),
    }


def _resolve_attachment_path_for_application(application: Application, document_type: str) -> Path:
    if document_type == "payslip":
        return resolve_document_path(application.payslip_path)
    if document_type == "bank_statement":
        return resolve_document_path(application.bank_statement_path)
    raise VerificationEmailError(f"Unsupported document_type '{document_type}'.")


def _resolve_attachment_path_for_branch_entry(entry: BranchEntry, document_type: str) -> Path:
    document = next(
        (doc for doc in (entry.documents or []) if doc.document_type == document_type),
        None,
    )
    if not document:
        raise VerificationEmailError(
            f"{document_type.replace('_', ' ').title()} document is missing for branch entry."
        )
    return resolve_branch_entry_path(document.file_path)


def _build_verification_context(
    application: Optional[Application] = None,
    branch_entry: Optional[BranchEntry] = None,
) -> dict:
    if application:
        return _application_email_payload(application)
    if branch_entry:
        return _branch_entry_email_payload(branch_entry)
    raise ValueError("Either application or branch_entry must be provided")


def _build_attachment_path(
    application: Optional[Application] = None,
    branch_entry: Optional[BranchEntry] = None,
    document_type: str = "",
) -> Path:
    if application:
        return _resolve_attachment_path_for_application(application, document_type)
    if branch_entry:
        return _resolve_attachment_path_for_branch_entry(branch_entry, document_type)
    raise ValueError("Either application or branch_entry must be provided")


def _build_verification_message(
    verification: Verification,
    attachment_path: Optional[Path] = None,
) -> "EmailMessage":
    data = verification.to_dict() if hasattr(verification, "to_dict") else {}
    # fallback payload for backward compatibility
    # when Verification is not fully hydrated.
    payload = {
        "full_name": verification.applicant_name if hasattr(verification, "applicant_name") else None,
        "cnic_number": verification.company_email,
        "company_name": verification.company_email,
        "employee_id": None,
    }
    return compose_verification_email(
        payload,
        document_type=verification.document_type,
        target_email=verification.company_email,
        verification_id=verification.verification_id,
        attachment_path=str(attachment_path) if attachment_path else None,
        note=verification.note,
    )


def _write_history(
    db: Session,
    verification: Verification,
    old_status: str,
    new_status: str,
    remarks: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> VerificationHistory:
    history = VerificationHistory(
        verification_id=verification.id,
        old_status=old_status,
        new_status=new_status,
        remarks=remarks,
        changed_by=changed_by,
        changed_at=_now(),
    )
    db.add(history)
    db.flush()
    return history


def _write_verification_audit(
    db: Session,
    action: str,
    message: str,
    branch_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    application_id: Optional[uuid.UUID] = None,
    details: Optional[dict] = None,
) -> None:
    write_audit(
        db,
        action=action,
        message=message,
        branch_id=branch_id,
        user_id=user_id,
        username=username,
        application_id=application_id,
        details=details,
    )


def _normalize_document_type(document_type: str) -> str:
    value = document_type.strip().lower()
    if value not in SUPPORTED_DOCUMENT_TYPES:
        raise VerificationEmailError(
            f"Unsupported document_type '{document_type}'. Use payslip or bank_statement."
        )
    return value


def _build_verification_record(
    db: Session,
    *,
    application: Optional[Application] = None,
    branch_entry: Optional[BranchEntry] = None,
    document_type: str,
    target_email: str,
    note: Optional[str] = None,
    created_by: Optional[int] = None,
    branch_id: Optional[int] = None,
) -> Verification:
    document_type = _normalize_document_type(document_type)
    target_email = validate_company_email(target_email)

    if application is None and branch_entry is None:
        raise ValueError("A verification must be tied to an application or branch entry.")

    attachment_path = _build_attachment_path(
        application=application,
        branch_entry=branch_entry,
        document_type=document_type,
    )
    if not attachment_path.exists():
        raise VerificationEmailError("Attachment file is missing for verification email.")

    public_id = _new_public_verification_id()
    verification = Verification(
        verification_id=public_id,
        application_id=application.id if application else None,
        branch_entry_id=branch_entry.id if branch_entry else None,
        branch_id=branch_id or (application.branch_id if application else branch_entry.branch_id),
        document_type=document_type,
        company_email=target_email,
        status=VERIFICATION_STATUS_PENDING,
        document_path=str(attachment_path),
        note=note.strip() if note else None,
        created_by=created_by,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(verification)
    db.flush()

    _write_history(
        db,
        verification,
        old_status="none",
        new_status=VERIFICATION_STATUS_PENDING,
        remarks="Verification request created.",
        changed_by=None,
    )

    if application:
        application.verification_email_id = public_id
        application.verification_email_document = document_type
        application.verification_email_target = target_email
        application.verification_email_status = VERIFICATION_STATUS_PENDING
        application.verification_email_last_error = None
        application.verification_email_sent_at = None
        application.verification_email_confirmed_at = None
        application.verification_email_note = note.strip() if note else None
    if branch_entry:
        branch_entry.verification_email_id = public_id
        branch_entry.verification_email_document = document_type
        branch_entry.verification_email_target = target_email
        branch_entry.verification_email_status = VERIFICATION_STATUS_PENDING
        branch_entry.verification_email_last_error = None
        branch_entry.verification_email_sent_at = None
        branch_entry.verification_email_confirmed_at = None
        branch_entry.verification_email_note = note.strip() if note else None

    return verification


def create_application_verification(
    db: Session,
    application: Application,
    document_type: str,
    target_email: str,
    note: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> Verification:
    verification = _build_verification_record(
        db,
        application=application,
        document_type=document_type,
        target_email=target_email,
        note=note,
        created_by=user_id,
        branch_id=application.branch_id,
    )
    _write_verification_audit(
        db,
        action="verification_created",
        message=f"Verification {verification.verification_id} created for {application.full_name}",
        branch_id=application.branch_id,
        user_id=user_id,
        username=username,
        application_id=application.id,
        details={
            "verification_id": verification.verification_id,
            "document_type": document_type,
            "company_email": target_email,
            "status": VERIFICATION_STATUS_PENDING,
        },
    )
    return verification


def create_branch_entry_verification(
    db: Session,
    entry: BranchEntry,
    document_type: str,
    target_email: str,
    note: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
) -> Verification:
    verification = _build_verification_record(
        db,
        branch_entry=entry,
        document_type=document_type,
        target_email=target_email,
        note=note,
        created_by=user_id,
        branch_id=entry.branch_id,
    )
    _write_verification_audit(
        db,
        action="verification_created",
        message=f"Verification {verification.verification_id} created for branch entry {entry.id}",
        branch_id=entry.branch_id,
        user_id=user_id,
        username=username,
        application_id=None,
        details={
            "verification_id": verification.verification_id,
            "document_type": document_type,
            "company_email": target_email,
            "status": VERIFICATION_STATUS_PENDING,
        },
    )
    return verification


def get_verification_by_public_id(db: Session, public_id: str) -> Verification:
    verification = (
        db.query(Verification)
        .filter(Verification.verification_id == public_id)
        .first()
    )
    if not verification:
        raise VerificationEmailError(f"Verification '{public_id}' not found")
    return verification


def get_latest_verification_for_application(db: Session, application: Application) -> Verification:
    if application.verification_email_id:
        return get_verification_by_public_id(db, application.verification_email_id)
    verification = (
        db.query(Verification)
        .filter(Verification.application_id == application.id)
        .order_by(Verification.created_at.desc())
        .first()
    )
    if not verification:
        raise VerificationEmailError("No verification request found for this application.")
    return verification


def get_latest_verification_for_branch_entry(db: Session, entry: BranchEntry) -> Verification:
    if entry.verification_email_id:
        return get_verification_by_public_id(db, entry.verification_email_id)
    verification = (
        db.query(Verification)
        .filter(Verification.branch_entry_id == entry.id)
        .order_by(Verification.created_at.desc())
        .first()
    )
    if not verification:
        raise VerificationEmailError("No verification request found for this branch entry.")
    return verification


def build_verification_email_message(verification: Verification) -> "EmailMessage":
    if not verification.document_path:
        raise VerificationEmailError("Verification attachment path is missing.")
    attachment_path = Path(verification.document_path)
    if not attachment_path.exists() or not attachment_path.is_file():
        raise VerificationEmailError("Verification attachment is missing on disk.")
    application_payload = {}
    if verification.application_id:
        application_payload = {
            "full_name": verification.applicant_name if hasattr(verification, "applicant_name") else "",
            "cnic_number": None,
            "company_name": None,
            "employee_id": None,
        }
    message = compose_verification_email(
        application_payload,
        document_type=verification.document_type,
        target_email=verification.company_email,
        verification_id=verification.verification_id,
        attachment_path=str(attachment_path),
        note=verification.note,
    )
    return message


def send_verification_message(verification: Verification) -> None:
    if not is_smtp_configured():
        raise VerificationEmailError("SMTP is not configured. Cannot send verification emails.")
    if not verification.company_email:
        raise VerificationEmailError("Verification target email is missing.")
    if not verification.document_path:
        raise VerificationEmailError("Verification attachment path is not set.")

    attachment_path = Path(verification.document_path)
    if not attachment_path.exists() or not attachment_path.is_file():
        raise VerificationEmailError("Verification attachment is missing on disk.")

    context = _build_verification_context(
        application=verification.application,
        branch_entry=verification.branch_entry,
    )
    message = compose_verification_email(
        context,
        document_type=verification.document_type,
        target_email=verification.company_email,
        verification_id=verification.verification_id,
        attachment_path=str(attachment_path),
        note=verification.note,
    )
    send_verification_email(message)


def _apply_status_update(
    db: Session,
    verification: Verification,
    new_status: str,
    remarks: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Verification:
    old_status = verification.status
    if old_status == new_status:
        return verification
    verification.status = new_status
    verification.updated_at = _now()
    if new_status == VERIFICATION_STATUS_VERIFIED:
        verification.verified_at = _now()
    elif new_status == VERIFICATION_STATUS_REJECTED:
        verification.rejected_at = _now()
    elif new_status == VERIFICATION_STATUS_CANCELED:
        verification.canceled_at = _now()
    _write_history(
        db,
        verification,
        old_status=old_status,
        new_status=new_status,
        remarks=remarks,
        changed_by=changed_by,
    )
    return verification


def complete_verification(
    db: Session,
    verification: Verification,
    result: str,
    remarks: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Verification:
    normalized = result.strip().lower()
    if normalized not in {VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_REJECTED}:
        raise VerificationEmailError("Verification result must be 'verified' or 'rejected'.")
    if verification.status not in {VERIFICATION_STATUS_PENDING}:
        raise VerificationEmailError(
            f"Cannot complete verification from status '{verification.status}'."
        )
    updated = _apply_status_update(db, verification, normalized, remarks=remarks, changed_by=changed_by)
    # Keep the linked application/branch-entry email status aligned with the verification result.
    if verification.application:
        verification.application.verification_email_status = normalized
        verification.application.verification_email_confirmed_at = _now()
        verification.application.verification_email_last_error = None
    if verification.branch_entry:
        verification.branch_entry.verification_email_status = normalized
        verification.branch_entry.verification_email_confirmed_at = _now()
        verification.branch_entry.verification_email_last_error = None
    action = "verification_verified" if normalized == VERIFICATION_STATUS_VERIFIED else "verification_rejected"
    write_audit(
        db,
        action=action,
        message=f"Verification {verification.verification_id} marked {normalized}.",
        branch_id=verification.branch_id,
        user_id=verification.created_by,
        username=changed_by,
        application_id=verification.application_id,
        details={
            "verification_id": verification.verification_id,
            "status": normalized,
            "remarks": remarks,
        },
    )
    return updated


def cancel_verification(
    db: Session,
    verification: Verification,
    reason: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Verification:
    if verification.status in {VERIFICATION_STATUS_VERIFIED, VERIFICATION_STATUS_REJECTED, VERIFICATION_STATUS_CANCELED}:
        raise VerificationEmailError(
            f"Cannot cancel verification from status '{verification.status}'."
        )
    verification.failure_reason = reason
    updated = _apply_status_update(db, verification, VERIFICATION_STATUS_CANCELED, remarks=reason, changed_by=changed_by)
    write_audit(
        db,
        action="verification_canceled",
        message=f"Verification {verification.verification_id} canceled.",
        branch_id=verification.branch_id,
        user_id=verification.created_by,
        username=changed_by,
        application_id=verification.application_id,
        details={
            "verification_id": verification.verification_id,
            "status": VERIFICATION_STATUS_CANCELED,
            "reason": reason,
        },
    )
    return updated


def resend_verification(
    db: Session,
    verification: Verification,
    note: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Verification:
    if verification.status not in {VERIFICATION_STATUS_CANCELED, VERIFICATION_STATUS_PENDING}:
        raise VerificationEmailError(
            f"Cannot resend verification from status '{verification.status}'."
        )
    verification.retry_count += 1
    verification.failure_reason = None
    verification.bounce_reason = None
    verification.sent_at = None
    verification.updated_at = _now()
    if note:
        verification.note = (verification.note or "") + "\n" + note.strip()
    _write_history(
        db,
        verification,
        old_status=verification.status,
        new_status=VERIFICATION_STATUS_PENDING,
        remarks="Verification resend requested.",
        changed_by=changed_by,
    )
    write_audit(
        db,
        action="verification_resent",
        message=f"Verification {verification.verification_id} resent.",
        branch_id=verification.branch_id,
        user_id=verification.created_by,
        username=changed_by,
        application_id=verification.application_id,
        details={
            "verification_id": verification.verification_id,
            "status": VERIFICATION_STATUS_PENDING,
            "retry_count": verification.retry_count,
        },
    )
    return verification


def add_webhook_event(
    db: Session,
    verification: Verification,
    event: str,
    reason: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Verification:
    normalized = event.strip().lower()
    if normalized in {"bounce", "delivery_failure"}:
        verification.bounce_reason = reason
        updated = _apply_status_update(db, verification, VERIFICATION_STATUS_CANCELED, remarks=reason, changed_by=changed_by)
        write_audit(
            db,
            action="verification_bounced" if normalized == "bounce" else "verification_delivery_failed",
            message=f"Verification {verification.verification_id} report received: {normalized}.",
            branch_id=verification.branch_id,
            user_id=verification.created_by,
            username=changed_by,
            application_id=verification.application_id,
            details={"event": normalized, "reason": reason},
        )
    elif normalized == "delivered":
        _write_history(db, verification, old_status=verification.status, new_status=verification.status, remarks="Delivery confirmed.", changed_by=changed_by)
    else:
        raise VerificationEmailError(f"Unsupported webhook event '{event}'.")
    return verification


def get_verification_history(db: Session, verification: Verification) -> list[VerificationHistory]:
    return (
        db.query(VerificationHistory)
        .filter(VerificationHistory.verification_id == verification.id)
        .order_by(VerificationHistory.changed_at.asc())
        .all()
    )


def get_verification_details(verification: Verification) -> dict:
    return {
        "verification_id": verification.verification_id,
        "application_id": str(verification.application_id) if verification.application_id else None,
        "branch_entry_id": str(verification.branch_entry_id) if verification.branch_entry_id else None,
        "company_email": verification.company_email,
        "document_type": verification.document_type,
        "status": verification.status,
        "failure_reason": verification.failure_reason,
        "bounce_reason": verification.bounce_reason,
        "retry_count": verification.retry_count,
        "sent_at": verification.sent_at.isoformat() if verification.sent_at else None,
        "verified_at": verification.verified_at.isoformat() if verification.verified_at else None,
        "rejected_at": verification.rejected_at.isoformat() if verification.rejected_at else None,
        "canceled_at": verification.canceled_at.isoformat() if verification.canceled_at else None,
        "created_at": verification.created_at.isoformat() if verification.created_at else None,
        "updated_at": verification.updated_at.isoformat() if verification.updated_at else None,
        "note": verification.note,
    }
