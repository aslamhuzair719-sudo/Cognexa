"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# OCR
TESSERACT_CMD: str = os.getenv(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)
OCR_DPI: int = int(os.getenv("OCR_DPI", "300"))

# Remittance ROI + PaddleOCR pipeline
PADDLE_OCR_LANG: str = os.getenv("PADDLE_OCR_LANG", "en")
PADDLE_USE_ANGLE_CLS: bool = os.getenv("PADDLE_USE_ANGLE_CLS", "1") not in {
    "0",
    "false",
    "False",
}
PADDLE_USE_GPU: bool = os.getenv("PADDLE_USE_GPU", "0") in {"1", "true", "True"}
OCR_SAVE_DEBUG: bool = os.getenv("OCR_SAVE_DEBUG", "0") in {"1", "true", "True"}
OCR_DENOISE_METHOD: str = os.getenv("OCR_DENOISE_METHOD", "nlm")  # nlm | gaussian | none

# LLM provider for branch scan / extraction: "gemini" | "groq" | "ollama"
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

# Google Gemini (Google AI Studio — recommended)
# GEMINI_API_KEY: customer account-opening verification / analysis queue
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
# GEMINI_BRANCH_API_KEY: branch console document scan (remittance, CNIC, payslip, etc.)
# Falls back to GEMINI_API_KEY when unset.
GEMINI_BRANCH_API_KEY: str = os.getenv("GEMINI_BRANCH_API_KEY", "")
GEMINI_URL: str = os.getenv(
    "GEMINI_URL",
    "https://generativelanguage.googleapis.com",
)
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VISION_MODEL: str = os.getenv("GEMINI_VISION_MODEL", GEMINI_MODEL)
GEMINI_TIMEOUT: int = int(os.getenv("GEMINI_TIMEOUT", "120"))
GEMINI_MAX_RETRIES: int = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

# Groq (OpenAI-compatible chat completions)
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_URL: str = os.getenv(
    "GROQ_URL",
    "https://api.groq.com/openai/v1/chat/completions",
)
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT: int = int(os.getenv("GROQ_TIMEOUT", "120"))
GROQ_MAX_RETRIES: int = int(os.getenv("GROQ_MAX_RETRIES", "2"))

# Ollama (local — set LLM_PROVIDER=ollama and uncomment Ollama call sites to use)
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")
# Vision model for image→JSON remittance extraction (defaults to OLLAMA_MODEL)
OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", OLLAMA_MODEL)
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "500"))
OLLAMA_MAX_RETRIES: int = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))

# Image quality thresholds
MIN_RESOLUTION_WIDTH: int = int(os.getenv("MIN_RESOLUTION_WIDTH", "600"))
MIN_RESOLUTION_HEIGHT: int = int(os.getenv("MIN_RESOLUTION_HEIGHT", "400"))
MIN_BLUR_VARIANCE: float = float(os.getenv("MIN_BLUR_VARIANCE", "80.0"))
MIN_BRIGHTNESS: float = float(os.getenv("MIN_BRIGHTNESS", "40.0"))
MAX_BRIGHTNESS: float = float(os.getenv("MAX_BRIGHTNESS", "220.0"))
MIN_OCR_CHARS: int = int(os.getenv("MIN_OCR_CHARS", "30"))

# Validation
SALARY_TOLERANCE_PERCENT: float = float(os.getenv("SALARY_TOLERANCE_PERCENT", "10.0"))
NAME_SIMILARITY_THRESHOLD: float = float(os.getenv("NAME_SIMILARITY_THRESHOLD", "0.82"))

# Storage
UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
APPLICATIONS_DIR: Path = UPLOAD_DIR / "applications"
APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
BRANCH_ENTRIES_DIR: Path = UPLOAD_DIR / "branch_entries"
BRANCH_ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
SIGNATURES_DIR: Path = UPLOAD_DIR / "signatures"
SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)

# Signature match threshold (percentage) for "likely match" messaging
SIGNATURE_MATCH_THRESHOLD: float = float(os.getenv("SIGNATURE_MATCH_THRESHOLD", "95.0"))
# Optional path to Siamese CNN weights (default: models/signature_siamese.pt)
SIGNATURE_SIAMESE_WEIGHTS: str = os.getenv("SIGNATURE_SIAMESE_WEIGHTS", "")

# Postgres
POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5433"))
POSTGRES_DB: str = os.getenv("POSTGRES_DB", "DocumentScan")
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "123456")
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}",
)

# Sessions
SESSION_SECRET: str = os.getenv("SESSION_SECRET", "document-scan-dev-secret-change-me")

# Logging
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# Defaults (CLI / local testing)
DEFAULT_PDF_PATH: str = os.getenv("DEFAULT_PDF_PATH", "docs/12.png")
