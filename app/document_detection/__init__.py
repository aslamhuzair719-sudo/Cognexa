"""Two-stage document gate: document presence, then supported type (demo scope)."""

from app.document_detection.registry import (
    SCAN_DOCUMENT_TYPES,
    label_for_type,
    normalize_detected_type,
)
from app.document_detection.schemas import DocumentGateResult, GateStatus
from app.document_detection.service import DocumentGateService, evaluate_document_gate

__all__ = [
    "DocumentGateResult",
    "DocumentGateService",
    "GateStatus",
    "SCAN_DOCUMENT_TYPES",
    "evaluate_document_gate",
    "label_for_type",
    "normalize_detected_type",
]
