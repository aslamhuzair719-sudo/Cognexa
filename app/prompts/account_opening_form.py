from app.prompts.common import BASE_SYSTEM_INSTRUCTION

ACCOUNT_OPENING_FORM_EXTRACTION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a bank account opening application form.
Extract applicant and employment details from the OCR text below.

Requested JSON schema:
{{
    "applicant_name": "Applicant full name",
    "age": "Applicant age in years",
    "father_name": "Father's name",
    "cnic_number": "CNIC as XXXXX-XXXXXXX-X if present",
    "date_of_birth": "Date of birth",
    "gender": "M or F if present",
    "country_to_stay": "Country of stay if listed",
    "mobile_number": "Mobile / phone number",
    "email": "Email address if listed",
    "company_name": "Employer / company name",
    "designation": "Job title / designation",
    "monthly_income": "Declared monthly income / salary",
    "employee_id": "Employee ID if listed"
}}

Use empty string "" when a field is missing. Do NOT invent values.

OCR TEXT:
{ocr_text}
"""

ACCOUNT_OPENING_FORM_VISION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a bank account opening application form from the attached image.

Extract the same fields as the OCR schema:
applicant_name, age, father_name, cnic_number, date_of_birth, gender, country_to_stay,
mobile_number, email, company_name, designation, monthly_income, employee_id.

Return JSON only with those keys. Use "" for missing fields.
"""
