"""Google Gemini LLM service (Google AI Studio / Generative Language API)."""

from __future__ import annotations

import json
from typing import Optional

import requests
from pydantic import BaseModel, ValidationError

from app import config
from app.logging_config import get_logger
from app.services.ollama_service import BaseLLMService
from app.services.schema_parser import parse_and_validate

logger = get_logger(__name__)


class GeminiService(BaseLLMService):
    """Gemini client via generateContent (text + vision)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        vision_model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.GEMINI_API_KEY
        self.base_url = (base_url or config.GEMINI_URL).rstrip("/")
        self.model = model or config.GEMINI_MODEL
        self.vision_model = vision_model or config.GEMINI_VISION_MODEL or self.model
        self.timeout = timeout or config.GEMINI_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else config.GEMINI_MAX_RETRIES
        )

    def _endpoint(self, model: Optional[str] = None) -> str:
        name = model or self.model
        return f"{self.base_url}/v1beta/models/{name}:generateContent"

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError(
                "Gemini API key is not set. Configure GEMINI_API_KEY (account opening) "
                "and/or GEMINI_BRANCH_API_KEY (branch scan) in .env."
            )
        return {
            "Content-Type": "application/json",
            "X-goog-api-key": self.api_key,
        }

    @staticmethod
    def _parse_response(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise RuntimeError(
                f"Gemini returned no candidates"
                + (f" (blocked: {block})" if block else "")
                + f": {str(data)[:500]}"
            )
        parts = (candidates[0].get("content") or {}).get("parts") or []
        texts = [p.get("text", "") for p in parts if p.get("text")]
        if not texts:
            raise RuntimeError(f"Gemini returned empty content: {str(data)[:500]}")
        return "".join(texts).strip()

    def _post(self, payload: dict, *, model: Optional[str] = None) -> str:
        try:
            response = requests.post(
                self._endpoint(model),
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Gemini HTTP {response.status_code}: {response.text[:500]}"
                )
            return self._parse_response(response.json())
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Failed to reach Gemini at {self._endpoint(model)}: {exc}"
            ) from exc

    def generate(self, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        return self._post(payload)

    def generate_with_image(
        self,
        prompt: str,
        image_b64: str,
        *,
        mime_type: str = "image/jpeg",
        model: Optional[str] = None,
    ) -> str:
        """Multimodal generateContent — image + text prompt."""
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": image_b64,
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
        return self._post(payload, model=model or self.vision_model)

    def extract_structured(
        self,
        prompt: str,
        document_type: str,
    ) -> BaseModel:
        """Generate JSON, validate with schema, retry on failure."""
        last_error: Optional[Exception] = None
        current_prompt = prompt

        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    "Gemini extraction attempt %s/%s for %s",
                    attempt,
                    attempts,
                    document_type,
                )
                raw = self.generate(current_prompt)
                return parse_and_validate(document_type, raw)
            except (ValueError, ValidationError, RuntimeError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("Gemini extraction attempt %s failed: %s", attempt, exc)
                current_prompt = (
                    prompt
                    + "\n\nREMINDER: Respond ONLY with a valid JSON object matching the "
                    "requested schema. No markdown fences, no commentary."
                )

    def extract_structured_from_image(
        self,
        prompt: str,
        image_b64: str,
        document_type: str,
        *,
        mime_type: str = "image/jpeg",
    ) -> BaseModel:
        """Vision generate JSON, validate with schema, retry on failure."""
        last_error: Optional[Exception] = None
        current_prompt = prompt

        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                logger.info(
                    "Gemini vision extraction attempt %s/%s for %s",
                    attempt,
                    attempts,
                    document_type,
                )
                raw = self.generate_with_image(
                    current_prompt,
                    image_b64,
                    mime_type=mime_type,
                )
                return parse_and_validate(document_type, raw)
            except (ValueError, ValidationError, RuntimeError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    "Gemini vision extraction attempt %s failed: %s", attempt, exc
                )
                current_prompt = (
                    prompt
                    + "\n\nREMINDER: Respond ONLY with a valid JSON object matching the "
                    "requested schema. No markdown fences, no commentary."
                )

        raise RuntimeError(
            f"Gemini vision extraction failed after {attempts} attempts for "
            f"{document_type}: {last_error}"
        )
