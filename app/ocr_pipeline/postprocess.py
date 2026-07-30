"""
OCR post-processing for remittance fields.

Cleans garbage characters, fixes common OCR confusions, normalizes
whitespace, and formats banking identifiers (CNIC, dates, accounts).
"""

from __future__ import annotations

import re
from typing import Callable, Dict, Optional

from app.utils.normalize import extract_cnic_number, format_cnic, normalize_cnic, parse_date

# Characters that frequently appear from table borders / noise
_GARBAGE_CHARS_RE = re.compile(r"[|\\/_=~`^<>\[\]{}]+")
_ISOLATED_SYMBOL_RE = re.compile(r"(?<!\w)[^\w\s.,:/+\-()%Rs](?!\w)")
_MULTI_SPACE_RE = re.compile(r"\s+")
_LABEL_PREFIX_RE = re.compile(
    r"^(?:"
    r"date|name|applicant|father|husband|s/?o|d/?o|w/?o|cnic|nic|mobile|"
    r"phone|cell|beneficiary|account\s*(?:no|number|#)?|amount|"
    r"branch(?:\s*code)?|cheque(?:\s*(?:no|number))?"
    r"|purpose|occupation|address|rs\.?|pkr"
    r")\s*[:\-.]?\s*",
    re.IGNORECASE,
)

# Common OCR glyph confusions in printed remittance forms
_OCR_SUBSTITUTIONS = (
    (re.compile(r"\bO(?=\d)"), "0"),  # O adjacent to digits → 0 (context applied later)
)


def strip_garbage(text: str) -> str:
    text = _GARBAGE_CHARS_RE.sub(" ", text)
    text = _ISOLATED_SYMBOL_RE.sub(" ", text)
    return text


def normalize_whitespace(text: str) -> str:
    return _MULTI_SPACE_RE.sub(" ", text).strip()


def strip_field_label(text: str) -> str:
    """Remove leaked printed labels that sit inside the ROI crop."""
    prev = None
    cleaned = text.strip()
    # Labels may be OCR'd twice; strip repeatedly
    while prev != cleaned:
        prev = cleaned
        cleaned = _LABEL_PREFIX_RE.sub("", cleaned).strip()
    return cleaned


def correct_common_ocr_mistakes(text: str, field_type: str) -> str:
    """
    Apply field-aware glyph corrections.

    Numeric fields: O→0, l/I→1, S→5, B→8 when surrounded by digits.
    Name fields: 0→O, 1→I when surrounded by letters.
    """
    if field_type in {"cnic", "phone", "account", "amount", "branch_code", "cheque", "date"}:
        chars = list(text)
        for i, ch in enumerate(chars):
            left = chars[i - 1] if i > 0 else ""
            right = chars[i + 1] if i + 1 < len(chars) else ""
            digit_neighbor = left.isdigit() or right.isdigit()
            if not digit_neighbor and not ch.isalpha():
                continue
            if ch in {"O", "o", "Q", "D"} and digit_neighbor:
                chars[i] = "0"
            elif ch in {"l", "I", "|", "!"} and digit_neighbor:
                chars[i] = "1"
            elif ch in {"S", "s"} and digit_neighbor:
                chars[i] = "5"
            elif ch in {"B"} and digit_neighbor:
                chars[i] = "8"
            elif ch in {"Z", "z"} and digit_neighbor:
                chars[i] = "2"
            elif ch in {"G"} and digit_neighbor:
                chars[i] = "6"
        return "".join(chars)

    if field_type in {"name", "amount_words", "text", "address"}:
        chars = list(text)
        for i, ch in enumerate(chars):
            left = chars[i - 1] if i > 0 else ""
            right = chars[i + 1] if i + 1 < len(chars) else ""
            letter_neighbor = left.isalpha() or right.isalpha()
            if ch == "0" and letter_neighbor:
                chars[i] = "O"
            elif ch == "1" and letter_neighbor:
                chars[i] = "l"
            elif ch == "5" and letter_neighbor:
                chars[i] = "S"
        return "".join(chars)

    return text


def format_date_field(text: str) -> str:
    """Normalize to DD/MM/YYYY when parseable."""
    cleaned = text.strip()
    # Digits glued together from checkbox date grids: DDMMYYYY
    digits = re.sub(r"\D", "", cleaned)
    if len(digits) == 8:
        candidate = f"{digits[:2]}/{digits[2:4]}/{digits[4:]}"
        if parse_date(candidate):
            return candidate
    dt = parse_date(cleaned)
    if dt:
        return dt.strftime("%d/%m/%Y")
    # Soft cleanup: unify separators
    soft = re.sub(r"[.\-]", "/", cleaned)
    soft = normalize_whitespace(soft)
    return soft


def format_cnic_field(text: str) -> str:
    found = extract_cnic_number(text)
    if found:
        return found
    digits = normalize_cnic(text)
    if len(digits) == 13:
        return format_cnic(digits)
    # Partial — return digits only for review
    return digits or normalize_whitespace(text)


def format_phone_field(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    # Drop leading country code 92 → keep local 03XXXXXXXXX
    if digits.startswith("92") and len(digits) >= 12:
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("3"):
        digits = "0" + digits
    return digits


def format_account_field(text: str) -> str:
    # Keep digits only for remittance account numbers / IBANs stripped of PK
    cleaned = text.upper().replace("PK", "")
    return re.sub(r"\D", "", cleaned)


def format_amount_field(text: str) -> str:
    cleaned = text.upper().replace("RS", " ").replace("PKR", " ").replace(",", "")
    cleaned = strip_garbage(cleaned)
    match = re.search(r"\d+(?:\.\d{1,2})?", cleaned)
    return match.group(0) if match else normalize_whitespace(cleaned)


def format_branch_code(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    return digits


def format_cheque_number(text: str) -> str:
    return re.sub(r"\D", "", text)


def format_name_field(text: str) -> str:
    cleaned = normalize_whitespace(strip_garbage(text))
    # Collapse repeated punctuation
    cleaned = re.sub(r"[^\w\s.\-']", " ", cleaned)
    cleaned = normalize_whitespace(cleaned)
    return cleaned.title() if cleaned.isupper() or cleaned.islower() else cleaned


def format_address_field(text: str) -> str:
    cleaned = normalize_whitespace(strip_garbage(text))
    cleaned = re.sub(r"[^\w\s.,/\-#]", " ", cleaned)
    return normalize_whitespace(cleaned)


_FORMATTERS: Dict[str, Callable[[str], str]] = {
    "date": format_date_field,
    "cnic": format_cnic_field,
    "phone": format_phone_field,
    "account": format_account_field,
    "amount": format_amount_field,
    "branch_code": format_branch_code,
    "cheque": format_cheque_number,
    "name": format_name_field,
    "address": format_address_field,
    "amount_words": lambda t: normalize_whitespace(strip_garbage(t)),
    "text": lambda t: normalize_whitespace(strip_garbage(t)),
}


def clean_field_text(raw: Optional[str], field_type: str) -> str:
    """Full post-process chain for one field."""
    if not raw:
        return ""
    text = str(raw)
    text = strip_garbage(text)
    text = strip_field_label(text)
    text = normalize_whitespace(text)
    text = correct_common_ocr_mistakes(text, field_type)
    formatter = _FORMATTERS.get(field_type)
    if formatter:
        text = formatter(text)
    return normalize_whitespace(text)
