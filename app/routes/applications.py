"""Public customer application submission (no AI)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db import get_db
from app.logging_config import get_logger
from app.models import Application, ApplicationStatus, Branch
from app.schemas.application import ApplicationForm, CnicInfo, EmploymentInfo, PersonalInfo
from app.services.analysis_queue import analysis_queue
from app.services.application_storage import DOC_LABELS, save_application_document
from app.services.audit import write_audit

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["applications"])

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}


def _validate_upload(upload: UploadFile, field_name: str) -> None:
    if not upload.filename:
        raise HTTPException(status_code=400, detail=f"Missing file for {field_name}")
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type for {field_name}: {suffix}. "
                f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )


@router.get("/branches")
def list_branches(db: Session = Depends(get_db)):
    branches = db.query(Branch).order_by(Branch.name).all()
    return [{"code": b.code, "name": b.name} for b in branches]


@router.post("/cnic/verify")
async def verify_cnic_against_document(
    cnic_number: str = Form(...),
    cnic_front: UploadFile = File(...),
    cnic_back: UploadFile | None = File(None),
):
    """
    Fast customer-form check: OCR CNIC front (Tesseract only, no LLM)
    and compare digits to the value typed on the form.
    """
    from app.services.ocr_service import TesseractOCRService
    from app.utils.normalize import (
        extract_cnic_number,
        format_cnic,
        is_valid_cnic,
        normalize_cnic,
    )

    form_digits = normalize_cnic(cnic_number)
    if not is_valid_cnic(form_digits):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid 13-digit CNIC (XXXXX-XXXXXXX-X) before uploading.",
        )

    _validate_upload(cnic_front, "cnic_front")
    if cnic_back is not None and cnic_back.filename:
        _validate_upload(cnic_back, "cnic_back")

    ocr = TesseractOCRService()
    extracted = None
    source = None

    front_bytes = await cnic_front.read()
    if not front_bytes:
        raise HTTPException(status_code=400, detail="CNIC front file is empty.")
    try:
        front_text = ocr.extract_text_from_bytes(
            front_bytes, cnic_front.filename or "cnic_front.jpg"
        )
        extracted = extract_cnic_number(front_text)
        if extracted:
            source = "cnic_front"
    except Exception as exc:
        logger.warning("CNIC front OCR failed: %s", exc)

    if not extracted and cnic_back is not None and cnic_back.filename:
        back_bytes = await cnic_back.read()
        if back_bytes:
            try:
                back_text = ocr.extract_text_from_bytes(
                    back_bytes, cnic_back.filename or "cnic_back.jpg"
                )
                extracted = extract_cnic_number(back_text)
                if extracted:
                    source = "cnic_back"
            except Exception as exc:
                logger.warning("CNIC back OCR failed: %s", exc)

    if not extracted:
        return {
            "match": False,
            "readable": False,
            "form_cnic": format_cnic(form_digits),
            "ocr_cnic": None,
            "source": None,
            "message": (
                "Could not read a CNIC number from the uploaded image. "
                "Please upload a clearer CNIC front photo."
            ),
        }

    ocr_digits = normalize_cnic(extracted)
    matched = form_digits == ocr_digits
    return {
        "match": matched,
        "readable": True,
        "form_cnic": format_cnic(form_digits),
        "ocr_cnic": format_cnic(ocr_digits),
        "source": source,
        "message": (
            "CNIC matched successfully."
            if matched
            else (
                f"CNIC on the document ({format_cnic(ocr_digits)}) does not match "
                f"what you entered ({format_cnic(form_digits)}). "
                "Please correct your CNIC details or upload the correct CNIC."
            )
        ),
    }


@router.post("/applications")
async def submit_application(
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
    # Branch + docs
    branch_code: str = Form(...),
    cnic_front: UploadFile = File(...),
    cnic_back: UploadFile = File(...),
    payslip: UploadFile = File(...),
    bank_statement: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Customer submits application + documents; AI analysis is queued."""
    try:
        ApplicationForm(
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

    branch_code = (branch_code or "").strip()
    branch = db.query(Branch).filter(Branch.code == branch_code).first()
    if not branch:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown branch: {branch_code or '(empty)'}. Choose Airport or Shahrae Faisal.",
        )

    uploads = {
        "cnic_front": cnic_front,
        "cnic_back": cnic_back,
        "payslip": payslip,
        "bank_statement": bank_statement,
    }
    for label in DOC_LABELS:
        _validate_upload(uploads[label], label)

    application_id = uuid.uuid4()
    saved_paths: dict[str, str] = {}
    try:
        for label, upload in uploads.items():
            data = await upload.read()
            if not data:
                raise HTTPException(status_code=400, detail=f"Empty file uploaded for {label}")
            saved_paths[label] = save_application_document(
                application_id, label, upload.filename or f"{label}.bin", data
            )

        application = Application(
            id=application_id,
            branch_id=branch.id,
            status=ApplicationStatus.pending.value,
            full_name=full_name.strip(),
            age=age.strip(),
            email=email.strip(),
            mobile_number=mobile_number.strip(),
            cnic_full_name=cnic_full_name.strip(),
            father_name=father_name.strip(),
            cnic_number=cnic_number.strip(),
            date_of_birth=date_of_birth.strip(),
            cnic_issue_date=cnic_issue_date.strip(),
            cnic_expiry_date=cnic_expiry_date.strip(),
            country_to_stay=country_to_stay.strip(),
            gender=gender.strip(),
            company_name=company_name.strip(),
            employee_id=employee_id.strip(),
            designation=designation.strip(),
            monthly_income=monthly_income.strip(),
            cnic_front_path=saved_paths["cnic_front"],
            cnic_back_path=saved_paths["cnic_back"],
            payslip_path=saved_paths["payslip"],
            bank_statement_path=saved_paths["bank_statement"],
        )
        db.add(application)
        db.flush()
        write_audit(
            db,
            action="application_submitted",
            message=f"Application submitted by {full_name.strip()}",
            branch_id=branch.id,
            application_id=application.id,
            details={
                "cnic_number": cnic_number.strip(),
                "email": email.strip(),
                "branch_code": branch.code,
            },
        )
        db.commit()
        db.refresh(application)
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to save application")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    analysis_queue.enqueue(application.id)

    logger.info(
        "Application %s submitted for branch %s by %s (queued for AI)",
        application_id,
        branch.code,
        full_name,
    )
    return {
        "application_id": str(application.id),
        "status": application.status,
        "branch": {"code": branch.code, "name": branch.name},
        "message": (
            "Application submitted successfully. "
            "AI has started analysing your documents — parsing and LLM summary "
            "will run at your branch next."
        ),
        "ai_status": "queued",
    }
