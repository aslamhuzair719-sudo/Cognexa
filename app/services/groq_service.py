"""Groq LLM service (OpenAI-compatible chat completions)."""

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


class GroqService(BaseLLMService):
    """Groq Cloud client via OpenAI-compatible /chat/completions."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else config.GROQ_API_KEY
        self.url = url or config.GROQ_URL
        self.model = model or config.GROQ_MODEL
        self.timeout = timeout or config.GROQ_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else config.GROQ_MAX_RETRIES
        )

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = requests.post(
                self.url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Groq HTTP {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"Groq returned no choices: {str(data)[:300]}")
            message = choices[0].get("message") or {}
            return (message.get("content") or "").strip()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Failed to reach Groq at {self.url} with model '{self.model}': {exc}"
            ) from exc

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
                    "Groq extraction attempt %s/%s for %s",
                    attempt,
                    attempts,
                    document_type,
                )
                raw = self.generate(current_prompt)
                return parse_and_validate(document_type, raw)
            except (ValueError, ValidationError, RuntimeError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("Extraction attempt %s failed: %s", attempt, exc)
                current_prompt = (
                    prompt
                    + "\n\nREMINDER: Respond ONLY with a valid JSON object matching the "
                    "requested schema. No markdown fences, no commentary."
                )

        raise RuntimeError(
            f"Groq extraction failed after {attempts} attempts for {document_type}: {last_error}"
        )
