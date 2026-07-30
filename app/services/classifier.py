"""Document classification service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from app.logging_config import get_logger

logger = get_logger(__name__)


class BaseClassifier(ABC):
    """Abstract base class for document classification."""

    @abstractmethod
    def classify(self, text: str) -> Dict[str, Any]:
        """Return document_type and confidence."""


class KeywordClassifier(BaseClassifier):
    """Keyword-based classifier for CNIC, payslip, and bank statement."""

    def __init__(self) -> None:
        self.keywords = {
            "cnic": [
                "national identity card",
                "identity number",
                "father name",
                "date of birth",
                "issue date",
                "expiry date",
                "holder's signature",
                "republic of pakistan",
                "nadra",
                "cnic",
            ],
            "payslip": [
                "payslip",
                "pay slip",
                "gross salary",
                "net pay",
                "net salary",
                "deduction",
                "overtime",
                "employee info",
                "pay period",
                "employee name",
                "earnings",
            ],
            "bank_statement": [
                "bank statement",
                "account statement",
                "opening balance",
                "closing balance",
                "transaction",
                "iban",
                "account number",
                "statement period",
                "withdrawal",
                "deposit",
            ],
        }

    def classify(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()
        scores: Dict[str, Dict[str, float]] = {}

        for doc_type, kw_list in self.keywords.items():
            matched = sum(1 for kw in kw_list if kw in text_lower)
            if matched > 0:
                confidence = round(matched / len(kw_list), 2)
                scores[doc_type] = {
                    "matched_count": matched,
                    "confidence": min(confidence, 1.0),
                }

        if not scores:
            logger.warning("Unable to classify document from OCR text")
            return {"document_type": "unknown", "confidence": 0.0}

        best_type = max(scores, key=lambda k: scores[k]["matched_count"])
        result = {
            "document_type": best_type,
            "confidence": scores[best_type]["confidence"],
        }
        logger.info(
            "Classified document as %s (confidence=%.2f)",
            result["document_type"],
            result["confidence"],
        )
        return result
