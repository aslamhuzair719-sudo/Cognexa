"""Compare two handwritten signature images (registered vs probe).

Current behavior: use Gemini Vision to estimate a match percentage.
Siamese CNN can be re-enabled later for faster offline matching.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict

import cv2
import numpy as np
import requests

from app import config
from app.logging_config import get_logger
from app.services.gemini_service import GeminiService
from app.services.llm_factory import resolve_gemini_api_key

logger = get_logger(__name__)


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return brace.group(0).strip()
    return text


def enhance_signature_image(data: bytes, *, max_side: int = 900) -> bytes:
    """Normalize a signature to clean black ink on white for consistent compare.

    Pipeline: grayscale → denoise → CLAHE → adaptive B&W → morphology →
    crop to ink → resize → PNG.
    """
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode signature image.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, h=8, templateWindowSize=7, searchWindowSize=21)

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Black ink on white background
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=12,
    )

    # Fallback to Otsu if adaptive left almost no ink (or nearly all ink)
    ink_ratio = float(np.mean(binary < 128))
    if ink_ratio < 0.005 or ink_ratio > 0.55:
        _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        binary = cv2.bitwise_not(otsu_inv)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    # Work on ink mask (white=ink) for cleanup, then flip back
    ink = cv2.bitwise_not(binary)
    ink = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel, iterations=1)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, kernel, iterations=1)
    binary = cv2.bitwise_not(ink)

    ys, xs = np.where(ink > 0)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError("Signature appears empty after enhancement (no ink detected).")

    pad = 16
    x0 = max(int(xs.min()) - pad, 0)
    x1 = min(int(xs.max()) + pad + 1, binary.shape[1])
    y0 = max(int(ys.min()) - pad, 0)
    y1 = min(int(ys.max()) + pad + 1, binary.shape[0])
    cropped = binary[y0:y1, x0:x1]

    h, w = cropped.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / float(longest)
        cropped = cv2.resize(
            cropped,
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            interpolation=cv2.INTER_AREA,
        )

    ok, buf = cv2.imencode(".png", cropped)
    if not ok:
        raise ValueError("Failed to encode enhanced signature image.")
    return buf.tobytes()


def _gemini_compare_two_images(
    *,
    registered_bytes: bytes,
    probe_bytes: bytes,
) -> Dict[str, Any]:
    """
    Gemini vision compare with TWO images in one request.

    Returns: {"match_percentage": float}
    """
    registered_b64 = base64.b64encode(registered_bytes).decode("ascii")
    probe_b64 = base64.b64encode(probe_bytes).decode("ascii")

    vision_model = config.GEMINI_VISION_MODEL or config.GEMINI_MODEL
    endpoint = f"{config.GEMINI_URL.rstrip('/')}/v1beta/models/{vision_model}:generateContent"
    api_key_branch = resolve_gemini_api_key(branch=True)
    api_key_account = resolve_gemini_api_key(branch=False)

    def _call(api_key: str) -> requests.Response:
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": api_key,
        }
        return requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=config.GEMINI_TIMEOUT,
        )

    prompt = (
        "You are a forensic signature examiner for bank verification. "
        "Image 1 is the registered reference signature. Image 2 is the probe to verify. "
        "Both images are already preprocessed to black ink on white background — "
        "ignore lighting/paper color and focus only on stroke geometry.\n\n"
        "CRITICAL: Separate two concepts:\n"
        "1) visual_similarity — how alike the shapes look (different people can score 70-95 here)\n"
        "2) same_author_confidence — likelihood the SAME person wrote both (forensic judgment)\n\n"
        "Analyze micro-features for same_author_confidence:\n"
        "- Stroke pressure/thickness variation along curves\n"
        "- Slant angle and consistency\n"
        "- Letter/loop proportions and spacing rhythm\n"
        "- Entry/exit strokes, connections, and hesitations\n"
        "- Distinctive personal habits (size, flourish, baseline drift)\n\n"
        "Scoring same_author_confidence (strict):\n"
        "- 90-100: Strong evidence SAME person wrote both\n"
        "- 75-89: Probable same author with minor natural variation\n"
        "- 50-74: Uncertain — similar style or partial imitation\n"
        "- 20-49: Likely different authors (forgery, copied style, different hand)\n"
        "- 0-19: Clearly different signatures\n\n"
        "If Image 2 mimics Image 1's style but shows different stroke habits, "
        "visual_similarity may be high but same_author_confidence MUST be below 50.\n\n"
        "Return ONLY valid JSON (no markdown, no code fences) with exactly:\n"
        '{ "visual_similarity": <0-100>, "same_author_confidence": <0-100>, '
        '"match_percentage": <same as same_author_confidence> }'
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": registered_b64,
                        }
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": probe_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    resp = _call(api_key_branch)
    if resp.status_code == 401 and api_key_account and api_key_account != api_key_branch:
        # Fallback for easier debugging: the branch key may be invalid/unauthorized.
        logger.warning("Gemini Vision auth failed for branch key; retrying with account key.")
        resp = _call(api_key_account)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini Vision HTTP {resp.status_code}: {resp.text[:500]}")

    raw_text = GeminiService._parse_response(resp.json())
    parsed = json.loads(_strip_json_fence(raw_text))

    if not isinstance(parsed, dict):
        raise ValueError(f"Gemini response not a JSON object: {raw_text[:300]}")

    # Prefer same_author_confidence over raw visual similarity.
    if "same_author_confidence" in parsed:
        pct = float(parsed["same_author_confidence"])
    elif "match_percentage" in parsed:
        pct = float(parsed["match_percentage"])
    else:
        raise ValueError(f"Gemini response missing match fields: {raw_text[:300]}")

    if pct < 0:
        pct = 0.0
    if pct > 100:
        pct = 100.0

    visual = parsed.get("visual_similarity")
    if visual is not None:
        visual = max(0.0, min(100.0, float(visual)))

    result: Dict[str, Any] = {"match_percentage": round(pct, 1)}
    if visual is not None:
        result["visual_similarity"] = round(visual, 1)
    return result


def compare_signature_images(registered_bytes: bytes, probe_bytes: bytes) -> dict:
    """Return comparison result dict for the frontend."""
    try:
        registered_clean = enhance_signature_image(registered_bytes)
        probe_clean = enhance_signature_image(probe_bytes)
        out = _gemini_compare_two_images(
            registered_bytes=registered_clean,
            probe_bytes=probe_clean,
        )
        pct = out["match_percentage"]
        scores: Dict[str, float] = {"similarity": round(pct, 1)}
        visual = out.get("visual_similarity")
        if visual is not None:
            scores["visual_similarity"] = round(float(visual), 1)
        return {
            "match_percentage": pct,
            "method": "gemini_vision",
            "scores": scores,
        }
    except Exception as exc:
        logger.exception("Gemini signature compare failed")
        raise ValueError(f"Signature comparison failed: {exc}") from exc
