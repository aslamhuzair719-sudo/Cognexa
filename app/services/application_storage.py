"""Persist application uploads under uploads/applications/{id}/."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict

from app import config


DOC_LABELS = ("cnic_front", "cnic_back", "payslip", "bank_statement")


def application_dir(application_id: uuid.UUID) -> Path:
    path = config.APPLICATIONS_DIR / str(application_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_application_document(
    application_id: uuid.UUID,
    label: str,
    filename: str,
    data: bytes,
) -> str:
    """Save a document and return path relative to APPLICATIONS_DIR."""
    suffix = Path(filename).suffix.lower() or ".bin"
    safe_label = label.replace("..", "")
    dest = application_dir(application_id) / f"{safe_label}{suffix}"
    dest.write_bytes(data)
    return f"{application_id}/{dest.name}"


def resolve_document_path(relative_path: str) -> Path:
    path = (config.APPLICATIONS_DIR / relative_path).resolve()
    root = config.APPLICATIONS_DIR.resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid document path")
    return path


def document_paths_map(application) -> Dict[str, Path]:
    return {
        "cnic_front": resolve_document_path(application.cnic_front_path),
        "cnic_back": resolve_document_path(application.cnic_back_path),
        "payslip": resolve_document_path(application.payslip_path),
        "bank_statement": resolve_document_path(application.bank_statement_path),
    }
