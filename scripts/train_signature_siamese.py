"""Train Siamese signature encoder on synthetic stroke pairs and save weights."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.signature_siamese import (  # noqa: E402
    EMBED_DIM,
    INPUT_H,
    INPUT_W,
    build_siamese_encoder,
    default_weights_path,
)


def _random_strokes(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    canvas = np.zeros((INPUT_H, INPUT_W), dtype=np.uint8)
    strokes = int(rng.integers(2, 6))
    for _ in range(strokes):
        pts = []
        x = int(rng.integers(20, INPUT_W - 20))
        y = int(rng.integers(30, INPUT_H - 20))
        for _ in range(int(rng.integers(3, 8))):
            x = int(np.clip(x + rng.integers(-35, 36), 5, INPUT_W - 5))
            y = int(np.clip(y + rng.integers(-18, 19), 5, INPUT_H - 5))
            pts.append([x, y])
        thickness = int(rng.integers(1, 3))
        pts_arr = np.array(pts, dtype=np.int32)
        if len(pts_arr) >= 2:
            cv2.polylines(canvas, [pts_arr], False, 255, thickness, cv2.LINE_AA)
        if rng.random() > 0.5:
            cv2.ellipse(
                canvas,
                (x, y),
                (int(rng.integers(10, 40)), int(rng.integers(4, 14))),
                int(rng.integers(-30, 30)),
                0,
                180,
                255,
                thickness,
                cv2.LINE_AA,
            )
    return canvas


def _augment(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = img.copy()
    angle = float(rng.uniform(-8, 8))
    scale = float(rng.uniform(0.9, 1.1))
    m = cv2.getRotationMatrix2D((INPUT_W / 2, INPUT_H / 2), angle, scale)
    out = cv2.warpAffine(out, m, (INPUT_W, INPUT_H), borderValue=0)
    if rng.random() > 0.5:
        out = cv2.GaussianBlur(out, (3, 3), 0)
    noise = rng.normal(0, 6, out.shape).astype(np.int16)
    out = np.clip(out.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return out


def _to_tensor(img: np.ndarray, torch):
    arr = img.astype(np.float32) / 255.0
    return torch.from_numpy(arr).unsqueeze(0)  # (1, H, W)


def train(epochs: int = 12, pairs: int = 800, lr: float = 1e-3) -> Path:
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, Dataset

    class PairDataset(Dataset):
        def __len__(self):
            return pairs

        def __getitem__(self, idx):
            rng = np.random.default_rng(idx + random.randint(0, 10_000))
            if idx % 2 == 0:
                base = _random_strokes(idx)
                a = _augment(base, rng)
                b = _augment(base, np.random.default_rng(idx + 999))
                label = 1.0
            else:
                a = _random_strokes(idx)
                b = _random_strokes(idx + 50_000)
                label = 0.0
            return _to_tensor(a, torch), _to_tensor(b, torch), torch.tensor(label)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = build_siamese_encoder().to(device)
    loader = DataLoader(PairDataset(), batch_size=32, shuffle=True)
    opt = torch.optim.Adam(encoder.parameters(), lr=lr)

    for epoch in range(1, epochs + 1):
        encoder.train()
        total_loss = 0.0
        correct = 0
        count = 0
        for x1, x2, y in loader:
            x1, x2, y = x1.to(device), x2.to(device), y.to(device)
            e1 = encoder(x1)
            e2 = encoder(x2)
            dist = F.pairwise_distance(e1, e2)
            # Contrastive-style: pull positives (y=1), push negatives (y=0)
            loss_pos = y * dist.pow(2)
            loss_neg = (1 - y) * F.relu(1.0 - dist).pow(2)
            loss = (loss_pos + loss_neg).mean()

            opt.zero_grad()
            loss.backward()
            opt.step()

            total_loss += float(loss.item()) * len(y)
            sim = 1.0 - dist / 2.0
            pred = (sim > 0.5).float()
            correct += int((pred == y).sum().item())
            count += len(y)

        acc = correct / max(count, 1)
        print(f"epoch {epoch}/{epochs} loss={total_loss / count:.4f} acc={acc:.3f}")

    out_path = default_weights_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(encoder.state_dict(), out_path)
    # Keep ASCII-only output to avoid Windows console encoding issues.
    print(f"Saved Siamese weights -> {out_path}")
    return out_path


if __name__ == "__main__":
    train()
