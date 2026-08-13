"""Index and search OCR / vision extracted document text for branch archival search."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Application, BranchEntry, BranchEntryDocument, DocumentArchive

logger = get_logger(__name__)

SOURCE_BRANCH_ENTRY = "branch_entry"
SOURCE_CUSTOMER_PORTAL = "customer_portal"

PORTAL_DOC_LABELS = {
    "cnic_front": "CNIC front",
    "cnic_back": "CNIC back",
    "payslip": "Payslip",
    "bank_statement": "Bank statement",
}

PORTAL_DOC_PATH_ATTR = {
    "cnic_front": "cnic_front_path",
    "cnic_back": "cnic_back_path",
    "payslip": "payslip_path",
    "bank_statement": "bank_statement_path",
}


def build_searchable_text(
    extracted_text: Optional[str],
    fields: Optional[dict] = None,
) -> str:
    parts: List[str] = []
    if extracted_text and str(extracted_text).strip():
        parts.append(str(extracted_text).strip())
    if fields:
        for key, value in fields.items():
            if value is None:
                continue
            text = str(value).strip()
            if text and text.lower() != "null":
                parts.append(f"{key}: {text}")
    return "\n".join(parts).strip()


def _upsert_archive_row(
    db: Session,
    *,
    branch_id: int,
    source: str,
    record_id: uuid.UUID,
    document_key: str,
    document_type: str,
    document_label: str,
    customer_name: str,
    original_filename: str,
    file_path: Optional[str],
    extracted_text: str,
    created_at: Optional[datetime] = None,
) -> None:
    text = (extracted_text or "").strip()
    if not text:
        return

    row = (
        db.query(DocumentArchive)
        .filter(
            DocumentArchive.branch_id == branch_id,
            DocumentArchive.source == source,
            DocumentArchive.record_id == record_id,
            DocumentArchive.document_key == document_key,
        )
        .first()
    )
    if row:
        row.document_type = document_type
        row.document_label = document_label
        row.customer_name = customer_name
        row.original_filename = original_filename
        row.file_path = file_path
        row.extracted_text = text
        row.indexed_at = datetime.utcnow()
        if created_at:
            row.created_at = created_at
        return

    db.add(
        DocumentArchive(
            branch_id=branch_id,
            source=source,
            record_id=record_id,
            document_key=document_key,
            document_type=document_type,
            document_label=document_label,
            customer_name=customer_name,
            original_filename=original_filename,
            file_path=file_path,
            extracted_text=text,
            created_at=created_at or datetime.utcnow(),
        )
    )


def index_branch_document(
    db: Session,
    entry: BranchEntry,
    doc: BranchEntryDocument,
    *,
    document_type_labels: Optional[Dict[str, str]] = None,
) -> None:
    labels = document_type_labels or {}
    text = build_searchable_text(doc.extracted_text, doc.fields_json)
    if not text:
        return
    _upsert_archive_row(
        db,
        branch_id=entry.branch_id,
        source=SOURCE_BRANCH_ENTRY,
        record_id=entry.id,
        document_key=str(doc.id),
        document_type=doc.document_type,
        document_label=labels.get(doc.document_type, doc.document_type),
        customer_name=entry.customer_name,
        original_filename=doc.original_filename or "",
        file_path=doc.file_path,
        extracted_text=text,
        created_at=doc.created_at or entry.created_at,
    )


def index_branch_entry(
    db: Session,
    entry: BranchEntry,
    *,
    document_type_labels: Optional[Dict[str, str]] = None,
) -> int:
    count = 0
    for doc in entry.documents or []:
        text = build_searchable_text(doc.extracted_text, doc.fields_json)
        if not text:
            continue
        index_branch_document(db, entry, doc, document_type_labels=document_type_labels)
        count += 1
    return count


def index_application_documents(
    db: Session,
    app: Application,
    extractions: Dict[str, str],
) -> int:
    count = 0
    for label, ocr_text in extractions.items():
        text = (ocr_text or "").strip()
        if not text:
            continue
        path_attr = PORTAL_DOC_PATH_ATTR.get(label)
        file_path = getattr(app, path_attr, None) if path_attr else None
        filename = file_path.rsplit("/", 1)[-1] if file_path else label
        _upsert_archive_row(
            db,
            branch_id=app.branch_id,
            source=SOURCE_CUSTOMER_PORTAL,
            record_id=app.id,
            document_key=label,
            document_type=label,
            document_label=PORTAL_DOC_LABELS.get(label, label),
            customer_name=app.full_name,
            original_filename=filename,
            file_path=file_path,
            extracted_text=text,
            created_at=app.created_at,
        )
        count += 1
    return count


def make_snippet(text: str, query: str, radius: int = 90) -> str:
    if not text or not query.strip():
        return (text or "")[: radius * 2]
    lower = text.lower()
    terms = [part for part in re.split(r"\s+", query.strip()) if part]
    hit_at = -1
    hit_len = 0
    for term in terms:
        idx = lower.find(term.lower())
        if idx >= 0 and (hit_at < 0 or idx < hit_at):
            hit_at = idx
            hit_len = len(term)
    if hit_at < 0:
        return text[: radius * 2] + ("…" if len(text) > radius * 2 else "")
    start = max(0, hit_at - radius)
    end = min(len(text), hit_at + hit_len + radius)
    snippet = text[start:end].replace("\n", " ")
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


def search_archives(
    db: Session,
    *,
    branch_id: int,
    query: str,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    q = query.strip()
    if not q:
        return {"query": q, "total": 0, "results": []}

    pattern = f"%{q}%"
    filters = [
        DocumentArchive.branch_id == branch_id,
        or_(
            DocumentArchive.extracted_text.ilike(pattern),
            DocumentArchive.customer_name.ilike(pattern),
            DocumentArchive.original_filename.ilike(pattern),
            DocumentArchive.document_label.ilike(pattern),
        ),
    ]
    if source and source not in ("", "all"):
        filters.append(DocumentArchive.source == source)

    base = db.query(DocumentArchive).filter(*filters)
    total = base.count()
    rows = (
        base.order_by(DocumentArchive.created_at.desc())
        .offset(max(0, offset))
        .limit(min(max(1, limit), 200))
        .all()
    )

    results = []
    for row in rows:
        if row.source == SOURCE_BRANCH_ENTRY:
            document_url = (
                f"/api/v1/branch/branch-entries/{row.record_id}/documents/{row.document_key}"
            )
            record_path = f"/branch/entries/{row.record_id}"
        else:
            document_url = (
                f"/api/v1/branch/applications/{row.record_id}/documents/{row.document_key}"
            )
            record_path = f"/branch/applications/{row.record_id}"

        suffix = (row.original_filename or row.file_path or "").lower()
        is_image = suffix.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"))
        is_pdf = suffix.endswith(".pdf")

        results.append(
            {
                "id": str(row.id),
                "source": row.source,
                "record_id": str(row.record_id),
                "document_key": row.document_key,
                "document_type": row.document_type,
                "document_label": row.document_label,
                "customer_name": row.customer_name,
                "original_filename": row.original_filename,
                "snippet": make_snippet(row.extracted_text, q),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "indexed_at": row.indexed_at.isoformat() if row.indexed_at else None,
                "document_url": document_url,
                "record_path": record_path,
                "is_image": is_image,
                "is_pdf": is_pdf,
            }
        )

    return {"query": q, "total": total, "results": results}


def backfill_branch_documents(db: Session, *, document_type_labels: Optional[Dict[str, str]] = None) -> int:
    """Index existing branch_entry_documents into document_archives."""
    from sqlalchemy.orm import joinedload

    entries = (
        db.query(BranchEntry)
        .options(joinedload(BranchEntry.documents))
        .order_by(BranchEntry.created_at.asc())
        .all()
    )
    indexed = 0
    for entry in entries:
        indexed += index_branch_entry(db, entry, document_type_labels=document_type_labels)
    return indexed
