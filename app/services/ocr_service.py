"""OCR service abstractions and Tesseract implementation."""

from __future__ import annotations

import io
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

import fitz
import pytesseract
from PIL import Image

from app import config
from app.logging_config import get_logger

logger = get_logger(__name__)
pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

ImageSource = Union[str, Path, bytes]


class BaseOCRService(ABC):
    """Abstract base class for OCR services."""

    @abstractmethod
    def extract_text(self, document_path: str) -> str:
        """Extract raw text from a document (PDF or image path)."""

    def extract_text_from_bytes(self, data: bytes, filename: str = "upload.bin") -> str:
        """Extract text from in-memory file bytes."""
        suffix = Path(filename).suffix.lower() or ".bin"
        tmp = config.UPLOAD_DIR / f"_ocr_tmp{suffix}"
        try:
            tmp.write_bytes(data)
            return self.extract_text(str(tmp))
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


class TesseractOCRService(BaseOCRService):
    """OCR via PyMuPDF embedded text when available, else Tesseract."""

    def extract_text(self, document_path: str) -> str:
        path = Path(document_path)
        suffix = path.suffix.lower()

        if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
            return self._ocr_image(path)

        return self._ocr_pdf_or_document(path)

    def _ocr_image(self, path: Path) -> str:
        logger.info("Running OCR on image: %s", path.name)
        with Image.open(path) as img:
            text = pytesseract.image_to_string(img)
        return text.strip()

    def _ocr_pdf_or_document(self, path: Path) -> str:
        logger.info("Extracting text from document: %s", path.name)
        doc = fitz.open(path)
        full_text = ""
        try:
            for page in doc:
                text = page.get_text().strip()
                if text and not self._is_text_garbage(text):
                    full_text += text + "\n"
                else:
                    logger.info(
                        "Page %s text appears unreliable; falling back to image OCR.",
                        page.number + 1,
                    )
                    pix = page.get_pixmap(dpi=config.OCR_DPI)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    full_text += pytesseract.image_to_string(img).strip() + "\n"
        finally:
            doc.close()
        return full_text.strip()

    def _is_text_garbage(self, text: str) -> bool:
        if not text:
            return True

        clean = text.strip()
        if len(clean) < 40:
            return True

        letters = sum(1 for c in clean if c.isalpha())
        if letters / max(1, len(clean)) < 0.35:
            return True

        words = re.findall(r"\b[A-Za-z]{3,}\b", clean)
        if len(words) < 5:
            return True

        common_words = {'the', 'and', 'for', 'with', 'from', 'date', 'name', 'account', 'branch', 'application', 'customer', 'company', 'employee'}
        valid_word_count = sum(1 for word in words if word.lower() in common_words)
        if valid_word_count / max(1, len(words)) < 0.12:
            return True

        return False
