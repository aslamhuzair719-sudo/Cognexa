"""Branch-upload account opening workflow — same OCR/LLM/validation stack as customer onboarding."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.logging_config import get_logger
from app.prompts.manager import PromptManager
from app.schemas.application import ApplicationForm, CnicInfo, EmploymentInfo, PersonalInfo
from app.schemas.cnic import CNICFields
from app.schemas.common import Recommendation
from app.schemas.payslip import PayslipFields
from app.schemas.verification import DocumentUploadStatus
from app.services.branch_entry_storage import resolve_branch_entry_path
from app.services.classifier import KeywordClassifier
from app.services.extraction_service import ExtractionPipeline
from app.services.image_quality import ImageQualityService
from app.services.llm_factory import get_llm_service
from app.services.ocr_service import TesseractOCRService
from app.services.report_generator import ReportGenerator
from app.services.validation_engine import ValidationEngine
from app.services.workflow_service import DOCUMENT_TYPE_LABELS

logger = get_logger(__name__)

ProgressCb = Optional[Callable[[str, str], None]]

# Workflow page type → validation upload slot (customer onboarding uses these keys)
WORKFLOW_UPLOAD_KEYS = {
    "cnic": "cnic_front",
    "payslip": "payslip",
    "account_opening_form": "account_opening_form",
}


class BranchWorkflowPipeline:
    """OCR → LLM extract → cross-validate, mirroring VerificationPipeline for branch uploads."""

    def __init__(self) -> None:
        self.ocr_service = TesseractOCRService()
        self.classifier = KeywordClassifier()
        self.llm_service = get_llm_service(branch=True)
        self.extraction = ExtractionPipeline(
            self.ocr_service,
            self.classifier,
            self.llm_service,
            PromptManager(),
        )
        self.image_quality = ImageQualityService()
        self.validation_engine = ValidationEngine()
        self.report_generator = ReportGenerator()

    def verify_entry(
        self,
        documents: List[Any],
        *,
        workflow_type: str = "account_opening",
        on_progress: ProgressCb = None,
    ) -> Dict[str, Any]:
        def _progress(stage: str, message: str) -> None:
            if on_progress:
                on_progress(stage, message)

        _progress("starting", "Cognexa AI workflow starting — OCR and LLM extraction…")

        upload_statuses: List[DocumentUploadStatus] = []
        quality_results = []
        readable_map: Dict[str, bool] = {}
        uploaded_map: Dict[str, bool] = {
            "cnic_front": False,
            "cnic_back": False,
            "payslip": False,
            "bank_statement": False,
        }
        cnic_front_fields: Optional[CNICFields] = None
        payslip_fields: Optional[PayslipFields] = None
        form_fields: Dict[str, Any] = {}
        cnic_page_count = 0
        extractions: Dict[str, Dict[str, Any]] = {}

        ordered_docs = sorted(
            documents,
            key=lambda doc: 0 if getattr(doc, "document_type", None) == "account_opening_form" else 1,
        )

        for index, doc in enumerate(ordered_docs, start=1):
            doc_type = getattr(doc, "document_type", None) or "unknown"
            label = DOCUMENT_TYPE_LABELS.get(doc_type, doc_type)
            path = resolve_branch_entry_path(doc.file_path)
            expected = doc_type if doc_type in DOCUMENT_TYPE_LABELS else None
            if doc_type == "cnic":
                cnic_page_count += 1
                if cnic_page_count > 1:
                    _progress(
                        "ocr",
                        f"Skipping CNIC back page {index}/{len(documents)} "
                        "(not required for account opening workflow)…",
                    )
                    extraction = self.extraction.process(
                        str(path),
                        on_progress=on_progress,
                        doc_label=f"{label} (archived only)",
                        expected_document_type=expected,
                    )
                    extractions[str(getattr(doc, "id", index))] = extraction
                    continue
                upload_key = "cnic_front"
            else:
                upload_key = WORKFLOW_UPLOAD_KEYS.get(doc_type, doc_type)

            _progress("ocr", f"OCR parsing {index}/{len(documents)}: {label}…")

            extraction = self.extraction.process(
                str(path),
                on_progress=on_progress,
                doc_label=label,
                expected_document_type=expected,
            )

            ocr_text = extraction.get("extracted_text") or ""
            iq = self.image_quality.assess(str(path), upload_key, ocr_text)
            quality_results.append(iq)
            readable_map[upload_key] = iq.readable
            if upload_key in uploaded_map:
                uploaded_map[upload_key] = True

            status = DocumentUploadStatus(
                document_label=upload_key,
                uploaded=True,
                classified_as=extraction.get("document_type"),
                classification_confidence=extraction.get("confidence"),
                extraction_ok=extraction.get("fields") is not None,
                error=extraction.get("error"),
            )
            upload_statuses.append(status)
            extractions[str(getattr(doc, "id", index))] = extraction

            fields = extraction.get("fields")
            if fields and doc_type == "cnic":
                cnic_front_fields = CNICFields(**fields)
            elif fields and doc_type == "payslip":
                payslip_fields = PayslipFields(**fields)
            elif fields and doc_type == "account_opening_form":
                form_fields = fields

            _progress(
                "llm",
                f"LLM extraction complete for {label}."
                if fields
                else f"LLM extraction returned no fields for {label}.",
            )

        merged_cnic = cnic_front_fields
        reference_form = self._build_reference_form(form_fields, merged_cnic, payslip_fields)

        _progress("validating", "Cross-validating extracted fields across documents (LLM comparison)…")
        sections = self.validation_engine.validate_all(
            reference_form,
            cnic_front=cnic_front_fields,
            cnic_back=None,
            payslip=payslip_fields,
            bank_statement=None,
            uploads=uploaded_map,
            image_quality_readable=readable_map,
            workflow_profile="branch_account_opening",
        )

        _progress("report", "Building verification report…")
        report = self.report_generator.generate(
            form=reference_form,
            sections=sections,
            uploaded_documents=upload_statuses,
            image_quality=quality_results,
        )

        cross_checks = self._cross_checks_from_sections(sections)
        validation_status = (
            "COMPLETE"
            if report.recommendation == Recommendation.APPROVED
            else "REVIEW_REQUIRED"
        )

        enriched_docs = []
        for index, doc in enumerate(ordered_docs, start=1):
            doc_type = getattr(doc, "document_type", None) or "unknown"
            extraction = extractions.get(str(getattr(doc, "id", index)), {})
            fields = extraction.get("fields") or {}
            enriched_docs.append(
                {
                    "document_id": str(getattr(doc, "id", "")),
                    "page": index,
                    "document_type": doc_type,
                    "document_type_label": DOCUMENT_TYPE_LABELS.get(doc_type, doc_type),
                    "confidence": float(extraction.get("confidence") or 0.0),
                    "fields": fields,
                    "extracted_text": extraction.get("extracted_text") or "",
                    "summary": {
                        "summary": "OCR + LLM extraction complete."
                        if fields
                        else (extraction.get("error") or "Extraction incomplete."),
                        "key_fields": {k: v for k, v in fields.items() if v},
                        "confidence": "high" if fields else "low",
                        "flags": [],
                    },
                    "error": extraction.get("error"),
                }
            )

        _progress("complete", "Workflow OCR, LLM extraction, and cross-validation complete.")

        return {
            "documents": enriched_docs,
            "validation": {
                "status": validation_status,
                "messages": report.summary[:6],
            },
            "cross_document_checks": cross_checks,
            "report": report.model_dump(mode="json"),
            "sections": {
                key: section.model_dump(mode="json")
                for key, section in sections.items()
            },
        }

    @staticmethod
    def _pick(*values: Any, default: str = "") -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text and text.lower() != "null":
                return text
        return default

    def _build_reference_form(
        self,
        form_fields: Dict[str, Any],
        cnic: Optional[CNICFields],
        payslip: Optional[PayslipFields],
    ) -> ApplicationForm:
        """Build reference application from account opening form; CNIC/payslip fill gaps only."""
        ff = form_fields or {}
        cf = cnic.model_dump() if cnic else {}
        pf = payslip.model_dump() if payslip else {}

        full_name = self._pick(
            ff.get("applicant_name"),
            cf.get("name"),
            pf.get("employee_name"),
            default="Unknown Applicant",
        )
        age = self._pick(ff.get("age"), default="N/A")
        email = self._pick(ff.get("email"), pf.get("email"), default="workflow@example.com")
        mobile = self._pick(ff.get("mobile_number"), pf.get("phone"), default="03000000000")

        father_name = self._pick(ff.get("father_name"), cf.get("father_name"), default=full_name)
        cnic_number = self._pick(ff.get("cnic_number"), cf.get("cnic_number"), default="00000-0000000-0")
        dob = self._pick(ff.get("date_of_birth"), cf.get("date_of_birth"), default="01.01.1990")
        issue_date = self._pick(cf.get("issue_date"), default="01.01.2020")
        expiry_date = self._pick(cf.get("expiry_date"), default="01.01.2030")
        gender = self._pick(ff.get("gender"), cf.get("gender"), default="M")
        country = self._pick(ff.get("country_to_stay"), cf.get("country_to_stay"), default="Pakistan")

        company = self._pick(ff.get("company_name"), pf.get("company_name"), default="N/A")
        designation = self._pick(ff.get("designation"), pf.get("designation"), default="N/A")
        income = self._pick(
            ff.get("monthly_income"),
            pf.get("gross_salary"),
            pf.get("net_pay"),
            default="0",
        )
        employee_id = self._pick(ff.get("employee_id"), pf.get("employee_id"), default="N/A")

        return ApplicationForm(
            personal=PersonalInfo(
                full_name=full_name,
                age=age,
                email=email,
                mobile_number=mobile,
            ),
            cnic=CnicInfo(
                full_name=full_name,
                father_name=father_name,
                cnic_number=cnic_number,
                date_of_birth=dob,
                issue_date=issue_date,
                expiry_date=expiry_date,
                country_to_stay=country,
                gender=gender,
            ),
            employment=EmploymentInfo(
                company_name=company,
                designation=designation,
                monthly_income=income,
                employee_id=employee_id,
            ),
        )

    @staticmethod
    def _cross_checks_from_sections(sections: Dict[str, Any]) -> List[Dict[str, Any]]:
        cross = sections.get("cross_validation")
        if not cross:
            return []
        checks = []
        for comp in getattr(cross, "comparisons", []) or []:
            result = str(getattr(comp, "result", "")).upper()
            checks.append(
                {
                    "field": getattr(comp, "field", ""),
                    "match": result == "PASS",
                    "customer_value": getattr(comp, "customer_value", None),
                    "document_value": getattr(comp, "document_value", None),
                    "message": getattr(comp, "message", None),
                }
            )
        return checks
