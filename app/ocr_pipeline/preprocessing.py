"""
OpenCV preprocessing for phone-captured banking forms.

Pipeline stages (each independently toggleable via PreprocessConfig):
  1. Document boundary detection + perspective correction
  2. Deskew (before template lock — keeps ROI canvas stable)
  3. Resize to fixed template size (resolution-independent ROIs)
  4. Grayscale + denoise + CLAHE + sharpen
  5. Adaptive threshold
  6. Horizontal / vertical table-line removal
  7. Small blob / artifact removal
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from app.logging_config import get_logger
from app.ocr_pipeline.config import PreprocessConfig

logger = get_logger(__name__)


def load_image(source: str | Path | bytes | np.ndarray) -> np.ndarray:
    """Load a BGR image from path, bytes, or ndarray."""
    if isinstance(source, np.ndarray):
        if source.ndim == 2:
            return cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
        return source.copy()

    if isinstance(source, (bytes, bytearray)):
        arr = np.frombuffer(source, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image bytes")
        return image

    path = Path(source)
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def order_quad_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 corner points as TL, TR, BR, BL for perspective warp."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def detect_document_quad(
    image: np.ndarray,
    min_area_ratio: float = 0.15,
    epsilon_ratio: float = 0.02,
) -> Optional[np.ndarray]:
    """
    Find the largest 4-point contour that looks like a document page.

    Returns ordered float32 quad (4x2) or None if detection fails.
    """
    h, w = image.shape[:2]
    min_area = h * w * min_area_ratio

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for contour in contours[:15]:
        area = cv2.contourArea(contour)
        if area < min_area:
            break
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon_ratio * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return order_quad_points(approx.reshape(4, 2).astype("float32"))

    if contours and cv2.contourArea(contours[0]) >= min_area:
        rect = cv2.minAreaRect(contours[0])
        box = cv2.boxPoints(rect).astype("float32")
        return order_quad_points(box)

    return None


def perspective_correct(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Warp the document quad into a frontal rectangle."""
    (tl, tr, br, bl) = quad
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_w = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_h = int(max(height_a, height_b))
    if max_w < 50 or max_h < 50:
        return image

    # Portrait forms photographed landscape-ish still warp correctly via quad.
    # Prefer portrait orientation when height/width ratio is inverted vs A4.
    rotate_output = max_w > max_h * 1.15
    if rotate_output:
        logger.debug(
            "Perspective warp output appears landscape; rotating to portrait orientation"
        )

    dst = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(quad, dst)
    warped = cv2.warpPerspective(image, matrix, (max_w, max_h))
    if rotate_output:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return warped


def resize_to_template(
    image: np.ndarray,
    width: int,
    height: int,
) -> np.ndarray:
    """
    Lock the warped page to a fixed canvas so percentage ROIs are stable
    across phone resolutions and capture distances.
    """
    if width <= 0 or height <= 0:
        return image
    h, w = image.shape[:2]
    if w == width and h == height:
        return image
    interp = cv2.INTER_AREA if (w > width or h > height) else cv2.INTER_CUBIC
    out = cv2.resize(image, (width, height), interpolation=interp)
    logger.info("Resized to template %dx%d (from %dx%d)", width, height, w, h)
    return out


def denoise(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """Remove sensor / compression noise while preserving stroke edges."""
    method = (cfg.denoise_method or "nlm").lower()
    if method == "none":
        return gray
    if method == "gaussian":
        k = cfg.gaussian_ksize if cfg.gaussian_ksize % 2 == 1 else cfg.gaussian_ksize + 1
        return cv2.GaussianBlur(gray, (k, k), 0)
    return cv2.fastNlMeansDenoising(
        gray,
        None,
        h=cfg.nlm_h,
        templateWindowSize=cfg.nlm_template_window,
        searchWindowSize=cfg.nlm_search_window,
    )


def apply_clahe(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """CLAHE lifts shadowed regions without blowing out bright areas."""
    clahe = cv2.createCLAHE(
        clipLimit=cfg.clahe_clip_limit,
        tileGridSize=(cfg.clahe_tile_grid, cfg.clahe_tile_grid),
    )
    return clahe.apply(gray)


def sharpen(gray: np.ndarray, amount: float = 1.2) -> np.ndarray:
    """Unsharp-mask to restore stroke edges softened by denoise / resize."""
    if amount <= 0:
        return gray
    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    return cv2.addWeighted(gray, 1.0 + amount, blur, -amount, 0)


def binarize(gray: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """Adaptive threshold handles uneven lighting better than Otsu alone."""
    block = cfg.adaptive_block_size
    if block % 2 == 0:
        block += 1
    if block < 3:
        block = 3
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block,
        cfg.adaptive_c,
    )


def remove_table_lines(binary: np.ndarray, cfg: PreprocessConfig) -> np.ndarray:
    """Strip horizontal and vertical form/table lines via morphology."""
    inv = cv2.bitwise_not(binary)
    h, w = inv.shape[:2]

    h_len = max(10, int(w * cfg.h_line_kernel_ratio))
    v_len = max(10, int(h * cfg.v_line_kernel_ratio))

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))

    h_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, h_kernel, iterations=1)
    v_lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, v_kernel, iterations=1)
    lines = cv2.bitwise_or(h_lines, v_lines)

    cleaned = cv2.subtract(inv, lines)
    reconnect = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, reconnect, iterations=1)
    return cv2.bitwise_not(cleaned)


def remove_small_blobs(binary: np.ndarray, min_area: int) -> np.ndarray:
    """Drop speckles / checkbox remnants smaller than min_area pixels."""
    inv = cv2.bitwise_not(binary)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
    out = np.zeros_like(inv)
    for label in range(1, num_labels):
        area = stats[label, cv2.CC_STAT_AREA]
        if area >= min_area:
            out[labels == label] = 255
    return cv2.bitwise_not(out)


def estimate_skew_angle(gray_or_binary: np.ndarray, max_angle: float = 15.0) -> float:
    """Estimate deskew angle from ink / edge geometry."""
    if gray_or_binary.ndim == 3:
        gray = cv2.cvtColor(gray_or_binary, cv2.COLOR_BGR2GRAY)
    else:
        gray = gray_or_binary
    # Prefer edges over full binary so filled regions don't dominate
    edges = cv2.Canny(gray, 50, 150)
    coords = np.column_stack(np.where(edges > 0))
    if coords.shape[0] < 100:
        return 0.0
    pts = coords[:, ::-1].astype(np.float32)
    angle = cv2.minAreaRect(pts)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) > max_angle:
        return 0.0
    return float(angle)


def deskew(image: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image around center to correct skew (same canvas size)."""
    if abs(angle) < 0.25:
        return image
    h, w = image.shape[:2]
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    border = 255 if image.ndim == 2 else (255, 255, 255)
    # Keep original size so a following template resize is deterministic
    return cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border,
    )


def preprocess_image(
    source: str | Path | bytes | np.ndarray,
    cfg: Optional[PreprocessConfig] = None,
    debug_dir: Optional[Path] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Run the full preprocessing chain.

    Returns:
        warped_color: template-sized BGR page (overlay / checkbox crops)
        ocr_gray: CLAHE + sharpened grayscale for text ROI OCR
        ocr_binary: line-cleaned binary (debug / optional numeric fields)
    """
    cfg = cfg or PreprocessConfig()
    image = load_image(source)
    logger.info("Preprocess start: shape=%s", image.shape)

    # --- 1. Document detect + perspective crop ---
    warped = image
    if cfg.detect_document:
        quad = detect_document_quad(
            image,
            min_area_ratio=cfg.min_contour_area_ratio,
            epsilon_ratio=cfg.approx_epsilon_ratio,
        )
        if quad is not None:
            warped = perspective_correct(image, quad)
            logger.info("Perspective corrected to %s", warped.shape)
        else:
            logger.warning("Document boundary not found; using full frame")

    # --- 2. Deskew BEFORE template lock ---
    if cfg.deskew:
        gray_for_skew = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        angle = estimate_skew_angle(gray_for_skew, cfg.max_deskew_angle)
        if abs(angle) >= 0.25:
            logger.info("Deskewing by %.2f degrees (pre-template)", angle)
            warped = deskew(warped, angle)

    # --- 3. Resize to fixed template size ---
    if cfg.resize_to_template:
        warped = resize_to_template(warped, cfg.template_width, cfg.template_height)

    # --- 4. Grayscale ---
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # --- 5. Denoise ---
    gray = denoise(gray, cfg)

    # --- 6. Contrast (CLAHE) ---
    if cfg.apply_clahe:
        gray = apply_clahe(gray, cfg)

    # --- 7. Sharpen ---
    if cfg.sharpen:
        gray = sharpen(gray, cfg.sharpen_amount)

    ocr_gray = gray.copy()

    # --- 8. Adaptive threshold (binary debug / numeric assist) ---
    if cfg.adaptive_threshold:
        binary = binarize(gray, cfg)
    else:
        binary = gray.copy()

    # --- 9. Remove table / box lines ---
    if cfg.remove_table_lines and cfg.adaptive_threshold:
        binary = remove_table_lines(binary, cfg)

    # --- 10. Remove speckles ---
    if cfg.remove_small_blobs and cfg.adaptive_threshold:
        binary = remove_small_blobs(binary, cfg.min_blob_area)

    if debug_dir:
        debug_dir = Path(debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "01_warped_color.png"), warped)
        cv2.imwrite(str(debug_dir / "02_ocr_gray.png"), ocr_gray)
        cv2.imwrite(str(debug_dir / "02_ocr_ready.png"), binary)

    logger.info(
        "Preprocess done: color=%s gray=%s binary=%s",
        warped.shape,
        ocr_gray.shape,
        binary.shape,
    )
    return warped, ocr_gray, binary
