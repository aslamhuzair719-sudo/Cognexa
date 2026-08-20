import unittest

from app.services.classifier import KeywordClassifier
from app.services.extraction_service import ExtractionPipeline
from app.services.workflow_service import WorkflowService


FIRST_APPLICANT_OCR = """
FIRST APPLICANT (Please complete all section in BLOCK Capitals)
Section 1 - Personal Information
Title Mr/Mrs/Miss/Ms/Other  Mrs Ashraf
Forenames  Iffat
3a. Current Residential Address  Gulshan Block-3, Apartment 102, Karachi, Sindh
Post Code 77777777
Country Pakistan
Date of Entry to this address 03102025
Last Address Gulshan Block-3, Apartment 102, Karachi, Sindh
Home Phone number 021-12345678
Mobile number 0321-1234567
Email Address Test@gmail.com
Date of Birth 13092002
Nationality Pakistan
10a. Do you have residence in the USA? No
b. Have you ever held a USA Green Card? No
Section 2 – Country of Residence for Tax Purposes and related TIN
"""

PAYSLIP_OCR = """
Employee Payslip
Pay Period 01/07/2026 - 31/07/2026
Employee Name Iffat Ashraf
Gross Salary 120000
Net Pay 98000
Earnings and Deductions
"""

CNIC_OCR = """
PAKISTAN
National Identity Card
NADRA
Name IFFAT ASHRAF
Identity Number 42201-1234567-8
Date of Issue 01.01.2020
Date of Expiry 01.01.2030
Holder's Signature
Republic of Pakistan
CNIC
"""


class TestWorkflowClassification(unittest.TestCase):
    def setUp(self):
        self.svc = WorkflowService.__new__(WorkflowService)
        self.svc.classifier = KeywordClassifier()

    def test_first_applicant_is_account_opening_form(self):
        doc_type, confidence, scores = self.svc._classify_page(FIRST_APPLICANT_OCR)
        self.assertEqual(doc_type, "account_opening_form")
        self.assertGreater(scores["account_opening_form"], scores["cnic"])
        self.assertGreater(confidence, 0.2)

    def test_keyword_classifier_does_not_call_form_a_cnic(self):
        result = KeywordClassifier().classify(FIRST_APPLICANT_OCR)
        self.assertEqual(result["document_type"], "account_opening_form")

    def test_labeled_blank_page_is_separator(self):
        self.assertTrue(self.svc._is_separator_text("Blank Page", 0.04))
        self.assertTrue(self.svc._is_separator_text("THIS PAGE IS INTENTIONALLY LEFT BLANK", 0.05))
        self.assertFalse(self.svc._is_separator_text(FIRST_APPLICANT_OCR, 0.12))

    def test_three_page_pack_assigns_form_payslip_cnic(self):
        docs = []
        for page, text in enumerate((FIRST_APPLICANT_OCR, PAYSLIP_OCR, CNIC_OCR), start=1):
            doc_type, confidence, scores = self.svc._classify_page(text)
            docs.append(
                {
                    "page": page,
                    "document_type": doc_type,
                    "document_type_label": doc_type,
                    "confidence": confidence,
                    "needs_review": True,
                    "raw_text": text,
                    "scores": scores,
                    "summary": {"flags": ["classification_only"]},
                }
            )
        self.svc._assign_group_document_types(docs)
        self.assertEqual(
            [doc["document_type"] for doc in docs],
            ["account_opening_form", "payslip", "cnic"],
        )

    def test_positional_fallback_when_keywords_are_weak(self):
        docs = []
        for page in (1, 2, 3):
            docs.append(
                {
                    "page": page,
                    "document_type": "cnic",
                    "document_type_label": "CNIC",
                    "confidence": 0.1,
                    "needs_review": True,
                    "raw_text": "date of birth address father name",
                    "scores": {
                        "account_opening_form": 0.0,
                        "payslip": 0.0,
                        "cnic": 0.1,
                    },
                    "summary": {"flags": []},
                }
            )
        self.svc._assign_group_document_types(docs)
        self.assertEqual(
            [doc["document_type"] for doc in docs],
            ["account_opening_form", "payslip", "cnic"],
        )

    def test_blank_pages_split_three_customers(self):
        pages = []
        page_no = 1
        for customer in range(3):
            for _ in range(3):
                pages.append({"page": page_no, "blank": False})
                page_no += 1
            if customer < 2:
                pages.append({"page": page_no, "blank": True})
                page_no += 1
        segments = self.svc._segment_pages(pages)
        self.assertEqual(len(segments["groups"]), 3)
        self.assertEqual(segments["groups"][0]["pages"], [1, 2, 3])
        self.assertEqual(segments["groups"][1]["pages"], [5, 6, 7])
        self.assertEqual(segments["groups"][2]["pages"], [9, 10, 11])
        self.assertEqual(segments["separator_pages"], [4, 8])

    def test_compose_name_from_title_forenames_surname(self):
        fields = ExtractionPipeline._compose_applicant_name(
            {
                "title": "Mrs",
                "forenames": "Iffat",
                "surname": "Ashraf",
                "applicant_name": "",
            }
        )
        self.assertEqual(fields["applicant_name"], "Mrs Iffat Ashraf")
        self.assertEqual(fields["gender"], "F")


if __name__ == "__main__":
    unittest.main()
