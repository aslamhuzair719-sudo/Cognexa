"""Parse and validate LLM JSON output against registered Pydantic schemas."""

from __future__ import annotations

import json
import re
from typing import Dict, Type

from pydantic import BaseModel

from app.schemas.bank_statement import BankStatementSchema
from app.schemas.cnic import CNICSchema
from app.schemas.payslip import PayslipSchema
from app.schemas.account_opening_form import AccountOpeningFormSchema

SCHEMA_MAP: Dict[str, Type[BaseModel]] = {
    "cnic": CNICSchema,
    "payslip": PayslipSchema,
    "bank_statement": BankStatementSchema,
    "account_opening_form": AccountOpeningFormSchema,
}


def register_schema(document_type: str, schema_cls: Type[BaseModel]) -> None:
    """Allow future document types without changing core call sites."""
    SCHEMA_MAP[document_type] = schema_cls


def clean_json_string(raw_str: str) -> str:
    markdown_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_str, re.DOTALL)
    if markdown_match:
        return markdown_match.group(1).strip()

    json_match = re.search(r"(\{.*\})", raw_str, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()

    return raw_str.strip()


def parse_and_validate(document_type: str, raw_response: str) -> BaseModel:
    if document_type not in SCHEMA_MAP:
        raise ValueError(f"Unsupported document type for validation: {document_type}")

    cleaned = clean_json_string(raw_response)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON from LLM: {exc}. Cleaned string: '{cleaned[:300]}'"
        ) from exc

    if "fields" not in data:
        data = {"document_type": document_type, "fields": data}

    schema_cls = SCHEMA_MAP[document_type]
    return schema_cls.model_validate(data)
