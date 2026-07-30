"""Resolve LLM provider from config and expose unified text/vision helpers."""

from __future__ import annotations

from typing import Optional, Union

import numpy as np

from app import config
from app.services.gemini_service import GeminiService
from app.services.groq_service import GroqService
from app.services.ollama_service import BaseLLMService, OllamaService


def get_llm_provider() -> str:
    return getattr(config, "LLM_PROVIDER", "gemini").strip().lower()


def resolve_gemini_api_key(*, branch: bool = False) -> str:
    """Account-opening uses GEMINI_API_KEY; branch scan uses GEMINI_BRANCH_API_KEY."""
    if branch:
        return (config.GEMINI_BRANCH_API_KEY or config.GEMINI_API_KEY or "").strip()
    return (config.GEMINI_API_KEY or "").strip()


def get_llm_service(*, model: Optional[str] = None, branch: bool = False) -> BaseLLMService:
    """Return the configured LLM service instance."""
    provider = get_llm_provider()
    if provider == "ollama":
        return OllamaService(model=model)
    if provider == "groq":
        return GroqService(model=model)
    return GeminiService(
        api_key=resolve_gemini_api_key(branch=branch),
        model=model,
    )


def get_branch_llm_service(*, model: Optional[str] = None) -> BaseLLMService:
    """Branch document scan — separate Gemini key when GEMINI_BRANCH_API_KEY is set."""
    return get_llm_service(model=model, branch=True)


def call_llm_text(
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    branch: bool = False,
) -> str:
    """Text-only LLM call via the active provider."""
    provider = get_llm_provider()
    if provider == "ollama":
        return OllamaService(model=model, timeout=timeout).generate(prompt)
    if provider == "groq":
        return GroqService(model=model, timeout=timeout).generate(prompt)
    return GeminiService(
        api_key=resolve_gemini_api_key(branch=branch),
        model=model,
        timeout=timeout,
    ).generate(prompt)


def call_llm_vision(
    image_b64: str,
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    branch: bool = False,
) -> str:
    """Image + text LLM call. Gemini and Ollama support vision; Groq does not."""
    provider = get_llm_provider()
    if provider == "ollama":
        from app.ocr_pipeline.llm_extract import call_ollama_vision

        return call_ollama_vision(image_b64, prompt, model=model, timeout=timeout)
    if provider == "groq":
        raise RuntimeError("Groq does not support vision; use gemini or ollama.")
    vision_model = model or config.GEMINI_VISION_MODEL or config.GEMINI_MODEL
    return GeminiService(
        api_key=resolve_gemini_api_key(branch=branch),
        model=vision_model,
        timeout=timeout,
    ).generate_with_image(
        prompt,
        image_b64,
        model=vision_model,
    )


def llm_engine_label(*, vision: bool = False) -> tuple[str, str]:
    """Return (engine, model_name) for meta blocks."""
    provider = get_llm_provider()
    if provider == "ollama":
        if vision:
            model = config.OLLAMA_VISION_MODEL or config.OLLAMA_MODEL
            return "ollama_vision", model
        return "ollama_ocr_text", config.OLLAMA_MODEL
    if provider == "groq":
        return "groq_ocr_text", config.GROQ_MODEL
    if vision:
        model = config.GEMINI_VISION_MODEL or config.GEMINI_MODEL
        return "gemini_vision", model
    return "gemini_ocr_text", config.GEMINI_MODEL


def call_llm_vision_source(
    source: Union[str, bytes, np.ndarray],
    prompt: str,
    *,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
    max_side: int = 1600,
    branch: bool = False,
) -> str:
    """Image/PDF source + prompt → LLM vision response."""
    from app.ocr_pipeline.llm_extract import source_to_base64_jpeg

    image_b64 = source_to_base64_jpeg(source, max_side=max_side)
    return call_llm_vision(
        image_b64,
        prompt,
        model=model,
        timeout=timeout,
        branch=branch,
    )


def supports_vision() -> bool:
    return get_llm_provider() in {"gemini", "ollama"}
