"""API routes for UBL remittance form OCR pipeline."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.auth_utils import get_current_user
from app.logging_config import get_logger
from app.models import User
from app.ocr_pipeline import RemittanceOCRPipeline
from app.ocr_pipeline.config import PipelineConfig
from app.ocr_pipeline.pipeline import EMPTY_CHECKBOXES, EMPTY_FIELDS

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MAX_FILE_SIZE = 15 * 1024 * 1024


@router.post("/remittance")
async def ocr_remittance_form(
    file: UploadFile = File(...),
    debug: bool = Query(False, description="Save intermediate preprocess/ROI images"),
    user: User = Depends(get_current_user),
):
    """
    Python OCR service for customer-submitted UBL remittance forms.

    Preprocess (OpenCV) → crop field ROIs → PaddleOCR → clean → validate → JSON.

    Branch officer scans use LLM vision instead (`POST /api/v1/branch/scan-document`).
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file upload")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 15 MB)")

    try:
        cfg = PipelineConfig.default()
        if debug:
            cfg.save_debug_images = True
        pipeline = RemittanceOCRPipeline(config=cfg)
        result = pipeline.process(data, include_debug=debug)
    except ImportError as exc:
        logger.error("Remittance OCR dependency missing: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Remittance OCR failed")
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc

    # Public response: text fields + boolean checkboxes + validation
    payload: dict = {k: result.get(k, "") for k in EMPTY_FIELDS}
    checkboxes = {
        k: bool(result.get(k, False)) for k in EMPTY_CHECKBOXES
    }
    payload.update(checkboxes)
    payload["checkboxes"] = checkboxes
    payload["validation"] = result.get("validation")
    if debug:
        payload["meta"] = result.get("meta")
    else:
        # Lightweight meta for production clients
        meta = result.get("meta") or {}
        payload["meta"] = {
            "form_id": meta.get("form_id"),
            "engine": meta.get("engine"),
            "confidences": meta.get("confidences"),
            "checkbox_meta": meta.get("checkbox_meta"),
            "roi_count": meta.get("roi_count"),
        }
    return payload
