"""Structured logging setup."""

from __future__ import annotations

import logging
import sys

from app import config


def setup_logging() -> None:
    """Configure root logger once for the application."""
    level = getattr(logging, config.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(config.SIRI_LOG_DIR / "sirilogs.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as exc:
        root.error("Failed to create log file handler: %s", exc)

    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
