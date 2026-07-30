"""
Checkbox / tick-mark detection for fixed-layout banking forms.

OCR cannot reliably read empty vs filled boxes. This module classifies a
cropped checkbox ROI by measuring dark ink inside the box interior and
returns a Python bool (JSON true / false).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from app.logging_config import get_logger

logger = get_logger(__name__)

# Interior dark-pixel ratio above this → checked
DEFAULT_FILL_THRESHOLD = 0.06
# Absolute gray level below this counts as ink (on typical white paper)
DEFAULT_INK_LEVEL = 150


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _interior_gray(gray: np.ndarray, inset_ratio: float = 0.22) -> np.ndarray:
    """Crop the central region so printed box borders are excluded."""
    h, w = gray.shape[:2]
    inset_y = max(1, int(h * inset_ratio))
    inset_x = max(1, int(w * inset_ratio))
    if h - 2 * inset_y < 3 or w - 2 * inset_x < 3:
        return gray
    return gray[inset_y : h - inset_y, inset_x : w - inset_x]


def detect_checkbox(
    crop: np.ndarray,
    *,
    fill_threshold: float = DEFAULT_FILL_THRESHOLD,
    ink_level: int = DEFAULT_INK_LEVEL,
) -> Tuple[bool, float]:
    """
    Decide whether a checkbox ROI is marked.

    Uses a hard darkness threshold on the box *interior* (borders excluded)
    so empty printed squares stay false and ticks / X / fills become true.

    Returns:
        checked: True if tick / cross / fill is present
        fill_ratio: fraction of interior pixels that are ink (0–1)
    """
    gray = _to_gray(crop)
    if gray.size == 0 or min(gray.shape[:2]) < 4:
        return False, 0.0

    # Light blur — phone JPEG noise without wiping thin pen strokes
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    interior = _interior_gray(blur)

    # Relative cutoff: ink is clearly darker than paper mean
    paper_ref = float(np.percentile(interior, 85))
    cutoff = min(ink_level, paper_ref - 35)
    ink = interior < cutoff
    fill_ratio = float(np.count_nonzero(ink)) / float(ink.size)

    # Require a coherent stroke, not a few JPEG speckles
    ink_u8 = (ink.astype(np.uint8) * 255)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(ink_u8, connectivity=8)
    largest_blob = 0
    for label in range(1, num_labels):
        largest_blob = max(largest_blob, int(stats[label, cv2.CC_STAT_AREA]))
    blob_ratio = largest_blob / float(ink.size)

    checked = fill_ratio >= fill_threshold and blob_ratio >= (fill_threshold * 0.5)
    return checked, round(fill_ratio, 4)


def detect_checkboxes(
    crops: Dict[str, np.ndarray],
    *,
    fill_threshold: float = DEFAULT_FILL_THRESHOLD,
) -> Dict[str, Dict[str, Any]]:
    """Run detection on every checkbox ROI crop."""
    out: Dict[str, Dict[str, Any]] = {}
    for key, crop in crops.items():
        checked, ratio = detect_checkbox(crop, fill_threshold=fill_threshold)
        out[key] = {
            "checked": checked,
            "fill_ratio": ratio,
            "confidence": round(min(1.0, abs(ratio - fill_threshold) * 4 + 0.5), 4),
        }
        logger.debug("Checkbox %s → %s (fill=%.3f)", key, checked, ratio)
    return out


# Human-readable purpose labels for checked purpose_* boxes
PURPOSE_LABELS: Dict[str, str] = {
    "purpose_family_maintenance": "Family Maintenance",
    "purpose_education": "Education",
    "purpose_medical": "Medical Treatment",
    "purpose_gift": "Gift / Donation",
    "purpose_investment": "Investment",
    "purpose_business": "Business / Trade",
    "purpose_other": "Other",
}


def purpose_from_checkboxes(checkboxes: Dict[str, bool]) -> Optional[str]:
    """Pick the first checked purpose option as a display string."""
    for key, label in PURPOSE_LABELS.items():
        if checkboxes.get(key):
            return label
    return None
