"""Supported document types for branch scan demo and type normalization."""

from __future__ import annotations

import re
from typing import Dict

# Demo scope — branch scan UI and gate (CNIC, Payslip, Remittance only).
SCAN_DOCUMENT_TYPES: Dict[str, str] = {
    "remittance_slip": "Remittance",
    "cnic": "CNIC",
    "payslip": "Pay Slip",
}

_TYPE_ALIASES: Dict[str, str] = {
    "remittance": "remittance_slip",
    "remittance_slip": "remittance_slip",
    "remittance form": "remittance_slip",
    "ubl remittance": "remittance_slip",
    "application form": "remittance_slip",
    "cnic": "cnic",
    "nic": "cnic",
    "national identity card": "cnic",
    "identity card": "cnic",
    "id card": "cnic",
    "nadra": "cnic",
    "payslip": "payslip",
    "pay slip": "payslip",
    "pay_slip": "payslip",
    "salary slip": "payslip",
    "salaryslip": "payslip",
    "bank statement": "bank_statement",
    "bank_statement": "bank_statement",
    "account statement": "bank_statement",
    "statement": "bank_statement",
    "passport": "passport",
    "utility bill": "utility_bill",
    "utility_bill": "utility_bill",
    "electricity bill": "electricity_bill",
    "electricity_bill": "electricity_bill",
    "electric bill": "electricity_bill",
    "gas bill": "utility_bill",
    "water bill": "utility_bill",
    "trade license": "trade_license",
    "trade_license": "trade_license",
    "tax certificate": "tax_certificate",
    "tax document": "tax_certificate",
    "cheque": "cheque",
    "check": "cheque",
    "driving license": "driving_license",
    "driving licence": "driving_license",
    "not_a_document": "not_a_document",
    "unknown": "unknown",
    "other": "other",
}

_UNSUPPORTED_LABELS: Dict[str, str] = {
    "bank_statement": "Bank Statement",
    "passport": "Passport",
    "utility_bill": "Utility Bill",
    "electricity_bill": "Electricity Bill",
    "trade_license": "Trade License",
    "tax_certificate": "Tax Certificate",
    "cheque": "Cheque",
    "driving_license": "Driving License",
    "other": "Other Document",
    "not_a_document": "Not a Document",
    "unknown": "Unknown",
}


class SupportedDocumentRegistry:
    """Registry of document types allowed through the demo scan pipeline."""

    def __init__(self, supported: Dict[str, str] | None = None) -> None:
        self._supported = dict(supported or SCAN_DOCUMENT_TYPES)

    @property
    def supported_types(self) -> Dict[str, str]:
        return dict(self._supported)

    def is_supported(self, doc_type: str) -> bool:
        return doc_type in self._supported

    def label(self, doc_type: str) -> str:
        if doc_type in self._supported:
            return self._supported[doc_type]
        if doc_type in _UNSUPPORTED_LABELS:
            return _UNSUPPORTED_LABELS[doc_type]
        return doc_type.replace("_", " ").title()


def normalize_detected_type(value: object) -> str:
    """Map free-form model labels to a canonical type key."""
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "unknown"
    if text in SCAN_DOCUMENT_TYPES:
        return text
    if text in _TYPE_ALIASES:
        return _TYPE_ALIASES[text]
    for alias, key in _TYPE_ALIASES.items():
        if alias in text or text in alias:
            return key
    return "other"


def label_for_type(doc_type: str, registry: SupportedDocumentRegistry | None = None) -> str:
    reg = registry or SupportedDocumentRegistry()
    return reg.label(doc_type)
