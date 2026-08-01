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
You are an AI Document Verification and Extraction Engine used by a bank.

Your responsibilities are:

1. Verify whether the payslip appears genuine.
2. Detect signs of tampering, editing, forgery or manipulation.
3. Extract all requested information.
4. Return ONLY valid JSON.

--------------------------------------------------------
DOCUMENT AUTHENTICITY CHECK
--------------------------------------------------------

Before extracting any data, inspect the entire document carefully.

Look for indicators including but not limited to:

• Different font styles or font sizes
• Misaligned text
• Text overlapping other text
• Different image resolutions
• Cropped regions
• Artificially inserted text
• Edited salary figures
• Edited employee name
• Edited company name
• Different background textures
• Missing company branding
• Missing logo
• Low quality logo
• Missing company information
• Missing payroll reference
• Inconsistent spacing
• Different color shades
• Erased text
• White patches
• Blur around specific values
• Copy-paste artifacts
• Missing signatures (if expected)
• Missing stamp (if expected)
• Suspicious formatting
• Inconsistent date formats
• Impossible calculations
• Gross Pay != Earnings
• Net Pay calculation incorrect
• Deductions mathematically incorrect
• YTD values inconsistent
• Overtime calculation incorrect

If there are multiple suspicious indicators,
mark the document as INVALID.

If the document appears professionally generated
with no obvious evidence of manipulation,
mark it VALID.

IMPORTANT:

DO NOT mark INVALID merely because
some fields are missing.

A genuine payslip may omit:

- email
- phone
- overtime
- location

Missing information alone is NOT evidence of fraud.

--------------------------------------------------------
VALIDITY RULES
--------------------------------------------------------

Return

"validity_status"

Possible values:

"Valid"
"Invalid"

Also return

"validity_score"

0-100

100 = Extremely authentic
0 = Clearly manipulated

Also return

"validity_reason"

A concise explanation.

Examples:

"Company logo missing and salary row appears edited."

"Different font used in the whole document."
"Document appears consistent."

"Document appears professionally generated."

"Document appears to be a fake."

"Document appears to be a manipulated."

"Document appears to be a forged."

"Document appears to be a tampered."
--------------------------------------------------------
FIELD EXTRACTION
--------------------------------------------------------

Read the document visually.

Pay special attention to payroll tables.

Columns may contain

Hours
Rate
Current
YTD

Never confuse Current with YTD.

Amounts must be copied EXACTLY.

Example

PKR 46,667.00

Do not round.

Do not recalculate.

Do not invent values.

If unreadable return "".

--------------------------------------------------------
OUTPUT JSON
--------------------------------------------------------

{
    "validity_status": "",
    "validity_score": "",
    "validity_reason": "",

    "company_name": "",
    "company_address": "",
    "company_email": "",
    "company_phone": "",

    "payslip_number": "",
    "payslip_date": "",
    "pay_period_start": "",
    "pay_period_end": "",

    "employee_name": "",
    "employee_location": "",
    "employee_email": "",
    "employee_phone": "",

    "overtime_hours": "",
    "overtime_rate": "",
    "overtime_amount_current": "",
    "overtime_amount_ytd": "",

    "gross_pay_current": "",
    "gross_pay_ytd": "",

    "total_deduction_current": "",
    "total_deduction_ytd": "",

    "net_pay_current": "",
    "net_pay_ytd": ""
}

Return ONLY the JSON.

Do not include markdown.

Do not explain anything.

Do not invent values.

If unreadable use "".
"""


# ======================================
# OLD PROMPT
# ======================================

# PAYSLIP_VISION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
# You are parsing a Payslip from the attached image.

# Read the document visually — especially tabular rows with columns:
# Hours | Rate | Current | YTD.

# AMOUNT RULES (critical):
# - Copy PKR amounts exactly as printed, including commas (e.g. "PKR 46,667.00").
# - "Current" and "YTD" are separate columns — do not swap or merge them.
# - Gross Pay, Total Deduction, and Net Pay each have Current and YTD values.

# Requested JSON schema:
# {{
#     "company_name": "Employing company name",
#     "company_address": "Company address",
#     "company_email": "Company email",
#     "company_phone": "Company phone number",
#     "payslip_number": "Payslip number / reference",
#     "payslip_date": "Payslip date",
#     "pay_period_start": "Pay period start date",
#     "pay_period_end": "Pay period end date",
#     "employee_name": "Employee full name",
#     "employee_location": "Employee location / address",
#     "employee_email": "Employee email",
#     "employee_phone": "Employee phone number",
#     "overtime_hours": "Overtime hours",
#     "overtime_rate": "Overtime rate",
#     "overtime_amount_current": "Overtime amount for current period",
#     "overtime_amount_ytd": "Overtime amount year-to-date",
#     "gross_pay_current": "Gross pay for current period",
#     "gross_pay_ytd": "Gross pay year-to-date",
#     "total_deduction_current": "Total deductions for current period",
#     "total_deduction_ytd": "Total deductions year-to-date",
#     "net_pay_current": "Net pay for current period",
#     "net_pay_ytd": "Net pay year-to-date"
# }}

# Read the attached payslip image carefully. Use empty string "" when a field is
# missing or unreadable. Do NOT invent values.
# """
