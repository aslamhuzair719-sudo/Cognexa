"""Document gate detector protocol."""

from __future__ import annotations

from typing import Protocol, Union

import numpy as np

from app.document_detection.schemas import RawGateDetection

ImageSource = Union[str, bytes, np.ndarray]


class DocumentGateDetector(Protocol):
    """Strategy interface for Stage 1 + 2 vision detection."""

    def detect(self, source: ImageSource, *, branch: bool = True) -> RawGateDetection:
        """Return raw document presence and type detection."""
