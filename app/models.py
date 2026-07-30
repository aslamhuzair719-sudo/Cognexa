"""SQLAlchemy ORM models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ApplicationStatus(str, enum.Enum):
    pending = "pending"
    analyzing = "analyzing"
    completed = "completed"
    accepted = "accepted"
    rejected = "rejected"


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="branch")
    applications: Mapped[list["Application"]] = relationship(back_populates="branch")
    branch_entries: Mapped[list["BranchEntry"]] = relationship(back_populates="branch")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="branch_user")
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)

    branch: Mapped["Branch"] = relationship(back_populates="users")


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ApplicationStatus.pending.value,
        index=True,
    )

    # Personal
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    age: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    mobile_number: Mapped[str] = mapped_column(String(64), nullable=False)
    # Legacy field retained for older rows; no longer collected on the form.
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # CNIC information
    cnic_full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    father_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cnic_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    date_of_birth: Mapped[str] = mapped_column(String(64), nullable=False)
    cnic_issue_date: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    cnic_expiry_date: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    country_to_stay: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    gender: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    # Employment
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    designation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    monthly_income: Mapped[str] = mapped_column(String(64), nullable=False)

    # Document relative paths under APPLICATIONS_DIR
    cnic_front_path: Mapped[str] = mapped_column(String(512), nullable=False)
    cnic_back_path: Mapped[str] = mapped_column(String(512), nullable=False)
    payslip_path: Mapped[str] = mapped_column(String(512), nullable=False)
    bank_statement_path: Mapped[str] = mapped_column(String(512), nullable=False)

    report_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    analyzed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    branch: Mapped["Branch"] = relationship(back_populates="applications")
    decider: Mapped[Optional["User"]] = relationship(foreign_keys=[decided_by])


class BranchEntry(Base):
    """Branch-created customer record from scanned documents (Branch Entry)."""

    __tablename__ = "branch_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id"), nullable=False, index=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )

    branch: Mapped["Branch"] = relationship(back_populates="branch_entries")
    creator: Mapped[Optional["User"]] = relationship(foreign_keys=[created_by])
    documents: Mapped[list["BranchEntryDocument"]] = relationship(
        back_populates="branch_entry",
        cascade="all, delete-orphan",
        order_by="BranchEntryDocument.created_at",
    )


class BranchEntryDocument(Base):
    """One scanned document attached to a Branch Entry."""

    __tablename__ = "branch_entry_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    branch_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("branch_entries.id"), nullable=False, index=True
    )
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fields_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    checkboxes_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    branch_entry: Mapped["BranchEntry"] = relationship(back_populates="documents")


class SignatureRecord(Base):
    """Registered customer signature keyed by bank account number."""

    __tablename__ = "signature_records"
    __table_args__ = (UniqueConstraint("account_number", name="uq_signature_account_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    account_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )

    branch: Mapped["Branch"] = relationship()
    creator: Mapped[Optional["User"]] = relationship(foreign_keys=[created_by])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
