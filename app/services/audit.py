"""Audit log helpers."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    message: str,
    branch_id: Optional[int] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    application_id: Optional[uuid.UUID | str] = None,
    details: Optional[dict[str, Any]] = None,
    commit: bool = False,
) -> AuditLog:
    app_uuid = None
    if application_id is not None:
        app_uuid = uuid.UUID(str(application_id))

    entry = AuditLog(
        branch_id=branch_id,
        user_id=user_id,
        username=username,
        application_id=app_uuid,
        action=action,
        message=message,
        details=details or {},
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return entry
