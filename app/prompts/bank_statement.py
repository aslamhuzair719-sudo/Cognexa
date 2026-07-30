from app.prompts.common import BASE_SYSTEM_INSTRUCTION

BANK_STATEMENT_EXTRACTION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a Pakistani bank statement (tabular format, e.g. Meezan Bank).
Extract header fields and ALL transaction rows from the OCR text below.

Requested JSON schema:
{{
    "account_title": "Account holder name (Account Title)",
    "account_number": "Account number",
    "iban": "IBAN",
    "currency": "Currency code (e.g. PKR)",
    "from_date": "Statement from date",
    "to_date": "Statement to date",
    "address": "Account holder address",
    "transactions": [
        {{
            "transaction_date": "DD/MM/YYYY",
            "description": "Transaction description",
            "debit": "Debit amount or empty string",
            "credit": "Credit amount or empty string",
            "available_balance": "Running balance after transaction"
        }}
    ]
}}

Rules:
- Include every transaction row visible in the OCR text.
- For Opening Balance rows, debit and credit are usually empty.
- Use empty string "" for missing values. Do NOT invent values.

OCR Text:
{ocr_text}
"""

BANK_STATEMENT_VISION_PROMPT = BASE_SYSTEM_INSTRUCTION + """
You are parsing a Pakistani bank statement (tabular format) from the attached image.

Extract header fields and ALL transaction rows visible in the statement table.

Requested JSON schema:
{{
    "account_title": "Account holder name (Account Title)",
    "account_number": "Account number",
    "iban": "IBAN",
    "currency": "Currency code (e.g. PKR)",
    "from_date": "Statement from date",
    "to_date": "Statement to date",
    "address": "Account holder address",
    "transactions": [
        {{
            "transaction_date": "DD/MM/YYYY",
            "description": "Transaction description",
            "debit": "Debit amount or empty string",
            "credit": "Credit amount or empty string",
            "available_balance": "Running balance after transaction"
        }}
    ]
}}

Rules:
- Include every transaction row visible in the table.
- For Opening Balance rows, debit and credit are usually empty.
- Use empty string "" for missing values. Do NOT invent values.

Read the attached bank statement image carefully.
"""
