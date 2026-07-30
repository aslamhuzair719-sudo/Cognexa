"""End-to-end account opening verification pipeline."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, Optional
from collections.abc import Callable

from app import config
from app.logging_config import get_logger
from app.prompts.manager import PromptManager
from app.schemas.application import ApplicationForm
from app.schemas.bank_statement import BankStatementFields
from app.schemas.cnic import CNICFields
from app.schemas.payslip import PayslipFields
from app.schemas.verification import DocumentUploadStatus, VerificationReport
from app.services.classifier import BaseClassifier, KeywordClassifier
from app.services.extraction_service import ExtractionPipeline
from app.services.image_quality import ImageQualityService
from app.services.ocr_service import BaseOCRService, TesseractOCRService
from app.services.llm_factory import get_llm_service
from app.services.ollama_service import BaseLLMService
from app.services.report_generator import ReportGenerator
from app.services.validation_engine import ValidationEngine

logger = get_logger(__name__)

EXPECTED_DOCS = ("cnic_front", "cnic_back", "payslip", "bank_statement")
EXPECTED_CLASSIFICATION = {
    "cnic_front": "cnic",
    "cnic_back": "cnic",
    "payslip": "payslip",
    "bank_statement": "bank_statement",
}


class VerificationPipeline:
    """Orchestrates OCR → classify → extract → validate → report.

    No business logic lives in API routes; this class is the composition root
    for Phase 1 verification.
    """

    def __init__(
        self,
        ocr_service: Optional[BaseOCRService] = None,
        classifier: Optional[BaseClassifier] = None,
        llm_service: Optional[BaseLLMService] = None,
        prompt_manager: Optional[PromptManager] = None,
        image_quality: Optional[ImageQualityService] = None,
        validation_engine: Optional[ValidationEngine] = None,
        report_generator: Optional[ReportGenerator] = None,
    ) -> None:
        self.ocr_service = ocr_service or TesseractOCRService()
        self.classifier = classifier or KeywordClassifier()
        self.llm_service = llm_service or get_llm_service()
        self.prompt_manager = prompt_manager or PromptManager()
        self.image_quality = image_quality or ImageQualityService()
        self.validation_engine = validation_engine or ValidationEngine()
        self.report_generator = report_generator or ReportGenerator()
        self.extraction = ExtractionPipeline(
            self.ocr_service,
            self.classifier,
            self.llm_service,
            self.prompt_manager,
        )

    def verify(
        self,
        form: ApplicationForm,
        documents: Dict[str, Optional[Path]],
        *,
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> VerificationReport:
        """Run full verification for an application.

        Args:
            form: Customer application form data.
            documents: Mapping of document labels to saved file paths
                       (cnic_front, cnic_back, payslip, bank_statement).
            on_progress: Optional callback(stage, message) for live AI activity UI.
        """
        def _progress(stage: str, message: str) -> None:
            if on_progress:
                on_progress(stage, message)

        logger.info("Starting verification for applicant %s", form.personal.full_name)
        _progress("starting", "AI analysis starting — preparing customer documents…")

        upload_statuses = []
        quality_results = []
        readable_map: Dict[str, bool] = {}
        uploaded_map: Dict[str, bool] = {}

        cnic_front_fields: Optional[CNICFields] = None
        cnic_back_fields: Optional[CNICFields] = None
        payslip_fields: Optional[PayslipFields] = None
        bank_fields: Optional[BankStatementFields] = None

        friendly = {
            "cnic_front": "CNIC front",
            "cnic_back": "CNIC back",
            "payslip": "payslip",
            "bank_statement": "bank statement",
        }

        for label in EXPECTED_DOCS:
            path = documents.get(label)
            uploaded = path is not None and Path(path).exists()
            uploaded_map[label] = uploaded

            status = DocumentUploadStatus(
                document_label=label,
                uploaded=uploaded,
            )

            if not uploaded:
                upload_statuses.append(status)
                continue

            label_name = friendly.get(label, label)
            extraction = self.extraction.process(
                str(path),
                on_progress=on_progress,
                doc_label=label_name,
                expected_document_type=EXPECTED_CLASSIFICATION[label],
            )
            ocr_text = extraction.get("extracted_text") or ""
            iq = self.image_quality.assess(str(path), label, ocr_text)
            quality_results.append(iq)
            readable_map[label] = iq.readable

            status.classified_as = extraction.get("document_type")
            status.classification_confidence = extraction.get("confidence")
            status.extraction_ok = extraction.get("fields") is not None
            status.error = extraction.get("error")

            expected_type = EXPECTED_CLASSIFICATION[label]
            classified = extraction.get("document_type")
            if classified and classified != "unknown" and classified != expected_type:
                status.error = (
                    (status.error + "; " if status.error else "")
                    + f"Expected {expected_type}, classified as {classified}"
                )

            fields = extraction.get("fields")
            if fields:
                if label in ("cnic_front", "cnic_back"):
                    model = CNICFields(**fields)
                    if label == "cnic_front":
                        cnic_front_fields = model
                    else:
                        cnic_back_fields = model
                elif label == "payslip":
                    payslip_fields = PayslipFields(**fields)
                elif label == "bank_statement":
                    bank_fields = BankStatementFields(**fields)

            upload_statuses.append(status)

        _progress("validating", "Validating extracted fields against the submitted form…")
        sections = self.validation_engine.validate_all(
            form,
            cnic_front=cnic_front_fields,
            cnic_back=cnic_back_fields,
            payslip=payslip_fields,
            bank_statement=bank_fields,
            uploads=uploaded_map,
            image_quality_readable=readable_map,
        )

        _progress("report", "Building verification report…")
        report = self.report_generator.generate(
            form=form,
            sections=sections,
            uploaded_documents=upload_statuses,
            image_quality=quality_results,
        )
        logger.info(
            "Verification complete: %s (score=%.1f)",
            report.recommendation.value,
            report.overall_score,
        )
        _progress("complete", "AI analysis complete — parsing and LLM summary done.")
        return report

    def save_upload(self, filename: str, data: bytes) -> Path:
        """Persist an uploaded file under UPLOAD_DIR and return its path."""
        safe_name = Path(filename).name
        dest = config.UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
        dest.write_bytes(data)
        return dest

    def cleanup_files(self, paths: Dict[str, Optional[Path]]) -> None:
        for path in paths.values():
            if path and path.exists():
                try:
                    path.unlink()
                except OSError:
                    logger.warning("Could not delete temp upload %s", path)
