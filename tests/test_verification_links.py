"""Tests for encrypted verification email links and payslip identity payload."""

from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from app.models import ApplicationStatus
from app.services.verification_service import (
    VERIFICATION_STATUS_PENDING,
    VERIFICATION_STATUS_REJECTED,
    VERIFICATION_STATUS_VERIFIED,
    _application_email_payload,
    _payslip_identity_from_report,
    apply_email_link_decision,
)
from app.services.verification_tokens import (
    VerificationLinkError,
    build_decision_urls,
    create_decision_token,
    decode_decision_token,
)


class TestVerificationTokens(unittest.TestCase):
    def test_decision_token_roundtrip(self):
        token = create_decision_token("VER-abc123", "accept")
        payload = decode_decision_token(token)
        self.assertEqual(payload["vid"], "VER-abc123")
        self.assertEqual(payload["action"], "accept")

    def test_decision_urls_use_localhost(self):
        accept_url, reject_url = build_decision_urls("VER-abc123")
        self.assertTrue(accept_url.startswith("http://localhost:8000/verify/"))
        self.assertTrue(reject_url.startswith("http://localhost:8000/verify/"))
        self.assertNotEqual(accept_url, reject_url)
        accept_token = accept_url.rsplit("/", 1)[-1]
        reject_token = reject_url.rsplit("/", 1)[-1]
        self.assertEqual(decode_decision_token(accept_token)["action"], "accept")
        self.assertEqual(decode_decision_token(reject_token)["action"], "reject")

    def test_tampered_token_is_rejected(self):
        token = create_decision_token("VER-abc123", "accept")
        with self.assertRaises(VerificationLinkError):
            decode_decision_token(token + "tamper")


class TestPayslipIdentityPayload(unittest.TestCase):
    def test_payslip_identity_from_report(self):
        report = {
            "payslip_validation": {
                "comparisons": [
                    {"field": "Employee Name", "document_value": "Ali Khan"},
                    {"field": "Company Name", "document_value": "Infotics Pvt Ltd"},
                ]
            }
        }
        name, company = _payslip_identity_from_report(report)
        self.assertEqual(name, "Ali Khan")
        self.assertEqual(company, "Infotics Pvt Ltd")

    def test_application_payload_prefers_payslip_fields(self):
        application = SimpleNamespace(
            full_name="Form Name",
            company_name="Form Company",
            cnic_number="12345-1234567-1",
            employee_id="E-1",
            branch=SimpleNamespace(name="Main"),
            report_json={
                "payslip_validation": {
                    "comparisons": [
                        {"field": "Employee Name", "document_value": "Payslip Name"},
                        {"field": "Company Name", "document_value": "Payslip Company"},
                    ]
                }
            },
        )
        payload = _application_email_payload(application)
        self.assertEqual(payload["full_name"], "Payslip Name")
        self.assertEqual(payload["company_name"], "Payslip Company")

    def test_application_payload_falls_back_to_application_fields(self):
        application = SimpleNamespace(
            full_name="Form Name",
            company_name="Form Company",
            cnic_number="12345-1234567-1",
            employee_id="E-1",
            branch=None,
            report_json=None,
        )
        payload = _application_email_payload(application)
        self.assertEqual(payload["full_name"], "Form Name")
        self.assertEqual(payload["company_name"], "Form Company")


class TestApplyEmailLinkDecision(unittest.TestCase):
    def _verification(self, status=VERIFICATION_STATUS_PENDING):
        application_id = uuid.uuid4()
        application = Mock()
        application.full_name = "Jane Doe"
        application.id = application_id
        application.status = "completed"
        application.decision_note = None
        application.decided_at = None
        application.verification_email_status = "sent"
        application.verification_email_confirmed_at = None
        application.verification_email_last_error = None

        verification = Mock()
        verification.status = status
        verification.company_email = "hr@acme.com"
        verification.verification_id = "VER-abc123"
        verification.branch_id = 1
        verification.application = application
        verification.application_id = application_id
        verification.branch_entry = None
        verification.created_by = None
        verification.verified_at = None
        verification.rejected_at = None
        verification.canceled_at = None
        return verification, application

    def test_accept_link_marks_application_accepted(self):
        verification, application = self._verification()
        db = Mock()
        title, message = apply_email_link_decision(db, verification, "accept")
        self.assertEqual(application.status, ApplicationStatus.accepted.value)
        self.assertEqual(verification.status, VERIFICATION_STATUS_VERIFIED)
        self.assertIn("Accepted", title)
        self.assertIn("Accepted", message)

    def test_reject_link_marks_application_rejected(self):
        verification, application = self._verification()
        db = Mock()
        title, message = apply_email_link_decision(db, verification, "reject")
        self.assertEqual(application.status, ApplicationStatus.rejected.value)
        self.assertEqual(verification.status, VERIFICATION_STATUS_REJECTED)
        self.assertIn("Rejected", title)

    def test_duplicate_click_is_idempotent(self):
        verification, application = self._verification(status=VERIFICATION_STATUS_VERIFIED)
        db = Mock()
        title, message = apply_email_link_decision(db, verification, "reject")
        self.assertEqual(title, "Already processed")
        self.assertIn("Accepted", message)
        self.assertEqual(application.status, "completed")


if __name__ == "__main__":
    unittest.main()
