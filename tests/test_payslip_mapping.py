import unittest

from app.schemas.payslip import PayslipFields, canonicalize_payslip_fields
from app.utils.payslip_ocr import enrich_payslip_from_ocr


SAMPLE_OCR = """
Open Source

Employee Name: Iffat Ashraf
Employee ID: EMP-2026-123
Department: Union Consulting

Pay Period: June O1- June 30, 2026
Payment Date: June 30, 2026
Employment Status: Full-Time

Basic Salary
Overtime Pay
Transportation Allowance
Meal Allowance
Gross Pay

5,000
22 Days
50,000
"""


class TestPayslipFieldMapping(unittest.TestCase):
    def test_aliases_fill_form_keys(self):
        mapped = canonicalize_payslip_fields(
            {
                "company_name": "Open Source",
                "employee_name": "Iffat Ashraf",
                "pay_period_start": "June 01, 2026",
                "pay_period_end": "June 30, 2026",
                "gross_pay_current": "50,000",
                "overtime_amount_current": "5,000",
                "net_pay_current": "50,000",
                "employee_email": "",
            }
        )
        self.assertEqual(mapped["company_name"], "Open Source")
        self.assertEqual(mapped["employee_name"], "Iffat Ashraf")
        self.assertEqual(mapped["period_start"], "June 01, 2026")
        self.assertEqual(mapped["period_end"], "June 30, 2026")
        self.assertEqual(mapped["payslip_period"], "June 01, 2026 - June 30, 2026")
        self.assertEqual(mapped["gross_salary"], "50,000")
        self.assertEqual(mapped["overtime"], "5,000")
        self.assertEqual(mapped["net_pay"], "50,000")
        self.assertEqual(mapped["net_salary"], "50,000")

    def test_pydantic_drops_aliases_into_form_fields(self):
        fields = PayslipFields(
            company_name="Open Source",
            employee_name="Iffat Ashraf",
            employee_id="EMP-2026-123",
            gross_pay_current="50,000",
            pay_period="June 01- June 30, 2026",
        )
        self.assertEqual(fields.gross_salary, "50,000")
        self.assertEqual(fields.payslip_period, "June 01- June 30, 2026")
        self.assertEqual(fields.period_start, "June 01")
        self.assertEqual(fields.period_end, "June 30, 2026")

    def test_ocr_fills_missing_labeled_fields(self):
        filled = enrich_payslip_from_ocr(
            SAMPLE_OCR,
            {"company_name": "Open Source", "employee_name": "Iffat Ashraf"},
        )
        self.assertEqual(filled["employee_id"], "EMP-2026-123")
        self.assertEqual(filled["department"], "Union Consulting")
        self.assertEqual(filled["designation"], "Union Consulting")
        self.assertEqual(filled["payslip_period"], "June O1- June 30, 2026")
        self.assertEqual(filled["payment_date"], "June 30, 2026")
        self.assertEqual(filled["employment_status"], "Full-Time")
        self.assertEqual(filled["company_name"], "Open Source")
        self.assertEqual(filled["employee_name"], "Iffat Ashraf")
        self.assertEqual(filled["gross_salary"], "50,000")


if __name__ == "__main__":
    unittest.main()
