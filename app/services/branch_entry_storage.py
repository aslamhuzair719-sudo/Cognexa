"""Persist branch-entry scan uploads under uploads/branch_entries/{id}/."""

from __future__ import annotations

import uuid
from pathlib import Path

from app import config


def branch_entry_dir(entry_id: uuid.UUID) -> Path:
    path = config.BRANCH_ENTRIES_DIR / str(entry_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_branch_entry_document(
    entry_id: uuid.UUID,
    doc_id: uuid.UUID,
    filename: str,
    data: bytes,
) -> str:
    """Save a document and return path relative to BRANCH_ENTRIES_DIR."""
    suffix = Path(filename).suffix.lower() or ".bin"
    dest = branch_entry_dir(entry_id) / f"{doc_id}{suffix}"
    dest.write_bytes(data)
    return f"{entry_id}/{dest.name}"


def resolve_branch_entry_path(relative_path: str) -> Path:
    path = (config.BRANCH_ENTRIES_DIR / relative_path).resolve()
    root = config.BRANCH_ENTRIES_DIR.resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid document path")
    return path
