"""Normalization helpers for fuzzy field comparison."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional, Tuple


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_cnic(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\D", "", str(value))


def format_cnic(digits: str) -> str:
    if len(digits) == 13:
        return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"
    return digits


# Pakistan CNIC: 13 digits, usually written as XXXXX-XXXXXXX-X
_CNIC_HYPHEN_RE = re.compile(r"(?<!\d)(\d{5})\s*[-–—]?\s*(\d{7})\s*[-–—]?\s*(\d)(?!\d)")
_CNIC_DIGITS_RE = re.compile(r"(?<!\d)(\d{13})(?!\d)")


def extract_cnic_number(text: Optional[str]) -> Optional[str]:
    """Pull a valid CNIC from noisy OCR text (preferred over LLM guesses)."""
    if not text:
        return None

    for match in _CNIC_HYPHEN_RE.finditer(text):
        digits = "".join(match.groups())
        if len(digits) == 13:
            return format_cnic(digits)

    for match in _CNIC_DIGITS_RE.finditer(text):
        return format_cnic(match.group(1))

    return None


def is_valid_cnic(value: Optional[str]) -> bool:
    digits = normalize_cnic(value)
    return len(digits) == 13


_GENDER_LABEL_RE = re.compile(
    r"(?:gender|sex|gander|gendar|sexe)\s*[:\-.]?\s*([mMfF])\b",
    re.IGNORECASE,
)
_GENDER_WORD_RE = re.compile(
    r"\b(male|female|man|woman)\b",
    re.IGNORECASE,
)
# Pakistani CNIC front often prints a lone M / F near other identity fields.
_GENDER_STANDALONE_RE = re.compile(
    r"(?<![A-Za-z0-9])([mMfF])(?![A-Za-z0-9])",
)


def extract_gender_from_ocr(text: Optional[str]) -> Optional[str]:
    """Pull M/F (or Male/Female) from noisy CNIC OCR text."""
    if not text:
        return None

    label = _GENDER_LABEL_RE.search(text)
    if label:
        return label.group(1).upper()

    word = _GENDER_WORD_RE.search(text)
    if word:
        value = word.group(1).lower()
        if value in {"male", "man"}:
            return "M"
        if value in {"female", "woman"}:
            return "F"

    # Prefer a standalone letter that appears after DOB/issue-style dates, common on CNIC fronts.
    candidates = _GENDER_STANDALONE_RE.findall(text)
    # Ignore common false positives from OCR noise if too many letters appear.
    letters = [c.upper() for c in candidates if c.upper() in {"M", "F"}]
    if len(letters) == 1:
        return letters[0]
    return None


def gender_from_cnic_number(value: Optional[str]) -> Optional[str]:
    """NADRA rule: last CNIC digit odd = Male (M), even = Female (F)."""
    digits = normalize_cnic(value)
    if len(digits) != 13:
        return None
    return "M" if int(digits[-1]) % 2 == 1 else "F"


def normalize_iban(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", "", str(value)).upper()


def normalize_account_number(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[\s\-]", "", str(value))


def parse_amount(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", "")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text or text in {".", "-", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


_DATE_FORMATS = (
    "%d.%m.%Y",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
)


def parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = re.sub(r"\s+", " ", str(value).strip())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        for fmt in ("%d%m%Y", "%Y%m%d"):
            try:
                return datetime.strptime(digits, fmt)
            except ValueError:
                continue
    return None


def dates_equal(a: Optional[str], b: Optional[str]) -> bool:
    da, db = parse_date(a), parse_date(b)
    if da and db:
        return da.date() == db.date()
    return normalize_text(a) == normalize_text(b) and bool(normalize_text(a))


def name_similarity(a: Optional[str], b: Optional[str]) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta and tb:
        overlap = len(ta & tb) / max(len(ta | tb), 1)
        seq = SequenceMatcher(None, na, nb).ratio()
        return max(overlap, seq)
    return SequenceMatcher(None, na, nb).ratio()


def names_match(a: Optional[str], b: Optional[str], threshold: float) -> Tuple[bool, float]:
    score = name_similarity(a, b)
    return score >= threshold, score
