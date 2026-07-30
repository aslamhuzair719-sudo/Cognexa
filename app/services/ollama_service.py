"""Ollama LLM service with retry and JSON validation."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Optional

import requests
from pydantic import BaseModel, ValidationError

from app import config
from app.logging_config import get_logger
from app.services.schema_parser import parse_and_validate

logger = get_logger(__name__)


class BaseLLMService(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate raw text from a prompt."""


class OllamaService(BaseLLMService):
    """Local Ollama client (gemma3:4b by default).

    Responsibilities:
    - send OCR-backed prompts
    - receive JSON
    - retry on failure
    - validate output against Pydantic schemas
    """

    def __init__(
        self,
        url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.url = url or config.OLLAMA_URL
        self.model = model or config.OLLAMA_MODEL
        self.timeout = timeout or config.OLLAMA_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else config.OLLAMA_MAX_RETRIES

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama HTTP {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
            return (data.get("response") or "").strip()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Failed to reach Ollama at {self.url}. "
                f"Ensure Ollama is running with model '{self.model}': {exc}"
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
                    "Ollama extraction attempt %s/%s for %s",
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
            f"Ollama extraction failed after {attempts} attempts for {document_type}: {last_error}"
        )
