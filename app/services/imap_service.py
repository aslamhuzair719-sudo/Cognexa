"""IMAP client utilities for fetching unread verification replies."""

from __future__ import annotations

import imaplib
import logging
import re
from email import policy
from email.parser import BytesParser
from typing import Generator, List, Optional

from app import config

logger = logging.getLogger(__name__)


def _connect() -> imaplib.IMAP4:
    # Basic configuration validation
    if not config.IMAP_HOST or not config.IMAP_USERNAME or not config.IMAP_PASSWORD:
        raise RuntimeError("IMAP is not configured (IMAP_HOST/IMAP_USERNAME/IMAP_PASSWORD required)")
    if config.IMAP_USE_SSL:
        client = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    else:
        client = imaplib.IMAP4(config.IMAP_HOST, config.IMAP_PORT)
    client.login(config.IMAP_USERNAME, config.IMAP_PASSWORD)
    return client


# Outgoing verification emails use: [Application Verification: VER-...]
# Replies typically keep that text in the subject (often with Re:/Fwd:).
VERIFICATION_SUBJECT_MARKER = "[Application Verification:"


def is_verification_reply_subject(subject: str) -> bool:
    """True when the subject looks like a verification request/reply."""
    if not subject:
        return False
    return VERIFICATION_SUBJECT_MARKER.lower() in subject.lower()


def fetch_unread_messages() -> List[dict]:
    """Fetch unread verification-reply candidates from INBOX.

    Only messages whose subject contains ``[Application Verification:`` are returned,
    so normal inbox mail is left unread and untouched.

    Returns a list of dicts with keys: subject, from, message_id, raw, email_message
    """
    # Skip if IMAP is not configured
    if not config.IMAP_HOST or not config.IMAP_USERNAME or not config.IMAP_PASSWORD:
        logger.info("IMAP not configured; skipping fetch_unread_messages")
        return []

    try:
        client = _connect()
    except Exception:
        logger.exception("IMAP connection failed (check IMAP_HOST/PORT and network connectivity)")
        return []

    results: List[dict] = []
    try:
        client.select("INBOX")
        # Prefer server-side SUBJECT filter to avoid downloading unrelated unread mail.
        typ, data = client.search(None, "UNSEEN", "SUBJECT", '"Application Verification"')
        if typ != "OK":
            logger.warning("IMAP search returned non-OK: %s", typ)
            return []
        ids = data[0].split() if data and data[0] else []
        for num in ids:
            try:
                logger.debug("Fetching message uid=%s", num)
                typ, msg_data = client.fetch(num, "RFC822")
                if typ != "OK":
                    logger.warning("IMAP fetch failed for %s: %s", num, typ)
                    continue
                raw = msg_data[0][1]
                msg = BytesParser(policy=policy.default).parsebytes(raw)
                subject = msg.get("Subject", "")
                from_hdr = msg.get("From", "")
                message_id = msg.get("Message-ID") or msg.get("Message-Id")
                if not is_verification_reply_subject(subject):
                    logger.debug("Skipping non-verification subject: %s", subject)
                    continue
                logger.debug("Fetched message num=%s subject=%s from=%s", num, subject, from_hdr)
                results.append({
                    "num": num,
                    "subject": subject,
                    "from": from_hdr,
                    "message_id": message_id,
                    "raw": raw,
                    "email_message": msg,
                })
            except Exception:
                logger.exception("Failed to fetch/parse message %s", num)
                continue
    finally:
        try:
            client.logout()
        except Exception:
            pass
    return results


def mark_seen(uid: bytes) -> None:
    try:
        client = _connect()
        client.select("INBOX")
        client.store(uid, "+FLAGS", r"(\Seen)")
        client.logout()
    except Exception:
        logger.exception("Failed to mark message seen: %s", uid)


def extract_verification_id(subject: str) -> Optional[str]:
    if not subject:
        return None
    m = re.search(r"(VER-[A-Za-z0-9\-]+)", subject)
    if m:
        return m.group(1)
    return None


def extract_plain_text(msg) -> str:
    # prefer text/plain
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get_content_disposition() or "")
            if ctype == "text/plain" and disp != "attachment":
                return part.get_content()
        # fallback to first text/*
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                return part.get_content()
        return ""
    return msg.get_content()


def _clean_reply_text(text: str) -> str:
    if not text:
        return ""
    lines: list[str] = []
    for raw_line in text.splitlines():
        if re.match(r"^\s*On .*wrote:", raw_line, re.I):
            break
        if re.match(r"^\s*[-]+\s*Original Message\s*[-]+", raw_line, re.I):
            break
        if re.match(r"^\s*From:\s", raw_line, re.I):
            break
        if re.match(r"^\s*Sent from my", raw_line, re.I):
            break
        if raw_line.strip().startswith(">"):
            continue
        lines.append(raw_line)
    return "\n".join(lines).strip()


def parse_reply_first_meaningful_line(text: str) -> str:
    """Return the most likely reply line, preferring explicit Approved/Rejected text."""
    if not text:
        return ""
    text = _clean_reply_text(text)
    candidate = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # ignore quoted reply lines
        if line.startswith(">"):
            continue
        if line.startswith("--"):
            break
        # ignore common mobile signatures or trailing metadata
        if re.match(r"^sent from my", line, re.I):
            break
        if re.search(r"^(from|to|subject|date):\s", line, re.I):
            continue
        normalized = normalize_reply_text(line)
        if normalized in {"approved", "rejected"}:
            return line
        if re.match(r"^(dear|hi|hello|regards|best regards|thank you|thanks)(\b|[ ,.!])", line, re.I):
            continue
        if not candidate:
            candidate = line
    if candidate:
        return candidate
    for raw_line in text.splitlines():
        normalized = normalize_reply_text(raw_line)
        if normalized in {"approved", "rejected"}:
            return raw_line.strip()
    return ""


def normalize_reply_text(line: str) -> str:
    import string

    if not line:
        return ""
    s = line.strip().lower()
    # remove punctuation
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s
