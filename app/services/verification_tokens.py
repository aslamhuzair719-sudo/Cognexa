"""Encrypted Accept / Reject tokens for company verification emails."""

from __future__ import annotations

from typing import Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import config

DECISION_SALT = "verification-email-decision"
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days
DecisionAction = Literal["accept", "reject"]


class VerificationLinkError(Exception):
    pass


def _serializer() -> URLSafeTimedSerializer:
    secret = config.VERIFICATION_LINK_SECRET or config.SESSION_SECRET
    return URLSafeTimedSerializer(secret, salt=DECISION_SALT)


def create_decision_token(verification_id: str, action: DecisionAction) -> str:
    if action not in {"accept", "reject"}:
        raise VerificationLinkError("Decision action must be accept or reject.")
    return _serializer().dumps({"vid": verification_id, "action": action})


def decode_decision_token(token: str) -> dict:
    try:
        payload = _serializer().loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise VerificationLinkError("This verification link has expired.") from exc
    except BadSignature as exc:
        raise VerificationLinkError("This verification link is invalid.") from exc

    action = (payload or {}).get("action")
    verification_id = (payload or {}).get("vid")
    if not verification_id or action not in {"accept", "reject"}:
        raise VerificationLinkError("This verification link is invalid.")
    return {"vid": verification_id, "action": action}


def build_decision_url(verification_id: str, action: DecisionAction) -> str:
    token = create_decision_token(verification_id, action)
    return f"{config.PUBLIC_BASE_URL}/verify/{token}"


def build_decision_urls(verification_id: str) -> tuple[str, str]:
    return (
        build_decision_url(verification_id, "accept"),
        build_decision_url(verification_id, "reject"),
    )
