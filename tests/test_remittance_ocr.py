"""Unit tests for remittance OCR post-processing, checkboxes, and validation."""

from __future__ import annotations

import unittest

import numpy as np

from app.ocr_pipeline.checkbox import detect_checkbox, purpose_from_checkboxes
from app.ocr_pipeline.config import load_roi_template
from app.ocr_pipeline.postprocess import (
    clean_field_text,
    format_account_field,
    format_cnic_field,
    format_date_field,
    format_phone_field,
)
from app.ocr_pipeline.roi import parse_rois
from app.ocr_pipeline.validators import validate_fields


class PostprocessTests(unittest.TestCase):
    def test_cnic_format(self):
        self.assertEqual(format_cnic_field("42101-1234567-1"), "42101-1234567-1")
        self.assertEqual(format_cnic_field("CNIC: 4210112345671"), "42101-1234567-1")

    def test_phone_format(self):
        self.assertEqual(format_phone_field("0300-1234567"), "03001234567")
        self.assertEqual(format_phone_field("923001234567"), "03001234567")

    def test_account_digits_only(self):
        self.assertEqual(format_account_field("PK12 ACCT 0011"), "120011")
        self.assertEqual(format_account_field("1234-5678-9012"), "123456789012")

    def test_date_format(self):
        self.assertEqual(format_date_field("27-07-2026"), "27/07/2026")
        self.assertEqual(format_date_field("27072026"), "27/07/2026")

    def test_clean_strips_label_and_garbage(self):
        text = clean_field_text("Name: | Ali // Khan ||", "name")
        self.assertIn("Ali", text)
        self.assertNotIn("|", text)


class CheckboxTests(unittest.TestCase):
    def test_empty_box_is_false(self):
        # White page with a thin empty square border
        img = np.full((60, 60, 3), 255, dtype=np.uint8)
        img[10:50, 10] = 0
        img[10:50, 49] = 0
        img[10, 10:50] = 0
        img[49, 10:50] = 0
        checked, ratio = detect_checkbox(img)
        self.assertFalse(checked)
        self.assertLess(ratio, 0.06)

    def test_ticked_box_is_true(self):
        img = np.full((60, 60, 3), 255, dtype=np.uint8)
        img[10:50, 10] = 0
        img[10:50, 49] = 0
        img[10, 10:50] = 0
        img[49, 10:50] = 0
        # Thick diagonal tick through the interior
        for i in range(16, 44):
            for t in range(-2, 3):
                y, x = i, min(59, max(0, i + t))
                img[y, x] = 0
        checked, ratio = detect_checkbox(img)
        self.assertTrue(checked, f"fill_ratio={ratio}")
        self.assertGreaterEqual(ratio, 0.045)

    def test_purpose_from_checkboxes(self):
        boxes = {
            "purpose_family_maintenance": False,
            "purpose_education": True,
            "purpose_medical": False,
        }
        self.assertEqual(purpose_from_checkboxes(boxes), "Education")


class ValidationTests(unittest.TestCase):
    def test_valid_payload(self):
        fields = {
            "date": "27/07/2026",
            "applicant_name": "Ali Khan",
            "father_name": "Ahmed Khan",
            "cnic": "42101-1234567-1",
            "mobile": "03001234567",
            "beneficiary_name": "Sara Ali",
            "beneficiary_account": "123456789012",
            "amount_figures": "15000.00",
            "amount_words": "Fifteen Thousand Only",
            "branch_code": "1234",
            "cheque_number": "12345678",
            "purpose": "Family Support",
            "occupation": "Engineer",
            "address": "Karachi",
            "cash": True,
            "cheque_mode": False,
            "account_debit": False,
            "purpose_family_maintenance": True,
            "purpose_education": False,
            "purpose_medical": False,
            "purpose_gift": False,
            "purpose_investment": False,
            "purpose_business": False,
            "purpose_other": False,
        }
        report = validate_fields(fields)
        self.assertTrue(report["is_valid"], report["errors"])
        self.assertTrue(report["fields"]["cash"]["value"] is True)

    def test_invalid_cnic_and_phone(self):
        report = validate_fields(
            {
                "date": "27/07/2026",
                "applicant_name": "Ali",
                "father_name": "",
                "cnic": "123",
                "mobile": "12345",
                "beneficiary_name": "Sara",
                "beneficiary_account": "12",
                "amount_figures": "abc",
                "amount_words": "",
                "branch_code": "1",
                "cheque_number": "",
                "purpose": "",
                "occupation": "",
                "address": "",
            }
        )
        self.assertFalse(report["is_valid"])
        self.assertTrue(any("cnic" in e for e in report["errors"]))


class RoiTemplateTests(unittest.TestCase):
    def test_template_loads(self):
        template = load_roi_template()
        rois = parse_rois(template)
        keys = {r.key for r in rois}
        self.assertIn("cnic", keys)
        self.assertIn("beneficiary_account", keys)
        self.assertIn("signature_area", keys)
        self.assertIn("applicant_name", keys)
        self.assertIn("purpose_education", keys)
        self.assertEqual(template.get("coordinate_space"), "normalized")
        self.assertEqual(len(template.get("template_size") or []), 2)
        # All boxes must be fractions, not absolute pixels
        for roi in rois:
            self.assertTrue(all(0 <= v <= 1.5 for v in roi.box), roi.key)
        sig = next(r for r in rois if r.key == "signature_area")
        self.assertTrue(sig.skip_ocr)
        edu = next(r for r in rois if r.key == "purpose_education")
        self.assertTrue(edu.is_checkbox)
        self.assertTrue(edu.skip_ocr)

    def test_rejects_pixel_boxes(self):
        with self.assertRaises(ValueError):
            parse_rois(
                {
                    "fields": {
                        "bad": {
                            "box": [100, 200, 50, 20],
                            "field_type": "text",
                        }
                    }
                }
            )


if __name__ == "__main__":
    unittest.main()
