"""LLM document-type classification for branch scan (one vision request)."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Optional, Union

import numpy as np

from app.logging_config import get_logger
from app.ocr_pipeline.llm_extract import _strip_json_fence
from app.services.llm_factory import (
    call_llm_vision_source,
    llm_engine_label,
    supports_vision,
)

logger = get_logger(__name__)

ImageSource = Union[str, bytes, np.ndarray]

# Keys must match branch scan DOCUMENT_TYPES / frontend DOCUMENT_TYPES.
SCAN_DOCUMENT_TYPES = {
    "remittance_slip": "Remittance",
    "cnic": "CNIC",
    "payslip": "Pay Slip",
    "bank_statement": "Bank Statement",
}

_TYPE_ALIASES = {
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
    "unknown": "unknown",
    "other": "unknown",
}

CLASSIFY_VISION_PROMPT = """You are a banking document classifier.

Look at the attached document image and identify its type.

Choose EXACTLY one document_type value from this list:
- remittance_slip — UBL remittance / application / transfer form
- cnic — Pakistani National Identity Card (CNIC / NIC)
- payslip — employee pay slip / salary slip
- bank_statement — bank account statement with transactions
- unknown — anything else, including photos of people, animals, objects,
  scenery, screenshots, or any document that is not one of the four types above

Return ONLY valid JSON (no markdown):
{
  "document_type": "remittance_slip | cnic | payslip | bank_statement | unknown",
  "confidence": "high | medium | low",
  "reason": "One short sentence explaining why"
}
"""


def _parse_json(raw: str) -> Dict[str, Any]:
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    raise RuntimeError(f"LLM returned invalid JSON for document type: {raw[:300]!r}")


def normalize_document_type(value: Any) -> str:
    """Map free-form LLM labels to a canonical scan type key."""
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
    return "unknown"


def label_for_type(doc_type: str) -> str:
    if doc_type == "unknown":
        return "Unknown"
    return SCAN_DOCUMENT_TYPES.get(doc_type, doc_type)


def build_type_check(
    *,
    selected: str,
    detected: str,
    confidence: str = "",
    reason: str = "",
    skipped: bool = False,
) -> Dict[str, Any]:
    selected_key = selected if selected in SCAN_DOCUMENT_TYPES else normalize_document_type(selected)
    detected_key = normalize_document_type(detected)

    if skipped:
        matched = True
        message = "Document type check was skipped."
    elif detected_key == "unknown":
        matched = False
        message = (
            f"This file does not look like a {label_for_type(selected_key)}, "
            "or any supported banking document. Please upload a valid document."
        )
    else:
        matched = selected_key == detected_key
        if matched:
            message = f"Document type confirmed: {label_for_type(detected_key)}."
        else:
            message = (
                f"Wrong document type. You selected {label_for_type(selected_key)}, "
                f"but this looks like a {label_for_type(detected_key)}."
            )

    return {
        "selected": selected_key,
        "selected_label": label_for_type(selected_key),
        "detected": detected_key,
        "detected_label": label_for_type(detected_key),
        "matched": matched,
        "confidence": (confidence or "").strip().lower() or None,
        "reason": (reason or "").strip() or None,
        "message": message,
        "skipped": skipped,
    }


def classify_document_type(
    source: ImageSource,
    *,
    selected_type: str,
    model: Optional[str] = None,
    max_side: int = 1200,
    branch: bool = True,
) -> Dict[str, Any]:
    """
    Ask the vision LLM once what document type the image is.

    Returns a type_check dict comparing selected_type vs detected type.
    """
    if not supports_vision():
        logger.warning("Vision LLM unavailable; skipping document type check")
        return build_type_check(
            selected=selected_type,
            detected=selected_type,
            skipped=True,
        )

    raw = call_llm_vision_source(
        source,
        CLASSIFY_VISION_PROMPT,
        model=model,
        max_side=max_side,
        branch=branch,
    )
    engine, used_model = llm_engine_label(vision=True)
    parsed = _parse_json(raw)
    detected = normalize_document_type(parsed.get("document_type"))
    confidence = str(parsed.get("confidence") or "").strip().lower()
    reason = str(parsed.get("reason") or "").strip()

    result = build_type_check(
        selected=selected_type,
        detected=detected,
        confidence=confidence,
        reason=reason,
    )
    result["meta"] = {"engine": engine, "model": used_model}
    logger.info(
        "Document type check: selected=%s detected=%s matched=%s confidence=%s",
        result["selected"],
        result["detected"],
        result["matched"],
        result["confidence"],
    )
    return result
