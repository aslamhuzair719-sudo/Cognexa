"""Cross-validation engine: compare application form vs extracted document fields."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from app import config
from app.logging_config import get_logger
from app.schemas.application import ApplicationForm
from app.schemas.bank_statement import BankStatementFields
from app.schemas.cnic import CNICFields
from app.schemas.common import CheckResult
from app.schemas.payslip import PayslipFields
from app.schemas.verification import FieldComparison, SectionResult
from app.utils.normalize import (
    dates_equal,
    names_match,
    normalize_account_number,
    normalize_cnic,
    normalize_iban,
    normalize_text,
    parse_amount,
    parse_date,
)

logger = get_logger(__name__)


def _normalize_gender(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw or raw.lower() in {"null", "none", "n/a", "na", "-"}:
        return ""
    # Preserve single-letter codes before punctuation stripping.
    if raw.upper() in {"M", "F", "O", "X"}:
        return raw.lower()
    text = normalize_text(raw)
    if not text:
        return ""
    if text in {"m", "male", "man"}:
        return "m"
    if text in {"f", "female", "woman"}:
        return "f"
    if text in {"o", "other", "x"}:
        return "o"
    # OCR sometimes returns "m." or "gender m"
    if re.search(r"\bm\b", text):
        return "m"
    if re.search(r"\bf\b", text):
        return "f"
    return text


class ValidationEngine:
    """Compares customer form data against extracted document fields.

    Every comparison returns PASS / FAIL / WARNING.
    """

    def __init__(
        self,
        name_threshold: Optional[float] = None,
        salary_tolerance_percent: Optional[float] = None,
    ) -> None:
        self.name_threshold = name_threshold or config.NAME_SIMILARITY_THRESHOLD
        self.salary_tolerance = salary_tolerance_percent or config.SALARY_TOLERANCE_PERCENT

    def validate_all(
        self,
        form: ApplicationForm,
        *,
        cnic_front: Optional[CNICFields] = None,
        cnic_back: Optional[CNICFields] = None,
        payslip: Optional[PayslipFields] = None,
        bank_statement: Optional[BankStatementFields] = None,
        uploads: Optional[Dict[str, bool]] = None,
        image_quality_readable: Optional[Dict[str, bool]] = None,
        workflow_profile: Optional[str] = None,
    ) -> Dict[str, SectionResult]:
        uploads = uploads or {}
        image_quality_readable = image_quality_readable or {}

        cnic_merged = self._merge_cnic(cnic_front, cnic_back)

        customer = self._customer_info_section(form, cnic_merged, payslip, bank_statement)
        cnic_section = self._cnic_section(
            form,
            cnic_merged,
            uploads,
            image_quality_readable,
            workflow_profile=workflow_profile,
        )
        payslip_section = self._payslip_section(form, payslip, uploads, image_quality_readable)
        if workflow_profile == "branch_account_opening":
            bank_section = self._workflow_skipped_section(
                "Bank Statement Validation",
                "Bank statement is not required for branch account opening workflow.",
            )
        else:
            bank_section = self._bank_section(form, bank_statement, uploads, image_quality_readable)
        cross = self._cross_section(form, cnic_merged, payslip, bank_statement)

        return {
            "customer_information_validation": customer,
            "cnic_validation": cnic_section,
            "payslip_validation": payslip_section,
            "bank_statement_validation": bank_section,
            "cross_validation": cross,
        }

    def _merge_cnic(
        self,
        front: Optional[CNICFields],
        back: Optional[CNICFields],
    ) -> Optional[CNICFields]:
        if not front and not back:
            return None
        if front and not back:
            return front
        if back and not front:
            return back
        data: Dict[str, Any] = {}
        for field in CNICFields.model_fields:
            fv = getattr(front, field) if front else None
            bv = getattr(back, field) if back else None
            data[field] = fv or bv
        return CNICFields(**data)

    # ---- section builders -------------------------------------------------

    def _customer_info_section(
        self,
        form: ApplicationForm,
        cnic: Optional[CNICFields],
        payslip: Optional[PayslipFields],
        bank: Optional[BankStatementFields],
    ) -> SectionResult:
        comparisons: List[FieldComparison] = []

        # Personal full name vs CNIC form name (same applicant)
        comparisons.append(
            self._compare_name(
                "Personal Name vs CNIC Form Name",
                form.personal.full_name,
                form.cnic.full_name,
                "Application Form",
                critical=False,
            )
        )

        if cnic:
            comparisons.append(
                self._compare_name(
                    "Full Name",
                    form.cnic.full_name,
                    cnic.name,
                    "CNIC",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_name(
                    "Father Name",
                    form.cnic.father_name,
                    cnic.father_name,
                    "CNIC",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_cnic_number(
                    form.cnic.cnic_number, cnic.cnic_number, "CNIC"
                )
            )
            comparisons.append(
                self._compare_dates(
                    "Date of Birth",
                    form.cnic.date_of_birth,
                    cnic.date_of_birth,
                    "CNIC",
                    critical=True,
                )
            )
        else:
            comparisons.append(
                FieldComparison(
                    field="CNIC Data Available",
                    customer_value="Expected",
                    document_value=None,
                    document_source="CNIC",
                    result=CheckResult.FAIL,
                    is_critical=True,
                    message="No CNIC fields extracted",
                )
            )

        if payslip:
            comparisons.append(
                self._compare_name(
                    "Employee Name vs Customer Name",
                    form.personal.full_name,
                    payslip.employee_name,
                    "Payslip",
                    critical=True,
                )
            )
        if bank:
            comparisons.append(
                self._compare_name(
                    "Account Holder vs Customer Name",
                    form.personal.full_name,
                    bank.account_holder,
                    "Bank Statement",
                    critical=True,
                )
            )

        return self._section("Customer Information Validation", comparisons)

    def _cnic_section(
        self,
        form: ApplicationForm,
        cnic: Optional[CNICFields],
        uploads: Dict[str, bool],
        readable: Dict[str, bool],
        workflow_profile: Optional[str] = None,
    ) -> SectionResult:
        comparisons: List[FieldComparison] = []

        front_up = uploads.get("cnic_front", False)
        back_up = uploads.get("cnic_back", False)
        branch_workflow = workflow_profile == "branch_account_opening"
        comparisons.append(
            FieldComparison(
                field="CNIC Front Uploaded",
                customer_value="Optional" if branch_workflow else "Required",
                document_value="Uploaded" if front_up else "Missing",
                document_source="Upload",
                result=CheckResult.PASS
                if front_up
                else (CheckResult.WARNING if branch_workflow else CheckResult.FAIL),
                is_critical=not branch_workflow,
                message="Optional for account opening workflow; form holds personal details"
                if branch_workflow and not front_up
                else None,
            )
        )
        if not branch_workflow:
            comparisons.append(
                FieldComparison(
                    field="CNIC Back Uploaded",
                    customer_value="Required",
                    document_value="Uploaded" if back_up else "Missing",
                    document_source="Upload",
                    result=CheckResult.PASS if back_up else CheckResult.FAIL,
                    is_critical=True,
                )
            )

        if cnic:
            comparisons.append(
                self._compare_name(
                    "Name", form.cnic.full_name, cnic.name, "CNIC", critical=True
                )
            )
            comparisons.append(
                self._compare_name(
                    "Father Name",
                    form.cnic.father_name,
                    cnic.father_name,
                    "CNIC",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_cnic_number(
                    form.cnic.cnic_number, cnic.cnic_number, "CNIC"
                )
            )
            comparisons.append(
                self._compare_dates(
                    "Date of Birth",
                    form.cnic.date_of_birth,
                    cnic.date_of_birth,
                    "CNIC",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_dates(
                    "Issue Date",
                    form.cnic.issue_date,
                    cnic.issue_date,
                    "CNIC",
                    critical=False,
                )
            )
            comparisons.append(
                self._compare_dates(
                    "Expiry Date",
                    form.cnic.expiry_date,
                    cnic.expiry_date,
                    "CNIC",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_gender(form.cnic.gender, cnic.gender)
            )
            comparisons.append(
                FieldComparison(
                    field="Country to Stay",
                    customer_value=form.cnic.country_to_stay,
                    document_value="—",
                    document_source="Application Form",
                    result=CheckResult.PASS if normalize_text(form.cnic.country_to_stay) else CheckResult.FAIL,
                    is_critical=False,
                    message="Declared on application (not printed on CNIC)",
                )
            )
            comparisons.append(self._cnic_expiry_check(cnic.expiry_date or form.cnic.expiry_date))
        else:
            comparisons.append(
                FieldComparison(
                    field="CNIC Extraction",
                    customer_value="Expected" if not branch_workflow else "Optional",
                    document_value=None,
                    document_source="CNIC",
                    result=CheckResult.WARNING if branch_workflow else CheckResult.FAIL,
                    is_critical=not branch_workflow,
                    message="Personal details taken from account opening form"
                    if branch_workflow
                    else "No CNIC fields extracted",
                )
            )

        for label in ("cnic_front", "cnic_back"):
            if branch_workflow and label == "cnic_back":
                continue
            if label in readable and not readable[label]:
                comparisons.append(
                    FieldComparison(
                        field=f"{label} Readable",
                        customer_value="Readable",
                        document_value="Unreadable",
                        document_source=label,
                        result=CheckResult.FAIL,
                        is_critical=True,
                        message="Document failed OCR readability check",
                    )
                )

        return self._section("CNIC Validation", comparisons)

    def _payslip_section(
        self,
        form: ApplicationForm,
        payslip: Optional[PayslipFields],
        uploads: Dict[str, bool],
        readable: Dict[str, bool],
    ) -> SectionResult:
        comparisons: List[FieldComparison] = []
        uploaded = uploads.get("payslip", False)
        comparisons.append(
            FieldComparison(
                field="Payslip Uploaded",
                customer_value="Required",
                document_value="Uploaded" if uploaded else "Missing",
                document_source="Upload",
                result=CheckResult.PASS if uploaded else CheckResult.FAIL,
                is_critical=True,
            )
        )

        if payslip:
            comparisons.append(
                self._compare_name(
                    "Employee Name",
                    form.personal.full_name,
                    payslip.employee_name,
                    "Payslip",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_text(
                    "Company Name",
                    form.employment.company_name,
                    payslip.company_name,
                    "Payslip",
                    critical=True,
                )
            )
            comparisons.append(
                self._compare_text(
                    "Employee ID",
                    form.employment.employee_id,
                    payslip.employee_id,
                    "Payslip",
                    critical=False,
                    fuzzy=False,
                )
            )
            comparisons.append(
                self._compare_text(
                    "Designation",
                    form.employment.designation,
                    payslip.designation,
                    "Payslip",
                    critical=False,
                    fuzzy=True,
                )
            )
            comparisons.append(
                self._compare_salary(
                    form.employment.monthly_income,
                    payslip.gross_salary or payslip.net_salary or payslip.net_pay,
                )
            )
            readable_ok = readable.get("payslip", True)
            comparisons.append(
                FieldComparison(
                    field="Payslip Readable",
                    customer_value="Readable",
                    document_value="Readable" if readable_ok else "Unreadable",
                    document_source="Payslip",
                    result=CheckResult.PASS if readable_ok else CheckResult.FAIL,
                    is_critical=True,
                )
            )
        elif uploaded:
            comparisons.append(
                FieldComparison(
                    field="Payslip Extraction",
                    customer_value="Required",
                    document_value=None,
                    document_source="Payslip",
                    result=CheckResult.FAIL,
                    is_critical=True,
                    message="Payslip uploaded but fields could not be extracted",
                )
            )

        return self._section("Payslip Validation", comparisons)

    def _bank_section(
        self,
        form: ApplicationForm,
        bank: Optional[BankStatementFields],
        uploads: Dict[str, bool],
        readable: Dict[str, bool],
    ) -> SectionResult:
        comparisons: List[FieldComparison] = []
        uploaded = uploads.get("bank_statement", False)
        comparisons.append(
            FieldComparison(
                field="Bank Statement Uploaded",
                customer_value="Required",
                document_value="Uploaded" if uploaded else "Missing",
                document_source="Upload",
                result=CheckResult.PASS if uploaded else CheckResult.FAIL,
                is_critical=True,
            )
        )

        if bank:
            comparisons.append(
                self._compare_name(
                    "Account Holder",
                    form.personal.full_name,
                    bank.account_holder,
                    "Bank Statement",
                    critical=True,
                )
            )
            extracted_fields = [
                ("Bank Name", bank.bank_name, bool(normalize_text(bank.bank_name))),
                (
                    "Account Number",
                    bank.account_number,
                    bool(normalize_account_number(bank.account_number)),
                ),
                ("IBAN", bank.iban, bool(normalize_iban(bank.iban))),
            ]
            for field_label, value, present in extracted_fields:
                comparisons.append(
                    FieldComparison(
                        field=field_label,
                        customer_value="—",
                        document_value=value,
                        document_source="Bank Statement",
                        result=CheckResult.PASS if present else CheckResult.FAIL,
                        is_critical=True,
                        message=None if present else f"{field_label} not found on statement",
                    )
                )
            readable_ok = readable.get("bank_statement", True)
            comparisons.append(
                FieldComparison(
                    field="Statement Readable",
                    customer_value="Readable",
                    document_value="Readable" if readable_ok else "Unreadable",
                    document_source="Bank Statement",
                    result=CheckResult.PASS if readable_ok else CheckResult.FAIL,
                    is_critical=True,
                )
            )
        elif uploaded:
            comparisons.append(
                FieldComparison(
                    field="Bank Statement Extraction",
                    customer_value="Required",
                    document_value=None,
                    document_source="Bank Statement",
                    result=CheckResult.FAIL,
                    is_critical=True,
                    message="Statement uploaded but fields could not be extracted",
                )
            )

        return self._section("Bank Statement Validation", comparisons)

    def _cross_section(
        self,
        form: ApplicationForm,
        cnic: Optional[CNICFields],
        payslip: Optional[PayslipFields],
        bank: Optional[BankStatementFields],
    ) -> SectionResult:
        comparisons: List[FieldComparison] = []
        names = [
            ("Form", form.personal.full_name),
            ("CNIC Form", form.cnic.full_name),
            ("CNIC", cnic.name if cnic else None),
            ("Payslip", payslip.employee_name if payslip else None),
            ("Bank Statement", bank.account_holder if bank else None),
        ]
        present = [(src, n) for src, n in names if n]
        if len(present) >= 2:
            base_src, base_name = present[0]
            for src, name in present[1:]:
                comparisons.append(
                    self._compare_name(
                        f"Name consistency ({base_src} vs {src})",
                        base_name,
                        name,
                        src,
                        critical=True,
                    )
                )
        else:
            comparisons.append(
                FieldComparison(
                    field="Cross-document Name Consistency",
                    customer_value=form.personal.full_name,
                    document_value=None,
                    result=CheckResult.WARNING,
                    message="Insufficient extracted names for cross-check",
                )
            )

        return self._section("Cross Validation", comparisons)

    # ---- comparison helpers -----------------------------------------------

    def _compare_name(
        self,
        field: str,
        customer: Optional[str],
        document: Optional[str],
        source: str,
        *,
        critical: bool,
    ) -> FieldComparison:
        if not document:
            return FieldComparison(
                field=field,
                customer_value=customer,
                document_value=None,
                document_source=source,
                result=CheckResult.FAIL if critical else CheckResult.WARNING,
                is_critical=critical,
                message=f"{field} not found on {source}",
            )
        ok, score = names_match(customer, document, self.name_threshold)
        if ok:
            result = CheckResult.PASS
            message = f"Name similarity {score:.0%}"
        elif score >= self.name_threshold * 0.75:
            result = CheckResult.WARNING
            message = f"Partial name match ({score:.0%})"
        else:
            result = CheckResult.FAIL
            message = f"Name mismatch ({score:.0%})"
        return FieldComparison(
            field=field,
            customer_value=customer,
            document_value=document,
            document_source=source,
            result=result,
            is_critical=critical,
            message=message,
        )

    def _compare_text(
        self,
        field: str,
        customer: Optional[str],
        document: Optional[str],
        source: str,
        *,
        critical: bool,
        fuzzy: bool = True,
    ) -> FieldComparison:
        if not document:
            return FieldComparison(
                field=field,
                customer_value=customer,
                document_value=None,
                document_source=source,
                result=CheckResult.FAIL if critical else CheckResult.WARNING,
                is_critical=critical,
                message=f"{field} missing on {source}",
            )
        if fuzzy:
            ok, score = names_match(customer, document, self.name_threshold)
        else:
            ok = normalize_text(customer) == normalize_text(document)
            score = 1.0 if ok else 0.0
        if ok:
            result = CheckResult.PASS
        elif fuzzy and score >= self.name_threshold * 0.7:
            result = CheckResult.WARNING
        else:
            result = CheckResult.FAIL
        return FieldComparison(
            field=field,
            customer_value=customer,
            document_value=document,
            document_source=source,
            result=result,
            is_critical=critical,
            message=None if result == CheckResult.PASS else f"{field} does not match",
        )

    def _compare_cnic_number(
        self, customer: str, document: Optional[str], source: str
    ) -> FieldComparison:
        c = normalize_cnic(customer)
        d = normalize_cnic(document)
        ok = bool(c) and c == d
        return FieldComparison(
            field="CNIC Number",
            customer_value=customer,
            document_value=document,
            document_source=source,
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            is_critical=True,
            message=None if ok else "CNIC number mismatch",
        )

    def _compare_gender(
        self, customer: Optional[str], document: Optional[str]
    ) -> FieldComparison:
        c = _normalize_gender(customer)
        d = _normalize_gender(document)
        if not d:
            return FieldComparison(
                field="Gender",
                customer_value=customer,
                document_value=document,
                document_source="CNIC",
                result=CheckResult.WARNING,
                is_critical=False,
                message="Gender not found on CNIC",
            )
        ok = bool(c) and c == d
        return FieldComparison(
            field="Gender",
            customer_value=customer,
            document_value=document,
            document_source="CNIC",
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            is_critical=False,
            message=None if ok else "Gender mismatch",
        )

    def _compare_dates(
        self,
        field: str,
        customer: Optional[str],
        document: Optional[str],
        source: str,
        *,
        critical: bool,
    ) -> FieldComparison:
        if not document:
            return FieldComparison(
                field=field,
                customer_value=customer,
                document_value=None,
                document_source=source,
                result=CheckResult.FAIL if critical else CheckResult.WARNING,
                is_critical=critical,
                message=f"{field} missing on {source}",
            )
        ok = dates_equal(customer, document)
        return FieldComparison(
            field=field,
            customer_value=customer,
            document_value=document,
            document_source=source,
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            is_critical=critical,
            message=None if ok else f"{field} mismatch",
        )

    def _cnic_expiry_check(self, expiry: Optional[str]) -> FieldComparison:
        if not expiry:
            return FieldComparison(
                field="CNIC Not Expired",
                customer_value="Valid",
                document_value=None,
                document_source="CNIC",
                result=CheckResult.WARNING,
                is_critical=False,
                message="Expiry date not found on CNIC",
            )
        exp = parse_date(expiry)
        if not exp:
            return FieldComparison(
                field="CNIC Not Expired",
                customer_value="Valid",
                document_value=expiry,
                document_source="CNIC",
                result=CheckResult.WARNING,
                is_critical=False,
                message="Could not parse CNIC expiry date",
            )
        expired = exp.date() < datetime.now().date()
        return FieldComparison(
            field="CNIC Not Expired",
            customer_value="Valid",
            document_value=expiry,
            document_source="CNIC",
            result=CheckResult.FAIL if expired else CheckResult.PASS,
            is_critical=True,
            message="CNIC is expired" if expired else "CNIC is within validity period",
        )

    def _compare_salary(
        self, declared: Optional[str], document_salary: Optional[str]
    ) -> FieldComparison:
        declared_amt = parse_amount(declared)
        doc_amt = parse_amount(document_salary)
        if declared_amt is None or doc_amt is None:
            return FieldComparison(
                field="Monthly Salary",
                customer_value=declared,
                document_value=document_salary,
                document_source="Payslip",
                result=CheckResult.WARNING,
                is_critical=False,
                message="Unable to numerically compare salary values",
            )
        if declared_amt == 0:
            ok = doc_amt == 0
            pct_diff = 0.0 if ok else 100.0
        else:
            pct_diff = abs(declared_amt - doc_amt) / abs(declared_amt) * 100.0
            ok = pct_diff <= self.salary_tolerance

        if ok:
            result = CheckResult.PASS
            message = f"Within {self.salary_tolerance:.0f}% tolerance ({pct_diff:.1f}% diff)"
        elif pct_diff <= self.salary_tolerance * 2:
            result = CheckResult.WARNING
            message = f"Salary difference {pct_diff:.1f}% exceeds tolerance"
        else:
            result = CheckResult.FAIL
            message = f"Salary mismatch ({pct_diff:.1f}% difference)"

        return FieldComparison(
            field="Monthly Salary",
            customer_value=declared,
            document_value=document_salary,
            document_source="Payslip",
            result=result,
            is_critical=False,
            message=message,
        )

    @staticmethod
    def _workflow_skipped_section(title: str, note: str) -> SectionResult:
        return SectionResult(
            title=title,
            status=CheckResult.PASS,
            comparisons=[
                FieldComparison(
                    field="Not required",
                    customer_value="N/A",
                    document_value="N/A",
                    document_source="Workflow",
                    result=CheckResult.PASS,
                    is_critical=False,
                    message=note,
                )
            ],
            notes=[note],
        )

    @staticmethod
    def _section(title: str, comparisons: List[FieldComparison]) -> SectionResult:
        if any(c.result == CheckResult.FAIL for c in comparisons):
            status = CheckResult.FAIL
        elif any(c.result == CheckResult.WARNING for c in comparisons):
            status = CheckResult.WARNING
        else:
            status = CheckResult.PASS
        notes = [c.message for c in comparisons if c.message and c.result != CheckResult.PASS]
        return SectionResult(title=title, status=status, comparisons=comparisons, notes=notes)
