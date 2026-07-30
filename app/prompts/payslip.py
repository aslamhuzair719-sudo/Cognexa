from app.prompts.common import BASE_SYSTEM_INSTRUCTION

PAYSLIP_EXTRACTION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a Payslip document.
Extract the following fields from the OCR text below.

Requested JSON schema:
{{
    "company_name": "Employing company name",
    "company_address": "Company address",
    "company_email": "Company email",
    "company_phone": "Company phone number",
    "payslip_number": "Payslip number / reference",
    "payslip_date": "Payslip date",
    "pay_period_start": "Pay period start date",
    "pay_period_end": "Pay period end date",
    "employee_name": "Employee full name",
    "employee_location": "Employee location / address",
    "employee_email": "Employee email",
    "employee_phone": "Employee phone number",
    "overtime_hours": "Overtime hours",
    "overtime_rate": "Overtime rate",
    "overtime_amount_current": "Overtime amount for current period",
    "overtime_amount_ytd": "Overtime amount year-to-date",
    "gross_pay_current": "Gross pay for current period",
    "gross_pay_ytd": "Gross pay year-to-date",
    "total_deduction_current": "Total deductions for current period",
    "total_deduction_ytd": "Total deductions year-to-date",
    "net_pay_current": "Net pay for current period",
    "net_pay_ytd": "Net pay year-to-date"
}}

Use empty string "" when a field is missing or unreadable. Do NOT invent values.

OCR Text:
{ocr_text}
"""

PAYSLIP_VISION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a Payslip from the attached image.

Read the document visually — especially tabular rows with columns:
Hours | Rate | Current | YTD.

AMOUNT RULES (critical):
- Copy PKR amounts exactly as printed, including commas (e.g. "PKR 46,667.00").
- "Current" and "YTD" are separate columns — do not swap or merge them.
- Gross Pay, Total Deduction, and Net Pay each have Current and YTD values.

Requested JSON schema:
{{
    "company_name": "Employing company name",
    "company_address": "Company address",
    "company_email": "Company email",
    "company_phone": "Company phone number",
    "payslip_number": "Payslip number / reference",
    "payslip_date": "Payslip date",
    "pay_period_start": "Pay period start date",
    "pay_period_end": "Pay period end date",
    "employee_name": "Employee full name",
    "employee_location": "Employee location / address",
    "employee_email": "Employee email",
    "employee_phone": "Employee phone number",
    "overtime_hours": "Overtime hours",
    "overtime_rate": "Overtime rate",
    "overtime_amount_current": "Overtime amount for current period",
    "overtime_amount_ytd": "Overtime amount year-to-date",
    "gross_pay_current": "Gross pay for current period",
    "gross_pay_ytd": "Gross pay year-to-date",
    "total_deduction_current": "Total deductions for current period",
    "total_deduction_ytd": "Total deductions year-to-date",
    "net_pay_current": "Net pay for current period",
    "net_pay_ytd": "Net pay year-to-date"
}}

Read the attached payslip image carefully. Use empty string "" when a field is
missing or unreadable. Do NOT invent values.
"""
