"""Bank-staff verification report generator."""

from __future__ import annotations

from typing import Dict, List, Optional

from app.logging_config import get_logger
from app.schemas.application import ApplicationForm
from app.schemas.common import CheckResult, Recommendation
from app.schemas.verification import (
    DocumentUploadStatus,
    FieldComparison,
    ImageQualityResult,
    SectionResult,
    VerificationReport,
)

logger = get_logger(__name__)


class ReportGenerator:
    """Build a staff-facing verification report (no OCR text)."""

    CRITICAL_FIELD_HINTS = {
        "cnic number",
        "cnic front uploaded",
        "cnic back uploaded",
        "cnic not expired",
        "payslip uploaded",
        "payslip readable",
        "bank statement uploaded",
        "statement readable",
        "iban",
        "account number",
        "full name",
        "name",
        "father name",
        "date of birth",
        "employee name",
        "account holder",
    }

    def generate(
        self,
        form: ApplicationForm,
        sections: Dict[str, SectionResult],
        uploaded_documents: List[DocumentUploadStatus],
        image_quality: List[ImageQualityResult],
    ) -> VerificationReport:
        all_comparisons = self._flatten(sections)
        score = self._score(all_comparisons, image_quality)
        missing = self._missing(uploaded_documents, all_comparisons)
        warnings = self._warnings(all_comparisons, image_quality)
        recommendation, detail = self._recommend(all_comparisons, missing, image_quality)
        summary = self._summary(
            recommendation, score, missing, warnings, sections, image_quality
        )

        status_label = {
            Recommendation.APPROVED: "Verified",
            Recommendation.REVIEW_REQUIRED: "Review Required",
            Recommendation.REJECTED: "Rejected",
        }[recommendation]

        return VerificationReport(
            application_status=status_label,
            overall_score=score,
            recommendation=recommendation,
            summary=summary,
            application_summary={
                "full_name": form.personal.full_name,
                "age": form.personal.age,
                "cnic_number": form.cnic.cnic_number,
                "cnic_full_name": form.cnic.full_name,
                "email": form.personal.email,
                "mobile_number": form.personal.mobile_number,
                "gender": form.cnic.gender,
                "country_to_stay": form.cnic.country_to_stay,
                "company_name": form.employment.company_name,
                "designation": form.employment.designation,
            },
            uploaded_documents=uploaded_documents,
            image_quality=image_quality,
            customer_information_validation=sections["customer_information_validation"],
            cnic_validation=sections["cnic_validation"],
            payslip_validation=sections["payslip_validation"],
            bank_statement_validation=sections["bank_statement_validation"],
            cross_validation=sections["cross_validation"],
            missing_information=missing,
            warnings=warnings,
            recommendation_detail=detail,
        )

    def _flatten(self, sections: Dict[str, SectionResult]) -> List[FieldComparison]:
        rows: List[FieldComparison] = []
        for section in sections.values():
            rows.extend(section.comparisons)
        return rows

    def _score(
        self,
        comparisons: List[FieldComparison],
        image_quality: Optional[List[ImageQualityResult]] = None,
    ) -> float:
        if image_quality:
            for iq in image_quality:
                for c in iq.checks:
                    if (
                        c.check in {"metadata_integrity", "software_editing"}
                        and c.result == CheckResult.FAIL
                    ):
                        return 0.0
        if not comparisons:
            return 0.0
        weights = {CheckResult.PASS: 1.0, CheckResult.WARNING: 0.5, CheckResult.FAIL: 0.0}
        total = sum(weights[c.result] for c in comparisons)
        return round(100.0 * total / len(comparisons), 1)

    def _missing(
        self,
        uploads: List[DocumentUploadStatus],
        comparisons: List[FieldComparison],
    ) -> List[str]:
        missing: List[str] = []
        for doc in uploads:
            if not doc.uploaded:
                missing.append(f"Missing mandatory document: {doc.document_label}")
            elif not doc.extraction_ok:
                missing.append(
                    f"Could not extract fields from {doc.document_label}"
                    + (f" ({doc.error})" if doc.error else "")
                )
        for c in comparisons:
            if c.result == CheckResult.FAIL and not c.document_value:
                msg = c.message or f"{c.field} missing from document"
                if msg not in missing:
                    missing.append(msg)
        return missing

    def _warnings(
        self,
        comparisons: List[FieldComparison],
        image_quality: List[ImageQualityResult],
    ) -> List[str]:
        warnings: List[str] = []
        for c in comparisons:
            if c.result == CheckResult.WARNING:
                warnings.append(c.message or f"Warning on {c.field}")
        for iq in image_quality:
            if iq.overall == CheckResult.WARNING:
                warnings.append(f"Image quality warning for {iq.document_label}")
            elif iq.overall == CheckResult.FAIL:
                warnings.append(f"Image quality check failed for {iq.document_label}")
            for check in iq.checks:
                if check.result in (CheckResult.WARNING, CheckResult.FAIL) and check.detail:
                    warnings.append(f"{iq.document_label}: {check.detail}")
        # de-dupe preserving order
        seen = set()
        unique: List[str] = []
        for w in warnings:
            if w not in seen:
                seen.add(w)
                unique.append(w)
        return unique

    def _recommend(
        self,
        comparisons: List[FieldComparison],
        missing: List[str],
        image_quality: List[ImageQualityResult],
    ) -> tuple[Recommendation, str]:
        critical_fails = [
            c
            for c in comparisons
            if c.result == CheckResult.FAIL
            and (c.is_critical or c.field.lower() in self.CRITICAL_FIELD_HINTS)
        ]
        unreadable = [iq for iq in image_quality if not iq.readable]
        tampered_docs = [
            iq.document_label
            for iq in image_quality
            for c in iq.checks
            if c.check in {"metadata_integrity", "software_editing"}
            and c.result == CheckResult.FAIL
        ]
        expired = any(
            c.field.lower() == "cnic not expired" and c.result == CheckResult.FAIL
            for c in comparisons
        )
        cnic_mismatch = any(
            c.field.lower() == "cnic number" and c.result == CheckResult.FAIL
            for c in comparisons
        )
        missing_docs = any("Missing mandatory document" in m for m in missing)

        if (
            expired
            or cnic_mismatch
            or missing_docs
            or unreadable
            or tampered_docs
            or critical_fails
        ):
            reasons = []
            if tampered_docs:
                reasons.append(
                    "Digital editing / software tampering detected on: "
                    + ", ".join(tampered_docs)
                )
            if expired:
                reasons.append("CNIC is expired")
            if cnic_mismatch:
                reasons.append("CNIC number mismatch")
            if missing_docs:
                reasons.append("Mandatory document missing")
            if unreadable:
                reasons.append(
                    "Unreadable document(s): "
                    + ", ".join(iq.document_label for iq in unreadable)
                )
            if critical_fails and not reasons:
                reasons.append(
                    f"{len(critical_fails)} critical validation failure(s)"
                )
            return (
                Recommendation.REJECTED,
                "Application rejected due to: " + "; ".join(reasons) + ".",
            )

        warnings = [c for c in comparisons if c.result == CheckResult.WARNING]
        soft_fails = [c for c in comparisons if c.result == CheckResult.FAIL]
        if warnings or soft_fails:
            return (
                Recommendation.REVIEW_REQUIRED,
                "Minor mismatches or warnings require manual review before approval.",
            )

        return (
            Recommendation.APPROVED,
            "All critical validations passed. Application recommended for approval.",
        )

    def _summary(
        self,
        recommendation: Recommendation,
        score: float,
        missing: List[str],
        warnings: List[str],
        sections: Dict[str, SectionResult],
        image_quality: List[ImageQualityResult],
    ) -> List[str]:
        lines: List[str] = []
        mandatory_ok = not any("Missing mandatory document" in m for m in missing)
        lines.append(
            "All mandatory documents were uploaded."
            if mandatory_ok
            else "One or more mandatory documents are missing."
        )

        cust = sections["customer_information_validation"].status
        if cust == CheckResult.PASS:
            lines.append("Customer information matches the uploaded documents.")
        elif cust == CheckResult.WARNING:
            lines.append("Customer information mostly matches with minor discrepancies.")
        else:
            lines.append("Customer information does not fully match the uploaded documents.")

        cnic = sections["cnic_validation"]
        expiry = next(
            (c for c in cnic.comparisons if c.field.lower() == "cnic not expired"),
            None,
        )
        if expiry and expiry.result == CheckResult.PASS:
            lines.append("CNIC is valid.")
        elif expiry and expiry.result == CheckResult.FAIL:
            lines.append("CNIC is expired.")
        else:
            lines.append("CNIC validity could not be fully confirmed.")

        tampered_docs = [
            iq.document_label
            for iq in image_quality
            for c in iq.checks
            if c.check in {"metadata_integrity", "software_editing"}
            and c.result == CheckResult.FAIL
        ]
        if tampered_docs:
            lines.append(
                "SECURITY WARNING: Image editing software metadata detected on: "
                + ", ".join(tampered_docs)
                + "."
            )

        if not warnings and recommendation == Recommendation.APPROVED:
            lines.append("No major discrepancies detected.")
        elif warnings:
            lines.append(f"{len(warnings)} warning(s) noted for staff review.")

        iq_fails = [iq for iq in image_quality if iq.overall == CheckResult.FAIL]
        if iq_fails and not tampered_docs:
            lines.append(
                "Image quality issues detected on: "
                + ", ".join(iq.document_label for iq in iq_fails)
                + "."
            )

        lines.append(f"Overall verification score: {score}%.")
        return lines
