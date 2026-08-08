"""Workflow PDF segmentation, classification, and deterministic processing."""

from __future__ import annotations

import io
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz
from PIL import Image

from app import config
from app.ocr_pipeline.document_extract import DOCUMENT_FIELD_KEYS
from app.logging_config import get_logger
from app.services.classifier import KeywordClassifier
from app.services.extraction_service import ExtractionPipeline
from app.services.llm_factory import get_llm_service
from app.services.ocr_service import TesseractOCRService
from app.utils.normalize import (
    extract_cnic_number,
    normalize_account_number,
    normalize_cnic,
    normalize_iban,
    normalize_text,
    names_match,
)

EXPECTED_WORKFLOW_TYPES = {
    "account_opening": {
        "label": "Account Opening Workflow",
        "expected_documents": [
            "cnic",
            "payslip",
            "account_opening_form",
        ],
    },
}

DOCUMENT_TYPE_LABELS = {
    "cnic": "CNIC",
    "payslip": "Payslip",
    "account_opening_form": "Account Opening Form",
}

ACCOUNT_OPENING_KEYWORDS = [
    "account opening",
    "application form",
    "customer name",
    "father name",
    "signature",
    "opening form",
    "branch code",
    "date of application",
    "account number",
    "balance",
    "nominee",
    "address",
]


class WorkflowService:
    """Process multi-customer workflow PDFs using the single-document extraction pipeline."""

    def __init__(self) -> None:
        self.classifier = KeywordClassifier()
        self.ocr = TesseractOCRService()
        self.llm = get_llm_service()
        self.pipeline = ExtractionPipeline(self.ocr, self.classifier, self.llm)
        self.logger = get_logger(__name__)

    def process_workflow(self, workflow_type: str, pdf_bytes: bytes) -> Dict[str, Any]:
        if workflow_type not in EXPECTED_WORKFLOW_TYPES:
            raise ValueError(f"Unsupported workflow type: {workflow_type}")

        rendered_pages = self._render_pdf_pages(pdf_bytes)
        total_pages = len(rendered_pages)
        if total_pages == 0:
            raise ValueError("Uploaded PDF contains no pages.")
        if total_pages > config.WORKFLOW_MAX_PAGE_COUNT:
            raise ValueError(
                f"PDF contains too many pages ({total_pages}). "
                f"Maximum supported is {config.WORKFLOW_MAX_PAGE_COUNT}."
            )

        segments = self._segment_pages(rendered_pages)
        if not segments["groups"]:
            raise ValueError("Workflow PDF contains only blank or separator pages.")

        documents = self._classify_pages(rendered_pages)
        groups = self._build_groups(segments["groups"], documents)
        status = "COMPLETE"
        for group in groups:
            if group["validation"]["status"] != "COMPLETE":
                status = "REVIEW_REQUIRED"
                break

        return {
            "workflow_id": self._generate_workflow_id(),
            "status": status,
            "workflow_phase": "classification",
            "workflow_type": workflow_type,
            "workflow_label": EXPECTED_WORKFLOW_TYPES[workflow_type]["label"],
            "total_pages": total_pages,
            "separator_pages": segments["separator_pages"],
            "customer_groups": groups,
        }

    def _render_pdf_pages(self, pdf_bytes: bytes) -> List[Dict[str, Any]]:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except RuntimeError as exc:
            raise ValueError(f"Unable to read PDF: {exc}") from exc

        pages: List[Dict[str, Any]] = []
        try:
            for idx, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=150, colorspace=fitz.csGRAY)
                image_bytes = pix.tobytes("png")
                pages.append({
                    "page": idx,
                    "image_bytes": image_bytes,
                    "blank": self._is_blank_page(image_bytes),
                })
        finally:
            doc.close()
        return pages

    def _is_blank_page(self, image_bytes: bytes) -> bool:
        with Image.open(io.BytesIO(image_bytes)) as img:
            image = img.convert("L")
            width, height = image.size
            crop_box = (
                int(width * 0.05),
                int(height * 0.05),
                int(width * 0.95),
                int(height * 0.95),
            )
            crop = image.crop(crop_box)
            pixels = list(crop.getdata())
            dark_pixels = sum(1 for value in pixels if value < 230)
            ink_ratio = dark_pixels / max(1, len(pixels))
            return ink_ratio < config.BLANK_PAGE_INK_RATIO_THRESHOLD

    def _segment_pages(self, rendered_pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        groups: List[Dict[str, Any]] = []
        separator_pages: List[int] = []
        current_pages: List[int] = []
        current_group_index = 0

        for page_data in rendered_pages:
            page_number = page_data["page"]
            if page_data["blank"]:
                if current_pages:
                    current_group_index += 1
                    groups.append(
                        {
                            "customer_id": f"CUSTOMER-{current_group_index:03d}",
                            "pages": current_pages,
                            "separator_page": page_number,
                        }
                    )
                    current_pages = []
                separator_pages.append(page_number)
                continue
            current_pages.append(page_number)

        if current_pages:
            current_group_index += 1
            groups.append(
                {
                    "customer_id": f"CUSTOMER-{current_group_index:03d}",
                    "pages": current_pages,
                    "separator_page": None,
                }
            )

        return {
            "total_pages": len(rendered_pages),
            "groups": groups,
            "separator_pages": separator_pages,
        }

    def _classify_pages(self, rendered_pages: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
        documents: Dict[int, Dict[str, Any]] = {}
        for page_data in rendered_pages:
            if page_data["blank"]:
                continue
            page_number = page_data["page"]
            raw_text = self._ocr_page(page_data["image_bytes"], page_number)
            doc_type, confidence = self._classify_page(raw_text)
            needs_review = confidence < config.WORKFLOW_CLASSIFICATION_CONFIDENCE_THRESHOLD
            documents[page_number] = {
                "page": page_number,
                "document_type": doc_type,
                "document_type_label": DOCUMENT_TYPE_LABELS.get(doc_type, doc_type),
                "confidence": confidence,
                "needs_review": needs_review,
                "raw_text": raw_text,
                "fields": {},
                "summary": {
                    "summary": "Page classified using OCR and keyword rules. LLM extraction will run when the group is queued.",
                    "key_fields": {},
                    "confidence": "low",
                    "flags": ["classification_only"],
                },
            }
        return documents

    def _ocr_page(self, image_bytes: bytes, page_number: int) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)

        try:
            return self.ocr.extract_text(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)

    def _classify_page(self, raw_text: str) -> tuple[str, float]:
        text = raw_text.strip()
        if not text:
            return "unknown", 0.0

        classification = self.classifier.classify(text)
        doc_type = classification["document_type"]
        confidence = classification["confidence"]
        text_lower = text.lower()

        if doc_type == "unknown" or doc_type == "bank_statement":
            if any(keyword in text_lower for keyword in ACCOUNT_OPENING_KEYWORDS):
                return "account_opening_form", max(confidence, 0.52)

        if doc_type not in DOCUMENT_TYPE_LABELS:
            return "unknown", confidence

        return doc_type, confidence

    def _extract_page(self, image_bytes: bytes, document_type: str, page_number: int) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)

        try:
            if document_type == "unknown":
                extracted_text = self.ocr.extract_text(str(tmp_path))
                return {
                    "extracted_text": extracted_text,
                    "fields": {},
                    "summary": {
                        "summary": "Document type could not be classified. OCR text extracted.",
                        "key_fields": {},
                        "confidence": "low",
                        "flags": ["classification_unknown"],
                    },
                }

            result = self.pipeline.process(
                str(tmp_path),
                doc_label=f"page-{page_number}.png",
                expected_document_type=document_type,
            )

            if result.get("error"):
                self.logger.warning(
                    "Workflow LLM extraction failed for page %d (%s): %s",
                    page_number,
                    document_type,
                    result["error"],
                )
                fallback = self._extract_structured_document(image_bytes, document_type)
                fallback["summary"]["summary"] = (
                    f"Workflow LLM extraction failed; OCR-only fallback used. Error: {result['error']}"
                )
                fallback["summary"]["flags"] = ["llm_fallback"]
                return fallback

            fields = result.get("fields") or {}
            extracted_text = result.get("extracted_text", "")
            summary = {
                "summary": "Structured fields extracted via LLM.",
                "key_fields": {k: v for k, v in fields.items() if v},
                "confidence": "high" if fields else "medium",
                "flags": [],
            }
            return {
                "extracted_text": extracted_text,
                "fields": fields,
                "summary": summary,
            }
        finally:
            tmp_path.unlink(missing_ok=True)

    def _extract_structured_document(self, image_bytes: bytes, document_type: str) -> Dict[str, Any]:
        # Workflow fallback extraction: OCR-only when LLM extraction is unavailable or fails.
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = Path(tmp.name)

        try:
            raw_text = self.ocr.extract_text(str(tmp_path))
            # Populate minimal structured fields from OCR heuristics.
            fields: Dict[str, Any] = {k: "" for k in DOCUMENT_FIELD_KEYS.get(document_type, [])}

            # Try to extract CNIC number or account identifiers from raw text when present
            if document_type in {"cnic", "account_opening_form"}:
                cnic = extract_cnic_number(raw_text)
                if cnic:
                    # Map probable key names to the canonical field if present
                    for candidate in ("cnic_number", "id_number", "identification_number"):
                        if candidate in fields:
                            fields[candidate] = cnic
                            break
                    else:
                        # fallback to first available key
                        if fields:
                            first = next(iter(fields))
                            fields[first] = cnic

            summary = {
                "summary": f"{DOCUMENT_TYPE_LABELS.get(document_type, document_type)} OCR text extracted (LLM skipped for workflow).",
                "key_fields": {k: v for k, v in fields.items() if v},
                "confidence": "medium" if any(fields.values()) else "low",
                "flags": [],
            }

            self.logger.info("Workflow OCR-only extraction for %s: filled=%d", document_type, sum(1 for v in fields.values() if v))

            return {
                "extracted_text": raw_text,
                "fields": fields,
                "summary": summary,
            }
        finally:
            tmp_path.unlink(missing_ok=True)

    def _build_groups(self, groups: List[Dict[str, Any]], documents: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        expected = set(EXPECTED_WORKFLOW_TYPES["account_opening"]["expected_documents"])

        for group in groups:
            docs = [documents[page] for page in group["pages"] if page in documents]
            page_types = [doc["document_type"] for doc in docs]
            missing = [DOCUMENT_TYPE_LABELS[doc] for doc in expected if doc not in page_types]
            unexpected = [doc["document_type_label"] for doc in docs if doc["document_type"] not in expected]
            needs_review = any(doc["needs_review"] for doc in docs) or bool(missing) or bool(unexpected)
            validation_status = "COMPLETE" if not needs_review else "REVIEW_REQUIRED"
            validation_messages = []
            if missing:
                validation_messages.append(f"Missing documents: {', '.join(missing)}.")
            if unexpected:
                validation_messages.append(
                    f"Unexpected document types detected: {', '.join(unexpected)}."
                )
            if not missing and not unexpected:
                validation_messages.append("Expected documents detected.")
            result.append(
                {
                    "customer_id": group["customer_id"],
                    "pages": docs,
                    "separator_page": group["separator_page"],
                    "validation": {
                        "status": validation_status,
                        "messages": validation_messages,
                    },
                    "cross_document_checks": self._cross_document_checks(docs),
                }
            )
        return result

    def _cross_document_checks(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not docs:
            return []

        checks: List[Dict[str, Any]] = []
        values: Dict[str, List[str]] = {}
        for doc in docs:
            fields = doc.get("fields") or {}
            raw_text = doc.get("extracted_text") or ""
            values.setdefault("cnic", [])
            if fields.get("cnic_number"):
                values["cnic"].append(fields["cnic_number"])
            else:
                cnic = extract_cnic_number(raw_text)
                if cnic:
                    values["cnic"].append(cnic)

            values.setdefault("name", [])
            for candidate in (fields.get("name"), fields.get("employee_name"), fields.get("applicant_name")):
                if candidate:
                    values["name"].append(str(candidate))
                    break

        if values.get("cnic"):
            normalized = [normalize_cnic(v) for v in values["cnic"] if v]
            unique = set(normalized)
            checks.append(
                {
                    "field": "cnic",
                    "match": len(unique) <= 1,
                    "values": list(unique),
                }
            )
        if values.get("name"):
            names = [normalize_text(v) for v in values["name"] if v]
            if names:
                reference = names[0]
                matches = [names_match(reference, other, config.NAME_SIMILARITY_THRESHOLD) for other in names[1:]]
                checks.append(
                    {
                        "field": "name",
                        "match": all(match for match, _ in matches) if matches else True,
                        "details": [
                            {"value": other, "match": match, "score": score}
                            for (match, score), other in zip(matches, names[1:])
                        ],
                    }
                )
        return checks

    def _generate_workflow_id(self) -> str:
        return f"WF-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
