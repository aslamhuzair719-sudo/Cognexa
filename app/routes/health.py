"""Health and legacy single-document scan routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.logging_config import get_logger
from app.prompts.manager import PromptManager
from app.services.classifier import KeywordClassifier
from app.services.extraction_service import ExtractionPipeline
from app.services.ocr_service import TesseractOCRService
from app.services.llm_factory import get_llm_service

logger = get_logger(__name__)
router = APIRouter(tags=["system"])

ocr_service = TesseractOCRService()
classifier = KeywordClassifier()
llm_service = get_llm_service()
extraction_pipeline = ExtractionPipeline(
    ocr_service, classifier, llm_service, PromptManager()
)


class ScanRequest(BaseModel):
    path: str = Field(..., description="Path to a document file on the server")
    epad_id: str | None = Field(None, description="Optional EPAD identifier")
    tender_id: str | None = Field(None, description="Optional tender identifier")


@router.get("/health")
def health():
    return {"status": "ok", "service": "bank-account-verification", "phase": 1}


@router.post("/scan")
def scan_document(request: ScanRequest):
    """Legacy single-document extraction endpoint (OCR → classify → extract)."""
    doc_path = Path(request.path).expanduser().resolve()
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {doc_path}")
    if not doc_path.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {doc_path}")

    supported = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
    if doc_path.suffix.lower() not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Supported: {', '.join(sorted(supported))}",
        )

    try:
        result = extraction_pipeline.process(str(doc_path))
    except Exception as exc:
        logger.exception("Scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "epad_id": request.epad_id,
        "tender_id": request.tender_id,
        "path": str(doc_path),
        "document_type": result.get("document_type"),
        "confidence": result.get("confidence"),
        "fields": result.get("fields"),
        "error": result.get("error"),
        # OCR text intentionally omitted from staff-facing responses by default;
        # include only when debugging via query would be a future option.
    }
