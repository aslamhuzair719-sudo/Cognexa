"""Vision LLM implementation of the document gate."""

from __future__ import annotations

import ast
import json
from typing import Optional

from app.document_detection.detector import ImageSource
from app.document_detection.prompts import DOCUMENT_GATE_VISION_PROMPT
from app.document_detection.registry import normalize_detected_type
from app.document_detection.schemas import RawGateDetection
from app.logging_config import get_logger
from app.ocr_pipeline.llm_extract import _strip_json_fence
from app.services.llm_factory import call_llm_vision_source, llm_engine_label, supports_vision

logger = get_logger(__name__)


def _parse_gate_json(raw: str) -> dict:
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        parsed = ast.literal_eval(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    raise RuntimeError(f"LLM returned invalid JSON for document gate: {raw[:300]!r}")


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class LLMDocumentGateDetector:
    """Single vision request returning document presence + detected type."""

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        max_side: int = 1200,
    ) -> None:
        self.model = model
        self.max_side = max_side

    def detect(self, source: ImageSource, *, branch: bool = True) -> RawGateDetection:
        if not supports_vision():
            raise RuntimeError("Vision LLM unavailable for document gate")

        raw = call_llm_vision_source(
            source,
            DOCUMENT_GATE_VISION_PROMPT,
            model=self.model,
            max_side=self.max_side,
            branch=branch,
        )
        engine, used_model = llm_engine_label(vision=True)
        parsed = _parse_gate_json(raw)

        is_document = bool(parsed.get("is_document", False))
        detected_raw = parsed.get("detected_type", "unknown")
        detected = normalize_detected_type(detected_raw)
        if detected == "not_a_document" or str(detected_raw).strip().lower() == "not_a_document":
            is_document = False
            detected = "not_a_document"

        result = RawGateDetection(
            is_document=is_document,
            document_confidence=_to_float(parsed.get("document_confidence"), 0.0),
            detected_type=detected,
            type_confidence=_to_float(parsed.get("type_confidence"), 0.0),
            reason=str(parsed.get("reason") or "").strip(),
        )
        logger.info(
            "Document gate LLM: is_document=%s detected=%s doc_conf=%.1f type_conf=%.1f",
            result.is_document,
            result.detected_type,
            result.document_confidence,
            result.type_confidence,
        )
        result.meta = {"engine": engine, "model": used_model}  # type: ignore[attr-defined]
        return result
