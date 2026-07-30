"""Branch user authentication (session cookie)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.auth_utils import SESSION_USER_KEY, get_current_user, get_optional_user, verify_password
from app.db import get_db
from app.models import User
from app.services.audit import write_audit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "branch": {"code": user.branch.code, "name": user.branch.name},
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .options(joinedload(User.branch))
        .filter(User.username == payload.username.strip())
        .first()
    )
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    request.session[SESSION_USER_KEY] = user.id
    write_audit(
        db,
        action="user_login",
        message=f"Branch user {user.username} signed in",
        branch_id=user.branch_id,
        user_id=user.id,
        username=user.username,
        commit=True,
    )
    return {"ok": True, "user": _user_payload(user)}


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    if user:
        write_audit(
            db,
            action="user_logout",
            message=f"Branch user {user.username} signed out",
            branch_id=user.branch_id,
            user_id=user.id,
            username=user.username,
            commit=True,
        )
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_payload(user)
