"""Pydantic models for the branch scan document gate."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class GateStatus(str, Enum):
    """Outcome of Stage 1 + Stage 2 document gate."""

    SUPPORTED = "supported"
    NOT_A_DOCUMENT = "not_a_document"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    TYPE_MISMATCH = "type_mismatch"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


class RawGateDetection(BaseModel):
    """Parsed vision model output before business rules."""

    is_document: bool = False
    document_confidence: float = 0.0
    detected_type: str = "unknown"
    type_confidence: float = 0.0
    reason: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)


class DocumentGateResult(BaseModel):
    """Final gate decision returned to API clients."""

    status: GateStatus
    is_document: bool = False
    document_confidence: float = 0.0
    supported: bool = False
    document_type: Optional[str] = None
    detected_type: str = "unknown"
    detected_type_label: str = "Unknown"
    supported_confidence: float = 0.0
    reason: str = ""
    message: str = ""
    next_stage: Optional[str] = None
    selected_type: str = ""
    selected_label: str = ""
    supported_documents: list[str] = Field(default_factory=list)
    skipped: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)

    @property
    def gate_rejected(self) -> bool:
        return self.status in {
            GateStatus.NOT_A_DOCUMENT,
            GateStatus.UNSUPPORTED_DOCUMENT,
            GateStatus.TYPE_MISMATCH,
            GateStatus.UNCERTAIN,
        }

    @property
    def type_mismatch(self) -> bool:
        return self.gate_rejected and not self.skipped

    def to_type_check(self) -> Dict[str, Any]:
        """Backward-compatible shape for existing branch scan UI."""
        matched = self.status in {GateStatus.SUPPORTED, GateStatus.SKIPPED}
        confidence_label: Optional[str] = None
        if self.document_confidence >= 85:
            confidence_label = "high"
        elif self.document_confidence >= 60:
            confidence_label = "medium"
        elif self.document_confidence > 0:
            confidence_label = "low"

        return {
            "selected": self.selected_type,
            "selected_label": self.selected_label,
            "detected": self.document_type or self.detected_type,
            "detected_label": self.detected_type_label,
            "matched": matched,
            "confidence": confidence_label,
            "reason": self.reason or None,
            "message": self.message,
            "skipped": self.skipped,
            "gate_status": self.status.value,
            "is_document": self.is_document,
            "supported": self.supported,
            "supported_documents": self.supported_documents,
        }

    def to_api_gate(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "is_document": self.is_document,
            "document_confidence": self.document_confidence,
            "supported": self.supported,
            "document_type": self.document_type,
            "detected_type": self.detected_type,
            "detected_type_label": self.detected_type_label,
            "supported_confidence": self.supported_confidence,
            "reason": self.reason,
            "message": self.message,
            "next_stage": self.next_stage,
            "gate_rejected": self.gate_rejected,
            "supported_documents": self.supported_documents,
        }

