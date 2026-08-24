"""Fill payslip form gaps from labeled OCR lines when the LLM omits a field."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from app.schemas.payslip import canonicalize_payslip_fields

_LABEL_PATTERNS = (
    ("employee_name", re.compile(r"employee\s*name\s*[:\-]\s*(.+)", re.I)),
    ("employee_id", re.compile(r"employee\s*(?:id|no|number|#)\s*[:\-]\s*(.+)", re.I)),
    ("department", re.compile(r"department\s*[:\-]\s*(.+)", re.I)),
    ("designation", re.compile(r"(?:designation|job\s*title|position)\s*[:\-]\s*(.+)", re.I)),
    ("payslip_period", re.compile(r"pay(?:slip)?\s*period\s*[:\-]\s*(.+)", re.I)),
    ("payment_date", re.compile(r"(?:payment|pay)\s*date\s*[:\-]\s*(.+)", re.I)),
    ("employment_status", re.compile(r"employment\s*status\s*[:\-]\s*(.+)", re.I)),
    ("payslip_number", re.compile(r"payslip\s*(?:no|number|#|ref(?:erence)?)\s*[:\-]\s*(.+)", re.I)),
    ("email", re.compile(r"(?:e-?mail)\s*[:\-]\s*(\S+@\S+)", re.I)),
    ("phone", re.compile(r"(?:phone|mobile|tel)\s*[:\-]\s*([+\d][\d\s\-()]{6,})", re.I)),
    ("gross_salary", re.compile(r"gross\s*(?:pay|salary)\s*[:\-]\s*(?:pkr\s*)?([\d,]+(?:\.\d+)?)", re.I)),
    ("net_pay", re.compile(r"net\s*(?:pay|salary)\s*[:\-]\s*(?:pkr\s*)?([\d,]+(?:\.\d+)?)", re.I)),
    ("basic_salary", re.compile(r"basic\s*(?:pay|salary)\s*[:\-]\s*(?:pkr\s*)?([\d,]+(?:\.\d+)?)", re.I)),
    ("overtime", re.compile(r"overtime(?:\s*pay)?\s*[:\-]\s*(?:pkr\s*)?([\d,]+(?:\.\d+)?)", re.I)),
    ("deductions", re.compile(r"(?:total\s*)?deductions?\s*[:\-]\s*(?:pkr\s*)?([\d,]+(?:\.\d+)?)", re.I)),
    ("company_name", re.compile(r"(?:company|employer)\s*(?:name)?\s*[:\-]\s*(.+)", re.I)),
)

_STOP_LINE = re.compile(
    r"^(thank you|earnings|deductions|basic salary|overtime pay|gross pay|"
    r"net pay|hours|rate|current|ytd|signature)\b",
    re.I,
)
_MONEY_RE = re.compile(r"\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?)\b")
_HEADING_AMOUNT_LABELS = (
    ("gross_salary", re.compile(r"gross\s*(?:pay|salary)\b", re.I)),
    ("net_pay", re.compile(r"net\s*(?:pay|salary)\b", re.I)),
)


def _largest_amount(values: list[str]) -> Optional[str]:
    if not values:
        return None
    return max(values, key=lambda v: float(v.replace(",", "")))


def _amounts_after_heading(ocr_text: str, heading: re.Pattern[str]) -> list[str]:
    match = heading.search(ocr_text or "")
    if not match:
        return []
    rest = ocr_text[match.end():]
    stop = re.search(r"thank you\b|[A-Za-z][A-Za-z ]{3,}:", rest, re.I)
    if stop:
        rest = rest[: stop.start()]
    return _MONEY_RE.findall(rest)


def _line_value(match: re.Match[str]) -> str:
    value = (match.group(1) or "").strip(" :-|\t")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _header_company(ocr_text: str) -> Optional[str]:
    for raw in (ocr_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if ":" in line or _STOP_LINE.match(line):
            return None
        if re.search(r"pay\s*slip|payslip|salary\s*slip", line, re.I):
            continue
        if len(line) < 2 or len(line) > 80:
            continue
        return line
    return None


def enrich_payslip_from_ocr(ocr_text: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Fill empty payslip fields from labeled OCR text."""
    merged = canonicalize_payslip_fields(fields)
    text = ocr_text or ""
    if not text.strip():
        return merged

    for key, pattern in _LABEL_PATTERNS:
        if merged.get(key):
            continue
        match = pattern.search(text)
        if not match:
            continue
        value = _line_value(match)
        if value:
            merged[key] = value

    for key, heading in _HEADING_AMOUNT_LABELS:
        if merged.get(key):
            continue
        amount = _largest_amount(_amounts_after_heading(text, heading))
        if amount:
            merged[key] = amount

    if not merged.get("company_name"):
        header = _header_company(text)
        if header:
            merged["company_name"] = header

    return canonicalize_payslip_fields(merged)
