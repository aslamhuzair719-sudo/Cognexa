"""Pydantic schemas for applications, documents, and verification reports."""

from app.schemas.application import ApplicationForm, CnicInfo, EmploymentInfo, PersonalInfo
from app.schemas.cnic import CNICFields, CNICSchema
from app.schemas.payslip import PayslipFields, PayslipSchema
from app.schemas.bank_statement import BankStatementFields, BankStatementSchema
from app.schemas.verification import (
    CheckResult,
    FieldComparison,
    ImageQualityResult,
    Recommendation,
    ValidationStatus,
    VerificationReport,
)

__all__ = [
    "ApplicationForm",
    "PersonalInfo",
    "CnicInfo",
    "EmploymentInfo",
    "CNICFields",
    "CNICSchema",
    "PayslipFields",
    "PayslipSchema",
    "BankStatementFields",
    "BankStatementSchema",
    "CheckResult",
    "FieldComparison",
    "ImageQualityResult",
    "Recommendation",
    "ValidationStatus",
    "VerificationReport",
]
