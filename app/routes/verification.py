"""Verification API routes — thin controllers, no business logic."""

from __future__ import annotations

import json
from html import escape as html_escape
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.logging_config import get_logger
from app.models import Verification
from app.schemas.application import (
    ApplicationForm,
    CnicInfo,
    EmploymentInfo,
    PersonalInfo,
)
from app.services.email_service import VerificationEmailError
from app.services.verification_pipeline import VerificationPipeline
from app.services.verification_service import apply_email_link_decision
from app.services.verification_tokens import VerificationLinkError, decode_decision_token

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["verification"])
public_router = APIRouter(tags=["verification-links"])

pipeline = VerificationPipeline()

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


def _validate_upload(upload: Optional[UploadFile], field_name: str) -> Optional[bytes]:
    if upload is None or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type for {field_name}: {suffix}. "
                f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )
    return None  # content read by caller


@router.post("/verify")
async def verify_application(
    # Personal
    full_name: str = Form(...),
    age: str = Form(...),
    email: str = Form(...),
    mobile_number: str = Form(...),
    # CNIC
    cnic_full_name: str = Form(...),
    father_name: str = Form(...),
    cnic_number: str = Form(...),
    date_of_birth: str = Form(...),
    cnic_issue_date: str = Form(...),
    cnic_expiry_date: str = Form(...),
    country_to_stay: str = Form(...),
    gender: str = Form(...),
    # Employment
    company_name: str = Form(...),
    employee_id: str = Form(...),
    designation: str = Form(...),
    monthly_income: str = Form(...),
    # Documents
    cnic_front: UploadFile = File(...),
    cnic_back: UploadFile = File(...),
    payslip: UploadFile = File(...),
    bank_statement: UploadFile = File(...),
):
    """Submit account-opening application for AI verification."""
    try:
        form = ApplicationForm(
            personal=PersonalInfo(
                full_name=full_name,
                age=age,
                email=email,
                mobile_number=mobile_number,
            ),
            cnic=CnicInfo(
                full_name=cnic_full_name,
                father_name=father_name,
                cnic_number=cnic_number,
                date_of_birth=date_of_birth,
                issue_date=cnic_issue_date,
                expiry_date=cnic_expiry_date,
                country_to_stay=country_to_stay,
                gender=gender,
            ),
            employment=EmploymentInfo(
                company_name=company_name,
                employee_id=employee_id,
                designation=designation,
                monthly_income=monthly_income,
            ),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc

    uploads = {
        "cnic_front": cnic_front,
        "cnic_back": cnic_back,
        "payslip": payslip,
        "bank_statement": bank_statement,
    }

    saved: dict[str, Optional[Path]] = {}
    try:
        for label, upload in uploads.items():
            _validate_upload(upload, label)
            if upload is None or not upload.filename:
                saved[label] = None
                continue
            data = await upload.read()
            if not data:
                raise HTTPException(status_code=400, detail=f"Empty file uploaded for {label}")
            saved[label] = pipeline.save_upload(upload.filename, data)

        report, _extractions = pipeline.verify(form, saved)
        return report.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Verification failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        pipeline.cleanup_files(saved)


@router.post("/verify/json")
async def verify_application_json(
    payload: str = Form(..., description="JSON string of ApplicationForm"),
    cnic_front: UploadFile = File(...),
    cnic_back: UploadFile = File(...),
    payslip: UploadFile = File(...),
    bank_statement: UploadFile = File(...),
):
    """Same as /verify but accepts application JSON in a single form field."""
    try:
        form = ApplicationForm.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=json.loads(exc.json())) from exc

    uploads = {
        "cnic_front": cnic_front,
        "cnic_back": cnic_back,
        "payslip": payslip,
        "bank_statement": bank_statement,
    }
    saved: dict[str, Optional[Path]] = {}
    try:
        for label, upload in uploads.items():
            _validate_upload(upload, label)
            data = await upload.read()
            if not data:
                raise HTTPException(status_code=400, detail=f"Empty file uploaded for {label}")
            saved[label] = pipeline.save_upload(upload.filename, data)

        report, _extractions = pipeline.verify(form, saved)
        return report.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Verification failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        pipeline.cleanup_files(saved)


def _decision_page(title: str, message: str, ok: bool) -> str:
    accent = "#15803d" if ok else "#b91c1c"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html_escape(title)}</title>
</head>
<body style="margin:0;font-family:Arial,Helvetica,sans-serif;background:#f4f7fb;color:#2e3a49;">
  <table width="100%" cellpadding="0" cellspacing="0" style="min-height:100vh;">
    <tr>
      <td align="center" style="padding:48px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 0 32px rgba(15,23,42,0.08);">
          <tr><td style="padding:20px 28px;background:#0f4c81;color:#ffffff;">
            <h1 style="margin:0;font-size:1.15rem;">Company Verification</h1>
          </td></tr>
          <tr><td style="padding:28px;">
            <p style="margin:0 0 8px;font-size:1.05rem;font-weight:bold;color:{accent};">{html_escape(title)}</p>
            <p style="margin:0;font-size:0.95rem;line-height:1.6;">{html_escape(message)}</p>
          </td></tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


@public_router.get("/verify/{token}", response_class=HTMLResponse)
def verification_decision_link(token: str, db: Session = Depends(get_db)):
    """Public Accept / Reject endpoint opened from encrypted verification email links."""
    try:
        payload = decode_decision_token(token)
    except VerificationLinkError as exc:
        return HTMLResponse(_decision_page("Invalid link", str(exc), ok=False), status_code=400)

    verification = (
        db.query(Verification)
        .options(
            joinedload(Verification.application),
            joinedload(Verification.branch_entry),
        )
        .filter(Verification.verification_id == payload["vid"])
        .first()
    )
    if not verification:
        return HTMLResponse(
            _decision_page("Not found", "This verification request could not be found.", ok=False),
            status_code=404,
        )

    try:
        title, message = apply_email_link_decision(db, verification, payload["action"])
        db.commit()
        return HTMLResponse(_decision_page(title, message, ok=True))
    except VerificationEmailError as exc:
        db.rollback()
        return HTMLResponse(_decision_page("Unable to process", str(exc), ok=False), status_code=400)
    except Exception:
        db.rollback()
        logger.exception("Failed to process verification email link")
        return HTMLResponse(
            _decision_page(
                "Unable to process",
                "The verification decision could not be recorded. Please try again or reply to the email.",
                ok=False,
            ),
            status_code=500,
        )
