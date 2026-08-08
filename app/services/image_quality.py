"""Image quality checks: blur, resolution, brightness, crop, OCR readability."""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional, Tuple

import fitz
import numpy as np
from PIL import Image, ImageStat

from app import config
from app.logging_config import get_logger
from app.schemas.common import CheckResult
from app.schemas.verification import ImageQualityCheck, ImageQualityResult

logger = get_logger(__name__)


class ImageQualityService:
    """Evaluate upload quality for bank staff review."""

    def assess(
        self,
        document_path: str,
        document_label: str,
        ocr_text: str = "",
    ) -> ImageQualityResult:
        try:
            image = self._load_image(document_path)
        except Exception as exc:
            logger.exception("Failed to load image for quality check: %s", document_path)
            return ImageQualityResult(
                document_label=document_label,
                overall=CheckResult.FAIL,
                readable=False,
                checks=[
                    ImageQualityCheck(
                        check="load",
                        result=CheckResult.FAIL,
                        detail=f"Unable to open document for quality checks: {exc}",
                    )
                ],
            )

        checks: List[ImageQualityCheck] = [
            self._check_resolution(image),
            self._check_blur(image),
            self._check_brightness(image),
            self._check_crop(image),
            self._check_ocr_readability(ocr_text),
            self._check_software_tampering(document_path, image),
        ]

        fails = [c for c in checks if c.result == CheckResult.FAIL]
        warnings = [c for c in checks if c.result == CheckResult.WARNING]
        overall = (
            CheckResult.FAIL
            if fails
            else CheckResult.WARNING
            if warnings
            else CheckResult.PASS
        )
        readable = not any(
            c.check == "ocr_readability" and c.result == CheckResult.FAIL for c in checks
        )

        return ImageQualityResult(
            document_label=document_label,
            overall=overall,
            checks=checks,
            readable=readable,
        )

    def _load_image(self, document_path: str) -> Image.Image:
        path = Path(document_path)
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}:
            return Image.open(path).convert("RGB")

        doc = fitz.open(path)
        try:
            page = doc[0]
            pix = page.get_pixmap(dpi=config.OCR_DPI)
            return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        finally:
            doc.close()

    def _check_resolution(self, image: Image.Image) -> ImageQualityCheck:
        w, h = image.size
        ok = w >= config.MIN_RESOLUTION_WIDTH and h >= config.MIN_RESOLUTION_HEIGHT
        return ImageQualityCheck(
            check="resolution",
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            detail=f"{w}x{h}px (min {config.MIN_RESOLUTION_WIDTH}x{config.MIN_RESOLUTION_HEIGHT})",
            value=float(min(w, h)),
        )

    def _check_blur(self, image: Image.Image) -> ImageQualityCheck:
        variance = self._laplacian_variance(image)
        if variance < config.MIN_BLUR_VARIANCE:
            result = CheckResult.FAIL
            detail = f"Image appears blurry (variance={variance:.1f})"
        elif variance < config.MIN_BLUR_VARIANCE * 1.5:
            result = CheckResult.WARNING
            detail = f"Image sharpness is marginal (variance={variance:.1f})"
        else:
            result = CheckResult.PASS
            detail = f"Sharpness OK (variance={variance:.1f})"
        return ImageQualityCheck(
            check="blur", result=result, detail=detail, value=variance
        )

    def _laplacian_variance(self, image: Image.Image) -> float:
        """Laplacian variance for blur detection.

        Downscales large images and uses an O(n) neighbor difference instead of
        sliding_window_view + tensordot, which previously allocated hundreds of
        MiB on high-res scans and raised ArrayMemoryError.
        """
        max_side = 1024
        img = image.convert("L")
        w, h = img.size
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
            img = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.BILINEAR,
            )

        gray = np.asarray(img, dtype=np.float32)
        if gray.shape[0] < 3 or gray.shape[1] < 3:
            return 0.0

        # 3x3 Laplacian [[0,1,0],[1,-4,1],[0,1,0]] without a full window tensor
        lap = (
            -4.0 * gray[1:-1, 1:-1]
            + gray[:-2, 1:-1]
            + gray[2:, 1:-1]
            + gray[1:-1, :-2]
            + gray[1:-1, 2:]
        )
        return float(lap.var())

    def _check_brightness(self, image: Image.Image) -> ImageQualityCheck:
        stat = ImageStat.Stat(image.convert("L"))
        mean = float(stat.mean[0])
        if mean < config.MIN_BRIGHTNESS:
            result = CheckResult.FAIL
            detail = f"Too dark (mean={mean:.1f})"
        elif mean > config.MAX_BRIGHTNESS:
            result = CheckResult.FAIL
            detail = f"Too bright / overexposed (mean={mean:.1f})"
        else:
            result = CheckResult.PASS
            detail = f"Brightness OK (mean={mean:.1f})"
        return ImageQualityCheck(
            check="brightness", result=result, detail=detail, value=mean
        )

    def _check_crop(self, image: Image.Image) -> ImageQualityCheck:
        """Heuristic: large near-uniform border suggests heavy crop / incomplete scan."""
        arr = np.asarray(image.convert("L"), dtype=np.float64)
        h, w = arr.shape
        border = max(2, min(h, w) // 40)
        edges = np.concatenate(
            [
                arr[:border, :].ravel(),
                arr[-border:, :].ravel(),
                arr[:, :border].ravel(),
                arr[:, -border:].ravel(),
            ]
        )
        edge_std = float(edges.std())
        # Very low edge variance often means blank/cropped margins dominate
        if edge_std < 8.0:
            return ImageQualityCheck(
                check="cropped_document",
                result=CheckResult.WARNING,
                detail="Document borders look incomplete or heavily cropped",
                value=edge_std,
            )
        return ImageQualityCheck(
            check="cropped_document",
            result=CheckResult.PASS,
            detail="Document framing appears adequate",
            value=edge_std,
        )

    def _check_ocr_readability(self, ocr_text: str) -> ImageQualityCheck:
        chars = len((ocr_text or "").strip())
        if chars < config.MIN_OCR_CHARS:
            return ImageQualityCheck(
                check="ocr_readability",
                result=CheckResult.FAIL,
                detail=f"Insufficient readable text extracted ({chars} chars)",
                value=float(chars),
            )
        return ImageQualityCheck(
            check="ocr_readability",
            result=CheckResult.PASS,
            detail=f"OCR extracted {chars} characters",
            value=float(chars),
        )

    def _check_software_tampering(
        self, document_path: str, image: Image.Image
    ) -> ImageQualityCheck:
        """Inspect file metadata and headers for editing software tags (Canva, Photoshop, GIMP, etc.)."""
        editors = [
            "canva",
            "photoshop",
            "gimp",
            "paint.net",
            "pixlr",
            "adobe",
            "illustrator",
            "inkscape",
            "coreldraw",
            "figma",
        ]
        found_software: Optional[str] = None

        # 1. PIL image info
        info = image.info or {}
        for key in ("software", "comment", "Software", "Comment"):
            val = str(info.get(key) or "").strip()
            for ed in editors:
                if ed in val.lower():
                    found_software = val
                    break
            if found_software:
                break

        # 2. EXIF data
        if not found_software:
            try:
                exif = image.getexif()
                if exif:
                    for tag_id, val in exif.items():
                        val_str = str(val).lower()
                        for ed in editors:
                            if ed in val_str:
                                found_software = str(val)
                                break
                        if found_software:
                            break
            except Exception:
                pass

        # 3. Direct raw file header/metadata scan (catches Canva / Photoshop comments embedded in PNG/JPEG/PDF chunks)
        if not found_software:
            try:
                path = Path(document_path)
                if path.exists() and path.is_file():
                    content = path.read_bytes()[:262144].lower()
                    for ed in ["canva", "photoshop", "gimp", "adobe photoshop", "paint.net", "figma"]:
                        if ed.encode("utf-8") in content:
                            found_software = ed.title()
                            break
            except Exception:
                pass

        if found_software:
            return ImageQualityCheck(
                check="metadata_integrity",
                result=CheckResult.FAIL,
                detail=f"Digital editing / forgery detected: image edited or created with software ({found_software})",
            )

        return ImageQualityCheck(
            check="metadata_integrity",
            result=CheckResult.PASS,
            detail="No editing software metadata detected",
        )

