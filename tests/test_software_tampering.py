import unittest
import tempfile
import os
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from app.services.image_quality import ImageQualityService
from app.services.report_generator import ReportGenerator
from app.schemas.common import CheckResult, Recommendation
from app.schemas.application import (
    ApplicationForm,
    PersonalInfo,
    CnicInfo,
    EmploymentInfo,
)
from app.schemas.verification import (
    SectionResult,
    DocumentUploadStatus,
)

class TestSoftwareTampering(unittest.TestCase):
    def setUp(self):
        self.quality_service = ImageQualityService()
        self.report_generator = ReportGenerator()

    def test_canva_metadata_detection_in_image(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img = Image.new("RGB", (800, 600), color=(255, 255, 255))
            pnginfo = PngInfo()
            pnginfo.add_text("software", "Canva v1.0")
            img.save(tmp.name, pnginfo=pnginfo)
            tmp_path = tmp.name

        try:
            res = self.quality_service.assess(tmp_path, "CNIC Front", "Sample OCR text here for test")
            self.assertEqual(res.overall, CheckResult.FAIL)
            tamper_check = next((c for c in res.checks if c.check == "metadata_integrity"), None)
            self.assertIsNotNone(tamper_check)
            self.assertEqual(tamper_check.result, CheckResult.FAIL)
            self.assertIn("Canva", tamper_check.detail)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_report_generator_rejects_and_zeroes_score_for_edited_image(self):
        form = ApplicationForm(
            personal=PersonalInfo(full_name="John Doe", age="30", email="john@example.com", mobile_number="03001234567"),
            cnic=CnicInfo(cnic_number="12345-1234567-1", full_name="John Doe", father_name="Jane Doe", issue_date="2020-01-01", expiry_date="2030-01-01", date_of_birth="1994-01-01", gender="Male", country_to_stay="Pakistan"),
            employment=EmploymentInfo(company_name="Test Corp", designation="Software Engineer", monthly_income="100000", employee_id="EMP-101")
        )
        sections = {
            "customer_information_validation": SectionResult(title="Customer Info", status=CheckResult.PASS, comparisons=[]),
            "cnic_validation": SectionResult(title="CNIC Info", status=CheckResult.PASS, comparisons=[]),
            "payslip_validation": SectionResult(title="Payslip Info", status=CheckResult.PASS, comparisons=[]),
            "bank_statement_validation": SectionResult(title="Bank Statement Info", status=CheckResult.PASS, comparisons=[]),
            "cross_validation": SectionResult(title="Cross Validation", status=CheckResult.PASS, comparisons=[]),
        }
        uploads = [
            DocumentUploadStatus(document_type="cnic_front", document_label="CNIC Front", uploaded=True, extraction_ok=True)
        ]

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img = Image.new("RGB", (800, 600), color=(255, 255, 255))
            pnginfo = PngInfo()
            pnginfo.add_text("software", "Canva v1.0")
            img.save(tmp.name, pnginfo=pnginfo)
            tmp_path = tmp.name

        try:
            iq_result = self.quality_service.assess(tmp_path, "CNIC Front", "Sample OCR text here for test")
            report = self.report_generator.generate(form, sections, uploads, [iq_result])
            
            self.assertEqual(report.overall_score, 0.0)
            self.assertEqual(report.recommendation, Recommendation.REJECTED)
            self.assertIn("Digital editing / software tampering detected", report.recommendation_detail)
            self.assertTrue(any("Image editing software metadata detected" in line for line in report.summary))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
