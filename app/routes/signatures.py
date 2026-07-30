"""Signature Scan APIs: register and compare signatures by account number."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import config
from app.auth_utils import get_current_user
from app.db import get_db
from app.logging_config import get_logger
from app.models import SignatureRecord, User
from app.services.audit import write_audit
from app.services.signature_compare import compare_signature_images
from app.services.signature_storage import (
    delete_signature_file,
    resolve_signature_path,
    save_signature_image,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/branch/signatures", tags=["signatures"])

ALLOWED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _normalize_account(account_number: str) -> str:
    cleaned = "".join(ch for ch in (account_number or "").strip() if ch.isalnum())
    if len(cleaned) < 4:
        raise HTTPException(
            status_code=422,
            detail="Account number must contain at least 4 letters or digits.",
        )
    return cleaned.upper()


async def _read_image_upload(file: UploadFile) -> tuple[bytes, str]:
    if not file or not file.filename:
        raise HTTPException(status_code=422, detail="Signature image is required.")

    suffix = Path(file.filename).suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Unsupported file type. Upload a PNG, JPG, WEBP, or similar image.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit.")
    return data, file.filename


def _record_payload(record: SignatureRecord) -> dict:
    return {
        "id": str(record.id),
        "account_number": record.account_number,
        "customer_name": record.customer_name or "",
        "original_filename": record.original_filename,
        "image_url": f"/api/v1/branch/signatures/{record.id}/image",
        "branch_id": record.branch_id,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.get("")
def list_signatures(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List registered signatures (newest first)."""
    rows = (
        db.query(SignatureRecord)
        .order_by(SignatureRecord.updated_at.desc())
        .limit(200)
        .all()
    )
    return {"items": [_record_payload(r) for r in rows], "count": len(rows)}


@router.post("/register")
async def register_signature(
    account_number: str = Form(...),
    customer_name: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register (or replace) a signature image for an account number."""
    account = _normalize_account(account_number)
    name = (customer_name or "").strip()[:255]
    data, filename = await _read_image_upload(file)

    # Quick sanity decode so we don't store corrupt files
    try:
        compare_signature_images(data, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = (
        db.query(SignatureRecord)
        .filter(SignatureRecord.account_number == account)
        .first()
    )

    if existing:
        old_path = existing.file_path
        new_relative = save_signature_image(existing.id, filename, data)
        existing.file_path = new_relative
        existing.original_filename = filename
        existing.customer_name = name or existing.customer_name
        existing.branch_id = user.branch_id
        existing.created_by = user.id
        existing.updated_at = datetime.utcnow()
        write_audit(
            db,
            action="signature_register",
            message=f"Updated signature for account {account}",
            branch_id=user.branch_id,
            user_id=user.id,
            username=user.username,
            details={"account_number": account, "updated": True},
        )
        db.commit()
        db.refresh(existing)
        if old_path and old_path != new_relative:
            delete_signature_file(old_path)
        return {"ok": True, "updated": True, "record": _record_payload(existing)}

    record_id = uuid4()
    relative = save_signature_image(record_id, filename, data)
    record = SignatureRecord(
        id=record_id,
        account_number=account,
        customer_name=name or None,
        original_filename=filename,
        file_path=relative,
        branch_id=user.branch_id,
        created_by=user.id,
    )
    db.add(record)
    write_audit(
        db,
        action="signature_register",
        message=f"Registered signature for account {account}",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        details={"account_number": account, "updated": False},
    )
    db.commit()
    db.refresh(record)
    return {"ok": True, "updated": False, "record": _record_payload(record)}


@router.post("/compare")
async def compare_signature(
    account_number: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Compare an uploaded signature against the registered signature
    for the given account number. Returns match percentage.
    """
    account = _normalize_account(account_number)
    probe_data, filename = await _read_image_upload(file)

    record = (
        db.query(SignatureRecord)
        .filter(SignatureRecord.account_number == account)
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No registered signature found for account {account}.",
        )

    try:
        registered_path = resolve_signature_path(record.file_path)
        registered_bytes = registered_path.read_bytes()
    except (ValueError, OSError) as exc:
        logger.error("Missing signature file for %s: %s", account, exc)
        raise HTTPException(
            status_code=500,
            detail="Registered signature file is missing on the server.",
        ) from exc

    try:
        result = compare_signature_images(registered_bytes, probe_data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    match_pct = result["match_percentage"]
    threshold = config.SIGNATURE_MATCH_THRESHOLD
    if match_pct >= threshold:
        verdict = "match"
        verdict_label = "Likely match"
    elif match_pct >= threshold * 0.85:
        verdict = "uncertain"
        verdict_label = "Uncertain — review manually"
    else:
        verdict = "mismatch"
        verdict_label = "Likely mismatch"

    write_audit(
        db,
        action="signature_compare",
        message=f"Compared signature for account {account}: {match_pct}%",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        details={
            "account_number": account,
            "match_percentage": match_pct,
            "verdict": verdict,
            "probe_filename": filename,
        },
    )
    db.commit()

    return {
        "ok": True,
        "account_number": account,
        "customer_name": record.customer_name or "",
        "match_percentage": match_pct,
        "threshold": threshold,
        "verdict": verdict,
        "verdict_label": verdict_label,
        "scores": result["scores"],
        "registered": _record_payload(record),
        "probe_filename": filename,
    }


@router.get("/{record_id}/image")
def get_signature_image(
    record_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = db.query(SignatureRecord).filter(SignatureRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Signature not found")

    try:
        path = resolve_signature_path(record.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Signature file not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Signature file not found")

    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=record.original_filename or path.name)


@router.delete("/{record_id}")
def delete_signature(
    record_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a registered signature and its stored image."""
    record = db.query(SignatureRecord).filter(SignatureRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Signature not found")

    account = record.account_number
    file_path = record.file_path
    db.delete(record)
    write_audit(
        db,
        action="signature_delete",
        message=f"Deleted signature for account {account}",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        details={"account_number": account, "record_id": str(record_id)},
    )
    db.commit()
    if file_path:
        delete_signature_file(file_path)

    return {"ok": True, "deleted_id": str(record_id), "account_number": account}
