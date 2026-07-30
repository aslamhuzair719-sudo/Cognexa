"""Prompt manager — selects document-specific extraction prompts."""

from __future__ import annotations

from typing import Dict

from app.prompts.bank_statement import (
    BANK_STATEMENT_EXTRACTION_PROMPT,
    BANK_STATEMENT_VISION_PROMPT,
)
from app.prompts.cnic import CNIC_EXTRACTION_PROMPT, CNIC_VISION_PROMPT
from app.prompts.payslip import PAYSLIP_EXTRACTION_PROMPT, PAYSLIP_VISION_PROMPT


class PromptManager:
    """Central registry for document-type extraction prompts.

    New document types (passport, utility bill, etc.) are added by
    registering a prompt here — core pipeline code stays unchanged.
    """

    def __init__(self) -> None:
        self._prompts: Dict[str, str] = {
            "cnic": CNIC_EXTRACTION_PROMPT,
            "payslip": PAYSLIP_EXTRACTION_PROMPT,
            "bank_statement": BANK_STATEMENT_EXTRACTION_PROMPT,
        }
        self._vision_prompts: Dict[str, str] = {
            "cnic": CNIC_VISION_PROMPT,
            "payslip": PAYSLIP_VISION_PROMPT,
            "bank_statement": BANK_STATEMENT_VISION_PROMPT,
        }

    def register(self, document_type: str, prompt_template: str) -> None:
        self._prompts[document_type] = prompt_template

    def register_vision(self, document_type: str, prompt_template: str) -> None:
        self._vision_prompts[document_type] = prompt_template

    def supported_types(self) -> list[str]:
        return list(self._prompts.keys())

    def get_prompt(self, document_type: str, ocr_text: str) -> str:
        template = self._prompts.get(document_type)
        if not template:
            raise KeyError(f"No prompt registered for document type: {document_type}")
        return template.format(ocr_text=ocr_text)

    def get_vision_prompt(self, document_type: str) -> str:
        template = self._vision_prompts.get(document_type)
        if not template:
            raise KeyError(
                f"No vision prompt registered for document type: {document_type}"
            )
        return template

    def has_prompt(self, document_type: str) -> bool:
        return document_type in self._prompts

    def has_vision_prompt(self, document_type: str) -> bool:
        return document_type in self._vision_prompts
