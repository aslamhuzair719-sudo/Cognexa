"""Shared enums used across verification schemas."""

from __future__ import annotations

from enum import Enum


class CheckResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


class Recommendation(str, Enum):
    APPROVED = "APPROVED"
    REVIEW_REQUIRED = "REVIEW REQUIRED"
    REJECTED = "REJECTED"


class DocumentSide(str, Enum):
    FRONT = "front"
    BACK = "back"
    SINGLE = "single"


class DocumentLabel(str, Enum):
    CNIC_FRONT = "cnic_front"
    CNIC_BACK = "cnic_back"
    PAYSLIP = "payslip"
    BANK_STATEMENT = "bank_statement"
