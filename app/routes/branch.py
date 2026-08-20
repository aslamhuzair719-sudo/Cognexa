"""Branch staff APIs: list, analyze, report, decide."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from sqlalchemy import func

from app.auth_utils import get_current_user
from app.db import get_db
from app.logging_config import get_logger
from app.models import (
    Application,
    ApplicationStatus,
    AuditLog,
    BranchEntry,
    BranchEntryDocument,
    User,
)
from app.services.analysis_queue import analysis_queue
from app.services.ai_progress import ai_progress
from app.services.queue_eta import eta_payload
from app.services.application_storage import resolve_document_path
from app.services.audit import write_audit
from app.services.branch_entry_storage import (
    resolve_branch_entry_path,
    save_branch_entry_document,
)
from app.services.email_queue import email_queue
from app.services.pdf_report import build_verification_pdf
from app.services.document_archive import index_branch_entry, search_archives
from app.services.workflow_queue import workflow_queue
from app.services.workflow_service import WorkflowService

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/branch", tags=["branch"])

SOURCE_CUSTOMER_PORTAL = "customer_portal"
SOURCE_BRANCH_ENTRY = "branch_entry"

DOC_FIELDS = {
    "cnic_front": "cnic_front_path",
    "cnic_back": "cnic_back_path",
    "payslip": "payslip_path",
    "bank_statement": "bank_statement_path",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _document_meta(application_id: UUID, label: str, relative: str) -> dict:
    path = Path(relative)
    suffix = path.suffix.lower()
    return {
        "path": relative,
        "filename": path.name,
        "url": f"/api/v1/branch/applications/{application_id}/documents/{label}",
        "is_image": suffix in IMAGE_EXTENSIONS,
        "is_pdf": suffix == ".pdf",
    }


class DecideRequest(BaseModel):
    decision: str = Field(..., description="accept or reject")
    note: Optional[str] = None


def _get_branch_application(db: Session, user: User, application_id: UUID) -> Application:
    application = (
        db.query(Application)
        .options(joinedload(Application.branch))
        .filter(Application.id == application_id)
        .first()
    )
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.branch_id != user.branch_id:
        raise HTTPException(status_code=403, detail="Application belongs to another branch")
    return application


def _list_item(app: Application) -> dict:
    return {
        "id": str(app.id),
        "status": app.status,
        "full_name": app.full_name,
        "cnic_number": app.cnic_number,
        "email": app.email,
        "mobile_number": app.mobile_number,
        "company_name": app.company_name,
        "designation": app.designation,
        "monthly_income": app.monthly_income,
        "decision_note": app.decision_note,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "analyzed_at": app.analyzed_at.isoformat() if app.analyzed_at else None,
        "decided_at": app.decided_at.isoformat() if app.decided_at else None,
        "branch": {"code": app.branch.code, "name": app.branch.name},
        "has_report": app.report_json is not None,
    }


def _detail(app: Application) -> dict:
    docs = {}
    for label, attr in DOC_FIELDS.items():
        rel = getattr(app, attr)
        docs[label] = _document_meta(app.id, label, rel)
    payload = _list_item(app)
    payload.update(
        {
            "age": app.age,
            "cnic_full_name": app.cnic_full_name,
            "father_name": app.father_name,
            "date_of_birth": app.date_of_birth,
            "cnic_issue_date": app.cnic_issue_date,
            "cnic_expiry_date": app.cnic_expiry_date,
            "country_to_stay": app.country_to_stay,
            "gender": app.gender,
            "employee_id": app.employee_id,
            "designation": app.designation,
            "monthly_income": app.monthly_income,
            "verification_email_document": app.verification_email_document,
            "verification_email_target": app.verification_email_target,
            "verification_email_status": app.verification_email_status,
            "verification_email_last_error": app.verification_email_last_error,
            "verification_email_sent_at": app.verification_email_sent_at.isoformat() if app.verification_email_sent_at else None,
            "verification_email_confirmed_at": app.verification_email_confirmed_at.isoformat() if app.verification_email_confirmed_at else None,
            "verification_email_note": app.verification_email_note,
            "documents": docs,
            "decision_note": app.decision_note,
            "ai_progress": ai_progress.snapshot_for_app(str(app.id), app.status),
            "queue_eta": eta_payload(
                str(app.id), app.status, analysis_queue.snapshot()
            ),
        }
    )
    return payload


@router.get("/applications")
def list_applications(
    status: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Application)
        .options(joinedload(Application.branch))
        .filter(Application.branch_id == user.branch_id)
    )
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            query = query.filter(Application.status.in_(statuses))
    apps = query.order_by(Application.created_at.desc()).all()
    return [_list_item(a) for a in apps]


def _dashboard_status_bucket(status: Optional[str]) -> Optional[str]:
    """Map portal + branch-entry statuses onto dashboard metric keys."""
    value = (status or "").strip().lower()
    if value in {"pending", "saved", "submitted"}:
        return "pending"
    if value == "analyzing":
        return "analyzing"
    if value in {"completed", "review_required", "analyzed"}:
        return "completed"
    if value in {"accepted", "approved"}:
        return "accepted"
    if value == "rejected":
        return "rejected"
    # failed stays in total only (not a decision outcome)
    return None


@router.get("/dashboard")
def branch_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    counts = {
        "total": 0,
        "pending": 0,
        "analyzing": 0,
        "completed": 0,
        "accepted": 0,
        "rejected": 0,
    }

    app_rows = (
        db.query(Application.status, func.count(Application.id))
        .filter(Application.branch_id == user.branch_id)
        .group_by(Application.status)
        .all()
    )
    for status_value, count in app_rows:
        counts["total"] += count
        bucket = _dashboard_status_bucket(status_value)
        if bucket:
            counts[bucket] += count

    entry_rows = (
        db.query(BranchEntry.status, func.count(BranchEntry.id))
        .filter(BranchEntry.branch_id == user.branch_id)
        .group_by(BranchEntry.status)
        .all()
    )
    for status_value, count in entry_rows:
        counts["total"] += count
        bucket = _dashboard_status_bucket(status_value)
        if bucket:
            counts[bucket] += count

    recent_apps = (
        db.query(Application)
        .options(joinedload(Application.branch))
        .filter(Application.branch_id == user.branch_id)
        .order_by(Application.created_at.desc())
        .limit(8)
        .all()
    )
    recent_entries = (
        db.query(BranchEntry)
        .options(
            joinedload(BranchEntry.branch),
            joinedload(BranchEntry.documents),
        )
        .filter(BranchEntry.branch_id == user.branch_id)
        .order_by(BranchEntry.created_at.desc())
        .limit(8)
        .all()
    )
    recent = []
    for app in recent_apps:
        item = _list_item(app)
        item["source"] = SOURCE_CUSTOMER_PORTAL
        recent.append(item)
    for entry in recent_entries:
        recent.append(_branch_entry_list_item(entry))
    recent.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    recent = recent[:8]

    recent_logs = (
        db.query(AuditLog)
        .filter(AuditLog.branch_id == user.branch_id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
    )
    decided = counts["accepted"] + counts["rejected"]
    acceptance_rate = round((counts["accepted"] / decided) * 100, 1) if decided else 0.0

    return {
        "branch": {"code": user.branch.code, "name": user.branch.name},
        "counts": counts,
        "acceptance_rate": acceptance_rate,
        "queue_size": counts["pending"] + counts["analyzing"],
        "recent_applications": recent,
        "recent_audit": [
            {
                "id": log.id,
                "action": log.action,
                "message": log.message,
                "username": log.username,
                "application_id": str(log.application_id) if log.application_id else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "details": log.details or {},
            }
            for log in recent_logs
        ],
    }


@router.get("/audit-logs")
def list_audit_logs(
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 300))
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.branch_id == user.branch_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id,
            "action": log.action,
            "message": log.message,
            "username": log.username,
            "application_id": str(log.application_id) if log.application_id else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "details": log.details or {},
        }
        for log in logs
    ]


@router.get("/applications/{application_id}")
def get_application(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_branch_application(db, user, application_id)
    return _detail(app)


@router.get("/applications/{application_id}/documents/{label}")
def get_document(
    application_id: UUID,
    label: str,
    download: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if label not in DOC_FIELDS:
        raise HTTPException(status_code=400, detail="Unknown document label")
    app = _get_branch_application(db, user, application_id)
    relative = getattr(app, DOC_FIELDS[label])
    path = resolve_document_path(relative)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document file missing on disk")
    return FileResponse(
        path,
        filename=path.name,
        content_disposition_type="attachment" if download else "inline",
    )


@router.post("/applications/{application_id}/analyze")
def analyze_application(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-queue AI analysis (runs serially via the background worker)."""
    app = _get_branch_application(db, user, application_id)
    if app.status in (ApplicationStatus.accepted.value, ApplicationStatus.rejected.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot analyze application in status {app.status}",
        )

    if app.status != ApplicationStatus.analyzing.value:
        app.status = ApplicationStatus.pending.value
    write_audit(
        db,
        action="analysis_queued",
        message=f"Cognexa AI analysis re-queued for {app.full_name}",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        application_id=app.id,
    )
    db.commit()

    analysis_queue.enqueue(app.id)
    return {
        "application_id": str(app.id),
        "status": app.status,
        "message": "Application queued for Cognexa AI analysis",
    }


@router.get("/applications/{application_id}/report")
def get_report(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_branch_application(db, user, application_id)
    if not app.report_json:
        raise HTTPException(status_code=404, detail="Report not available yet. Wait for Cognexa AI analysis.")
    return app.report_json


@router.get("/applications/{application_id}/report/download")
def download_report_json(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_branch_application(db, user, application_id)
    if not app.report_json:
        raise HTTPException(status_code=404, detail="Report not available yet. Wait for Cognexa AI analysis.")
    filename = f"verification_report_{application_id}.json"
    body = json.dumps(app.report_json, indent=2, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/applications/{application_id}/report/pdf")
def download_report_pdf(
    application_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_branch_application(db, user, application_id)
    if not app.report_json:
        raise HTTPException(status_code=404, detail="Report not available yet. Wait for Cognexa AI analysis.")
    pdf_bytes = build_verification_pdf(
        app.report_json,
        applicant_name=app.full_name,
        application_id=str(app.id),
    )
    filename = f"verification_report_{application_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class VerificationEmailRequest(BaseModel):
    document_type: str = Field(..., description="payslip or bank_statement")
    target_email: str = Field(..., description="Company or bank verification email")
    note: Optional[str] = Field(None, description="Optional note to include with the request")


class VerificationEmailConfirmRequest(BaseModel):
    note: Optional[str] = Field(None, description="Optional confirmation note")


@router.post("/applications/{application_id}/verification-email")
def send_verification_email(
    application_id: UUID,
    payload: VerificationEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.verification_service import (
        VerificationEmailError,
        create_application_verification,
        validate_company_email,
    )
    from app.services.email_service import is_smtp_configured

    app = _get_branch_application(db, user, application_id)
    document_type = payload.document_type.strip().lower()
    if document_type not in {"payslip", "bank_statement"}:
        raise HTTPException(
            status_code=400,
            detail="document_type must be 'payslip' or 'bank_statement'",
        )

    if document_type == "payslip" and not app.payslip_path:
        raise HTTPException(status_code=400, detail="Payslip document is missing")
    if document_type == "bank_statement" and not app.bank_statement_path:
        raise HTTPException(status_code=400, detail="Bank statement document is missing")

    if not is_smtp_configured():
        raise HTTPException(
            status_code=500,
            detail="SMTP is not configured. Cannot send verification emails.",
        )

    try:
        target_email = validate_company_email(payload.target_email)
        verification = create_application_verification(
            db,
            app,
            document_type=document_type,
            target_email=target_email,
            note=payload.note,
            user_id=user.id,
            username=user.username,
        )
        db.commit()
        email_queue.enqueue(verification.verification_id)
        return {
            "application_id": str(app.id),
            "verification_id": verification.verification_id,
            "verification_email_status": app.verification_email_status,
            "verification_email_target": app.verification_email_target,
            "verification_email_sent_at": None,
        }
    except VerificationEmailError as exc:
        db.rollback()
        write_audit(
            db,
            action="verification_email_failed",
            message=(
                f"Verification email creation failed for {app.full_name}: {exc}"
            ),
            branch_id=user.branch_id,
            user_id=user.id,
            username=user.username,
            application_id=app.id,
            details={
                "document_type": document_type,
                "target_email": payload.target_email,
                "status": "failed",
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        write_audit(
            db,
            action="verification_email_failed",
            message=(
                f"Verification email creation failed for {app.full_name}: {exc}"
            ),
            branch_id=user.branch_id,
            user_id=user.id,
            username=user.username,
            application_id=app.id,
            details={
                "document_type": document_type,
                "target_email": payload.target_email,
                "status": "failed",
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to create verification request") from exc


@router.post("/applications/{application_id}/verification-email/confirm")
def confirm_verification_email(
    application_id: UUID,
    payload: VerificationEmailConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_branch_application(db, user, application_id)
    if app.verification_email_status != "sent":
        raise HTTPException(
            status_code=400,
            detail="No sent verification email to confirm.",
        )
    app.verification_email_status = "confirmed"
    app.verification_email_confirmed_at = datetime.utcnow()
    if payload.note:
        app.verification_email_note = (app.verification_email_note or "") + "\n" + payload.note.strip()
    write_audit(
        db,
        action="verification_email_confirmed",
        message=(
            f"Verification email confirmed for {app.full_name}"
        ),
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        application_id=app.id,
        details={
            "status": "confirmed",
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(app)
    return {
        "application_id": str(app.id),
        "verification_email_status": app.verification_email_status,
        "verification_email_confirmed_at": app.verification_email_confirmed_at.isoformat(),
    }


@router.post("/applications/{application_id}/decide")
def decide_application(
    application_id: UUID,
    payload: DecideRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    app = _get_branch_application(db, user, application_id)
    decision = payload.decision.strip().lower()
    if decision in {"approve", "accepted", "accept"}:
        decision = "accept"
    if decision not in {"accept", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be 'accept' or 'reject'")

    if app.status not in (
        ApplicationStatus.completed.value,
        ApplicationStatus.accepted.value,
        ApplicationStatus.rejected.value,
    ):
        raise HTTPException(
            status_code=400,
            detail="Wait for AI analysis to complete before accepting or rejecting",
        )

    if decision == "reject":
        note = (payload.note or "").strip()
        if not note:
            raise HTTPException(status_code=400, detail="Rejection requires a description/note")
        app.status = ApplicationStatus.rejected.value
        app.decision_note = note
    else:
        app.status = ApplicationStatus.accepted.value
        app.decision_note = (payload.note or "").strip() or None

    app.decided_at = datetime.utcnow()
    app.decided_by = user.id
    write_audit(
        db,
        action="application_accepted" if decision == "accept" else "application_rejected",
        message=(
            f"Application for {app.full_name} was "
            f"{'accepted' if decision == 'accept' else 'rejected'} by {user.username}"
        ),
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        application_id=app.id,
        details={"status": app.status, "decision_note": app.decision_note},
    )
    db.commit()
    db.refresh(app)
    return {
        "application_id": str(app.id),
        "status": app.status,
        "decision_note": app.decision_note,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Document Scan Tool
# ──────────────────────────────────────────────────────────────────────────────

DOCUMENT_TYPES = {
    "remittance_slip": "Remittance",
    "cnic": "CNIC",
    "payslip": "Pay Slip",
    "bank_statement": "Bank Statement",
    "account_opening_form": "Account Opening Form",
}

SCAN_ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".pdf"
}

MAX_SCAN_FILE_SIZE = 15 * 1024 * 1024  # 15 MB


def _inspect_image_flags(data: bytes, filename: str) -> list[str]:
    """Extract metadata and image quality flags for branch scan review."""
    flags: list[str] = []
    editors = ["photoshop", "gimp", "canva", "paint.net", "pixlr", "adobe", "illustrator", "inkscape", "coreldraw", "figma"]
    found_software = None
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        info = img.info or {}
        for key in ("software", "comment", "Software", "Comment"):
            val = str(info.get(key) or "").strip()
            for ed in editors:
                if ed in val.lower():
                    found_software = val
                    break
            if found_software:
                break

        if not found_software:
            exif = img.getexif()
            if exif:
                for tag_id, val in exif.items():
                    val_str = str(val).lower()
                    for ed in editors:
                        if ed in val_str:
                            found_software = str(val)
                            break
                    if found_software:
                        break
    except Exception:
        pass

    if not found_software and data:
        header = data[:262144].lower()
        for ed in ["canva", "photoshop", "gimp", "adobe photoshop", "paint.net", "figma"]:
            if ed.encode("utf-8") in header:
                found_software = ed.title()
                break

    if found_software:
        flags.append(f"🛡️ Metadata Alert: Digital editing software traces detected ({found_software}).")

    return flags


@router.post("/detect-document")
async def detect_document_gate(
    file: UploadFile = File(...),
    selected_type: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
):
    """
    Stage 1 + Stage 2 Document Gate evaluation.
    Determines whether the file is a document and if it is a supported banking document.
    """
    from app.document_detection import evaluate_document_gate

    data = await file.read()
    if len(data) > MAX_SCAN_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024} KB). Maximum is 15 MB.",
        )
    gate_result = evaluate_document_gate(data, selected_type=selected_type, branch=True)
    scan_flags = _inspect_image_flags(data, file.filename or "file")
    res_dict = gate_result.to_api_gate()
    res_dict["flags"] = scan_flags
    res_dict["editing_detected"] = bool(scan_flags)
    return res_dict


@router.post("/scan-document")
async def scan_document(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    OCR + AI summary for any branch banking document.
    Accepts an image or PDF plus a document_type key.
    Returns extracted_text and a structured AI summary.
    """
    from app import config as app_config
    from app.services.ocr_service import TesseractOCRService
    from app.services.llm_factory import get_llm_service
    from app.document_detection import evaluate_document_gate

    # Validate document type
    doc_label = DOCUMENT_TYPES.get(document_type)
    if doc_label is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown document_type '{document_type}'. "
                   f"Valid values: {', '.join(DOCUMENT_TYPES.keys())}",
        )

    # Validate extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SCAN_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. "
                   f"Allowed: {', '.join(sorted(SCAN_ALLOWED_EXTENSIONS))}",
        )

    # Read and size-check
    data = await file.read()
    if len(data) > MAX_SCAN_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024} KB). Maximum is 15 MB.",
        )

    # Two-stage document gate: Stage 1 (Document presence) + Stage 2 (Supported document check)
    gate_result = evaluate_document_gate(data, selected_type=document_type, branch=True)
    type_check = gate_result.to_type_check()
    api_gate = gate_result.to_api_gate()
    scan_flags = _inspect_image_flags(data, file.filename or "file")

    type_step_message = (
        "Document type check skipped."
        if gate_result.skipped
        else gate_result.message or "Document type check complete."
    )

    def _with_type_check(payload: dict) -> dict:
        payload["gate"] = api_gate
        payload["type_check"] = type_check
        payload["type_mismatch"] = gate_result.type_mismatch
        return payload

    # Hard stop on Stage 1 (NOT_A_DOCUMENT) or Stage 2 (UNSUPPORTED_DOCUMENT) or type mismatch
    if gate_result.gate_rejected and not gate_result.skipped:
        return _with_type_check(
            {
                "document_type": gate_result.detected_type_label or "Unknown",
                "filename": file.filename,
                "pipeline": "document_type_check",
                "fields": {},
                "checkboxes": {},
                "transactions": [],
                "extracted_text": "",
                "summary": {
                    "document_type": gate_result.detected_type_label,
                    "summary": gate_result.message,
                    "key_fields": {},
                    "confidence": "high" if gate_result.document_confidence >= 85 else "medium",
                    "flags": [
                        gate_result.message,
                        *(
                            [gate_result.reason]
                            if gate_result.reason
                            else []
                        ),
                        *scan_flags,
                    ],
                },
                "meta": gate_result.meta or {},
                "ai_activity": {
                    "pipeline": "document_type_check",
                    "ai_working": False,
                    "messages": [
                        "Stage 1 & Stage 2 Document Gate evaluation complete.",
                        gate_result.message,
                    ],
                },
            }
        )

    # Branch officer scans: remittance slips → LLM vision only.
    # Customer-submitted forms use the Python ROI/PaddleOCR service
    # at POST /api/v1/ocr/remittance — never mix the two paths.
    if document_type == "remittance_slip":
        try:
            from app.ocr_pipeline.llm_extract import extract_remittance_with_llm
            from app.ocr_pipeline.pipeline import EMPTY_CHECKBOXES, EMPTY_FIELDS

            remittance = extract_remittance_with_llm(data, branch=True)
            fields = {k: remittance.get(k, "") for k in EMPTY_FIELDS}
            checkboxes = {
                k: bool(remittance.get(k, False)) for k in EMPTY_CHECKBOXES
            }
            # Legacy payment aliases (same mapping as the Python pipeline)
            if checkboxes.get("cash_transfer"):
                checkboxes["cash"] = True
            if checkboxes.get("cashiers_cheque"):
                checkboxes["cheque_mode"] = True
            fields.update(checkboxes)
            meta = remittance.get("meta") or {}
            checked_labels = [k for k, v in checkboxes.items() if v]
            text_lines = [
                f"{k}: {v}" for k, v in fields.items() if isinstance(v, str) and v
            ]
            text_lines.extend(
                f"{k}: {'true' if v else 'false'}" for k, v in checkboxes.items()
            )
            filled = sum(1 for v in fields.values() if isinstance(v, str) and v.strip())
            confidence_label = (
                "high" if filled >= 8 else "medium" if filled >= 4 else "low"
            )
            return _with_type_check({
                "document_type": doc_label,
                "filename": file.filename,
                "pipeline": "remittance_llm_vision",
                "fields": fields,
                "checkboxes": checkboxes,
                "validation": {},
                "extracted_text": "\n".join(text_lines),
                "summary": {
                    "document_type": doc_label,
                    "summary": (
                        "Structured fields extracted. "
                        "Checkboxes classified as true/false."
                    ),
                    "key_fields": {
                        "amount": fields.get("amount_figures") or None,
                        "date": fields.get("date") or None,
                        "parties": fields.get("beneficiary_name") or None,
                        "reference_number": fields.get("cheque_number") or None,
                        "bank": "UBL",
                        "purpose": fields.get("purpose") or None,
                        "payment_cash": checkboxes.get("cash"),
                        "payment_cheque": checkboxes.get("cheque_mode"),
                        "payment_account_debit": checkboxes.get("account_debit"),
                        "checked_options": (
                            ", ".join(checked_labels) if checked_labels else None
                        ),
                    },
                    "confidence": confidence_label,
                    "flags": scan_flags,
                },
                "meta": {
                    "engine": meta.get("engine"),
                    "raw_preview": meta.get("raw_preview"),
                },
                "ai_activity": {
                    "pipeline": "remittance_llm_vision",
                    "ai_working": False,
                    "messages": [
                        type_step_message,
                        "Document parsing complete.",
                        "LLM extraction complete — form fields are ready to review.",
                    ],
                },
            })
        except ImportError as exc:
            logger.warning(
                "LLM remittance extract unavailable (%s); falling back to Tesseract",
                exc,
            )
        except Exception as exc:
            logger.error(
                "LLM remittance extract failed, falling back to Tesseract: %s",
                exc,
            )

    # CNIC / payslip / bank statement: Gemini vision structured fields
    if document_type in {"cnic", "payslip", "bank_statement"}:
        try:
            from app.ocr_pipeline.document_extract import (
                DOCUMENT_FIELD_KEYS,
                extract_document_with_llm,
            )

            extracted = extract_document_with_llm(document_type, data, branch=True)
            field_keys = DOCUMENT_FIELD_KEYS[document_type]
            fields = {k: extracted.get(k, "") for k in field_keys}
            transactions = extracted.get("transactions") or []
            meta = extracted.get("meta") or {}
            if document_type == "bank_statement":
                from app.ocr_pipeline.document_extract import format_bank_statement_text

                extracted_text = format_bank_statement_text(fields, transactions)
            else:
                text_lines = [f"{k}: {v}" for k, v in fields.items() if v]
                extracted_text = "\n".join(text_lines)
            filled = sum(1 for v in fields.values() if v and str(v).strip())
            if document_type == "bank_statement":
                filled += len(transactions)
            confidence_label = (
                "high" if filled >= 8 else "medium" if filled >= 4 else "low"
            )
            return _with_type_check({
                "document_type": doc_label,
                "filename": file.filename,
                "pipeline": "document_llm_vision",
                "fields": fields,
                "transactions": transactions,
                "extracted_text": extracted_text,
                "summary": {
                    "document_type": doc_label,
                    "summary": f"{doc_label} fields extracted successfully.",
                    "key_fields": fields,
                    "confidence": confidence_label,
                    "flags": scan_flags,
                },
                "meta": {
                    "engine": meta.get("engine"),
                },
                "ai_activity": {
                    "pipeline": "document_llm_vision",
                    "ai_working": False,
                    "messages": [
                        type_step_message,
                        "Document parsing complete.",
                        f"LLM {doc_label.lower()} extraction complete — fields are ready to review.",
                    ],
                },
            })
        except ImportError as exc:
            logger.warning(
                "LLM document extract unavailable (%s); falling back to Tesseract",
                exc,
            )
        except Exception as exc:
            logger.error(
                "LLM document extract failed, falling back to Tesseract: %s",
                exc,
            )

    # Cheques: LLM vision/text extract (Tesseract alone misses handwriting + logos)
    if document_type == "cheque" and suffix != ".pdf":
        try:
            from app.ocr_pipeline.llm_extract import (
                CHEQUE_FIELD_KEYS,
                extract_cheque_with_llm,
            )

            cheque = extract_cheque_with_llm(data, branch=True)
            fields = {k: cheque.get(k, "") for k in CHEQUE_FIELD_KEYS}
            meta = cheque.get("meta") or {}
            text_lines = [f"{k}: {v}" for k, v in fields.items() if v]
            filled = sum(1 for v in fields.values() if v and v.strip())
            confidence_label = (
                "high" if filled >= 8 else "medium" if filled >= 4 else "low"
            )
            bank_display = (
                fields.get("bank_name")
                or fields.get("bank_code")
                or None
            )
            return _with_type_check({
                "document_type": doc_label,
                "filename": file.filename,
                "pipeline": "cheque_llm",
                "fields": fields,
                "extracted_text": "\n".join(text_lines),
                "summary": {
                    "document_type": doc_label,
                    "summary": "Cheque fields extracted successfully.",
                    "key_fields": {
                        "amount": fields.get("amount_figures") or None,
                        "date": fields.get("date") or None,
                        "parties": fields.get("payee") or fields.get("account_name") or None,
                        "reference_number": fields.get("cheque_number") or None,
                        "bank": bank_display,
                        "purpose": None,
                        "amount_words": fields.get("amount_words") or None,
                        "iban": fields.get("iban") or None,
                        "branch": fields.get("branch_name") or None,
                        "product": fields.get("product_name") or None,
                    },
                    "confidence": confidence_label,
                    "flags": scan_flags,
                },
                "meta": {
                    "engine": meta.get("engine"),
                },
                "ai_activity": {
                    "pipeline": "cheque_llm",
                    "ai_working": False,
                    "messages": [
                        type_step_message,
                        "Document parsing complete.",
                        "LLM cheque extraction complete — fields are ready to review.",
                    ],
                },
            })
        except ImportError as exc:
            logger.warning(
                "LLM cheque extract unavailable (%s); falling back to Tesseract",
                exc,
            )
        except Exception as exc:
            logger.error(
                "LLM cheque extract failed, falling back to Tesseract: %s",
                exc,
            )

    # Run OCR (generic documents)
    try:
        ocr = TesseractOCRService()
        extracted_text = ocr.extract_text_from_bytes(data, file.filename or f"upload{suffix}")
    except Exception as exc:
        logger.error("OCR failed for scan-document: %s", exc)
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {exc}") from exc

    if not extracted_text.strip():
        raise HTTPException(
            status_code=422,
            detail="No text could be extracted from the document. "
                   "Please upload a clearer image.",
        )

    # Prefer LLM_PROVIDER from .env (gemini | groq | ollama)
    summary_data: dict = {}
    try:
        llm = get_llm_service(branch=True)
        prompt = _build_scan_prompt(doc_label, extracted_text)
        raw_json = llm.generate(prompt)
        import json as _json
        summary_data = _json.loads(raw_json)
        if isinstance(summary_data, dict):
            existing_flags = summary_data.get("flags") or []
            summary_data["flags"] = list(set(existing_flags + scan_flags))
    except Exception as exc:
        logger.warning("LLM summarization failed for scan-document: %s", exc)
        # Gracefully degrade — return OCR text without summary
        summary_data = {
            "document_type": doc_label,
            "summary": "AI summary unavailable (LLM error). "
                       "Please review the extracted text manually.",
            "key_fields": {},
            "confidence": "low",
            "flags": [f"LLM error: {str(exc)[:120]}", *scan_flags],
        }

    return _with_type_check({
        "document_type": doc_label,
        "filename": file.filename,
        "extracted_text": extracted_text,
        "summary": summary_data,
        "ai_activity": {
            "pipeline": "ocr_llm_summary",
            "ai_working": False,
            "messages": [
                type_step_message,
                "Document parsing complete — OCR text extracted.",
                "LLM summary complete — key fields are ready to review.",
            ],
        },
    })


WORKFLOW_TYPES = {
    "account_opening": "Account Opening Workflow",
}


def _workflow_page_numbers(group: dict) -> list[int]:
    raw_pages = group.get("pages") or []
    page_numbers: list[int] = []
    for item in raw_pages:
        if isinstance(item, dict):
            page_numbers.append(int(item["page"]))
        else:
            page_numbers.append(int(item))
    return page_numbers


def _create_workflow_branch_entry(
    db: Session,
    *,
    user: User,
    group: dict,
    rendered_pages: list[dict],
    docs_by_page: dict[int, dict],
    workflow_type: str,
    customer_name: Optional[str] = None,
) -> BranchEntry:
    page_numbers = _workflow_page_numbers(group)
    if not page_numbers:
        raise HTTPException(status_code=400, detail="Selected group has no pages")

    entry = BranchEntry(
        branch_id=user.branch_id,
        created_by=user.id,
        customer_name=customer_name or group.get("customer_id") or "Customer",
        status="pending",
        workflow_type=workflow_type,
        workflow_group_id=group.get("customer_id"),
        workflow_meta_json={
            "workflow_type": workflow_type,
            "workflow_group_id": group.get("customer_id"),
            "validation_preview": group.get("validation"),
            "cross_document_checks_preview": group.get("cross_document_checks"),
            "progress": {
                "stage": "queued",
                "message": "Waiting in workflow queue…",
            },
        },
    )
    db.add(entry)
    db.flush()

    for page_no in page_numbers:
        page_doc = docs_by_page.get(page_no) or {}
        page_data = next((p for p in rendered_pages if p["page"] == page_no), None)
        img_bytes = page_data["image_bytes"] if page_data else b""
        doc_type = page_doc.get("document_type") or "unknown"
        summary = page_doc.get("summary") or {
            "summary": "Queued for OCR and extraction.",
            "key_fields": {},
            "confidence": "low",
            "flags": ["queued"],
        }

        doc_id = uuid4()
        filename = f"page-{page_no}.png"
        relative = save_branch_entry_document(entry.id, doc_id, filename, img_bytes)

        doc = BranchEntryDocument(
            id=doc_id,
            branch_entry_id=entry.id,
            document_type=doc_type,
            original_filename=filename,
            file_path=relative,
            extracted_text=page_doc.get("raw_text") or "",
            fields_json=page_doc.get("fields") or {},
            checkboxes_json={},
            summary_json=summary,
        )
        db.add(doc)

    return entry


async def _read_workflow_pdf(file: UploadFile) -> bytes:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Workflow upload must be a PDF file.")
    data = await file.read()
    if len(data) > MAX_SCAN_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024} KB). Maximum is 15 MB.",
        )
    return data


@router.post("/process-workflow")
async def process_workflow(
    workflow_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Process a workflow PDF containing multiple customer documents."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Workflow upload must be a PDF file.",
        )

    data = await file.read()
    if len(data) > MAX_SCAN_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024} KB). Maximum is 15 MB.",
        )

    if workflow_type not in WORKFLOW_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported workflow_type '{workflow_type}'. "
                   f"Valid values: {', '.join(WORKFLOW_TYPES.keys())}",
        )

    try:
        service = WorkflowService()
        result = service.process_workflow(workflow_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Workflow processing failed: %s", exc)
        raise HTTPException(status_code=500, detail="Workflow processing failed.") from exc

    return result


@router.post("/process-workflow/commit-all")
async def commit_workflow_all(
    workflow_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save every detected customer group as Branch Entries and queue serial extraction."""
    if workflow_type not in WORKFLOW_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported workflow_type '{workflow_type}'. "
                   f"Valid values: {', '.join(WORKFLOW_TYPES.keys())}",
        )

    data = await _read_workflow_pdf(file)
    service = WorkflowService()
    try:
        workflow_result = service.process_workflow(workflow_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    groups = workflow_result.get("customer_groups") or []
    if not groups:
        raise HTTPException(status_code=422, detail="No customer groups detected in PDF.")

    rendered_pages = service._render_pdf_pages(data)
    docs_by_page = service._classify_pages(rendered_pages)
    entry_ids: list[str] = []

    for group in groups:
        entry = _create_workflow_branch_entry(
            db,
            user=user,
            group=group,
            rendered_pages=rendered_pages,
            docs_by_page=docs_by_page,
            workflow_type=workflow_type,
        )
        index_branch_entry(db, entry, document_type_labels=DOCUMENT_TYPES)
        entry_ids.append(str(entry.id))

    write_audit(
        db,
        action="branch_entries_created_via_workflow",
        message=f"Queued {len(entry_ids)} workflow customer group(s) for extraction",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        details={"entry_ids": entry_ids, "workflow_type": workflow_type},
    )
    db.commit()

    for entry_id in entry_ids:
        workflow_queue.enqueue(entry_id)

    return {
        "entry_ids": entry_ids,
        "count": len(entry_ids),
        "message": f"Queued {len(entry_ids)} customer(s) for OCR, extraction, and cross-check.",
    }


@router.post("/process-workflow/commit-group")
async def commit_workflow_group(
    workflow_type: str = Form(...),
    group_index: int = Form(...),
    file: UploadFile = File(...),
    customer_name: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save one detected workflow group as a Branch Entry and queue extraction."""
    if workflow_type not in WORKFLOW_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported workflow_type '{workflow_type}'.")

    data = await _read_workflow_pdf(file)
    service = WorkflowService()
    try:
        workflow_result = service.process_workflow(workflow_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    groups = workflow_result.get("customer_groups") or []
    if group_index < 0 or group_index >= len(groups):
        raise HTTPException(status_code=400, detail="Invalid group_index")

    group = groups[group_index]
    rendered_pages = service._render_pdf_pages(data)
    docs_by_page = service._classify_pages(rendered_pages)

    entry = _create_workflow_branch_entry(
        db,
        user=user,
        group=group,
        rendered_pages=rendered_pages,
        docs_by_page=docs_by_page,
        workflow_type=workflow_type,
        customer_name=customer_name,
    )
    index_branch_entry(db, entry, document_type_labels=DOCUMENT_TYPES)

    write_audit(
        db,
        action="branch_entry_created_via_workflow",
        message=f"Branch Entry queued from workflow group {group.get('customer_id')}",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        details={"branch_entry_id": str(entry.id), "group_index": group_index},
    )
    db.commit()
    workflow_queue.enqueue(entry.id)

    return {
        "entry_id": str(entry.id),
        "message": "Customer queued for OCR, extraction, and cross-document check.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Branch Entry (multi-document save) + unified records
# ──────────────────────────────────────────────────────────────────────────────


def _field_from_docs(docs: list[BranchEntryDocument], *keys: str) -> str:
    for doc in docs:
        fields = doc.fields_json or {}
        for key in keys:
            value = fields.get(key)
            if value is not None and str(value).strip() and str(value).strip().lower() != "null":
                return str(value).strip()
    return ""


def _branch_entry_list_item(entry: BranchEntry) -> dict:
    docs = list(entry.documents or [])
    workflow_meta = entry.workflow_meta_json or {}
    status = entry.status or "saved"
    return {
        "id": str(entry.id),
        "source": SOURCE_BRANCH_ENTRY,
        "status": status,
        "full_name": entry.customer_name,
        "cnic_number": _field_from_docs(docs, "cnic", "cnic_number"),
        "email": _field_from_docs(docs, "email"),
        "mobile_number": _field_from_docs(docs, "mobile", "mobile_number"),
        "company_name": _field_from_docs(docs, "company_name"),
        "designation": "",
        "monthly_income": "",
        "decision_note": None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "analyzed_at": entry.analyzed_at.isoformat() if entry.analyzed_at else None,
        "decided_at": None,
        "document_count": len(docs),
        "workflow_type": entry.workflow_type,
        "workflow_group_id": entry.workflow_group_id,
        "workflow_progress": workflow_meta.get("progress"),
        "overall_score": workflow_meta.get("overall_score"),
        "recommendation": workflow_meta.get("recommendation"),
        "branch": {
            "code": entry.branch.code if entry.branch else None,
            "name": entry.branch.name if entry.branch else None,
        },
        "has_report": bool(
            workflow_meta.get("report")
            or (entry.analyzed_at and status in {"completed", "review_required"})
        ),
    }


def _get_branch_entry(db: Session, user: User, entry_id: UUID) -> BranchEntry:
    entry = (
        db.query(BranchEntry)
        .options(
            joinedload(BranchEntry.branch),
            joinedload(BranchEntry.documents),
            joinedload(BranchEntry.creator),
        )
        .filter(BranchEntry.id == entry_id)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Branch entry not found")
    if entry.branch_id != user.branch_id:
        raise HTTPException(status_code=403, detail="Entry belongs to another branch")
    return entry


def _branch_entry_doc_meta(entry_id: UUID, doc: BranchEntryDocument) -> dict:
    path = Path(doc.file_path)
    suffix = path.suffix.lower()
    return {
        "id": str(doc.id),
        "document_type": doc.document_type,
        "document_type_label": DOCUMENT_TYPES.get(doc.document_type, doc.document_type),
        "original_filename": doc.original_filename,
        "path": doc.file_path,
        "filename": path.name,
        "url": f"/api/v1/branch/branch-entries/{entry_id}/documents/{doc.id}",
        "is_image": suffix in IMAGE_EXTENSIONS,
        "is_pdf": suffix == ".pdf",
        "fields": doc.fields_json or {},
        "checkboxes": doc.checkboxes_json or {},
        "summary": doc.summary_json or {},
        "extracted_text": doc.extracted_text or "",
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


@router.get("/archive/search")
def archive_search(
    q: str = "",
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Full-text search across archived OCR / vision extracted document text."""
    query = (q or "").strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="Search query must be at least 2 characters.")
    return search_archives(
        db,
        branch_id=user.branch_id,
        query=query,
        source=source,
        limit=limit,
        offset=offset,
    )


@router.get("/records")
def list_records(
    source: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unified Queue list: Customer Portal applications + Branch Entries."""
    rows: list[dict] = []

    include_portal = source in (None, "", "all", SOURCE_CUSTOMER_PORTAL)
    include_branch = source in (None, "", "all", SOURCE_BRANCH_ENTRY)

    portal_snapshot = analysis_queue.snapshot() if include_portal else None
    workflow_snapshot = workflow_queue.snapshot() if include_branch else None

    if include_portal:
        apps = (
            db.query(Application)
            .options(joinedload(Application.branch))
            .filter(Application.branch_id == user.branch_id)
            .order_by(Application.created_at.desc())
            .all()
        )
        for app in apps:
            item = _list_item(app)
            item["source"] = SOURCE_CUSTOMER_PORTAL
            item["document_count"] = 4
            item["queue_eta"] = eta_payload(str(app.id), app.status, portal_snapshot)
            rows.append(item)

    if include_branch:
        entries = (
            db.query(BranchEntry)
            .options(
                joinedload(BranchEntry.branch),
                joinedload(BranchEntry.documents),
            )
            .filter(BranchEntry.branch_id == user.branch_id)
            .order_by(BranchEntry.created_at.desc())
            .all()
        )
        for entry in entries:
            item = _branch_entry_list_item(entry)
            item["queue_eta"] = eta_payload(
                str(entry.id), entry.status, workflow_snapshot
            )
            rows.append(item)

    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


@router.post("/branch-entries")
async def create_branch_entry(
    customer_name: str = Form(...),
    payload: str = Form(...),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Save one or more scanned documents against a customer name (Branch Entry).

    payload JSON:
      { "documents": [ { document_type, fields, checkboxes, extracted_text, summary, original_filename? } ] }
    files: same order as documents[]
    """
    name = (customer_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Customer name is required.")

    try:
        meta = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid payload JSON.") from exc

    docs_meta = meta.get("documents") if isinstance(meta, dict) else None
    if not isinstance(docs_meta, list) or not docs_meta:
        raise HTTPException(status_code=400, detail="At least one document is required.")
    if len(files) != len(docs_meta):
        raise HTTPException(
            status_code=400,
            detail=f"files count ({len(files)}) must match documents ({len(docs_meta)}).",
        )

    entry = BranchEntry(
        branch_id=user.branch_id,
        created_by=user.id,
        customer_name=name,
        status="saved",
    )
    db.add(entry)
    db.flush()

    saved_docs: list[BranchEntryDocument] = []
    for upload, doc_meta in zip(files, docs_meta):
        if not isinstance(doc_meta, dict):
            raise HTTPException(status_code=400, detail="Each document meta must be an object.")

        doc_type = str(doc_meta.get("document_type") or "").strip()
        if doc_type not in DOCUMENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown document_type '{doc_type}'.",
            )

        filename = upload.filename or doc_meta.get("original_filename") or "document.bin"
        suffix = Path(filename).suffix.lower()
        if suffix not in SCAN_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{suffix}' for {filename}.",
            )

        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"Empty file: {filename}")
        if len(data) > MAX_SCAN_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({len(data) // 1024} KB). Maximum is 15 MB.",
            )

        doc_id = uuid4()
        relative = save_branch_entry_document(entry.id, doc_id, filename, data)

        fields = doc_meta.get("fields") if isinstance(doc_meta.get("fields"), dict) else {}
        checkboxes = (
            doc_meta.get("checkboxes")
            if isinstance(doc_meta.get("checkboxes"), dict)
            else {}
        )
        summary = doc_meta.get("summary") if isinstance(doc_meta.get("summary"), dict) else {}
        extracted = doc_meta.get("extracted_text")
        extracted_text = extracted if isinstance(extracted, str) else ""

        doc = BranchEntryDocument(
            id=doc_id,
            branch_entry_id=entry.id,
            document_type=doc_type,
            original_filename=filename,
            file_path=relative,
            extracted_text=extracted_text,
            fields_json=fields,
            checkboxes_json=checkboxes,
            summary_json=summary,
        )
        db.add(doc)
        saved_docs.append(doc)

    write_audit(
        db,
        action="branch_entry_created",
        message=f"Branch Entry saved for {name} ({len(saved_docs)} document(s))",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        details={
            "branch_entry_id": str(entry.id),
            "customer_name": name,
            "document_count": len(saved_docs),
            "document_types": [d.document_type for d in saved_docs],
        },
    )
    db.commit()

    entry = _get_branch_entry(db, user, entry.id)
    index_branch_entry(db, entry, document_type_labels=DOCUMENT_TYPES)
    db.commit()

    return {
        "id": str(entry.id),
        "source": SOURCE_BRANCH_ENTRY,
        "customer_name": entry.customer_name,
        "document_count": len(entry.documents or []),
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "message": f"Saved {len(entry.documents or [])} document(s) for {entry.customer_name}.",
    }


@router.get("/branch-entries/{entry_id}")
def get_branch_entry(
    entry_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _get_branch_entry(db, user, entry_id)
    item = _branch_entry_list_item(entry)
    item.update(
        {
            "customer_name": entry.customer_name,
            "status": entry.status or "saved",
            "workflow_type": entry.workflow_type,
            "workflow_group_id": entry.workflow_group_id,
            "workflow_meta": entry.workflow_meta_json or {},
            "created_by": entry.creator.username if entry.creator else None,
            "verification_email_document": entry.verification_email_document,
            "verification_email_target": entry.verification_email_target,
            "verification_email_status": entry.verification_email_status,
            "verification_email_last_error": entry.verification_email_last_error,
            "verification_email_sent_at": entry.verification_email_sent_at.isoformat() if entry.verification_email_sent_at else None,
            "verification_email_confirmed_at": entry.verification_email_confirmed_at.isoformat() if entry.verification_email_confirmed_at else None,
            "verification_email_note": entry.verification_email_note,
            "documents": [_branch_entry_doc_meta(entry.id, d) for d in (entry.documents or [])],
            "queue_eta": eta_payload(
                str(entry.id), entry.status or "saved", workflow_queue.snapshot()
            ),
        }
    )
    return item


def _branch_entry_email_application(entry: BranchEntry) -> dict:
    return {
        "full_name": entry.customer_name,
        "cnic_number": _field_from_docs(entry.documents or [], "cnic", "cnic_number"),
        "company_name": _field_from_docs(entry.documents or [], "company_name"),
        "employee_id": _field_from_docs(entry.documents or [], "employee_id"),
    }


class BranchEntryVerificationEmailRequest(BaseModel):
    document_type: str = Field(..., description="payslip or bank_statement")
    target_email: str = Field(..., description="Company or bank verification email")
    note: Optional[str] = Field(None, description="Optional note")


class BranchEntryVerificationEmailConfirmRequest(BaseModel):
    note: Optional[str] = Field(None, description="Optional note")


@router.post("/branch-entries/{entry_id}/verification-email")
def send_branch_entry_verification_email(
    entry_id: UUID,
    payload: BranchEntryVerificationEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.verification_service import (
        VerificationEmailError,
        create_branch_entry_verification,
        validate_company_email,
    )
    from app.services.email_service import is_smtp_configured

    entry = _get_branch_entry(db, user, entry_id)
    document_type = payload.document_type.strip().lower()
    if document_type not in {"payslip", "bank_statement"}:
        raise HTTPException(
            status_code=400,
            detail="document_type must be 'payslip' or 'bank_statement'",
        )

    if not any(d.document_type == document_type for d in (entry.documents or [])):
        raise HTTPException(
            status_code=400,
            detail=f"{document_type.replace('_', ' ').title()} document is missing",
        )

    if not is_smtp_configured():
        raise HTTPException(
            status_code=500,
            detail="SMTP is not configured. Cannot send verification emails.",
        )

    try:
        target_email = validate_company_email(payload.target_email)
        verification = create_branch_entry_verification(
            db,
            entry,
            document_type=document_type,
            target_email=target_email,
            note=payload.note,
            user_id=user.id,
            username=user.username,
        )
        db.commit()
        email_queue.enqueue(verification.verification_id)
        return {
            "entry_id": str(entry.id),
            "verification_id": verification.verification_id,
            "verification_email_status": entry.verification_email_status,
            "verification_email_target": entry.verification_email_target,
            "verification_email_sent_at": None,
        }
    except VerificationEmailError as exc:
        db.rollback()
        write_audit(
            db,
            action="verification_email_failed",
            message=(
                f"Verification email creation failed for {entry.customer_name}: {exc}"
            ),
            branch_id=user.branch_id,
            user_id=user.id,
            username=user.username,
            application_id=None,
            details={
                "document_type": document_type,
                "target_email": payload.target_email,
                "status": "failed",
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        write_audit(
            db,
            action="verification_email_failed",
            message=(
                f"Verification email creation failed for {entry.customer_name}: {exc}"
            ),
            branch_id=user.branch_id,
            user_id=user.id,
            username=user.username,
            application_id=None,
            details={
                "document_type": document_type,
                "target_email": payload.target_email,
                "status": "failed",
                "error": str(exc),
            },
        )
        raise HTTPException(status_code=500, detail="Failed to create verification request") from exc


@router.post("/branch-entries/{entry_id}/verification-email/confirm")
def confirm_branch_entry_verification_email(
    entry_id: UUID,
    payload: BranchEntryVerificationEmailConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _get_branch_entry(db, user, entry_id)
    if entry.verification_email_status != "sent":
        raise HTTPException(
            status_code=400,
            detail="No sent verification email to confirm.",
        )
    entry.verification_email_status = "confirmed"
    entry.verification_email_confirmed_at = datetime.utcnow()
    if payload.note:
        entry.verification_email_note = (entry.verification_email_note or "") + "\n" + payload.note.strip()
    write_audit(
        db,
        action="verification_email_confirmed",
        message=(
            f"Verification email confirmed for {entry.customer_name}"
        ),
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        application_id=None,
        details={
            "status": "confirmed",
            "note": payload.note,
        },
    )
    db.commit()
    db.refresh(entry)
    return {
        "entry_id": str(entry.id),
        "verification_email_status": entry.verification_email_status,
        "verification_email_confirmed_at": entry.verification_email_confirmed_at.isoformat(),
    }


@router.get("/branch-entries/{entry_id}/documents/{doc_id}")
def get_branch_entry_document(
    entry_id: UUID,
    doc_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    download: bool = False,
):
    entry = _get_branch_entry(db, user, entry_id)
    doc = next((d for d in (entry.documents or []) if d.id == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        path = resolve_branch_entry_path(doc.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk")

    media = "application/octet-stream"
    suffix = path.suffix.lower()
    if suffix in {".png"}:
        media = "image/png"
    elif suffix in {".jpg", ".jpeg"}:
        media = "image/jpeg"
    elif suffix == ".webp":
        media = "image/webp"
    elif suffix == ".pdf":
        media = "application/pdf"

    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{doc.original_filename or path.name}"'
    return FileResponse(path, media_type=media, headers=headers)
