"""Verification report and comparison result schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import CheckResult, Recommendation


# Backward-compatible alias used in some modules
ValidationStatus = CheckResult


class FieldComparison(BaseModel):
    field: str
    customer_value: Optional[str] = None
    document_value: Optional[str] = None
    document_source: Optional[str] = None
    result: CheckResult
    is_critical: bool = False
    message: Optional[str] = None


class ImageQualityCheck(BaseModel):
    check: str
    result: CheckResult
    detail: Optional[str] = None
    value: Optional[float] = None


class ImageQualityResult(BaseModel):
    document_label: str
    overall: CheckResult
    checks: List[ImageQualityCheck] = Field(default_factory=list)
    readable: bool = True


class DocumentUploadStatus(BaseModel):
    document_label: str
    uploaded: bool
    classified_as: Optional[str] = None
    classification_confidence: Optional[float] = None
    extraction_ok: bool = False
    error: Optional[str] = None


class SectionResult(BaseModel):
    title: str
    status: CheckResult
    comparisons: List[FieldComparison] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    """Bank-staff facing verification report. Does not include OCR text."""

    application_status: str
    overall_score: float
    recommendation: Recommendation
    summary: List[str] = Field(default_factory=list)

    application_summary: Dict[str, Any] = Field(default_factory=dict)
    uploaded_documents: List[DocumentUploadStatus] = Field(default_factory=list)
    image_quality: List[ImageQualityResult] = Field(default_factory=list)

    customer_information_validation: SectionResult
    cnic_validation: SectionResult
    payslip_validation: SectionResult
    bank_statement_validation: SectionResult
    cross_validation: SectionResult

    missing_information: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendation_detail: str = ""
