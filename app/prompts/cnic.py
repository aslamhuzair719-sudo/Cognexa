from app.prompts.common import BASE_SYSTEM_INSTRUCTION

CNIC_EXTRACTION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a Pakistan National Identity Card (CNIC).
Extract the following fields from the OCR text below:

CNIC NUMBER RULES (critical):
- A Pakistani CNIC has exactly 13 digits in the form XXXXX-XXXXXXX-X (5-7-1).
- Copy the FULL identity number exactly as it appears near "Identity Number".
- Do NOT drop leading digits. Example: "A 35202-6787205-9" -> "35202-6787205-9".
- Never return a partial fragment like "787205-9" or "705-9".
- Ignore stray letters glued to the number (e.g. leading "A").

GENDER RULES (critical):
- Pakistani CNIC prints gender as a single letter: M or F (sometimes Male/Female).
- Look for labels such as Gender, Sex, or a lone M/F near the identity fields.
- Return exactly "M" or "F". Do not return null if M or F is visible in the OCR text.
- Map Male/Man -> "M", Female/Woman -> "F".

Requested JSON schema:
{{
    "name": "Full Name",
    "father_name": "Father's Name",
    "gender": "M or F only",
    "country_to_stay": "Country to stay / country of stay if listed",
    "cnic_number": "Full 13-digit CNIC as XXXXX-XXXXXXX-X",
    "date_of_birth": "Date of Birth (format DD.MM.YYYY or as listed)",
    "issue_date": "Date of Issuance (format DD.MM.YYYY or as listed)",
    "expiry_date": "Date of Expiry (format DD.MM.YYYY or as listed)"
}}

Use empty string "" when a field is missing or unreadable. Do NOT invent values.

OCR TEXT:
{ocr_text}
"""

CNIC_VISION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a Pakistan National Identity Card (CNIC) from the attached image.

CNIC NUMBER RULES (critical):
- A Pakistani CNIC has exactly 13 digits in the form XXXXX-XXXXXXX-X (5-7-1).
- Copy the FULL identity number exactly as printed near "Identity Number".
- Do NOT drop leading digits. Never return a partial fragment.

GENDER RULES (critical):
- Return exactly "M" or "F" when visible. Map Male -> "M", Female -> "F".

Requested JSON schema:
{{
    "name": "Full Name",
    "father_name": "Father's Name",
    "gender": "M or F only",
    "country_to_stay": "Country to stay / country of stay if listed",
    "cnic_number": "Full 13-digit CNIC as XXXXX-XXXXXXX-X",
    "date_of_birth": "Date of Birth (format DD.MM.YYYY or as listed)",
    "issue_date": "Date of Issuance (format DD.MM.YYYY or as listed)",
    "expiry_date": "Date of Expiry (format DD.MM.YYYY or as listed)"
}}

Read the attached CNIC image carefully. Use empty string "" when a field is missing
or unreadable. Do NOT invent values.
"""
