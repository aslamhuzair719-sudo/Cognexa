from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, Field, model_validator

_EMPTY = {"", "null", "none", "n/a", "na", "-", "—", "nil"}

# LLM / OCR labels that should land on the review form.
_FIELD_SOURCES: Dict[str, tuple[str, ...]] = {
    "validity_status": ("validity_status",),
    "validity_score": ("validity_score",),
    "validity_reason": ("validity_reason",),
    "company_name": ("company_name", "employer", "employer_name", "organisation", "organization"),
    "employee_name": ("employee_name", "name", "staff_name"),
    "employee_id": ("employee_id", "employee_no", "employee_number", "emp_id", "staff_id", "staff_no"),
    "designation": ("designation", "job_title", "position", "title", "department"),
    "department": ("department", "dept", "division"),
    "email": ("email", "employee_email", "company_email"),
    "phone": ("phone", "employee_phone", "company_phone", "mobile"),
    "payslip_number": ("payslip_number", "payslip_no", "pay_slip_number", "reference", "payroll_reference"),
    "payslip_date": ("payslip_date", "payment_date", "pay_date"),
    "payment_date": ("payment_date", "pay_date", "payslip_date"),
    "employment_status": ("employment_status", "job_status", "employee_status"),
    "period_start": ("period_start", "pay_period_start", "from_date"),
    "period_end": ("period_end", "pay_period_end", "to_date"),
    "payslip_period": ("payslip_period", "pay_period", "salary_period"),
    "basic_salary": ("basic_salary", "basic_pay", "basic"),
    "gross_salary": ("gross_salary", "gross_pay_current", "gross_pay", "gross"),
    "overtime": ("overtime", "overtime_amount_current", "overtime_pay", "overtime_amount"),
    "deductions": ("deductions", "total_deduction_current", "total_deductions", "total_deduction"),
    "net_pay": ("net_pay", "net_pay_current", "net_salary", "take_home"),
    "net_salary": ("net_salary", "net_pay_current", "net_pay", "take_home"),
}

PAYSLIP_FORM_KEYS = tuple(_FIELD_SOURCES.keys())


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in _EMPTY:
        return ""
    return text


def canonicalize_payslip_fields(data: Any) -> Dict[str, str]:
    """Map LLM/OCR aliases onto the payslip review-form keys."""
    raw = data if isinstance(data, dict) else {}
    out: Dict[str, str] = {}
    for target, sources in _FIELD_SOURCES.items():
        chosen = ""
        for source in sources:
            chosen = _clean_value(raw.get(source))
            if chosen:
                break
        out[target] = chosen

    if not out.get("payslip_period"):
        start = out.get("period_start") or ""
        end = out.get("period_end") or ""
        if start and end:
            out["payslip_period"] = f"{start} - {end}"
        elif start or end:
            out["payslip_period"] = start or end

    if out.get("payslip_period") and (not out.get("period_start") or not out.get("period_end")):
        period = out["payslip_period"]
        for sep in (" - ", " – ", " — ", "-", " to ", " TO "):
            if sep in period:
                left, right = period.split(sep, 1)
                if not out.get("period_start"):
                    out["period_start"] = left.strip()
                if not out.get("period_end"):
                    out["period_end"] = right.strip()
                break

    if out.get("net_pay") and not out.get("net_salary"):
        out["net_salary"] = out["net_pay"]
    if out.get("net_salary") and not out.get("net_pay"):
        out["net_pay"] = out["net_salary"]
    if out.get("designation") and not out.get("department"):
        # Keep department blank unless it was explicitly extracted.
        pass
    if out.get("department") and not out.get("designation"):
        out["designation"] = out["department"]
    if out.get("payment_date") and not out.get("payslip_date"):
        out["payslip_date"] = out["payment_date"]
    if out.get("payslip_date") and not out.get("payment_date"):
        out["payment_date"] = out["payslip_date"]
    return out


class PayslipFields(BaseModel):
    validity_status: Optional[str] = Field(None, description="Valid / Invalid authenticity status")
    validity_score: Optional[str] = Field(None, description="Authenticity score 0-100")
    validity_reason: Optional[str] = Field(None, description="Short authenticity explanation")
    company_name: Optional[str] = Field(None, description="Name of the employing company")
    employee_name: Optional[str] = Field(None, description="Full name of the employee")
    employee_id: Optional[str] = Field(None, description="Employee ID / Number")
    designation: Optional[str] = Field(None, description="Job title / designation")
    department: Optional[str] = Field(None, description="Department / division")
    email: Optional[str] = Field(None, description="Email address of the employee")
    phone: Optional[str] = Field(None, description="Phone number of the employee")
    payslip_number: Optional[str] = Field(None, description="Payslip reference number")
    payslip_date: Optional[str] = Field(None, description="Payslip / document date")
    payment_date: Optional[str] = Field(None, description="Salary payment date")
    employment_status: Optional[str] = Field(None, description="Employment status e.g. Full-Time")
    period_start: Optional[str] = Field(None, description="Start date of pay period")
    period_end: Optional[str] = Field(None, description="End date of pay period")
    payslip_period: Optional[str] = Field(None, description="Payslip period as a single string")
    basic_salary: Optional[str] = Field(None, description="Basic salary amount")
    gross_salary: Optional[str] = Field(None, description="Gross salary / gross pay amount")
    overtime: Optional[str] = Field(None, description="Overtime payment amount")
    deductions: Optional[str] = Field(None, description="Total deductions amount")
    net_pay: Optional[str] = Field(None, description="Net pay amount")
    net_salary: Optional[str] = Field(None, description="Alias for net salary")

    @model_validator(mode="before")
    @classmethod
    def map_llm_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        mapped = canonicalize_payslip_fields(data)
        # Preserve already-canonical values; mapped keys win when filled.
        merged = dict(data)
        for key, value in mapped.items():
            if value:
                merged[key] = value
            elif key not in merged:
                merged[key] = None
        return merged


class PayslipSchema(BaseModel):
    document_type: Literal["payslip"] = "payslip"
    fields: PayslipFields
