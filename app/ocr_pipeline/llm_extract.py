"""
LLM extraction for remittance forms and bank cheques.

Active path: Gemini (Google AI Studio) — vision or OCR text → structured JSON.
Fallback providers: Groq (text), Ollama (vision/text) via LLM_PROVIDER in .env.
"""

from __future__ import annotations

import base64
import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

import cv2
import numpy as np
import requests

from app import config
from app.logging_config import get_logger

logger = get_logger(__name__)

ImageSource = Union[str, Path, bytes, np.ndarray]

_REMITTANCE_SCHEMA_BLOCK = """
Return ONLY a valid JSON object with exactly this schema (no markdown):
{
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
  "checkboxes": {
    "non_account_holder": false,
    "cash_transfer": false,
    "cashiers_cheque": false,
    "online_transfer": false,
    "currency_pkr": false,
    "purpose_family_maintenance": false,
    "purpose_education": false,
    "purpose_medical": false,
    "purpose_gift": false,
    "purpose_investment": false,
    "purpose_business": false,
    "purpose_other": false
  }
}

Field mapping tips for this form:
- applicant_name / father_name / cnic / mobile / address / occupation
  come from the "Remitter's/Applicant's Details" section.
- beneficiary_name / beneficiary_account come from "Beneficiary Details".
- amount_figures / amount_words / cheque_number come from "Remittance Details".
- purpose: use the checked purpose option label (e.g. "Education").
- cnic must be 13 digits when readable.
- mobile should be a Pakistani mobile number when readable.
"""

# Prompt: OCR text → structured JSON (Groq / text-only models)
REMITTANCE_TEXT_PROMPT = """You are a banking document extraction assistant.
Below is OCR text from a UBL Application / Remittance Form.

Extract ONLY the handwritten or typed VALUES (never printed labels).
For checkboxes: return true if the text indicates the box is ticked/marked, false if empty.
If a field is missing, blank, or unreadable, use an empty string "" for text
fields and false for checkboxes. Do NOT invent values.
""" + _REMITTANCE_SCHEMA_BLOCK + """
OCR TEXT:
<<<
{ocr_text}
>>>
"""

# Prompt: ask the vision LLM to read the form image directly (Ollama vision)
REMITTANCE_VISION_PROMPT = """You are a banking document extraction assistant.
Look carefully at the attached UBL Application / Remittance Form image.

Extract ONLY the handwritten or typed VALUES (never printed labels).
For checkboxes: return true if the box is ticked/marked, false if empty.
If a field is missing, blank, or unreadable, use an empty string "" for text
fields and false for checkboxes. Do NOT invent values.
""" + _REMITTANCE_SCHEMA_BLOCK

_CHEQUE_SCHEMA_BLOCK = """
Return ONLY a valid JSON object with exactly this schema (no markdown):
{
  "bank_name": "",
  "bank_code": "",
  "product_name": "",
  "branch_name": "",
  "branch_address": "",
  "cheque_number": "",
  "date": "",
  "payee": "",
  "amount_figures": "",
  "amount_words": "",
  "currency": "PKR",
  "iban": "",
  "account_name": "",
  "micr_line": ""
}

Field tips for Pakistani bank cheques:
- bank_name: full bank name (e.g. "Habib Bank Limited").
- bank_code: short brand code when visible (HBL, UBL, MCB, ABL, NBP, etc.).
  Never invent. If the logo looks like "IABL" / "H8L" but the printed bank
  name is Habib Bank Limited, bank_code must be "HBL".
- product_name: account product line near the logo (e.g. "FreedomAccount").
- branch_name / branch_address: printed branch lines under the bank header.
- cheque_number: top-right cheque number (also appears in the MICR line).
- date: handwritten or printed cheque date.
- payee: name on the "Pay" line (may be "Cash").
- amount_figures / amount_words: numeric box and rupees-in-words line.
- iban / account_name: printed account details when readable.
- micr_line: bottom MICR digits/symbols if readable.
If a field is missing, blank, redacted, or unreadable, use "".
Do NOT invent values.
"""

CHEQUE_TEXT_PROMPT = """You are a banking document extraction assistant.
Below is OCR text from a bank cheque (Pakistan).

OCR often misreads stylized logos (e.g. HBL → IABL). Prefer the printed
bank name ("Habib Bank Limited") over logo OCR when they conflict.

Extract values into the schema. Use "" when unknown.
""" + _CHEQUE_SCHEMA_BLOCK + """
OCR TEXT:
<<<
{ocr_text}
>>>
"""

CHEQUE_VISION_PROMPT = """You are a banking document extraction assistant.
Look carefully at the attached bank cheque image (Pakistan).

Read printed AND handwritten fields. OCR of logos is unreliable —
if the cheque shows Habib Bank Limited / HBL FreedomAccount, bank_code is HBL
even if the logo font looks like IABL.

Extract values into the schema. Use "" when unknown or redacted.
""" + _CHEQUE_SCHEMA_BLOCK

CHEQUE_FIELD_KEYS = (
    "bank_name",
    "bank_code",
    "product_name",
    "branch_name",
    "branch_address",
    "cheque_number",
    "date",
    "payee",
    "amount_figures",
    "amount_words",
    "currency",
    "iban",
    "account_name",
    "micr_line",
)

def _load_bgr(source: ImageSource) -> np.ndarray:
    """Load an image as BGR ndarray from path, bytes, or array."""
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


def image_to_base64_jpeg(
    source: ImageSource,
    *,
    max_side: int = 1600,
    quality: int = 85,
) -> str:
    """
    Encode the form image as base64 JPEG for Ollama vision APIs.

    Downscales very large phone photos so the request stays manageable.
    """
    image = _load_bgr(source)
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest > max_side:
        scale = max_side / float(longest)
        image = cv2.resize(
            image,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )

    ok, buf = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("Failed to JPEG-encode image for LLM vision")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _pdf_bytes_to_bgr(data: bytes, *, dpi: int = 200) -> np.ndarray:
    """Render the first page of a PDF to a BGR ndarray."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.page_count < 1:
            raise ValueError("PDF has no pages")
        pix = doc[0].get_pixmap(dpi=dpi)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
        if pix.n == 1:
            return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    finally:
        doc.close()


def source_to_base64_jpeg(
    source: ImageSource,
    *,
    max_side: int = 1600,
    quality: int = 85,
) -> str:
    """
    Encode an image or PDF (first page) as base64 JPEG for vision LLMs.
    """
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
        if data.lstrip().startswith(b"%PDF"):
            image = _pdf_bytes_to_bgr(data)
            return image_to_base64_jpeg(image, max_side=max_side, quality=quality)
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() == ".pdf":
            image = _pdf_bytes_to_bgr(path.read_bytes())
            return image_to_base64_jpeg(image, max_side=max_side, quality=quality)
    return image_to_base64_jpeg(source, max_side=max_side, quality=quality)


def _strip_json_fence(raw: str) -> str:
    """Remove optional ```json ... ``` wrappers from model output."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    # Fallback: first {...} block
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return brace.group(0).strip()
    return text


def _normalize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all expected remittance keys exist with safe defaults."""
    text_defaults = {
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
    checkbox_defaults = {
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
    }

    out: Dict[str, Any] = {}
    for key, default in text_defaults.items():
        value = data.get(key, default)
        out[key] = "" if value is None else str(value).strip()

    raw_boxes = data.get("checkboxes") if isinstance(data.get("checkboxes"), dict) else {}
    boxes: Dict[str, bool] = {}
    for key, default in checkbox_defaults.items():
        # Allow flat keys as well as nested checkboxes
        value = raw_boxes.get(key, data.get(key, default))
        if isinstance(value, bool):
            boxes[key] = value
        elif isinstance(value, str):
            boxes[key] = value.strip().lower() in {"true", "1", "yes", "checked"}
        else:
            boxes[key] = bool(value)
    out["checkboxes"] = boxes
    out.update(boxes)
    return out


def _chat_url(generate_url: str) -> str:
    """Map .../api/generate → .../api/chat for multimodal messages."""
    if generate_url.rstrip("/").endswith("/api/generate"):
        return generate_url.rstrip("/")[: -len("/api/generate")] + "/api/chat"
    if generate_url.rstrip("/").endswith("/api/chat"):
        return generate_url
    return generate_url.rstrip("/") + "/api/chat"


def call_ollama_text(
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """Call Ollama /api/generate with a text-only prompt (no image)."""
    from app.services.ollama_service import OllamaService

    service = OllamaService(
        model=model or config.OLLAMA_MODEL,
        timeout=timeout or config.OLLAMA_TIMEOUT,
    )
    return service.generate(prompt)


def call_ollama_vision(
    image_b64: str,
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """
    Call Ollama with an image + text prompt.

    Tries /api/chat (messages + images) first, then /api/generate with images.
    Kept for local Ollama — used when LLM_PROVIDER=ollama.
    """
    model = model or getattr(config, "OLLAMA_VISION_MODEL", None) or config.OLLAMA_MODEL
    timeout = timeout or config.OLLAMA_TIMEOUT
    chat_url = _chat_url(config.OLLAMA_URL)
    generate_url = config.OLLAMA_URL

    # Preferred multimodal chat API
    chat_payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
    }

    try:
        logger.info("LLM vision extract via chat API model=%s", model)
        response = requests.post(chat_url, json=chat_payload, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            # chat: {message: {content: "..."}}
            message = data.get("message") or {}
            content = (message.get("content") or data.get("response") or "").strip()
            if content:
                return content
        else:
            logger.warning(
                "Ollama chat vision HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )
    except requests.exceptions.RequestException as exc:
        logger.warning("Ollama chat vision failed (%s); trying generate API", exc)

    # Fallback: /api/generate with images[]
    gen_payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0},
    }
    try:
        logger.info("LLM vision extract via generate API model=%s", model)
        response = requests.post(generate_url, json=gen_payload, timeout=timeout)
        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama HTTP {response.status_code}: {response.text[:500]}"
            )
        data = response.json()
        return (data.get("response") or "").strip()
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"Failed to reach Ollama vision model '{model}' at {generate_url}: {exc}. "
            "Pull a vision model (e.g. `ollama pull gemma3:4b` or `ollama pull llava`)."
        ) from exc


def call_groq_text(
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """Call Groq OpenAI-compatible chat completions with a text prompt."""
    from app.services.groq_service import GroqService

    service = GroqService(model=model, timeout=timeout)
    return service.generate(prompt)


def _ocr_image_text(source: ImageSource) -> str:
    """Run Tesseract OCR on an image source for text-only LLM extraction."""
    import pytesseract
    from PIL import Image

    from app.services.ocr_service import TesseractOCRService

    if isinstance(source, (bytes, bytearray)):
        b = bytes(source)
        # If bytes look like a PDF, save it with a .pdf extension so PyMuPDF
        # extraction runs (otherwise it will try to treat it as an image).
        filename = "remittance.pdf" if b.lstrip().startswith(b"%PDF") else "remittance.jpg"
        return TesseractOCRService().extract_text_from_bytes(b, filename)
    if isinstance(source, (str, Path)):
        return TesseractOCRService().extract_text(str(source))

    # ndarray path
    image = _load_bgr(source)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return pytesseract.image_to_string(Image.fromarray(rgb)).strip()


def extract_remittance_with_llm(
    source: ImageSource,
    *,
    model: Optional[str] = None,
    max_side: int = 1600,
    branch: bool = False,
) -> Dict[str, Any]:
    """
    Ask the LLM to extract remittance fields from the form.

Active provider (Gemini/Groq): OCR text → structured JSON.
Gemini/Ollama remittance: vision image → JSON, with OCR text fallback.

    Returns a dict matching the remittance JSON schema (text fields +
    boolean checkboxes), plus a small `meta` block.
    """
    from app.services.llm_factory import call_llm_text, call_llm_vision, llm_engine_label, supports_vision

    provider = getattr(config, "LLM_PROVIDER", "gemini").strip().lower()

    if supports_vision():
        # Gemini / Ollama: vision first (handwriting), OCR text fallback
        vision_engine, vision_model = llm_engine_label(vision=True)
        try:
            image_b64 = source_to_base64_jpeg(source, max_side=max_side)
            raw = call_llm_vision(
                image_b64,
                REMITTANCE_VISION_PROMPT,
                model=vision_model if provider == "gemini" else model,
                branch=branch,
            )
            engine = vision_engine
            used_model = vision_model
        except Exception as exc:
            logger.warning(
                "%s vision remittance failed (%s); falling back to OCR text",
                provider,
                exc,
            )
            ocr_text = _ocr_image_text(source)
            if not ocr_text.strip():
                raise RuntimeError(
                    "No OCR text extracted from remittance image for LLM extraction."
                ) from exc
            prompt = REMITTANCE_TEXT_PROMPT.replace("{ocr_text}", ocr_text[:12000])
            raw = call_llm_text(prompt, model=model, branch=branch)
            engine, used_model = llm_engine_label(vision=False)
    else:
        # Groq: OCR text only (no vision)
        ocr_text = _ocr_image_text(source)
        if not ocr_text.strip():
            raise RuntimeError(
                "No OCR text extracted from remittance image for Groq extraction."
            )
        prompt = REMITTANCE_TEXT_PROMPT.replace("{ocr_text}", ocr_text[:12000])
        raw = call_llm_text(prompt, model=model, branch=branch)
        engine, used_model = llm_engine_label(vision=False)

    try:
        parsed = json.loads(_strip_json_fence(raw))
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
    except (json.JSONDecodeError, ValueError):
        # Some models may return Python-style dicts with single quotes.
        cleaned = _strip_json_fence(raw)
        try:
            parsed = ast.literal_eval(cleaned)
            if isinstance(parsed, dict):
                pass
            else:
                raise ValueError("LLM response is not a dict")
        except Exception as exc:
            logger.error("Failed to parse LLM JSON: %s | raw=%r", exc, raw[:500])
            raise RuntimeError(f"LLM returned invalid JSON: {exc}") from exc

    result = _normalize_payload(parsed)

    # Post-process: blank only obvious prompt placeholders, not real OCR/vision text.
    def _empty_if_placeholder(value: str) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        if re.fullmatch(r"X+", v, re.IGNORECASE):
            return ""
        if re.fullmatch(r"0?3X{6,}", v, re.IGNORECASE):
            return ""
        if v.lower() in {"address", "occupation", "purpose", "line of business"}:
            return ""
        return v

    def _prefer_digits_or_keep(value: str, *, min_digits: int) -> str:
        v = (value or "").strip()
        if not v:
            return ""
        digits = re.sub(r"\D+", "", v)
        if len(digits) >= min_digits:
            return digits
        return v

    out = result
    for key in ("mobile", "cnic", "occupation", "address", "purpose"):
        out[key] = _empty_if_placeholder(out.get(key, ""))

    out["beneficiary_account"] = _prefer_digits_or_keep(
        out.get("beneficiary_account", ""), min_digits=5
    )
    out["branch_code"] = _prefer_digits_or_keep(
        out.get("branch_code", ""), min_digits=2
    )
    out["cheque_number"] = _prefer_digits_or_keep(
        out.get("cheque_number", ""), min_digits=2
    )

    result = out

    result["meta"] = {
        "engine": engine,
        "model": used_model,
        "raw_preview": raw[:400],
    }
    logger.info(
        "LLM remittance extraction complete (%s): applicant=%r beneficiary=%r purpose=%r",
        engine,
        result.get("applicant_name"),
        result.get("beneficiary_name"),
        result.get("purpose"),
    )
    return result


def _normalize_cheque_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all expected cheque keys exist with safe string defaults."""
    out: Dict[str, Any] = {}
    for key in CHEQUE_FIELD_KEYS:
        default = "PKR" if key == "currency" else ""
        value = data.get(key, default)
        out[key] = "" if value is None else str(value).strip()
    if not out.get("currency"):
        out["currency"] = "PKR"

    # Correct common logo OCR mistakes when bank name is clear
    bank_name = out.get("bank_name", "").lower()
    code = out.get("bank_code", "").upper().replace(" ", "")
    if "habib bank" in bank_name or "hbl" in bank_name:
        if code in {"", "IABL", "H8L", "IBL", "HB1", "HBI"}:
            out["bank_code"] = "HBL"
        product = out.get("product_name", "")
        if product.upper().startswith("IABL "):
            out["product_name"] = "HBL " + product[5:].lstrip()
        elif product.upper() in {"IABL", "IABL FREEDOMACCOUNT"}:
            out["product_name"] = "HBL FreedomAccount"

    # Swap IBAN misplaced into account_name (common vision mix-up)
    iban_pat = re.compile(r"^PK\d{2}\s*[A-Z]{4}", re.IGNORECASE)
    if not out.get("iban") and iban_pat.match(out.get("account_name", "")):
        out["iban"] = out["account_name"]
        out["account_name"] = ""
    elif out.get("iban") and not iban_pat.match(out["iban"]) and iban_pat.match(
        out.get("account_name", "")
    ):
        out["iban"], out["account_name"] = out["account_name"], out["iban"]

    return out


def extract_cheque_with_llm(
    source: ImageSource,
    *,
    model: Optional[str] = None,
    max_side: int = 1600,
    branch: bool = False,
) -> Dict[str, Any]:
    """
    Extract structured fields from a bank cheque image.

    Gemini/Ollama: vision image → structured JSON.
    Groq fallback: OCR text → structured JSON.
    """
    from app.services.llm_factory import (
        call_llm_text,
        call_llm_vision_source,
        llm_engine_label,
        supports_vision,
    )

    if supports_vision():
        raw = call_llm_vision_source(
            source,
            CHEQUE_VISION_PROMPT,
            model=model,
            max_side=max_side,
            branch=branch,
        )
        engine, used_model = llm_engine_label(vision=True)
    else:
        ocr_text = _ocr_image_text(source)
        if not ocr_text.strip():
            raise RuntimeError(
                "No OCR text extracted from cheque image for LLM extraction."
            )
        fixed = re.sub(
            r"\bIABL\b",
            "HBL",
            ocr_text,
            flags=re.IGNORECASE,
        )
        if "habib bank" in fixed.lower() and "HBL" not in fixed.upper():
            fixed = "HBL\n" + fixed
        prompt = CHEQUE_TEXT_PROMPT.replace("{ocr_text}", fixed[:12000])
        raw = call_llm_text(prompt, model=model, branch=branch)
        engine, used_model = llm_engine_label(vision=False)

    try:
        parsed = json.loads(_strip_json_fence(raw))
        if not isinstance(parsed, dict):
            raise ValueError("LLM response is not a JSON object")
    except (json.JSONDecodeError, ValueError):
        cleaned = _strip_json_fence(raw)
        try:
            parsed = ast.literal_eval(cleaned)
            if isinstance(parsed, dict):
                pass
            else:
                raise ValueError("LLM response is not a dict")
        except Exception as exc:
            logger.error("Failed to parse cheque LLM JSON: %s | raw=%r", exc, raw[:500])
            raise RuntimeError(f"LLM returned invalid JSON: {exc}") from exc

    result = _normalize_cheque_payload(parsed)
    result["meta"] = {
        "engine": engine,
        "model": used_model,
        "raw_preview": raw[:400],
    }
    logger.info(
        "LLM cheque extraction complete (%s): bank=%r cheque_no=%r amount=%r",
        engine,
        result.get("bank_name") or result.get("bank_code"),
        result.get("cheque_number"),
        result.get("amount_figures"),
    )
    return result
