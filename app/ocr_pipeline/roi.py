"""
Region-of-Interest extraction for fixed-layout banking forms.

OCR is never run on the full page. Each field is cropped from the
template-sized warped document using normalized [x, y, w, h] boxes
(fractions of width/height) defined in the ROI JSON template.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from app.logging_config import get_logger
from app.ocr_pipeline.config import PreprocessConfig, load_roi_template

logger = get_logger(__name__)

# Distinct BGR colors for debug overlay (cycles if more ROIs than colors)
_ROI_COLORS: List[Tuple[int, int, int]] = [
    (0, 180, 0),
    (255, 128, 0),
    (0, 128, 255),
    (180, 0, 255),
    (0, 220, 220),
    (220, 0, 120),
    (40, 40, 220),
    (0, 160, 80),
    (200, 100, 0),
    (100, 100, 255),
    (0, 200, 160),
    (160, 60, 200),
]


@dataclass(frozen=True)
class FieldROI:
    """One extractable (or skippable) field region on the form."""

    key: str
    box: Tuple[float, float, float, float]  # normalized x, y, w, h (absolute)
    label: str
    field_type: str
    ocr_mode: str = "printed"  # printed | mixed | handwritten | skip | checkbox
    # Extra left inset (0–1 of ROI width) to skip printed labels inside the box
    label_inset: float = 0.0
    anchor: str = ""  # section header key when defined via offset

    @property
    def is_checkbox(self) -> bool:
        return self.field_type == "checkbox" or self.ocr_mode == "checkbox"

    @property
    def skip_ocr(self) -> bool:
        return (
            self.ocr_mode == "skip"
            or self.field_type == "signature"
            or self.is_checkbox
        )


def parse_rois(
    template: Dict[str, Any],
    anchors: Optional[Dict[str, float]] = None,
) -> List[FieldROI]:
    """
    Parse ROI template into FieldROI list.

    If fields use anchor+offset, pass detected `anchors` so Y is resolved
    against live header positions. Without anchors, offset fields fall back
    to layout priors from anchors.detect_section_anchors priors via a
    synthetic prior map.
    """
    from app.ocr_pipeline.anchors import resolve_box

    if anchors is None:
        # Static priors — used at import/test time before an image exists
        anchors = {
            "page_top": 0.0,
            "remittance_details": 0.055,
            "beneficiary_details": 0.230,
            "applicant_details": 0.470,
            "purpose_of_remittance": 0.720,
            "declaration": 0.820,
            "page_bottom": 1.0,
        }

    fields = template.get("fields") or {}
    rois: List[FieldROI] = []
    for key, meta in fields.items():
        box = resolve_box(meta, anchors)
        if any(abs(float(v)) > 1.5 for v in box):
            raise ValueError(
                f"ROI '{key}' looks like absolute pixels {box}. "
                "Use normalized fractions in [0, 1]."
            )
        # Clamp into page
        x, y, w, h = box
        x = max(0.0, min(x, 0.99))
        y = max(0.0, min(y, 0.99))
        w = max(0.005, min(w, 1.0 - x))
        h = max(0.005, min(h, 1.0 - y))
        rois.append(
            FieldROI(
                key=key,
                box=(x, y, w, h),
                label=str(meta.get("label") or key),
                field_type=str(meta.get("field_type") or "text"),
                ocr_mode=str(meta.get("ocr_mode") or "printed"),
                label_inset=float(meta.get("label_inset") or 0.0),
                anchor=str(meta.get("anchor") or ""),
            )
        )
    return rois


def load_rois(
    template_path: Optional[Path] = None,
    anchors: Optional[Dict[str, float]] = None,
) -> List[FieldROI]:
    return parse_rois(load_roi_template(template_path), anchors=anchors)


def _clamp_box(
    x: int, y: int, w: int, h: int, img_w: int, img_h: int
) -> Tuple[int, int, int, int]:
    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    w = max(1, min(w, img_w - x))
    h = max(1, min(h, img_h - y))
    return x, y, w, h


def normalized_to_pixels(
    box: Tuple[float, float, float, float],
    img_w: int,
    img_h: int,
    *,
    pad_ratio: float = 0.0,
    label_inset: float = 0.0,
) -> Tuple[int, int, int, int]:
    """Convert normalized [x,y,w,h] → integer pixel crop on the template canvas."""
    nx, ny, nw, nh = box
    # Skip printed label sitting inside the left of the ROI
    if label_inset > 0:
        nx = nx + nw * label_inset
        nw = nw * (1.0 - label_inset)
    pad_x = int(img_w * pad_ratio)
    pad_y = int(img_h * pad_ratio)
    x = int(round(nx * img_w)) - pad_x
    y = int(round(ny * img_h)) - pad_y
    w = int(round(nw * img_w)) + 2 * pad_x
    h = int(round(nh * img_h)) + 2 * pad_y
    return _clamp_box(x, y, w, h, img_w, img_h)


def crop_roi(
    image: np.ndarray,
    roi: FieldROI,
    pad_ratio: float = 0.0,
) -> np.ndarray:
    """Crop a normalized ROI from the template-sized page."""
    img_h, img_w = image.shape[:2]
    x, y, w, h = normalized_to_pixels(
        roi.box,
        img_w,
        img_h,
        pad_ratio=pad_ratio,
        label_inset=roi.label_inset,
    )
    return image[y : y + h, x : x + w].copy()


def prepare_roi_for_ocr(
    crop: np.ndarray,
    cfg: Optional[PreprocessConfig] = None,
) -> np.ndarray:
    """
    Pad + upscale + light sharpen so PaddleOCR can detect thin field strips.

    Phone photos often yield 16–40px-tall field boxes after warp; the detector
    collapses on razor-thin crops unless we add white margin and upscale.
    """
    cfg = cfg or PreprocessConfig()
    if crop.size == 0:
        return crop

    out = crop
    # White vertical/horizontal padding — critical for short handwritten lines
    pad_y = max(8, out.shape[0] // 3)
    pad_x = max(4, out.shape[1] // 40)
    border = 255
    if out.ndim == 2:
        out = cv2.copyMakeBorder(
            out, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=border
        )
    else:
        out = cv2.copyMakeBorder(
            out,
            pad_y,
            pad_y,
            pad_x,
            pad_x,
            cv2.BORDER_CONSTANT,
            value=(border, border, border),
        )

    h = out.shape[0]
    if h < cfg.min_roi_height:
        scale = max(cfg.upscale_factor, cfg.min_roi_height / max(h, 1))
        out = cv2.resize(
            out,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

    if out.ndim == 2:
        if cfg.sharpen:
            blur = cv2.GaussianBlur(out, (0, 0), 1.0)
            out = cv2.addWeighted(out, 1.4, blur, -0.4, 0)
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    elif cfg.sharpen:
        blur = cv2.GaussianBlur(out, (0, 0), 1.0)
        out = cv2.addWeighted(out, 1.4, blur, -0.4, 0)
    return out


def boxes_overlap(
    a: Tuple[int, int, int, int],
    b: Tuple[int, int, int, int],
) -> bool:
    """True if two pixel boxes (x,y,w,h) intersect with positive area."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
    )


def find_roi_overlaps(
    rois: Sequence[FieldROI],
    img_w: int,
    img_h: int,
) -> List[Dict[str, Any]]:
    """Report pairwise overlaps between text/checkbox ROIs (signature ignored)."""
    active = [r for r in rois if r.field_type != "signature"]
    pixels = {
        r.key: normalized_to_pixels(r.box, img_w, img_h, label_inset=r.label_inset)
        for r in active
    }
    overlaps: List[Dict[str, Any]] = []
    keys = list(pixels.keys())
    for i, ka in enumerate(keys):
        for kb in keys[i + 1 :]:
            if boxes_overlap(pixels[ka], pixels[kb]):
                overlaps.append({"a": ka, "b": kb})
                logger.warning("ROI overlap detected: %s ↔ %s", ka, kb)
    return overlaps


def log_roi_geometry(
    rois: Iterable[FieldROI],
    img_w: int,
    img_h: int,
) -> List[Dict[str, Any]]:
    """Log and return pixel geometry for every ROI."""
    rows: List[Dict[str, Any]] = []
    for roi in rois:
        x, y, w, h = normalized_to_pixels(
            roi.box, img_w, img_h, label_inset=roi.label_inset
        )
        row = {
            "name": roi.key,
            "label": roi.label,
            "field_type": roi.field_type,
            "normalized": list(roi.box),
            "x": x,
            "y": y,
            "width": w,
            "height": h,
        }
        rows.append(row)
        logger.info(
            "ROI %-28s norm=%s → px=(x=%d,y=%d,w=%d,h=%d) type=%s",
            roi.key,
            [round(v, 4) for v in roi.box],
            x,
            y,
            w,
            h,
            roi.field_type,
        )
    return rows


def extract_all_rois(
    warped_binary: np.ndarray,
    rois: Iterable[FieldROI],
    cfg: Optional[PreprocessConfig] = None,
    debug_dir: Optional[Path] = None,
) -> Dict[str, np.ndarray]:
    """Crop and OCR-prep every text ROI (skips signature + checkbox)."""
    cfg = cfg or PreprocessConfig()
    crops: Dict[str, np.ndarray] = {}
    debug_dir = Path(debug_dir) if debug_dir else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "rois").mkdir(parents=True, exist_ok=True)

    for roi in rois:
        if roi.skip_ocr:
            logger.debug("Skipping OCR for ROI %s (%s)", roi.key, roi.ocr_mode)
            continue
        raw = crop_roi(warped_binary, roi, pad_ratio=cfg.roi_pad_ratio)
        prepared = prepare_roi_for_ocr(raw, cfg)
        crops[roi.key] = prepared
        if debug_dir is not None:
            # Requested flat names: debug/date.png, debug/applicant_name.png, ...
            cv2.imwrite(str(debug_dir / f"{roi.key}.png"), prepared)
            cv2.imwrite(str(debug_dir / "rois" / f"{roi.key}.png"), prepared)
    return crops


def extract_checkbox_rois(
    warped_color: np.ndarray,
    rois: Iterable[FieldROI],
    debug_dir: Optional[Path] = None,
) -> Dict[str, np.ndarray]:
    """
    Crop checkbox ROIs from the warped color page.

    Uses color (not line-stripped binary) so tick marks are not erased by
    table-line / small-blob cleanup intended for text OCR.
    """
    crops: Dict[str, np.ndarray] = {}
    debug_dir = Path(debug_dir) if debug_dir else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "rois").mkdir(parents=True, exist_ok=True)

    for roi in rois:
        if not roi.is_checkbox:
            continue
        raw = crop_roi(warped_color, roi, pad_ratio=0.0)
        crops[roi.key] = raw
        if debug_dir is not None:
            cv2.imwrite(str(debug_dir / f"{roi.key}.png"), raw)
            cv2.imwrite(str(debug_dir / "rois" / f"{roi.key}.png"), raw)
    return crops


def save_low_confidence_crops(
    crops: Dict[str, np.ndarray],
    confidences: Dict[str, float],
    debug_dir: Path,
    threshold: float = 0.75,
) -> List[str]:
    """Copy ROIs with OCR confidence below threshold into debug/low_confidence/."""
    out_dir = Path(debug_dir) / "low_confidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []
    for key, conf in confidences.items():
        if conf >= threshold:
            continue
        crop = crops.get(key)
        if crop is None:
            continue
        path = out_dir / f"{key}.png"
        cv2.imwrite(str(path), crop)
        saved.append(key)
        logger.warning(
            "Low OCR confidence for %s: %.3f < %.2f → saved %s",
            key,
            conf,
            threshold,
            path,
        )
    return saved


def draw_roi_overlay(color_image: np.ndarray, rois: Iterable[FieldROI]) -> np.ndarray:
    """Draw every ROI in a distinct color with its key label."""
    canvas = color_image.copy()
    h, w = canvas.shape[:2]
    for idx, roi in enumerate(rois):
        x1, y1, bw, bh = normalized_to_pixels(
            roi.box, w, h, label_inset=roi.label_inset
        )
        x2, y2 = x1 + bw, y1 + bh
        if roi.is_checkbox:
            color = (0, 140, 255)
        elif roi.skip_ocr:
            color = (160, 160, 160)
        else:
            color = _ROI_COLORS[idx % len(_ROI_COLORS)]
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            canvas,
            roi.key,
            (x1, max(14, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )
    return canvas
