"""Pydantic schema for UBL remittance OCR output."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RemittanceCheckboxes(BaseModel):
    """Form tick boxes — true = marked, false = empty."""

    non_account_holder: bool = False
    cash_transfer: bool = False
    cashiers_cheque: bool = False
    online_transfer: bool = False
    currency_pkr: bool = False
    purpose_family_maintenance: bool = False
    purpose_education: bool = False
    purpose_medical: bool = False
    purpose_gift: bool = False
    purpose_investment: bool = False
    purpose_business: bool = False
    purpose_other: bool = False
    # Legacy aliases
    cash: bool = False
    cheque_mode: bool = False
    account_debit: bool = False


class RemittanceFields(BaseModel):
    date: str = ""
    applicant_name: str = ""
    father_name: str = ""
    cnic: str = ""
    mobile: str = ""
    beneficiary_name: str = ""
    beneficiary_account: str = ""
    amount_figures: str = ""
    amount_words: str = ""
    branch_code: str = ""
    cheque_number: str = ""
    purpose: str = ""
    occupation: str = ""
    address: str = ""
    non_account_holder: bool = False
    cash_transfer: bool = False
    cashiers_cheque: bool = False
    online_transfer: bool = False
    currency_pkr: bool = False
    purpose_family_maintenance: bool = False
    purpose_education: bool = False
    purpose_medical: bool = False
    purpose_gift: bool = False
    purpose_investment: bool = False
    purpose_business: bool = False
    purpose_other: bool = False
    cash: bool = False
    cheque_mode: bool = False
    account_debit: bool = False


class FieldValidation(BaseModel):
    valid: bool
    message: str
    value: Any = ""


class RemittanceValidation(BaseModel):
    is_valid: bool
    fields: Dict[str, FieldValidation] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class RemittanceOCRResult(RemittanceFields):
    checkboxes: Optional[RemittanceCheckboxes] = None
    validation: Optional[RemittanceValidation] = None
    meta: Optional[Dict[str, Any]] = None
