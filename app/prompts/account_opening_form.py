from app.prompts.common import BASE_SYSTEM_INSTRUCTION

ACCOUNT_OPENING_FORM_EXTRACTION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a bank account opening application form, including UBL-style
"FIRST APPLICANT" packs with Section 1 Personal Information and Section 2 tax/TIN.

Extract applicant details from the OCR text below.

Requested JSON schema:
{{
    "title": "Mr / Mrs / Miss / Ms / Other",
    "surname": "Surname / family name only",
    "forenames": "Forenames / given names only",
    "applicant_name": "Full name = Title + Forenames + Surname",
    "age": "Applicant age in years if listed",
    "father_name": "Father's name if listed",
    "cnic_number": "CNIC as XXXXX-XXXXXXX-X if present",
    "date_of_birth": "Date of birth (normalize DDMMYYYY boxes to DD/MM/YYYY)",
    "gender": "M or F if present; Mrs/Miss/Ms implies F, Mr implies M",
    "current_address": "Current residential address",
    "postcode": "Post code / ZIP",
    "last_address": "Previous / last address if listed",
    "date_of_entry_to_address": "Date of entry to current address",
    "country_to_stay": "Country of the current address",
    "nationality": "Nationality",
    "home_phone": "Home phone number",
    "mobile_number": "Mobile number",
    "email": "Email address",
    "usa_residence": "Yes or No — residence in the USA",
    "usa_green_card": "Yes or No — ever held a USA Green Card",
    "tax_residence_country": "Country of residence for tax purposes",
    "tin": "Tax identification number if listed",
    "company_name": "Employer / company name if listed",
    "designation": "Job title / designation if listed",
    "monthly_income": "Declared monthly income / salary if listed",
    "employee_id": "Employee ID if listed"
}}

Use empty string "" when a field is missing. Do NOT invent values.
If surname and forenames are present, always fill applicant_name.

OCR TEXT:
{ocr_text}
"""

ACCOUNT_OPENING_FORM_VISION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a bank account opening application form from the attached image.
This may be a "FIRST APPLICANT" form with boxed dates/postcodes and Yes/No checkboxes.

Extract these fields:
title, surname, forenames, applicant_name, age, father_name, cnic_number,
date_of_birth, gender, current_address, postcode, last_address,
date_of_entry_to_address, country_to_stay, nationality, home_phone,
mobile_number, email, usa_residence, usa_green_card, tax_residence_country,
tin, company_name, designation, monthly_income, employee_id.

Rules:
- Combine Title + Forenames + Surname into applicant_name.
- Read digit boxes left-to-right for dates (DDMMYYYY) and postcodes.
- usa_residence / usa_green_card must be Yes or No from the checked box.
- Return JSON only with those keys. Use "" for missing fields.
"""
