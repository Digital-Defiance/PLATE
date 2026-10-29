from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .config import Config
from .scene import Loaded


def noise_fraction(rgb: np.ndarray, alpha: np.ndarray | None = None) -> float:
    """Share of pixels that differ visibly from their 3x3 median: ~0 for clean flat art,
    large for JPEG/scan noise. (Genuine edges contribute only a thin, constant fringe.)"""
    med = cv2.medianBlur(rgb, 3).astype(np.int16)
    diff = np.abs(rgb.astype(np.int16) - med).max(axis=2)
    if alpha is not None and (alpha > 250).any():
        diff = diff[alpha > 250]
    return float((diff > 6).mean())


def load_image(path: Path | str, cfg: Config) -> Loaded:
    im = Image.open(path)
    im = im.convert("RGBA")
    w, h = im.size
    scale = 1.0
    longest = max(w, h)
    if longest > cfg.work_size:
        scale = cfg.work_size / longest
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    arr = np.asarray(im)
    rgb, alpha = arr[..., :3].copy(), arr[..., 3].copy()
    level = cfg.denoise
    if level < 0:                       # auto: only filter inputs that are actually noisy
        level = 2 if noise_fraction(rgb, alpha) > 0.04 else 0
    if level:
        # edge-preserving: bilateral keeps corners and small features that a median erases
        for _ in range(level):
            rgb = cv2.bilateralFilter(rgb, 9, 40, 5)
    return Loaded(rgb=rgb, alpha=alpha, orig_size=(w, h), scale=scale if scale != 1.0 else 1.0)
