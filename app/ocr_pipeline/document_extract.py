"""Structured field extraction for branch scan documents (CNIC, payslip, bank statement)."""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional, Union

import numpy as np

from app import config
from app.logging_config import get_logger
from app.ocr_pipeline.llm_extract import _strip_json_fence
from app.prompts.manager import PromptManager
from app.schemas.payslip import PAYSLIP_FORM_KEYS, canonicalize_payslip_fields
from app.services.llm_factory import (
    call_llm_text,
    call_llm_vision_source,
    llm_engine_label,
    supports_vision,
)

logger = get_logger(__name__)

ImageSource = Union[str, bytes, np.ndarray]

CNIC_FIELD_KEYS = (
    "name",
    "father_name",
    "gender",
    "country_to_stay",
    "cnic_number",
    "date_of_birth",
    "issue_date",
    "expiry_date",
)

PAYSLIP_FIELD_KEYS = PAYSLIP_FORM_KEYS

BANK_STATEMENT_FIELD_KEYS = (
    "account_title",
    "account_number",
    "iban",
    "currency",
    "from_date",
    "to_date",
    "address",
)

ACCOUNT_OPENING_FORM_FIELD_KEYS = (
    "title",
    "surname",
    "forenames",
    "applicant_name",
    "age",
    "father_name",
    "cnic_number",
    "date_of_birth",
    "gender",
    "current_address",
    "postcode",
    "last_address",
    "date_of_entry_to_address",
    "country_to_stay",
    "nationality",
    "home_phone",
    "mobile_number",
    "email",
    "usa_residence",
    "usa_green_card",
    "tax_residence_country",
    "tin",
    "company_name",
    "designation",
    "monthly_income",
    "employee_id",
)

DOCUMENT_FIELD_KEYS = {
    "cnic": CNIC_FIELD_KEYS,
    "payslip": PAYSLIP_FIELD_KEYS,
    "bank_statement": BANK_STATEMENT_FIELD_KEYS,
    "account_opening_form": ACCOUNT_OPENING_FORM_FIELD_KEYS,
}

_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")

_HEADER_RULES = (
    ("account_title", re.compile(r"account\s*title\s*[:]\s*(.+)", re.I)),
    ("account_number", re.compile(r"account\s*number\s*[:]\s*(.+)", re.I)),
    ("iban", re.compile(r"iban\s*[:]\s*(.+)", re.I)),
    ("currency", re.compile(r"currency\s*[:]\s*(.+)", re.I)),
    ("from_date", re.compile(r"from\s*date\s*[:]\s*(.+)", re.I)),
    ("to_date", re.compile(r"to\s*date\s*[:]\s*(.+)", re.I)),
    ("address", re.compile(r"address\s*[:]\s*(.+)", re.I)),
)


def _normalize_fields(
    data: Dict[str, Any],
    keys: tuple[str, ...],
    *,
    document_type: str = "",
) -> Dict[str, Any]:
    source = dict(data or {})
    if document_type == "payslip":
        source.update(canonicalize_payslip_fields(source))
    out: Dict[str, Any] = {}
    for key in keys:
        value = source.get(key, "")
        out[key] = "" if value is None else str(value).strip()
    return out


def _normalize_transaction(row: Dict[str, Any]) -> Dict[str, str]:
    return {
        "transaction_date": str(row.get("transaction_date") or row.get("date") or "").strip(),
        "description": str(row.get("description") or "").strip(),
        "debit": str(row.get("debit") or "").strip(),
        "credit": str(row.get("credit") or "").strip(),
        "available_balance": str(
            row.get("available_balance") or row.get("balance") or ""
        ).strip(),
    }


def _transaction_from_parts(parts: List[str]) -> Optional[Dict[str, str]]:
    if not parts:
        return None
    date = parts[0].strip()
    if not _DATE_RE.match(date):
        return None
    description = parts[1].strip() if len(parts) > 1 else ""
    debit = credit = balance = ""
    rest = [p.strip() for p in parts[2:]]
    if len(rest) == 1:
        balance = rest[0]
    elif len(rest) == 2:
        if rest[0]:
            debit = rest[0]
        balance = rest[1] or rest[0]
    elif len(rest) >= 3:
        debit, credit, balance = rest[0], rest[1], rest[2]
    return _normalize_transaction(
        {
            "transaction_date": date,
            "description": description,
            "debit": debit,
            "credit": credit,
            "available_balance": balance,
        }
    )


def parse_bank_statement_ocr(ocr_text: str) -> Dict[str, Any]:
    """Rule-based parser for tabular Pakistani bank statements."""
    fields = {key: "" for key in BANK_STATEMENT_FIELD_KEYS}
    transactions: List[Dict[str, str]] = []

    for raw_line in (ocr_text or "").splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "STATEMENT OF ACCOUNT":
            continue

        matched_header = False
        for key, pattern in _HEADER_RULES:
            match = pattern.search(line)
            if match:
                fields[key] = match.group(1).strip()
                matched_header = True
                break
        if matched_header:
            continue

        lower = line.lower()
        if "transaction date" in lower and "description" in lower:
            continue

        if "|" in line:
            tx = _transaction_from_parts([p for p in line.split("|")])
            if tx:
                transactions.append(tx)
            continue

        date_match = re.match(r"^(\d{1,2}/\d{1,2}/\d{2,4})\s+(.+)$", line)
        if date_match:
            tail = date_match.group(2)
            if "|" in tail:
                tx = _transaction_from_parts([date_match.group(1)] + tail.split("|"))
            else:
                chunks = re.split(r"\s{2,}", tail)
                tx = _transaction_from_parts([date_match.group(1), *chunks])
            if tx:
                transactions.append(tx)

    return {"fields": fields, "transactions": transactions}


def format_bank_statement_text(
    fields: Dict[str, str],
    transactions: List[Dict[str, str]],
) -> str:
    lines = ["STATEMENT OF ACCOUNT"]
    if fields.get("account_title"):
        lines.append(f"Account Title : {fields['account_title']}")
    if fields.get("account_number"):
        lines.append(f"Account Number: {fields['account_number']}")
    if fields.get("iban"):
        lines.append(f"IBAN: {fields['iban']}")
    if fields.get("currency"):
        lines.append(f"Currency: {fields['currency']}")
    if fields.get("from_date"):
        lines.append(f"From Date: {fields['from_date']}")
    if fields.get("to_date"):
        lines.append(f"To Date: {fields['to_date']}")
    if fields.get("address"):
        lines.append(f"Address: {fields['address']}")
    lines.append(
        "Transaction Date | Description | Debit | Credit | Available Balance"
    )
    for tx in transactions:
        lines.append(
            f"{tx.get('transaction_date', '')} | {tx.get('description', '')} | "
            f"{tx.get('debit', '')} | {tx.get('credit', '')} | "
            f"{tx.get('available_balance', '')}"
        )
    return "\n".join(lines)


def _parse_llm_json(raw: str, label: str) -> Dict[str, Any]:
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
        return parsed
    except (json.JSONDecodeError, ValueError):
        try:
            parsed = ast.literal_eval(cleaned)
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("LLM response is not a dictionary")
        except Exception as exc:
            logger.error("Failed to parse %s LLM JSON: %s | raw=%r", label, exc, raw[:500])
            raise RuntimeError(f"LLM returned invalid JSON: {exc}") from exc


def _merge_bank_statement(
    rule_data: Dict[str, Any],
    llm_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    fields = dict(rule_data.get("fields") or {})
    transactions = list(rule_data.get("transactions") or [])

    if llm_data:
        for key in BANK_STATEMENT_FIELD_KEYS:
            value = llm_data.get(key)
            if value and not fields.get(key):
                fields[key] = str(value).strip()
        llm_tx = llm_data.get("transactions")
        if isinstance(llm_tx, list) and llm_tx and not transactions:
            transactions = [
                _normalize_transaction(row)
                for row in llm_tx
                if isinstance(row, dict)
            ]

    return {"fields": fields, "transactions": transactions}


def extract_bank_statement_from_ocr(
    ocr_text: str,
    *,
    model: Optional[str] = None,
    branch: bool = False,
) -> Dict[str, Any]:
    """Extract bank statement header + transaction table from OCR text."""
    if not (ocr_text or "").strip():
        raise RuntimeError("No OCR text extracted from bank statement.")

    rule_data = parse_bank_statement_ocr(ocr_text)
    rule_filled = sum(1 for v in rule_data["fields"].values() if v)
    rule_tx = len(rule_data["transactions"])

    llm_data: Optional[Dict[str, Any]] = None
    engine = "ocr_rules"
    used_model = "rules"

    # Use LLM when rule-based extraction is weak.
    if rule_filled < 3 and rule_tx == 0:
        from app.prompts.manager import PromptManager

        prompt_mgr = PromptManager()
        prompt = prompt_mgr.get_prompt("bank_statement", ocr_text[:12000])
        try:
            raw = call_llm_text(prompt, model=model, branch=branch)
            engine, used_model = llm_engine_label(vision=False)
            llm_data = _parse_llm_json(raw, "bank_statement")
        except Exception as exc:
            logger.warning("Bank statement LLM extract failed, using OCR rules only: %s", exc)

    merged = _merge_bank_statement(rule_data, llm_data)
    fields = merged["fields"]
    transactions = merged["transactions"]
    filled = sum(1 for v in fields.values() if v)

    result: Dict[str, Any] = dict(fields)
    result["transactions"] = transactions
    result["meta"] = {
        "engine": engine,
        "model": used_model,
        "raw_preview": format_bank_statement_text(fields, transactions)[:400],
    }
    logger.info(
        "Bank statement extraction complete (%s): header=%d transactions=%d",
        engine,
        filled,
        len(transactions),
    )
    return result


def extract_document_from_ocr_text(
    document_type: str,
    ocr_text: str,
    *,
    model: Optional[str] = None,
    branch: bool = False,
) -> Dict[str, Any]:
    """Extract structured fields from already-extracted OCR text."""
    if document_type == "bank_statement":
        return extract_bank_statement_from_ocr(ocr_text, model=model, branch=branch)

    from app.prompts.manager import PromptManager

    keys = DOCUMENT_FIELD_KEYS.get(document_type)
    if not keys:
        raise ValueError(f"Unsupported document type: {document_type}")
    if not (ocr_text or "").strip():
        raise RuntimeError(
            f"No OCR text extracted from {document_type} document for LLM extraction."
        )

    prompt_mgr = PromptManager()
    prompt = prompt_mgr.get_prompt(document_type, ocr_text[:12000])

    raw = call_llm_text(prompt, model=model, branch=branch)
    engine, used_model = llm_engine_label(vision=False)

    parsed = _parse_llm_json(raw, document_type)
    result = _normalize_fields(parsed, keys, document_type=document_type)
    result["meta"] = {
        "engine": engine,
        "model": used_model,
        "raw_preview": raw[:400],
    }
    logger.info(
        "LLM %s extraction complete (%s): filled=%d",
        document_type,
        engine,
        sum(1 for v in result.values() if isinstance(v, str) and v),
    )
    return result


def _extract_with_vision(
    document_type: str,
    source: ImageSource,
    *,
    model: Optional[str] = None,
    max_side: int = 1600,
    branch: bool = False,
) -> Dict[str, Any]:
    """Gemini/Ollama vision extraction for structured documents."""
    prompt_mgr = PromptManager()
    prompt = prompt_mgr.get_vision_prompt(document_type)
    raw = call_llm_vision_source(
        source,
        prompt,
        model=model,
        max_side=max_side,
        branch=branch,
    )
    engine, used_model = llm_engine_label(vision=True)
    parsed = _parse_llm_json(raw, document_type)

    if document_type == "bank_statement":
        fields = _normalize_fields(parsed, BANK_STATEMENT_FIELD_KEYS, document_type=document_type)
        tx_raw = parsed.get("transactions")
        transactions: List[Dict[str, str]] = []
        if isinstance(tx_raw, list):
            transactions = [
                _normalize_transaction(row)
                for row in tx_raw
                if isinstance(row, dict)
            ]
        result: Dict[str, Any] = dict(fields)
        result["transactions"] = transactions
        result["meta"] = {
            "engine": engine,
            "model": used_model,
            "raw_preview": format_bank_statement_text(fields, transactions)[:400],
        }
        return result

    keys = DOCUMENT_FIELD_KEYS[document_type]
    result = _normalize_fields(parsed, keys, document_type=document_type)
    result["meta"] = {
        "engine": engine,
        "model": used_model,
        "raw_preview": raw[:400],
    }
    return result


def extract_document_with_llm(
    document_type: str,
    source: ImageSource,
    *,
    model: Optional[str] = None,
    max_side: int = 1600,
    branch: bool = False,
) -> Dict[str, Any]:
    """Extract structured fields for CNIC, payslip, or bank statement via vision."""
    if not supports_vision():
        from app.ocr_pipeline.llm_extract import _ocr_image_text

        ocr_text = _ocr_image_text(source)
        return extract_document_from_ocr_text(
            document_type, ocr_text, model=model, branch=branch
        )

    result = _extract_with_vision(
        document_type,
        source,
        model=model,
        max_side=max_side,
        branch=branch,
    )
    filled = sum(
        1 for k, v in result.items()
        if k != "meta" and k != "transactions" and isinstance(v, str) and v
    )
    if document_type == "bank_statement":
        filled += len(result.get("transactions") or [])
    logger.info(
        "LLM %s vision extraction complete (%s): filled=%d",
        document_type,
        result.get("meta", {}).get("engine"),
        filled,
    )
    return result
