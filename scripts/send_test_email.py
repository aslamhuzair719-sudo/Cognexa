"""Send a simple test email using the application's SMTP configuration.

Usage:
  python scripts/send_test_email.py recipient@example.com

The script reads SMTP configuration from the application's environment (or .env).
Do NOT include secrets in this file; set them in your environment or .env before running.
"""

from __future__ import annotations

import sys
from email.message import EmailMessage

from app import config
from app.logging_config import setup_logging
from app.logging_config import get_logger
from app.services.email_service import send_verification_email


def main():
    setup_logging()
    logger = get_logger(__name__)

    if len(sys.argv) < 2:
        print("Usage: python scripts/send_test_email.py recipient@example.com")
        sys.exit(2)

    recipient = sys.argv[1]
    subject = f"Test email from DocumentScan ({config.SMTP_HOST})"
    body = "This is a test message from the DocumentScan application.\nIf you received this, SMTP send worked."

    if not config.SMTP_HOST or not config.EMAIL_FROM:
        logger.error("SMTP_HOST and EMAIL_FROM must be configured in environment or .env")
        sys.exit(1)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{config.EMAIL_FROM_NAME} <{config.EMAIL_FROM}>" if config.EMAIL_FROM_NAME else config.EMAIL_FROM
    message["To"] = recipient
    message.set_content(body)

    try:
        send_verification_email(message)
        logger.info("Test email sent to %s", recipient)
    except Exception as exc:
        logger.exception("Failed to send test email: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
