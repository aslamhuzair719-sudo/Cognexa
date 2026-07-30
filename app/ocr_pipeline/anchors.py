"""
Detect dark section header bars on UBL remittance forms and use them as
vertical anchors so percentage field ROIs stay locked even when the
warped crop includes/excludes variable top margins.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)


def _row_dark_bands(
    gray: np.ndarray,
    *,
    dark_thresh: int = 110,
    min_dark_ratio: float = 0.35,
    min_height: int = 8,
    max_height_ratio: float = 0.05,
    merge_gap: int = 3,
) -> List[Tuple[int, int]]:
    """
    Find vertical spans (y0, y1) of wide dark header bars via row ink density.
    """
    h, w = gray.shape[:2]
    dark_ratio = (gray < dark_thresh).mean(axis=1)
    peaks = np.where(dark_ratio >= min_dark_ratio)[0]
    if peaks.size == 0:
        return []

    bands: List[Tuple[int, int]] = []
    start = int(peaks[0])
    prev = int(peaks[0])
    for y in peaks[1:]:
        y = int(y)
        if y <= prev + merge_gap:
            prev = y
        else:
            if prev - start + 1 >= min_height:
                bands.append((start, prev))
            start = prev = y
    if prev - start + 1 >= min_height:
        bands.append((start, prev))

    max_h = int(h * max_height_ratio)
    filtered = [(a, b) for a, b in bands if (b - a + 1) <= max_h]
    # Drop the very bottom footer strip if present
    filtered = [(a, b) for a, b in filtered if a < int(h * 0.92)]
    return filtered


def detect_section_anchors(color_image: np.ndarray) -> Dict[str, float]:
    """
    Return normalized Y positions (0–1) for section headers.

    Falls back to layout priors if detection is incomplete.
    """
    if color_image.ndim == 3:
        gray = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = color_image
    h = gray.shape[0]

    priors = {
        "page_top": 0.0,
        "remittance_details": 0.015,
        "beneficiary_details": 0.215,
        "applicant_details": 0.470,
        "purpose_of_remittance": 0.720,
        "declaration": 0.820,
        "page_bottom": 1.0,
    }

    bands = _row_dark_bands(gray)
    if len(bands) < 2:
        logger.warning(
            "Only %d header band(s) found — using layout priors for anchors",
            len(bands),
        )
        return priors

    # On this form the first dark bar is Remittance Details (page often crops
    # the logo/date row). Map subsequent bars in document order.
    key_order = [
        "remittance_details",
        "beneficiary_details",
        "applicant_details",
        "purpose_of_remittance",
        "declaration",
    ]
    anchors = dict(priors)
    for i, key in enumerate(key_order):
        if i >= len(bands):
            break
        y0, y1 = bands[i]
        anchors[key] = ((y0 + y1) / 2.0) / h

    # If purpose/declaration missing, estimate from applicant
    if len(bands) == 3:
        anchors["purpose_of_remittance"] = min(0.95, anchors["applicant_details"] + 0.25)
        anchors["declaration"] = min(0.97, anchors["purpose_of_remittance"] + 0.10)

    logger.info(
        "Section anchors (norm Y): remittance=%.3f beneficiary=%.3f applicant=%.3f purpose=%.3f",
        anchors["remittance_details"],
        anchors["beneficiary_details"],
        anchors["applicant_details"],
        anchors["purpose_of_remittance"],
    )
    return anchors


def resolve_box(
    meta: Dict[str, Any],
    anchors: Dict[str, float],
) -> Tuple[float, float, float, float]:
    """
    Resolve a field box to absolute normalized [x, y, w, h].

      1) Absolute:  "box": [x, y, w, h]
      2) Anchored:  "anchor": "applicant_details",
                    "offset": [x, dy, w, h]
    """
    if "offset" in meta and meta.get("anchor"):
        anchor_key = str(meta["anchor"])
        base_y = float(anchors.get(anchor_key, anchors.get("page_top", 0.0)))
        ox, dy, ow, oh = meta["offset"]
        return (
            float(ox),
            float(base_y) + float(dy),
            float(ow),
            float(oh),
        )

    box = meta.get("box")
    if not box or len(box) != 4:
        raise ValueError("Field must define 'box' or 'anchor'+'offset'")
    return float(box[0]), float(box[1]), float(box[2]), float(box[3])


def draw_anchor_overlay(
    color_image: np.ndarray,
    anchors: Dict[str, float],
) -> np.ndarray:
    """Debug: draw horizontal lines at detected section anchors."""
    canvas = color_image.copy()
    h, w = canvas.shape[:2]
    for name, ny in anchors.items():
        if name in {"page_top", "page_bottom"}:
            continue
        y = int(ny * h)
        cv2.line(canvas, (0, y), (w, y), (255, 0, 255), 1)
        cv2.putText(
            canvas,
            name,
            (8, max(12, y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 0, 255),
            1,
            cv2.LINE_AA,
        )
    return canvas
