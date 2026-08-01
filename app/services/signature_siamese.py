"""Siamese CNN for signature embedding and similarity scoring."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from app import config
from app.logging_config import get_logger

logger = get_logger(__name__)

_MODEL: Optional[object] = None
_DEVICE: Optional[object] = None

INPUT_H = 128
INPUT_W = 256
EMBED_DIM = 128


def _models_dir() -> Path:
    path = config.BASE_DIR / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_weights_path() -> Path:
    custom = (getattr(config, "SIGNATURE_SIAMESE_WEIGHTS", "") or "").strip()
    if custom:
        return Path(custom)
    return _models_dir() / "signature_siamese.pt"


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required for Siamese signature verification. "
            "Install with: pip install torch"
        ) from exc
    return torch, nn, F


def build_siamese_encoder():
    """Shared-weight CNN encoder used by the Siamese twin towers."""
    torch, nn, F = _require_torch()

    class Encoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(1, 32, kernel_size=3, padding=1),
                nn.BatchNorm2d(32),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, kernel_size=3, padding=1),
                nn.BatchNorm2d(64),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(64, 128, kernel_size=3, padding=1),
                nn.BatchNorm2d(128),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(128, 256, kernel_size=3, padding=1),
                nn.BatchNorm2d(256),
                nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool2d((4, 8)),
            )
            self.head = nn.Sequential(
                nn.Flatten(),
                nn.Linear(256 * 4 * 8, 256),
                nn.ReLU(inplace=True),
                nn.Dropout(0.15),
                nn.Linear(256, EMBED_DIM),
            )

        def forward(self, x):
            x = self.features(x)
            x = self.head(x)
            return F.normalize(x, p=2, dim=1)

    return Encoder()


def _get_device():
    global _DEVICE
    if _DEVICE is not None:
        return _DEVICE
    torch, _, _ = _require_torch()
    _DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _DEVICE


def load_encoder(weights_path: Optional[Path] = None):
    """Load Siamese encoder weights (lazy singleton)."""
    global _MODEL
    if _MODEL is not None:
        return _MODEL

    torch, _, _ = _require_torch()
    path = weights_path or default_weights_path()
    encoder = build_siamese_encoder()
    device = _get_device()

    if path.is_file():
        state = torch.load(path, map_location=device, weights_only=True)
        encoder.load_state_dict(state)
        logger.info("Loaded Siamese signature weights from %s", path)
    else:
        logger.warning(
            "Siamese weights not found at %s — run scripts/train_signature_siamese.py",
            path,
        )

    encoder.to(device)
    encoder.eval()
    _MODEL = encoder
    return _MODEL


def preprocess_signature_bytes(data: bytes) -> np.ndarray:
    """Decode bytes → normalized grayscale ink canvas for the Siamese network."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image. Please upload a valid image file.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return np.zeros((INPUT_H, INPUT_W), dtype=np.float32)

    pad = 8
    x0 = max(int(xs.min()) - pad, 0)
    x1 = min(int(xs.max()) + pad + 1, mask.shape[1])
    y0 = max(int(ys.min()) - pad, 0)
    y1 = min(int(ys.max()) + pad + 1, mask.shape[0])
    cropped = mask[y0:y1, x0:x1]

    resized = cv2.resize(cropped, (INPUT_W, INPUT_H), interpolation=cv2.INTER_AREA)
    return (resized.astype(np.float32) / 255.0)


def embed_signature(canvas: np.ndarray) -> np.ndarray:
    """Return L2-normalized embedding vector for one preprocessed signature."""
    if canvas.max() == 0:
        raise ValueError("Signature appears empty (no ink detected).")

    torch, _, _ = _require_torch()
    encoder = load_encoder()
    device = _get_device()

    tensor = torch.from_numpy(canvas).unsqueeze(0).unsqueeze(0).to(device)
    with torch.no_grad():
        vector = encoder(tensor).cpu().numpy()[0]
    return vector


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for unit vectors in [0, 1] after clamping negative values."""
    sim = float(np.dot(a, b))
    return float(np.clip((sim + 1.0) / 2.0, 0.0, 1.0))


def compare_siamese_arrays(reg_canvas: np.ndarray, probe_canvas: np.ndarray) -> Tuple[float, dict]:
    """Compare two preprocessed signature canvases via Siamese embeddings."""
    reg_emb = embed_signature(reg_canvas)
    probe_emb = embed_signature(probe_canvas)
    sim = cosine_similarity(reg_emb, probe_emb)
    distance = float(np.linalg.norm(reg_emb - probe_emb))
    # Map cosine → percentage; distance is auxiliary visual signal for UI
    match_pct = round(sim * 100.0, 1)
    scores = {
        "visual_similarity": round(max(0.0, (1.0 - distance / 2.0) * 100.0), 1),
        "similarity": match_pct,
    }
    return match_pct, scores


def compare_siamese_bytes(registered_bytes: bytes, probe_bytes: bytes) -> dict:
    """Full pipeline: bytes → preprocess → Siamese compare."""
    reg = preprocess_signature_bytes(registered_bytes)
    probe = preprocess_signature_bytes(probe_bytes)
    if reg.max() == 0:
        raise ValueError("Registered signature appears empty (no ink detected).")
    if probe.max() == 0:
        raise ValueError("Uploaded signature appears empty (no ink detected).")

    match_pct, scores = compare_siamese_arrays(reg, probe)
    logger.info("Siamese signature compare: similarity=%.1f%%", match_pct)
    return {
        "match_percentage": match_pct,
        "method": "siamese_cnn",
        "scores": scores,
    }
