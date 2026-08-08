"""Document gate evaluation service for Stage 1 (presence) and Stage 2 (type support)."""

from __future__ import annotations

from typing import Optional, Union

import numpy as np

from app.document_detection.detector import DocumentGateDetector, ImageSource
from app.document_detection.registry import (
    SCAN_DOCUMENT_TYPES,
    SupportedDocumentRegistry,
    label_for_type,
    normalize_detected_type,
)
from app.document_detection.schemas import DocumentGateResult, GateStatus, RawGateDetection
from app.document_detection.strategies.llm_gate import LLMDocumentGateDetector
from app.logging_config import get_logger

logger = get_logger(__name__)

SUPPORTED_LABELS_TEXT = "CNIC, Payslip, Remittance"


class DocumentGateService:
    """Service orchestrating Stage 1 (document presence) and Stage 2 (supported type)."""

    def __init__(
        self,
        detector: Optional[DocumentGateDetector] = None,
        registry: Optional[SupportedDocumentRegistry] = None,
    ) -> None:
        self.detector = detector or LLMDocumentGateDetector()
        self.registry = registry or SupportedDocumentRegistry()

    def evaluate(
        self,
        source: ImageSource,
        *,
        selected_type: Optional[str] = None,
        branch: bool = True,
    ) -> DocumentGateResult:
        """Run two-stage document gate analysis."""
        raw: RawGateDetection
        try:
            raw = self.detector.detect(source, branch=branch)
        except Exception as exc:
            logger.warning("Document gate detector failed: %s; fallback to skipped", exc)
            return self._build_skipped_result(selected_type, str(exc))

        # STAGE 1: Is this a document?
        if not raw.is_document or raw.detected_type == "not_a_document":
            reason_text = raw.reason or "The uploaded image does not contain a structured printed document."
            return DocumentGateResult(
                status=GateStatus.NOT_A_DOCUMENT,
                is_document=False,
                document_confidence=raw.document_confidence,
                supported=False,
                document_type=None,
                detected_type="not_a_document",
                detected_type_label="Not a Document",
                supported_confidence=0.0,
                reason=reason_text,
                message="The uploaded image is not a document.",
                next_stage=None,
                selected_type=selected_type or "",
                selected_label=label_for_type(selected_type or "", self.registry),
                supported_documents=list(SCAN_DOCUMENT_TYPES.values()),
                meta=getattr(raw, "meta", {}),
            )

        # STAGE 2: Is it a supported banking document?
        detected_key = raw.detected_type
        detected_label = self.registry.label(detected_key)

        is_supported = self.registry.is_supported(detected_key)

        if not is_supported:
            return DocumentGateResult(
                status=GateStatus.UNSUPPORTED_DOCUMENT,
                is_document=True,
                document_confidence=raw.document_confidence,
                supported=False,
                document_type=None,
                detected_type=detected_key,
                detected_type_label=detected_label,
                supported_confidence=raw.type_confidence,
                reason=raw.reason or f"The document is a {detected_label}.",
                message=f"This is a valid document ({detected_label}) but it is not supported by this system.",
                next_stage=None,
                selected_type=selected_type or "",
                selected_label=label_for_type(selected_type or "", self.registry),
                supported_documents=list(SCAN_DOCUMENT_TYPES.values()),
                meta=getattr(raw, "meta", {}),
            )

        # Stage 1 and Stage 2 Passed -> Supported Document
        selected_key = normalize_detected_type(selected_type) if selected_type else None
        status = GateStatus.SUPPORTED
        if selected_key and selected_key != "unknown" and selected_key != detected_key:
            # Note: type mismatch, but document is supported
            status = GateStatus.TYPE_MISMATCH

        return DocumentGateResult(
            status=status,
            is_document=True,
            document_confidence=raw.document_confidence,
            supported=True,
            document_type=detected_key,
            detected_type=detected_key,
            detected_type_label=detected_label,
            supported_confidence=raw.type_confidence,
            reason=raw.reason or f"Document confirmed as {detected_label}.",
            message=f"Supported document confirmed ({detected_label}). Proceeding to analysis...",
            next_stage="quality_analysis",
            selected_type=selected_type or "",
            selected_label=label_for_type(selected_type or "", self.registry),
            supported_documents=list(SCAN_DOCUMENT_TYPES.values()),
            meta=getattr(raw, "meta", {}),
        )

    def _build_skipped_result(self, selected_type: Optional[str], err_msg: str) -> DocumentGateResult:
        selected_key = normalize_detected_type(selected_type) if selected_type else ""
        return DocumentGateResult(
            status=GateStatus.SKIPPED,
            is_document=True,
            document_confidence=0.0,
            supported=True,
            document_type=selected_key if selected_key != "unknown" else None,
            detected_type=selected_key or "unknown",
            detected_type_label=label_for_type(selected_key or "unknown", self.registry),
            supported_confidence=0.0,
            reason="Document gate skipped due to detection error.",
            message="Document type check skipped.",
            next_stage="quality_analysis",
            selected_type=selected_type or "",
            selected_label=label_for_type(selected_type or "", self.registry),
            skipped=True,
            supported_documents=list(SCAN_DOCUMENT_TYPES.values()),
            meta={"error": err_msg},
        )


def evaluate_document_gate(
    source: ImageSource,
    *,
    selected_type: Optional[str] = None,
    detector: Optional[DocumentGateDetector] = None,
    branch: bool = True,
) -> DocumentGateResult:
    """Convenience helper to run DocumentGateService."""
    service = DocumentGateService(detector=detector)
    return service.evaluate(source, selected_type=selected_type, branch=branch)
