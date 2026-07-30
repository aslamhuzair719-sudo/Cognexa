"""
Remittance OCR pipeline orchestrator.

Flow:
  image → detect → perspective → deskew → resize to fixed template
        → CLAHE / threshold / line removal
        → normalized ROI crops (never full-page OCR)
        → PaddleOCR per text field + checkbox ink detect
        → post-process → validate → JSON
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np

from app.logging_config import get_logger
from app.ocr_pipeline.checkbox import (
    detect_checkboxes,
    purpose_from_checkboxes,
)
from app.ocr_pipeline.anchors import (
    detect_section_anchors,
    draw_anchor_overlay,
)
from app.ocr_pipeline.config import (
    PipelineConfig,
    apply_template_size_to_config,
    load_roi_template,
)
from app.ocr_pipeline.engine import PaddleOCREngine, get_paddle_engine
from app.ocr_pipeline.postprocess import clean_field_text
from app.ocr_pipeline.preprocessing import preprocess_image
from app.ocr_pipeline.roi import (
    draw_roi_overlay,
    extract_all_rois,
    extract_checkbox_rois,
    find_roi_overlaps,
    load_rois,
    log_roi_geometry,
    save_low_confidence_crops,
)
from app.ocr_pipeline.validators import FIELD_TYPE_BY_KEY, validate_fields

logger = get_logger(__name__)

ImageSource = Union[str, Path, bytes, np.ndarray]

# Canonical empty payload matching the required output schema
EMPTY_FIELDS: Dict[str, str] = {
    "date": "",
    "applicant_name": "",
    "father_name": "",
    "cnic": "",
    "mobile": "",
    "beneficiary_name": "",
    "beneficiary_account": "",
    "amount_figures": "",
    "amount_words": "",
    "branch_code": "",
    "cheque_number": "",
    "purpose": "",
    "occupation": "",
    "address": "",
}

# Checkbox keys → default unchecked (JSON false)
EMPTY_CHECKBOXES: Dict[str, bool] = {
    "non_account_holder": False,
    "cash_transfer": False,
    "cashiers_cheque": False,
    "online_transfer": False,
    "currency_pkr": False,
    "purpose_family_maintenance": False,
    "purpose_education": False,
    "purpose_medical": False,
    "purpose_gift": False,
    "purpose_investment": False,
    "purpose_business": False,
    "purpose_other": False,
    # Legacy aliases kept for API compatibility
    "cash": False,
    "cheque_mode": False,
    "account_debit": False,
}


class RemittanceOCRPipeline:
    """Production ROI-based OCR pipeline for UBL remittance forms."""

    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        engine: Optional[PaddleOCREngine] = None,
    ):
        self.config = config or PipelineConfig.default()
        self.template = load_roi_template(self.config.roi_template_path)
        apply_template_size_to_config(self.config.preprocess, self.template)
        self.form_id = str(self.template.get("form_id") or "ubl_remittance")
        self.engine = engine or get_paddle_engine(self.config.paddle)
        # Placeholder — rematerialized per image after header detection
        self.rois = load_rois(self.config.roi_template_path)

    def process(
        self,
        source: ImageSource,
        *,
        include_debug: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the full remittance OCR pipeline.

        Returns structured JSON with string fields, boolean checkboxes,
        validation, and meta.
        """
        debug_dir = None
        if self.config.save_debug_images or include_debug:
            debug_dir = Path(self.config.debug_dir or "uploads/ocr_debug")
            debug_dir.mkdir(parents=True, exist_ok=True)

        # 1) Preprocess → fixed template canvas
        warped_color, ocr_gray, ocr_binary = preprocess_image(
            source,
            cfg=self.config.preprocess,
            debug_dir=debug_dir,
        )
        img_h, img_w = ocr_gray.shape[:2]

        # 2) Detect section headers → materialize ROIs against live anchors
        anchors = detect_section_anchors(warped_color)
        self.rois = load_rois(self.config.roi_template_path, anchors=anchors)

        # 3) Geometry log + overlap report (before OCR)
        geometry = log_roi_geometry(self.rois, img_w, img_h)
        overlaps = find_roi_overlaps(self.rois, img_w, img_h)
        if overlaps:
            logger.warning("Found %d ROI overlap pair(s)", len(overlaps))

        if debug_dir is not None:
            overlay = draw_roi_overlay(warped_color, self.rois)
            cv2.imwrite(str(debug_dir / "roi_overlay.png"), overlay)
            cv2.imwrite(str(debug_dir / "03_roi_overlay.png"), overlay)
            cv2.imwrite(
                str(debug_dir / "03b_anchors.png"),
                draw_anchor_overlay(warped_color, anchors),
            )

        # 4) Crop individual fields from CLAHE grayscale (never full-page OCR)
        #    Harsh binary destroys handwriting — PaddleOCR gets soft gray crops.
        crops = extract_all_rois(
            ocr_gray,
            self.rois,
            cfg=self.config.preprocess,
            debug_dir=debug_dir,
        )
        checkbox_crops = extract_checkbox_rois(
            warped_color,
            self.rois,
            debug_dir=debug_dir,
        )

        # 4) Per-ROI OCR
        raw_results = self.engine.recognize_many(crops)

        # 5) Checkbox ink detection → true / false
        checkbox_raw = detect_checkboxes(checkbox_crops)
        checkboxes = dict(EMPTY_CHECKBOXES)
        checkbox_meta: Dict[str, Any] = {}
        for key, payload in checkbox_raw.items():
            checkboxes[key] = bool(payload["checked"])
            checkbox_meta[key] = {
                "fill_ratio": payload["fill_ratio"],
                "confidence": payload["confidence"],
            }
        # Map new payment checkboxes onto legacy aliases when useful
        if checkboxes.get("cash_transfer"):
            checkboxes["cash"] = True
        if checkboxes.get("cashiers_cheque"):
            checkboxes["cheque_mode"] = True

        # 6) Post-process text fields + confidence logging
        fields: Dict[str, Any] = dict(EMPTY_FIELDS)
        confidences: Dict[str, float] = {}
        raw_texts: Dict[str, str] = {}

        roi_by_key = {r.key: r for r in self.rois}
        for key, payload in raw_results.items():
            raw = payload.get("raw_text") or ""
            conf = float(payload.get("confidence") or 0.0)
            confidences[key] = conf
            raw_texts[key] = raw
            roi = roi_by_key.get(key)
            field_type = (
                roi.field_type if roi else FIELD_TYPE_BY_KEY.get(key, "text")
            )
            cleaned = clean_field_text(raw, field_type) if key in fields else ""
            if key in fields:
                fields[key] = cleaned
            logger.info(
                "OCR %-28s conf=%.3f raw=%r → %r",
                key,
                conf,
                (raw[:80] if raw else ""),
                (cleaned[:80] if cleaned else ""),
            )

        # Low-confidence debug dumps
        low_conf_saved: List[str] = []
        if debug_dir is not None:
            low_conf_saved = save_low_confidence_crops(
                crops,
                confidences,
                debug_dir,
                threshold=self.config.preprocess.low_confidence_threshold,
            )

        # Derive purpose from checked purpose boxes when write-in empty
        if not (fields.get("purpose") or "").strip():
            derived = purpose_from_checkboxes(checkboxes)
            if derived:
                fields["purpose"] = derived

        fields.update(checkboxes)

        # 7) Validation
        validation = validate_fields(fields)

        # 8) Structured output
        result: Dict[str, Any] = dict(fields)
        result["checkboxes"] = {
            k: bool(checkboxes.get(k, False)) for k in EMPTY_CHECKBOXES
        }
        result["validation"] = validation
        result["meta"] = {
            "form_id": self.form_id,
            "engine": "paddleocr+checkbox",
            "template_size": [img_w, img_h],
            "roi_count": len(crops) + len(checkbox_crops),
            "confidences": confidences,
            "checkbox_meta": checkbox_meta,
            "raw_texts": raw_texts,
            "roi_geometry": geometry,
            "roi_overlaps": overlaps,
            "section_anchors": {k: round(v, 4) for k, v in anchors.items()},
            "low_confidence_rois": low_conf_saved,
            "preprocess": self.config.preprocess.to_dict(),
            "image_shape": list(ocr_gray.shape),
            "binary_shape": list(ocr_binary.shape),
            "debug_dir": str(debug_dir) if debug_dir else None,
        }
        if include_debug:
            result["meta"]["lines"] = {
                k: v.get("lines") for k, v in raw_results.items()
            }

        logger.info(
            "Remittance OCR complete: valid=%s errors=%s checked=%s overlaps=%s low_conf=%s",
            validation["is_valid"],
            len(validation["errors"]),
            sum(1 for v in checkboxes.values() if v),
            len(overlaps),
            len(low_conf_saved),
        )
        return result

    def extract_fields(self, source: ImageSource) -> Dict[str, Any]:
        """Return only the canonical field dict (no meta/validation)."""
        full = self.process(source)
        out: Dict[str, Any] = {k: full.get(k, "") for k in EMPTY_FIELDS}
        out.update({k: bool(full.get(k, False)) for k in EMPTY_CHECKBOXES})
        out["checkboxes"] = {
            k: bool(full.get(k, False)) for k in EMPTY_CHECKBOXES
        }
        return out


def process_remittance_image(
    source: ImageSource,
    *,
    config: Optional[PipelineConfig] = None,
    include_debug: bool = False,
) -> Dict[str, Any]:
    """Module-level convenience entrypoint."""
    return RemittanceOCRPipeline(config=config).process(
        source, include_debug=include_debug
    )
