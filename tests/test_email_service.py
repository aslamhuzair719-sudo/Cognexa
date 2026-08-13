"""Unit tests for email verification helpers."""

import socket
import unittest
from unittest.mock import Mock, patch

from app.services.email_service import (
    VerificationEmailError,
    compose_verification_email,
    is_smtp_configured,
    send_verification_email,
    validate_verification_target,
)
from app import config


class TestEmailService(unittest.TestCase):
    @patch("app.services.email_service._validate_email_exists")
    def test_validate_verification_target_accepts_company_email(self, mock_validate_exists):
        mock_validate_exists.return_value = None
        email = validate_verification_target("verify@company-example.com")
        self.assertEqual(email, "verify@company-example.com")

    # def test_validate_verification_target_rejects_free_email(self):
    #     with self.assertRaises(VerificationEmailError):
    #         validate_verification_target("user@gmail.com")

    @patch("app.services.email_service._validate_email_exists")
    def test_validate_verification_target_rejects_unknown_domain(self, mock_validate_exists):
        mock_validate_exists.side_effect = VerificationEmailError(
            "Email domain does not accept mail or does not exist."
        )

        with self.assertRaises(VerificationEmailError) as context:
            validate_verification_target("user@unknown-domain-example.com")

        self.assertIn("Email domain does not accept mail or does not exist", str(context.exception))

    @patch("app.services.email_service.dns.resolver.resolve")
    @patch("app.services.email_service.smtplib.SMTP")
    def test_validate_verification_target_checks_recipient_exists(self, mock_smtp, mock_resolve):
        mock_record = Mock(preference=10, exchange="mx.example.com.")
        mock_resolve.return_value = [mock_record]

        smtp_instance = mock_smtp.return_value.__enter__.return_value
        smtp_instance.rcpt.return_value = (250, b"OK")

        email = validate_verification_target("user@valid-company.com")
        self.assertEqual(email, "user@valid-company.com")

    def test_compose_verification_email_sets_expected_subject(self):
        application = {
            "full_name": "Jane Doe",
            "cnic_number": "12345-1234567-1",
            "company_name": "Acme Co",
            "employee_id": "EMP-001",
        }
        message = compose_verification_email(
            application, document_type="payslip", target_email="verify@company-example.com"
        )
        self.assertEqual(message["To"], "verify@company-example.com")
        self.assertIn("Document Verification Request", message["Subject"])
        body = message.get_body(preferencelist=("plain",))
        self.assertIsNotNone(body)
        self.assertIn("Jane Doe", body.get_content())
        self.assertIn("Acme Co", body.get_content())
        html = message.get_body(preferencelist=("html",))
        self.assertIsNotNone(html)
        self.assertIn("Jane Doe", html.get_content())
        self.assertIn("Acme Co", html.get_content())

    def test_compose_verification_email_uses_applicant_name_fallback(self):
        message = compose_verification_email(
            {
                "applicant_name": "Payslip Employee",
                "company_name": "Payslip Ltd",
            },
            document_type="payslip",
            target_email="verify@company-example.com",
        )
        body = message.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("Payslip Employee", body)
        self.assertIn("Payslip Ltd", body)

    def test_compose_verification_email_includes_encrypted_decision_links(self):
        message = compose_verification_email(
            {
                "full_name": "Jane Doe",
                "company_name": "Acme Co",
            },
            document_type="payslip",
            target_email="verify@company-example.com",
            verification_id="VER-abc123",
        )
        self.assertEqual(message["Subject"], "[Application Verification: VER-abc123]")
        plain = message.get_body(preferencelist=("plain",)).get_content()
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("http://localhost:8000/verify/", plain)
        self.assertIn("Accept:", plain)
        self.assertIn("Reject:", plain)
        self.assertIn("Accept</a>", html)
        self.assertIn("Reject</a>", html)

    @patch("app.services.email_service.smtplib.SMTP")
    def test_send_verification_email_uses_smtp(self, mock_smtp):
        config.SMTP_HOST = "smtp.example.com"
        config.SMTP_PORT = 587
        config.SMTP_USERNAME = "user"
        config.SMTP_PASSWORD = "pass"
        config.SMTP_USE_TLS = True
        config.SMTP_USE_SSL = False
        config.EMAIL_FROM = "verify@example.com"
        config.EMAIL_FROM_NAME = "Verifier"

        message = compose_verification_email(
            {
                "full_name": "Jane Doe",
                "cnic_number": "12345-1234567-1",
                "company_name": "Acme Co",
                "employee_id": "EMP-001",
            },
            document_type="payslip",
            target_email="verify@company-example.com",
        )
        send_verification_email(message)

        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
        smtp_instance = mock_smtp.return_value.__enter__.return_value
        smtp_instance.starttls.assert_called_once()
        smtp_instance.login.assert_called_once_with("user", "pass")
        smtp_instance.send_message.assert_called_once_with(message)

    def test_is_smtp_configured_returns_false_when_missing(self):
        config.SMTP_HOST = ""
        config.SMTP_PORT = 587
        config.EMAIL_FROM = ""
        self.assertFalse(is_smtp_configured())


if __name__ == "__main__":
    unittest.main()
