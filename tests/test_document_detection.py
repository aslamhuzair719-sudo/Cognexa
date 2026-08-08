"""Unit tests for Stage 1 & Stage 2 Document Detection & Gating Service."""

import unittest
from unittest.mock import MagicMock

from app.document_detection.detector import DocumentGateDetector
from app.document_detection.registry import SupportedDocumentRegistry
from app.document_detection.schemas import GateStatus, RawGateDetection
from app.document_detection.service import DocumentGateService, evaluate_document_gate


class DummyDetector(DocumentGateDetector):
    """Mock detector returning preconfigured RawGateDetection."""

    def __init__(self, raw: RawGateDetection):
        self.raw = raw

    def detect(self, source, *, branch: bool = True) -> RawGateDetection:
        return self.raw


class TestDocumentDetectionGate(unittest.TestCase):
    """Test suite for Document Gate Service (Stage 1 & Stage 2)."""

    def test_stage_1_not_a_document(self):
        """Test Stage 1 rejection when image is not a document (e.g. cat, dog, selfie)."""
        raw = RawGateDetection(
            is_document=False,
            document_confidence=15.0,
            detected_type="not_a_document",
            type_confidence=95.0,
            reason="The uploaded image shows a cat.",
        )
        detector = DummyDetector(raw)
        service = DocumentGateService(detector=detector)

        result = service.evaluate("dummy_image.png", selected_type="cnic")

        self.assertEqual(result.status, GateStatus.NOT_A_DOCUMENT)
        self.assertFalse(result.is_document)
        self.assertFalse(result.supported)
        self.assertIsNone(result.document_type)
        self.assertTrue(result.gate_rejected)
        self.assertEqual(result.message, "The uploaded image is not a document.")
        self.assertIn("CNIC", result.supported_documents)

    def test_stage_2_unsupported_document(self):
        """Test Stage 2 rejection when document is valid but unsupported (e.g. Electricity Bill)."""
        raw = RawGateDetection(
            is_document=True,
            document_confidence=98.5,
            detected_type="electricity_bill",
            type_confidence=92.0,
            reason="The document is an electricity bill.",
        )
        detector = DummyDetector(raw)
        service = DocumentGateService(detector=detector)

        result = service.evaluate("electricity_bill.jpg", selected_type="cnic")

        self.assertEqual(result.status, GateStatus.UNSUPPORTED_DOCUMENT)
        self.assertTrue(result.is_document)
        self.assertFalse(result.supported)
        self.assertIsNone(result.document_type)
        self.assertEqual(result.detected_type_label, "Electricity Bill")
        self.assertTrue(result.gate_rejected)
        self.assertIn("not supported", result.message)

    def test_stage_2_supported_cnic(self):
        """Test Stage 1 & Stage 2 pass for CNIC."""
        raw = RawGateDetection(
            is_document=True,
            document_confidence=99.4,
            detected_type="cnic",
            type_confidence=98.7,
            reason="Structured CNIC document detected.",
        )
        detector = DummyDetector(raw)
        service = DocumentGateService(detector=detector)

        result = service.evaluate("cnic.jpg", selected_type="cnic")

        self.assertEqual(result.status, GateStatus.SUPPORTED)
        self.assertTrue(result.is_document)
        self.assertTrue(result.supported)
        self.assertEqual(result.document_type, "cnic")
        self.assertFalse(result.gate_rejected)
        self.assertEqual(result.next_stage, "quality_analysis")
        self.assertIn("Supported document confirmed", result.message)

    def test_stage_2_supported_payslip(self):
        """Test Stage 1 & Stage 2 pass for Payslip."""
        raw = RawGateDetection(
            is_document=True,
            document_confidence=97.0,
            detected_type="payslip",
            type_confidence=94.0,
            reason="Salary slip document detected.",
        )
        detector = DummyDetector(raw)
        service = DocumentGateService(detector=detector)

        result = service.evaluate("payslip.pdf", selected_type="payslip")

        self.assertEqual(result.status, GateStatus.SUPPORTED)
        self.assertTrue(result.is_document)
        self.assertTrue(result.supported)
        self.assertEqual(result.document_type, "payslip")

    def test_stage_2_supported_remittance(self):
        """Test Stage 1 & Stage 2 pass for Remittance Slip."""
        raw = RawGateDetection(
            is_document=True,
            document_confidence=99.0,
            detected_type="remittance_slip",
            type_confidence=96.0,
            reason="UBL Remittance form detected.",
        )
        detector = DummyDetector(raw)
        service = DocumentGateService(detector=detector)

        result = service.evaluate("remittance.jpg", selected_type="remittance_slip")

        self.assertEqual(result.status, GateStatus.SUPPORTED)
        self.assertTrue(result.is_document)
        self.assertTrue(result.supported)
        self.assertEqual(result.document_type, "remittance_slip")

    def test_type_check_mapping(self):
        """Test backward-compatible shape for UI consuming to_type_check()."""
        raw = RawGateDetection(
            is_document=True,
            document_confidence=90.0,
            detected_type="cnic",
            type_confidence=90.0,
            reason="CNIC card",
        )
        detector = DummyDetector(raw)
        result = evaluate_document_gate("cnic.jpg", selected_type="cnic", detector=detector)

        tc = result.to_type_check()
        self.assertTrue(tc["matched"])
        self.assertEqual(tc["gate_status"], "supported")
        self.assertTrue(tc["is_document"])
        self.assertTrue(tc["supported"])


if __name__ == "__main__":
    unittest.main()
