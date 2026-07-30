"""Seed hardcoded branches and branch users."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.auth_utils import hash_password
from app.logging_config import get_logger
from app.models import Branch, User

logger = get_logger(__name__)

BRANCHES = [
    {"code": "airport", "name": "Airport Branch"},
    {"code": "shah_faisal", "name": "Shahrae Faisal Branch"},
]

USERS = [
    {
        "username": "airport",
        "password": "Airport@123",
        "branch_code": "airport",
    },
    {
        "username": "shahfaisal",
        "password": "ShahFaisal@123",
        "branch_code": "shah_faisal",
    },
]


def seed_branches_and_users(db: Session) -> None:
    code_to_branch: dict[str, Branch] = {}
    for item in BRANCHES:
        branch = db.query(Branch).filter(Branch.code == item["code"]).first()
        if not branch:
            branch = Branch(code=item["code"], name=item["name"])
            db.add(branch)
            db.flush()
            logger.info("Seeded branch %s", item["code"])
        code_to_branch[item["code"]] = branch

    for item in USERS:
        existing = db.query(User).filter(User.username == item["username"]).first()
        if existing:
            continue
        branch = code_to_branch[item["branch_code"]]
        user = User(
            username=item["username"],
            password_hash=hash_password(item["password"]),
            role="branch_user",
            branch_id=branch.id,
        )
        db.add(user)
        logger.info("Seeded user %s for branch %s", item["username"], item["branch_code"])
