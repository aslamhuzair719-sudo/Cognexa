"""Regex validation for remittance OCR fields."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple, Union

from app.utils.normalize import is_valid_cnic, parse_amount, parse_date

FieldValue = Union[str, bool]

# Pakistani mobile: 03XX-XXXXXXX (11 digits)
_PHONE_RE = re.compile(r"^03\d{9}$")
# Account numbers on remittance slips vary; accept 8–24 digits (covers IBAN BBAN)
_ACCOUNT_RE = re.compile(r"^\d{8,24}$")
# Amount: positive number with optional 2 decimals
_AMOUNT_RE = re.compile(r"^\d+(?:\.\d{1,2})?$")
# Branch codes are typically 3–6 digits at UBL
_BRANCH_RE = re.compile(r"^\d{3,6}$")
_CHEQUE_RE = re.compile(r"^\d{6,14}$")
_DATE_DISPLAY_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def validate_cnic(value: str) -> Tuple[bool, str]:
    if not value:
        return False, "CNIC is empty"
    if is_valid_cnic(value):
        return True, "ok"
    return False, "CNIC must be 13 digits (XXXXX-XXXXXXX-X)"


def validate_date(value: str) -> Tuple[bool, str]:
    if not value:
        return False, "Date is empty"
    if parse_date(value) is None:
        return False, "Unrecognized date format"
    return True, "ok"


def validate_phone(value: str) -> Tuple[bool, str]:
    if not value:
        return False, "Mobile number is empty"
    if _PHONE_RE.match(value):
        return True, "ok"
    return False, "Mobile must be 03XXXXXXXXX (11 digits)"


def validate_account(value: str) -> Tuple[bool, str]:
    if not value:
        return False, "Account number is empty"
    if _ACCOUNT_RE.match(value):
        return True, "ok"
    return False, "Account number must be 8–24 digits"


def validate_amount(value: str) -> Tuple[bool, str]:
    if not value:
        return False, "Amount is empty"
    if not _AMOUNT_RE.match(value):
        return False, "Amount must be numeric"
    amount = parse_amount(value)
    if amount is None or amount <= 0:
        return False, "Amount must be greater than zero"
    return True, "ok"


def validate_branch_code(value: str) -> Tuple[bool, str]:
    if not value:
        return False, "Branch code is empty"
    if _BRANCH_RE.match(value):
        return True, "ok"
    return False, "Branch code must be 3–6 digits"


def validate_cheque(value: str) -> Tuple[bool, str]:
    if not value:
        # Cheque number is optional on some remittance flows
        return True, "optional"
    if _CHEQUE_RE.match(value):
        return True, "ok"
    return False, "Cheque number must be 6–14 digits"


def validate_nonempty(value: str, label: str) -> Tuple[bool, str]:
    if value and value.strip():
        return True, "ok"
    return False, f"{label} is empty"


_VALIDATORS = {
    "cnic": validate_cnic,
    "date": validate_date,
    "phone": validate_phone,
    "account": validate_account,
    "amount": validate_amount,
    "branch_code": validate_branch_code,
    "cheque": validate_cheque,
}


def validate_checkbox(value: Any) -> Tuple[bool, str]:
    if isinstance(value, bool):
        return True, "ok"
    if isinstance(value, str) and value.strip().lower() in {"true", "false", "0", "1"}:
        return True, "ok"
    return False, "Checkbox must be true or false"


# Map output JSON keys → field_type used by validators
FIELD_TYPE_BY_KEY = {
    "date": "date",
    "applicant_name": "name",
    "father_name": "name",
    "cnic": "cnic",
    "mobile": "phone",
    "beneficiary_name": "name",
    "beneficiary_account": "account",
    "amount_figures": "amount",
    "amount_words": "amount_words",
    "branch_code": "branch_code",
    "cheque_number": "cheque",
    "purpose": "text",
    "occupation": "text",
    "address": "address",
    "cash": "checkbox",
    "cheque_mode": "checkbox",
    "account_debit": "checkbox",
    "non_account_holder": "checkbox",
    "cash_transfer": "checkbox",
    "cashiers_cheque": "checkbox",
    "online_transfer": "checkbox",
    "currency_pkr": "checkbox",
    "purpose_family_maintenance": "checkbox",
    "purpose_education": "checkbox",
    "purpose_medical": "checkbox",
    "purpose_gift": "checkbox",
    "purpose_investment": "checkbox",
    "purpose_business": "checkbox",
    "purpose_other": "checkbox",
}


def validate_fields(fields: Dict[str, FieldValue]) -> Dict[str, Any]:
    """
    Validate extracted remittance fields.

    Returns a report:
      {
        "is_valid": bool,
        "fields": { key: {"valid": bool, "message": str, "value": ...} },
        "errors": [str, ...]
      }
    """
    report_fields: Dict[str, Dict[str, Any]] = {}
    errors = []

    for key, value in fields.items():
        # Nested checkboxes dict is informational — skip as a field
        if key == "checkboxes" and isinstance(value, dict):
            continue
        ftype = FIELD_TYPE_BY_KEY.get(key, "text")
        if ftype == "checkbox":
            ok, msg = validate_checkbox(value)
        else:
            text = "" if value is None else str(value)
            validator = _VALIDATORS.get(ftype)
            if validator:
                ok, msg = validator(text)
            elif ftype in {"name", "text", "address", "amount_words"}:
                # Soft check — warn only for critical identity names
                if key in {"applicant_name", "beneficiary_name"}:
                    ok, msg = validate_nonempty(text, key)
                else:
                    ok, msg = True, "ok"
            else:
                ok, msg = True, "ok"

        report_fields[key] = {"valid": ok, "message": msg, "value": value}
        if not ok and msg != "optional":
            errors.append(f"{key}: {msg}")

    return {
        "is_valid": len(errors) == 0,
        "fields": report_fields,
        "errors": errors,
    }
