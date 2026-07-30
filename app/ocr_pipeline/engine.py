"""PaddleOCR engine wrapper — per-ROI recognition with angle classification."""

from __future__ import annotations

from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.logging_config import get_logger
from app.ocr_pipeline.config import PaddleOCRConfig

logger = get_logger(__name__)

_ENGINE_LOCK = Lock()
_ENGINE_SINGLETON: Optional["PaddleOCREngine"] = None


class PaddleOCREngine:
    """
    Lazy-loaded PaddleOCR singleton.

    Supports PaddleOCR 2.x (`use_angle_cls` + list results) and 3.x
    (`use_textline_orientation` + OCRResult / dict results).
    """

    def __init__(self, cfg: Optional[PaddleOCRConfig] = None):
        self.cfg = cfg or PaddleOCRConfig.from_env()
        self._ocr = None

    def _ensure_loaded(self) -> None:
        if self._ocr is not None:
            return
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ImportError(
                "paddleocr is required for remittance OCR. "
                "Install with: pip install paddlepaddle paddleocr"
            ) from exc

        logger.info(
            "Initializing PaddleOCR (lang=%s, angle_cls=%s, gpu=%s)",
            self.cfg.lang,
            self.cfg.use_angle_cls,
            self.cfg.use_gpu,
        )

        # Try PaddleOCR 2.x kwargs first (stable on Windows), then 3.x
        init_attempts = [
            {
                "lang": self.cfg.lang,
                "use_angle_cls": self.cfg.use_angle_cls,
                "show_log": self.cfg.show_log,
                "use_gpu": self.cfg.use_gpu,
            },
            {
                "lang": self.cfg.lang,
                "use_angle_cls": self.cfg.use_angle_cls,
            },
            {
                "lang": self.cfg.lang,
                "use_textline_orientation": self.cfg.use_angle_cls,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
            },
            {"lang": self.cfg.lang},
        ]
        last_err: Optional[Exception] = None
        for kwargs in init_attempts:
            try:
                self._ocr = PaddleOCR(**kwargs)
                logger.info("PaddleOCR ready with kwargs=%s", list(kwargs.keys()))
                return
            except TypeError as exc:
                last_err = exc
                continue
        raise RuntimeError(f"Could not initialize PaddleOCR: {last_err}")

    def recognize(
        self,
        image: np.ndarray,
        *,
        cls: Optional[bool] = None,
    ) -> Tuple[str, float, List[Dict[str, Any]]]:
        """
        OCR a single ROI image.

        Returns:
            text: joined line text
            confidence: mean recognition confidence (0–1)
            lines: per-line detail for debugging / audit
        """
        self._ensure_loaded()
        if image is None or image.size == 0:
            return "", 0.0, []

        use_cls = self.cfg.use_angle_cls if cls is None else cls
        result = self._run_ocr(image, use_cls=use_cls)
        return self._parse_result(result)

    def _run_ocr(self, image: np.ndarray, *, use_cls: bool) -> Any:
        """Call PaddleOCR across 2.x / 3.x method signatures."""
        # Prefer predict() on 3.x (cleaner API); fall back to ocr()
        if hasattr(self._ocr, "predict"):
            try:
                return self._ocr.predict(
                    image,
                    use_textline_orientation=use_cls,
                )
            except TypeError:
                try:
                    return self._ocr.predict(image)
                except Exception:
                    pass

        try:
            return self._ocr.ocr(image, cls=use_cls)
        except TypeError:
            return self._ocr.ocr(image)

    @staticmethod
    def _parse_result(result: Any) -> Tuple[str, float, List[Dict[str, Any]]]:
        """Normalize PaddleOCR output across 2.x / 3.x result shapes."""
        lines: List[Dict[str, Any]] = []
        if not result:
            return "", 0.0, lines

        # PaddleOCR 3.x: list of OCRResult / dict-like objects
        if isinstance(result, list) and result and not _looks_like_v2_page(result[0]):
            for page in result:
                lines.extend(_lines_from_v3_page(page))
            if lines:
                text = " ".join(line["text"] for line in lines).strip()
                conf = float(sum(line["confidence"] for line in lines) / len(lines))
                return text, conf, lines

        # Typical 2.x: [ [ [box, (text, conf)], ... ] ]  or None page
        page = result[0] if isinstance(result, list) else result
        if page is None:
            return "", 0.0, lines

        if isinstance(page, dict):
            lines.extend(_lines_from_v3_page(page))
        else:
            for item in page:
                if not item:
                    continue
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        payload = item[1]
                        if isinstance(payload, (list, tuple)) and len(payload) >= 2:
                            text, conf = payload[0], payload[1]
                        else:
                            text, conf = str(payload), 0.0
                        lines.append({"text": str(text), "confidence": float(conf)})
                except (TypeError, ValueError, IndexError):
                    continue

        if not lines:
            return "", 0.0, lines

        text = " ".join(line["text"] for line in lines).strip()
        conf = float(sum(line["confidence"] for line in lines) / len(lines))
        return text, conf, lines

    def recognize_many(
        self, crops: Dict[str, np.ndarray]
    ) -> Dict[str, Dict[str, Any]]:
        """OCR each ROI crop independently."""
        out: Dict[str, Dict[str, Any]] = {}
        for key, crop in crops.items():
            text, conf, lines = self.recognize(crop)
            out[key] = {
                "raw_text": text,
                "confidence": round(conf, 4),
                "lines": lines,
            }
            logger.debug("ROI %s → '%s' (conf=%.3f)", key, text[:80], conf)
        return out


def _looks_like_v2_page(page: Any) -> bool:
    """Heuristic: 2.x page is a list of [box, (text, score)] pairs."""
    if page is None:
        return True
    if isinstance(page, dict):
        return False
    # OCRResult objects from 3.x expose rec_texts / keys
    if hasattr(page, "keys") or hasattr(page, "get") or hasattr(page, "rec_texts"):
        # list of detection boxes looks like nested lists of numbers — treat carefully
        if isinstance(page, list) and page:
            first = page[0]
            if isinstance(first, (list, tuple)) and len(first) >= 2:
                return True
        return False
    if isinstance(page, list):
        return True
    return False


def _lines_from_v3_page(page: Any) -> List[Dict[str, Any]]:
    """Extract text/score pairs from a PaddleOCR 3.x page / OCRResult."""
    lines: List[Dict[str, Any]] = []
    data: Any = page
    if hasattr(page, "json") and callable(page.json):
        try:
            data = page.json
            if callable(data):
                data = data()
        except Exception:
            data = page
    if hasattr(page, "keys") and not isinstance(page, dict):
        # Mapping-like OCRResult
        try:
            data = dict(page)
        except Exception:
            data = page

    texts: List[Any] = []
    scores: List[Any] = []
    if isinstance(data, dict):
        # Common keys across paddlex OCRResult
        nested = data.get("res") if isinstance(data.get("res"), dict) else data
        texts = (
            nested.get("rec_texts")
            or nested.get("texts")
            or nested.get("rec_text")
            or []
        )
        scores = (
            nested.get("rec_scores")
            or nested.get("scores")
            or nested.get("rec_score")
            or []
        )
        if isinstance(texts, str):
            texts = [texts]
        if isinstance(scores, (int, float)):
            scores = [scores]
    else:
        # Attribute access on OCRResult
        texts = getattr(page, "rec_texts", None) or getattr(page, "texts", None) or []
        scores = getattr(page, "rec_scores", None) or getattr(page, "scores", None) or []

    if not scores:
        scores = [1.0] * len(list(texts))
    for text, score in zip(list(texts), list(scores)):
        if text is None:
            continue
        try:
            lines.append({"text": str(text), "confidence": float(score)})
        except (TypeError, ValueError):
            lines.append({"text": str(text), "confidence": 0.0})
    return lines


def get_paddle_engine(cfg: Optional[PaddleOCRConfig] = None) -> PaddleOCREngine:
    """Process-wide singleton — model load is expensive."""
    global _ENGINE_SINGLETON
    with _ENGINE_LOCK:
        if _ENGINE_SINGLETON is None:
            _ENGINE_SINGLETON = PaddleOCREngine(cfg)
        return _ENGINE_SINGLETON
