"""Persist registered signature images under uploads/signatures/."""

from __future__ import annotations

import uuid
from pathlib import Path

from app import config


def save_signature_image(
    record_id: uuid.UUID,
    filename: str,
    data: bytes,
) -> str:
    """Save a signature image and return path relative to SIGNATURES_DIR."""
    suffix = Path(filename).suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        suffix = ".png"
    dest = config.SIGNATURES_DIR / f"{record_id}{suffix}"
    dest.write_bytes(data)
    return dest.name


def resolve_signature_path(relative_path: str) -> Path:
    path = (config.SIGNATURES_DIR / relative_path).resolve()
    root = config.SIGNATURES_DIR.resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Invalid signature path")
    return path


def delete_signature_file(relative_path: str) -> None:
    try:
        path = resolve_signature_path(relative_path)
        if path.is_file():
            path.unlink()
    except ValueError:
        pass
