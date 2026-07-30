"""Password hashing and session helpers."""

from __future__ import annotations

from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import User

SESSION_USER_KEY = "user_id"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = (
        db.query(User)
        .options(joinedload(User.branch))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        return None
    return (
        db.query(User)
        .options(joinedload(User.branch))
        .filter(User.id == user_id)
        .first()
    )
