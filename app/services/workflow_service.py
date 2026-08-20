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
        "required_documents": [
            "account_opening_form",
            "payslip",
        ],
        "optional_documents": [
            "cnic",  # front only — CNIC back is not required
        ],
    },
}

DOCUMENT_TYPE_LABELS = {
    "cnic": "CNIC",
    "payslip": "Payslip",
    "account_opening_form": "Account Opening Form",
}

ACCOUNT_OPENING_KEYWORDS = [
    "first applicant",
    "account opening",
    "application form",
    "opening form",
    "please complete all section",
    "block capitals",
    "personal information",
    "forenames",
    "current residential address",
    "date of entry to this address",
    "country of residence for tax",
    "related tin",
    "green card",
    "residence in the usa",
    "mr/mrs/miss",
    "nationality",
    "post code",
    "postcode",
    "section 1",
    "section 2",
]

CNIC_KEYWORDS = [
    "national identity card",
    "identity card",
    "identity number",
    "nadra",
    "cnic",
    "republic of pakistan",
    "holder's signature",
    "date of issue",
    "date of expiry",
    "issue date",
    "expiry date",
]

PAYSLIP_KEYWORDS = [
    "payslip",
    "pay slip",
    "salary slip",
    "gross salary",
    "net pay",
    "net salary",
    "basic salary",
    "pay period",
    "earnings",
    "deduction",
    "overtime",
    "ytd",
    "year to date",
]

SEPARATOR_PHRASES = [
    "blank page",
    "this page is intentionally left blank",
    "intentionally left blank",
    "this page is blank",
    "page is intentionally blank",
]

WORKFLOW_SEQUENCE = ("account_opening_form", "payslip", "cnic")
MAYBE_BLANK_INK_RATIO = 0.08
SEPARATOR_TEXT_CHAR_LIMIT = 120


class WorkflowService:
    """Process multi-customer workflow PDFs using the single-document extraction pipeline."""

    def __init__(self) -> None:
        self.classifier = KeywordClassifier()
        self.ocr = TesseractOCRService()
        self.llm = get_llm_service(branch=True)
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

        self._ocr_and_mark_separators(rendered_pages)
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
                ink_ratio = self._ink_ratio(image_bytes)
                pages.append({
                    "page": idx,
                    "image_bytes": image_bytes,
                    "ink_ratio": ink_ratio,
                    "blank": ink_ratio < config.BLANK_PAGE_INK_RATIO_THRESHOLD,
                    "raw_text": "",
                })
        finally:
            doc.close()
        return pages

    def _ink_ratio(self, image_bytes: bytes) -> float:
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
            return dark_pixels / max(1, len(pixels))

    def _is_blank_page(self, image_bytes: bytes) -> bool:
        return self._ink_ratio(image_bytes) < config.BLANK_PAGE_INK_RATIO_THRESHOLD

    @staticmethod
    def _letters_only(text: str) -> str:
        return "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in (text or ""))

    def _is_separator_text(self, raw_text: str, ink_ratio: float) -> bool:
        if ink_ratio < config.BLANK_PAGE_INK_RATIO_THRESHOLD:
            return True
        letters = " ".join(self._letters_only(raw_text).split())
        lower = (raw_text or "").lower()
        if not letters:
            return ink_ratio < MAYBE_BLANK_INK_RATIO
        if any(phrase in lower for phrase in SEPARATOR_PHRASES):
            return len(letters) < SEPARATOR_TEXT_CHAR_LIMIT
        return len(letters) < 25 and ink_ratio < MAYBE_BLANK_INK_RATIO

    def _ocr_and_mark_separators(self, rendered_pages: List[Dict[str, Any]]) -> None:
        for page_data in rendered_pages:
            if page_data.get("blank"):
                page_data["raw_text"] = ""
                continue
            raw_text = self._ocr_page(page_data["image_bytes"], page_data["page"])
            page_data["raw_text"] = raw_text
            if self._is_separator_text(raw_text, float(page_data.get("ink_ratio") or 0)):
                page_data["blank"] = True
                self.logger.info(
                    "Treating page %s as a customer separator (ink=%.4f, text=%r)",
                    page_data["page"],
                    float(page_data.get("ink_ratio") or 0),
                    (raw_text or "")[:80],
                )

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
            raw_text = page_data.get("raw_text") or ""
            if not raw_text:
                raw_text = self._ocr_page(page_data["image_bytes"], page_number)
                page_data["raw_text"] = raw_text
            doc_type, confidence, scores = self._classify_page(raw_text)
            needs_review = confidence < config.WORKFLOW_CLASSIFICATION_CONFIDENCE_THRESHOLD
            documents[page_number] = {
                "page": page_number,
                "document_type": doc_type,
                "document_type_label": DOCUMENT_TYPE_LABELS.get(doc_type, doc_type),
                "confidence": confidence,
                "needs_review": needs_review,
                "raw_text": raw_text,
                "scores": scores,
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

    @staticmethod
    def _keyword_score(text_lower: str, keywords: List[str]) -> float:
        if not keywords:
            return 0.0
        matched = sum(1 for keyword in keywords if keyword in text_lower)
        if matched <= 0:
            return 0.0
        return round(min(1.0, matched / max(3, len(keywords) * 0.45)), 2)

    def _type_scores(self, raw_text: str) -> Dict[str, float]:
        text_lower = (raw_text or "").lower()
        return {
            "account_opening_form": self._keyword_score(text_lower, ACCOUNT_OPENING_KEYWORDS),
            "payslip": self._keyword_score(text_lower, PAYSLIP_KEYWORDS),
            "cnic": self._keyword_score(text_lower, CNIC_KEYWORDS),
        }

    def _classify_page(self, raw_text: str) -> tuple[str, float, Dict[str, float]]:
        text = (raw_text or "").strip()
        scores = self._type_scores(text)
        if not text or max(scores.values()) <= 0:
            classification = self.classifier.classify(text) if text else {
                "document_type": "unknown",
                "confidence": 0.0,
            }
            fallback_type = classification["document_type"]
            if fallback_type == "bank_statement":
                fallback_type = "account_opening_form"
            if fallback_type not in DOCUMENT_TYPE_LABELS:
                fallback_type = "unknown"
            scores[fallback_type] = max(
                scores.get(fallback_type, 0.0),
                float(classification.get("confidence") or 0.0),
            )
            return fallback_type, float(classification.get("confidence") or 0.0), scores

        best_type = max(scores, key=scores.get)
        return best_type, scores[best_type], scores

    def _assign_group_document_types(self, docs: List[Dict[str, Any]]) -> None:
        """Prefer distinctive scores, then the expected form → payslip → CNIC order."""
        if not docs:
            return

        scores_by_index = [doc.get("scores") or self._type_scores(doc.get("raw_text") or "") for doc in docs]
        assigned: Dict[int, str] = {}

        def best_index(doc_type: str, excluded: set[int]) -> tuple[Optional[int], float]:
            best_i: Optional[int] = None
            best_score = -1.0
            for index, score_map in enumerate(scores_by_index):
                if index in excluded:
                    continue
                value = float(score_map.get(doc_type) or 0.0)
                if value > best_score:
                    best_score = value
                    best_i = index
            return best_i, best_score

        form_index, form_score = best_index("account_opening_form", set())
        if len(docs) in {2, 3, 4} and (form_index is None or form_score < 0.2):
            form_index = 0
        if form_index is not None:
            assigned[form_index] = "account_opening_form"

        payslip_index, payslip_score = best_index("payslip", set(assigned))
        if len(docs) >= 2 and (payslip_index is None or payslip_score < 0.2):
            fallback = 1 if 1 not in assigned else payslip_index
            payslip_index = fallback
        if payslip_index is not None and payslip_index not in assigned:
            assigned[payslip_index] = "payslip"

        for index, doc in enumerate(docs):
            if index in assigned:
                continue
            cnic_score = float(scores_by_index[index].get("cnic") or 0.0)
            if cnic_score >= 0.1 or index >= 2:
                assigned[index] = "cnic"
            elif doc.get("document_type") in DOCUMENT_TYPE_LABELS:
                assigned[index] = doc["document_type"]
            else:
                assigned[index] = WORKFLOW_SEQUENCE[min(index, len(WORKFLOW_SEQUENCE) - 1)]

        for index, doc in enumerate(docs):
            new_type = assigned.get(index, doc.get("document_type") or "unknown")
            old_type = doc.get("document_type")
            flags = list((doc.get("summary") or {}).get("flags") or [])
            if new_type != old_type:
                flags.append("sequence_corrected")
            score = float((doc.get("scores") or {}).get(new_type) or 0.0)
            if new_type in {"account_opening_form", "payslip", "cnic"} and score < 0.2:
                score = max(score, 0.72)
                flags.append("sequence_assigned")
            doc["document_type"] = new_type
            doc["document_type_label"] = DOCUMENT_TYPE_LABELS.get(new_type, new_type)
            doc["confidence"] = max(float(doc.get("confidence") or 0.0), score)
            doc["needs_review"] = doc["confidence"] < config.WORKFLOW_CLASSIFICATION_CONFIDENCE_THRESHOLD
            summary = dict(doc.get("summary") or {})
            summary["flags"] = flags
            doc["summary"] = summary
            doc.pop("scores", None)

        types_present = {doc.get("document_type") for doc in docs}
        compact_pack = len(docs) in {2, 3, 4} and "account_opening_form" in types_present and "payslip" in types_present
        if compact_pack:
            for doc in docs:
                if doc.get("document_type") in DOCUMENT_TYPE_LABELS:
                    doc["confidence"] = max(float(doc.get("confidence") or 0.0), 0.75)
                    doc["needs_review"] = False

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

    def _validate_group_documents(
        self,
        docs: List[Dict[str, Any]],
        workflow_type: str = "account_opening",
    ) -> Dict[str, Any]:
        spec = EXPECTED_WORKFLOW_TYPES.get(workflow_type, {})
        required = set(spec.get("required_documents", spec.get("expected_documents", [])))
        optional = set(spec.get("optional_documents", []))
        allowed = required | optional

        page_types = [doc.get("document_type") for doc in docs]
        missing = [DOCUMENT_TYPE_LABELS[doc] for doc in required if doc not in page_types]
        unexpected = [
            doc.get("document_type_label") or doc.get("document_type", "unknown")
            for doc in docs
            if doc.get("document_type") not in allowed
        ]
        cnic_pages = sum(1 for doc_type in page_types if doc_type == "cnic")
        cross_checks = self._cross_document_checks(docs)
        cross_mismatch = any(not check.get("match", True) for check in cross_checks)
        needs_review = (
            any(doc.get("needs_review") for doc in docs)
            or bool(missing)
            or bool(unexpected)
            or cross_mismatch
        )
        validation_status = "COMPLETE" if not needs_review else "REVIEW_REQUIRED"
        validation_messages: List[str] = []
        if missing:
            validation_messages.append(f"Missing documents: {', '.join(missing)}.")
        if cnic_pages > 1:
            validation_messages.append(
                "Multiple CNIC pages detected; only CNIC front is used. "
                "CNIC back is not required for account opening workflow."
            )
        if unexpected:
            validation_messages.append(
                f"Unexpected document types detected: {', '.join(unexpected)}."
            )
        if cross_mismatch:
            validation_messages.append("Cross-document field mismatches detected.")
        if not missing and not unexpected and not cross_mismatch:
            validation_messages.append(
                "Account opening form and payslip present; personal details are taken from the form."
            )

        return {
            "status": validation_status,
            "messages": validation_messages,
            "cross_document_checks": cross_checks,
        }

    def _build_groups(self, groups: List[Dict[str, Any]], documents: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for group in groups:
            docs = [documents[page] for page in group["pages"] if page in documents]
            self._assign_group_document_types(docs)
            validation = self._validate_group_documents(docs)
            result.append(
                {
                    "customer_id": group["customer_id"],
                    "pages": docs,
                    "separator_page": group["separator_page"],
                    "validation": {
                        "status": validation["status"],
                        "messages": validation["messages"],
                    },
                    "cross_document_checks": validation["cross_document_checks"],
                }
            )
        return result

    def extract_saved_documents(
        self,
        documents: List[Any],
        *,
        workflow_type: str = "account_opening",
        on_progress: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run onboarding-style OCR + LLM extraction and ValidationEngine cross-checks."""
        from app.services.branch_workflow_pipeline import BranchWorkflowPipeline

        pipeline = BranchWorkflowPipeline()
        return pipeline.verify_entry(
            documents,
            workflow_type=workflow_type,
            on_progress=on_progress,
        )

    @staticmethod
    def infer_customer_name(documents: List[Dict[str, Any]]) -> str:
        for doc in documents:
            fields = doc.get("fields") or {}
            for key in ("name", "applicant_name", "employee_name", "full_name"):
                value = fields.get(key)
                if value and str(value).strip():
                    return str(value).strip()
        return ""

    def _cross_document_checks(self, docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not docs:
            return []

        checks: List[Dict[str, Any]] = []
        values: Dict[str, List[str]] = {}
        for doc in docs:
            fields = doc.get("fields") or {}
            raw_text = doc.get("extracted_text") or doc.get("raw_text") or ""
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
