"""Configurable preprocessing and OCR settings for the remittance pipeline."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from app import config as app_config

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_ROI_TEMPLATE = TEMPLATES_DIR / "ubl_remittance_rois.json"


@dataclass
class PreprocessConfig:
    """
    Tunable image-prep knobs for phone-captured banking forms.

    Disable individual stages when calibrating against a new scanner / camera
    setup without rewriting code.
    """

    # Document boundary + warp
    detect_document: bool = True
    min_contour_area_ratio: float = 0.15  # ignore tiny contours vs full frame
    approx_epsilon_ratio: float = 0.02  # polygon simplification strength

    # Color / noise / contrast
    convert_grayscale: bool = True
    denoise_method: str = "nlm"  # "nlm" | "gaussian" | "none"
    gaussian_ksize: int = 3
    nlm_h: float = 10.0
    nlm_template_window: int = 7
    nlm_search_window: int = 21
    apply_clahe: bool = True
    clahe_clip_limit: float = 2.0
    clahe_tile_grid: int = 8

    # Binarization
    adaptive_threshold: bool = True
    adaptive_block_size: int = 31  # must be odd
    adaptive_c: int = 10

    # Table / form line removal (critical for boxed remittance fields)
    remove_table_lines: bool = True
    h_line_kernel_ratio: float = 0.04  # fraction of image width
    v_line_kernel_ratio: float = 0.04  # fraction of image height

    # Artifact cleanup
    remove_small_blobs: bool = True
    min_blob_area: int = 20

    # Geometric correction
    deskew: bool = True
    max_deskew_angle: float = 15.0

    # Lock page to a fixed canvas so percentage ROIs never drift with resolution
    resize_to_template: bool = True
    template_width: int = 1000
    template_height: int = 1400

    # Sharpen after denoise / CLAHE
    sharpen: bool = True
    sharpen_amount: float = 1.2

    # Upscale small phone crops before OCR
    min_roi_height: int = 48
    upscale_factor: float = 2.0

    # Debug / QA
    low_confidence_threshold: float = 0.75
    # Horizontal inset from left of field box to skip printed labels (fraction of ROI width)
    label_inset_ratio: float = 0.0
    # Default crop padding — keep tiny so labels / borders stay out
    roi_pad_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "PreprocessConfig":
        if not data:
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_env(cls) -> "PreprocessConfig":
        """Override defaults from environment when present."""
        cfg = cls()
        if os.getenv("OCR_DENOISE_METHOD"):
            cfg.denoise_method = os.getenv("OCR_DENOISE_METHOD", cfg.denoise_method)
        if os.getenv("OCR_DETECT_DOCUMENT"):
            cfg.detect_document = os.getenv("OCR_DETECT_DOCUMENT", "1") not in {
                "0",
                "false",
                "False",
            }
        if os.getenv("OCR_REMOVE_TABLE_LINES"):
            cfg.remove_table_lines = os.getenv("OCR_REMOVE_TABLE_LINES", "1") not in {
                "0",
                "false",
                "False",
            }
        return cfg


@dataclass
class PaddleOCRConfig:
    """PaddleOCR runtime options."""

    lang: str = "en"
    use_angle_cls: bool = True  # detect / correct text orientation per ROI
    use_gpu: bool = False
    show_log: bool = False
    # Prefer detection+recognition; for tiny ROIs we may skip detection
    det: bool = True
    rec: bool = True
    cls: bool = True

    @classmethod
    def from_env(cls) -> "PaddleOCRConfig":
        return cls(
            lang=os.getenv("PADDLE_OCR_LANG", "en"),
            use_angle_cls=os.getenv("PADDLE_USE_ANGLE_CLS", "1") not in {"0", "false"},
            use_gpu=os.getenv("PADDLE_USE_GPU", "0") in {"1", "true", "True"},
            show_log=os.getenv("PADDLE_SHOW_LOG", "0") in {"1", "true", "True"},
        )


@dataclass
class PipelineConfig:
    """Top-level remittance OCR pipeline configuration."""

    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig.from_env)
    paddle: PaddleOCRConfig = field(default_factory=PaddleOCRConfig.from_env)
    roi_template_path: Path = field(default_factory=lambda: DEFAULT_ROI_TEMPLATE)
    debug_dir: Optional[Path] = None
    save_debug_images: bool = False

    @classmethod
    def default(cls) -> "PipelineConfig":
        debug = os.getenv("OCR_DEBUG_DIR")
        return cls(
            debug_dir=Path(debug) if debug else (app_config.UPLOAD_DIR / "ocr_debug"),
            save_debug_images=os.getenv("OCR_SAVE_DEBUG", "0") in {"1", "true", "True"},
        )


def load_roi_template(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load normalized ROI definitions for a fixed form template."""
    template_path = Path(path) if path else DEFAULT_ROI_TEMPLATE
    with template_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def apply_template_size_to_config(
    cfg: PreprocessConfig,
    template: Dict[str, Any],
) -> PreprocessConfig:
    """Override template canvas size from the ROI JSON when present."""
    size = template.get("template_size")
    if isinstance(size, (list, tuple)) and len(size) == 2:
        cfg.template_width = int(size[0])
        cfg.template_height = int(size[1])
    return cfg
