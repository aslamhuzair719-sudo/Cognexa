"""Single-document extraction pipeline (vision or OCR → classify → extract)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from app.logging_config import get_logger
from app.prompts.manager import PromptManager
from app.services.classifier import BaseClassifier
from app.services.gemini_service import GeminiService
from app.services.llm_factory import get_llm_service, supports_vision
from app.services.ocr_service import BaseOCRService
from app.services.ollama_service import BaseLLMService
from app.utils.normalize import (
    extract_cnic_number,
    extract_gender_from_ocr,
    gender_from_cnic_number,
    is_valid_cnic,
)

logger = get_logger(__name__)

ProgressCb = Optional[Callable[[str, str], None]]


class ExtractionPipeline:
    """Extract structured fields from one document file."""

    def __init__(
        self,
        ocr_service: BaseOCRService,
        classifier: BaseClassifier,
        llm_service: BaseLLMService,
        prompt_manager: Optional[PromptManager] = None,
    ) -> None:
        self.ocr_service = ocr_service
        self.classifier = classifier
        self.llm_service = llm_service
        self.prompt_manager = prompt_manager or PromptManager()

    def process(
        self,
        document_path: str,
        *,
        on_progress: ProgressCb = None,
        doc_label: str = "document",
        expected_document_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        def _progress(stage: str, message: str) -> None:
            if on_progress:
                on_progress(stage, message)

        _progress("ocr", f"Parsing {doc_label} text with OCR…")
        raw_text = self.ocr_service.extract_text(document_path)
        if not raw_text.strip() and not (
            supports_vision() and expected_document_type
        ):
            return {
                "document_type": "unknown",
                "confidence": 0.0,
                "extracted_text": "",
                "fields": None,
                "error": "No text could be extracted from the document.",
            }

        _progress("ocr", f"OCR parsing complete for {doc_label}.")

        if expected_document_type and supports_vision():
            doc_type = expected_document_type
            confidence = 1.0
        else:
            classification = self.classifier.classify(raw_text)
            doc_type = classification["document_type"]
            confidence = classification["confidence"]

        if doc_type == "unknown":
            return {
                "document_type": "unknown",
                "confidence": confidence,
                "extracted_text": raw_text,
                "fields": None,
                "error": "Document type could not be classified.",
            }

        if not self.prompt_manager.has_prompt(doc_type):
            return {
                "document_type": doc_type,
                "confidence": confidence,
                "extracted_text": raw_text,
                "fields": None,
                "error": f"Prompt template missing for classified type: {doc_type}",
            }

        _progress(
            "llm",
            f"Gemini vision is extracting fields from {doc_label} — AI is working…",
        )
        try:
            if supports_vision() and isinstance(self.llm_service, GeminiService):
                prompt = self.prompt_manager.get_vision_prompt(doc_type)
                from app.ocr_pipeline.llm_extract import source_to_base64_jpeg

                image_b64 = source_to_base64_jpeg(document_path)
                validated = self.llm_service.extract_structured_from_image(
                    prompt,
                    image_b64,
                    doc_type,
                )
            else:
                prompt = self.prompt_manager.get_prompt(doc_type, raw_text)
                validated = self.llm_service.extract_structured(prompt, doc_type)

            fields = validated.fields.model_dump()
            fields = self._post_correct_fields(doc_type, raw_text, fields)
            _progress("llm", f"LLM extraction complete for {doc_label}.")
            return {
                "document_type": doc_type,
                "confidence": confidence,
                "extracted_text": raw_text,
                "fields": fields,
                "error": None,
            }
        except Exception as exc:
            logger.exception("Extraction failed for %s", document_path)
            return {
                "document_type": doc_type,
                "confidence": confidence,
                "extracted_text": raw_text,
                "fields": None,
                "error": str(exc),
            }

    def _post_correct_fields(
        self, doc_type: str, ocr_text: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fix fields the LLM commonly mangles using deterministic OCR patterns."""
        if doc_type != "cnic":
            return fields

        ocr_cnic = extract_cnic_number(ocr_text)
        llm_cnic = fields.get("cnic_number")
        if ocr_cnic and (not is_valid_cnic(llm_cnic) or llm_cnic != ocr_cnic):
            logger.info(
                "Correcting CNIC from OCR regex: llm=%r -> ocr=%r",
                llm_cnic,
                ocr_cnic,
            )
            fields["cnic_number"] = ocr_cnic

        gender = fields.get("gender")
        if isinstance(gender, str):
            gender = gender.strip()
            if gender.lower() in {"", "null", "none", "n/a", "na", "-"}:
                gender = None
            fields["gender"] = gender

        if not fields.get("gender"):
            ocr_gender = extract_gender_from_ocr(ocr_text)
            if ocr_gender:
                logger.info("Filling CNIC gender from OCR text: %r", ocr_gender)
                fields["gender"] = ocr_gender
            else:
                digit_gender = gender_from_cnic_number(fields.get("cnic_number"))
                if digit_gender:
                    logger.info(
                        "Filling CNIC gender from CNIC check digit: %r", digit_gender
                    )
                    fields["gender"] = digit_gender

        return fields
