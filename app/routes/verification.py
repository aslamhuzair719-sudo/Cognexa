"""Verification API routes — thin controllers, no business logic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import ValidationError

from app.logging_config import get_logger
from app.schemas.application import (
    ApplicationForm,
    CnicInfo,
    EmploymentInfo,
    PersonalInfo,
)
from app.services.verification_pipeline import VerificationPipeline

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["verification"])

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

        report = pipeline.verify(form, saved)
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

        report = pipeline.verify(form, saved)
        return report.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Verification failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        pipeline.cleanup_files(saved)
