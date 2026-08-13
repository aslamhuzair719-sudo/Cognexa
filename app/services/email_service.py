"""Email verification helpers for branch document validation."""

from __future__ import annotations

import mimetypes
import socket
import smtplib
from email.message import EmailMessage
from html import escape as html_escape
from pathlib import Path
from typing import Iterable, Optional

import dns.exception
import dns.resolver
from pydantic import EmailStr, ValidationError

from app import config
from app.logging_config import get_logger

logger = get_logger(__name__)

FREE_EMAIL_DOMAINS: set[str] = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "aol.com",
    "icloud.com",
    "me.com",
    "mail.com",
    "protonmail.com",
    "zoho.com",
    "yandex.com",
    "gmx.com",
    "msn.com",
    "rediffmail.com",
    "rocketmail.com",
    "inbox.com",
    "qq.com",
    "163.com",
    "126.com",
    "hotmail.co.uk",
    "yahoo.co.uk",
}

VERIFICATION_EMAIL_STATUS_NONE = "none"
VERIFICATION_EMAIL_STATUS_SENT = "sent"
VERIFICATION_EMAIL_STATUS_FAILED = "failed"
VERIFICATION_EMAIL_STATUS_BOUNCED = "bounced"
VERIFICATION_EMAIL_STATUS_CONFIRMED = "confirmed"

SUPPORTED_DOCUMENT_TYPES = {"payslip", "bank_statement"}


class VerificationEmailError(Exception):
    pass


class VerificationEmailConfigurationError(VerificationEmailError):
    pass


MX_LOOKUP_TIMEOUT = 10
SMTP_VERIFY_TIMEOUT = 10


def _is_free_email_domain(domain: str) -> bool:
    normalized = domain.lower().strip()
    if normalized in FREE_EMAIL_DOMAINS:
        return True
    return any(normalized.endswith("." + banned) for banned in FREE_EMAIL_DOMAINS)


def _resolve_mx_hosts(domain: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=MX_LOOKUP_TIMEOUT)
        hosts = sorted(
            (
                (record.preference, str(record.exchange).rstrip("."))
                for record in answers
            ),
            key=lambda item: item[0],
        )
        return [host for _, host in hosts]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.exception.Timeout):
        pass

    try:
        socket.getaddrinfo(domain, 25, proto=socket.IPPROTO_TCP)
        return [domain]
    except OSError:
        return []


def _check_email_recipient_exists(recipient: str, mx_hosts: list[str]) -> Optional[bool]:
    temporary_failure = False
    last_connection_error: Optional[Exception] = None
    hard_rejection = False
    sender = config.EMAIL_FROM or f"verify@{recipient.split('@', 1)[1]}"

    for host in mx_hosts:
        try:
            with smtplib.SMTP(host, 25, timeout=SMTP_VERIFY_TIMEOUT) as smtp:
                smtp.ehlo_or_helo_if_needed()
                smtp.mail(sender)
                code, _ = smtp.rcpt(recipient)
                if code in {250, 251}:
                    return True
                if code in {450, 451, 452}:
                    temporary_failure = True
                    continue
                if code in {550, 551, 552, 553, 554}:
                    hard_rejection = True
                    continue
                temporary_failure = True
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPRecipientsRefused, smtplib.SMTPResponseException, smtplib.SMTPException, OSError) as exc:
            last_connection_error = exc
            continue

    if hard_rejection:
        return False
    if temporary_failure or last_connection_error:
        logger.warning(
            "Unable to conclusively verify recipient %s at %s: temporary or connection failure.",
            recipient,
            mx_hosts,
        )
        return None
    return None


def _validate_email_exists(email: str) -> None:
    domain = email.split("@", 1)[1].lower()
    mx_hosts = _resolve_mx_hosts(domain)
    if not mx_hosts:
        raise VerificationEmailError(
            "Email domain does not accept mail or does not exist."
        )
    exists = _check_email_recipient_exists(email, mx_hosts)
    if exists is False:
        raise VerificationEmailError("Email address does not exist.")


def validate_verification_target(email: str) -> EmailStr:
    from pydantic import BaseModel

    class RecipientModel(BaseModel):
        email: EmailStr

    try:
        recipient = RecipientModel(email=email).email
    except Exception as exc:
        raise VerificationEmailError("Invalid email address") from exc

    # domain = str(recipient).split("@", 1)[1].lower()
    # if _is_free_email_domain(domain):
    #     raise VerificationEmailError(
    #         "Free email domains are not allowed for verification."
    #     )

    _validate_email_exists(str(recipient))
    return recipient


def _format_from_header() -> str:
    if config.EMAIL_FROM_NAME:
        return f"{config.EMAIL_FROM_NAME} <{config.EMAIL_FROM}>"
    return config.EMAIL_FROM


def _display_applicant_name(application: dict) -> str:
    return str(
        application.get("full_name")
        or application.get("applicant_name")
        or application.get("employee_name")
        or ""
    ).strip()


def _display_company_name(application: dict) -> str:
    return str(application.get("company_name") or "").strip()


def compose_verification_email(
    application: dict,
    document_type: str,
    target_email: str,
    verification_id: Optional[str] = None,
    attachment_path: Optional[str] = None,
    note: Optional[str] = None,
) -> EmailMessage:
    if document_type not in SUPPORTED_DOCUMENT_TYPES:
        raise VerificationEmailError(
            f"Unsupported document_type '{document_type}'. Use payslip or bank_statement."
        )

    # Subject must include the public verification id in the required format when provided.
    if verification_id:
        subject = f"[Application Verification: {verification_id}]"
    else:
        subject = (
            "Document Verification Request: "
            + ("Payslip" if document_type == "payslip" else "Bank Statement")
        )

    document_label = "Payslip" if document_type == "payslip" else "Bank Statement"
    verification_id_text = f"Verification ID: {verification_id}" if verification_id else ""
    applicant_name = _display_applicant_name(application)
    company_name = _display_company_name(application)
    applicant_html = html_escape(applicant_name)
    company_html = html_escape(company_name)
    target_email_html = html_escape(target_email)
    request_date_html = html_escape(str(application.get("request_date") or ""))
    note_section = (
        f"<p><strong>Branch note:</strong> {html_escape(note)}</p>" if note else ""
    )

    links_html = ""
    links_text = ""
    if verification_id:
        from app.services.verification_tokens import build_decision_urls

        accept_url, reject_url = build_decision_urls(verification_id)
        accept_html = html_escape(accept_url, quote=True)
        reject_html = html_escape(reject_url, quote=True)
        links_html = f"""
            <p style="margin:0 0 12px;font-size:0.95rem;line-height:1.6;">Please click one of the buttons below to record your decision:</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 24px;">
              <tr>
                <td align="center">
                  <table cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding-right:12px;">
                        <a href="{accept_html}" style="display:inline-block;background:#15803d;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:bold;font-size:0.95rem;">Accept</a>
                      </td>
                      <td>
                        <a href="{reject_html}" style="display:inline-block;background:#b91c1c;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:bold;font-size:0.95rem;">Reject</a>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
            <p style="margin:0 0 16px;font-size:0.82rem;color:#667085;line-height:1.5;">If the buttons do not work, copy and open one of these links:<br/>
            Accept: {accept_html}<br/>
            Reject: {reject_html}</p>
        """
        links_text = (
            "Please click one of the following links to record your decision:\n"
            f"Accept: {accept_url}\n"
            f"Reject: {reject_url}\n\n"
        )

    # Instruction block required at the end of every email per product spec.
    instructions_html = """
            <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;"/>
            <pre style="background:#f8fafc;padding:12px;border-radius:8px;font-size:0.85rem;">--------------------------------------------
Verification Instructions

Please click Accept or Reject in this email.

You may also reply using ONLY one of the following words.

Approved

Rejected

Do not include additional text.

Replies from any email address other than the intended recipient will be ignored automatically.
--------------------------------------------</pre>
    """

    html_body = f"""
    <html>
      <body style="font-family:Arial,Helvetica,sans-serif;color:#2e3a49;background:#f4f7fb;padding:0;margin:0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 0 32px rgba(15,23,42,0.08);">
          <tr><td style="padding:24px 32px;background:#0f4c81;color:#ffffff;text-align:center;">
            <h1 style="margin:0;font-size:1.4rem;letter-spacing:0.03em;">Company Verification Request</h1>
            <p style="margin:8px 0 0;font-size:0.95rem;">Please review the attached {document_label} submitted for verification.</p>
          </td></tr>
          <tr><td style="padding:28px 32px;">
            <p style="margin:0 0 16px;font-size:0.95rem;line-height:1.6;">Dear Sir/Madam,</p>
            <p style="margin:0 0 16px;font-size:0.95rem;line-height:1.6;">The bank is requesting confirmation of the attached document submitted by <strong>{applicant_html or "the applicant"}</strong>. Please verify whether this document is genuine and issued by your organisation.</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:18px 0 24px;">
              <tr><td style="background:#f0f4fb;padding:16px;border-radius:10px;">
                <p style="margin:0 0 10px;font-size:0.9rem;"><strong>Applicant name:</strong> {applicant_html}</p>
                <p style="margin:0 0 10px;font-size:0.9rem;"><strong>Company name:</strong> {company_html}</p>
                <p style="margin:0 0 10px;font-size:0.9rem;"><strong>Verification email:</strong> {target_email_html}</p>
                <p style="margin:0 0 10px;font-size:0.9rem;"><strong>Document type:</strong> {document_label}</p>
                <p style="margin:0;font-size:0.9rem;"><strong>Request date:</strong> {request_date_html}</p>
                <p style="margin:0;font-size:0.9rem;"><strong>{html_escape(verification_id_text)}</strong></p>
              </td></tr>
            </table>
            {note_section}
            {links_html}
            <p style="margin:0 0 16px;font-size:0.95rem;line-height:1.6;">If you are unable to confirm, let us know the appropriate contact for document validation.</p>
            <p style="margin:0;font-size:0.95rem;line-height:1.6;">Best regards,<br/>Document Verification Team</p>
          </td></tr>
                        <tr><td style="padding:0 32px 24px;">
                        <p style="margin:0;font-size:0.78rem;color:#667085;">This email was sent by the bank's secure document verification system. Do not reply from a free email account.</p>
                        {instructions_html}
                    </td></tr>
        </table>
      </body>
    </html>
    """

    plain_text = (
        f"Dear Sir/Madam,\n\n"
        f"Please verify whether the attached document submitted by {applicant_name} "
        f"is genuine and issued by your organisation.\n\n"
        f"Applicant name: {applicant_name}\n"
        f"Company name: {company_name}\n"
        f"Document type: {document_label}\n"
        f"{verification_id_text}\n\n"
        # f"{links_text}"
        f"You may also reply using ONLY one of the following words: Approved or Rejected\n"
        f"Do not include additional text. Replies from any email address other than the intended recipient will be ignored automatically.\n\n"
        f"Best regards,\n"
        f"Document Verification Team\n"
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _format_from_header()
    message["To"] = target_email
    message.set_content(plain_text)
    message.add_alternative(html_body, subtype="html")

    if attachment_path:
        path = Path(attachment_path)
        if not path.exists() or not path.is_file():
            raise VerificationEmailError("Attachment is missing for verification email.")
        mime_type, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        with path.open("rb") as file:
            message.add_attachment(
                file.read(),
                maintype=maintype,
                subtype=subtype,
                filename=path.name,
            )
    return message


def send_verification_email(message: EmailMessage) -> None:
    if not config.SMTP_HOST or not config.EMAIL_FROM:
        raise VerificationEmailConfigurationError(
            "SMTP host and from address must be configured to send verification emails."
        )

    try:
        if config.SMTP_USE_SSL:
            # Implicit SSL (SMTPS), commonly port 465
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_CONNECT_TIMEOUT) as smtp:
                if config.SMTP_USERNAME and config.SMTP_PASSWORD:
                    smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_CONNECT_TIMEOUT) as smtp:
                if config.SMTP_USE_TLS:
                    smtp.starttls()
                if config.SMTP_USERNAME and config.SMTP_PASSWORD:
                    smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                smtp.send_message(message)
    except Exception as exc:
        logger.exception("SMTP send failed for host %s:%s", config.SMTP_HOST, config.SMTP_PORT)
        raise VerificationEmailError(f"SMTP send failed: {exc}") from exc


def is_smtp_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_PORT and config.EMAIL_FROM)
