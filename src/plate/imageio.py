from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Config
from .scene import Loaded


class ImageLoadError(ValueError):
    """The input is missing, unreadable or not a supported image."""


def _to_8bit(im: Image.Image) -> Image.Image:
    """Pillow's convert() clips 16/32-bit integer and float pixels to 0..255, which
    turns a 16-bit grayscale PNG white. Scale those modes to 8-bit explicitly."""
    if im.mode not in ("I", "F") and not im.mode.startswith("I;16"):
        return im
    a = np.asarray(im, dtype=np.float64)
    top = float(a.max()) if a.size else 0.0
    if im.mode == "F" and top <= 1.0:
        a = a * 255.0
    elif top > 255.0:
        a = a * (255.0 / max(65535.0, top))
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "L")


def open_rgba(path: Path | str) -> Image.Image:
    """Open any Pillow-readable image as 8-bit RGBA in its DISPLAYED orientation
    (EXIF rotation applied, as every image viewer shows it). Raises ImageLoadError
    with a readable message instead of a library traceback."""
    p = Path(path)
    if p.is_dir():
        raise ImageLoadError(f"{p} is a directory, not an image")
    if not p.exists():
        raise ImageLoadError(f"no such file: {p}")
    try:
        with Image.open(p) as im:
            im.load()
            im = ImageOps.exif_transpose(im)
            return _to_8bit(im).convert("RGBA")
    except Image.DecompressionBombError as e:
        raise ImageLoadError(f"{p} is too large to decode safely ({e})") from e
    except UnidentifiedImageError as e:
        raise ImageLoadError(f"{p} is not a recognised image format") from e
    except (OSError, SyntaxError, ValueError) as e:
        raise ImageLoadError(f"cannot read {p}: {e}") from e


def noise_fraction(rgb: np.ndarray, alpha: np.ndarray | None = None) -> float:
    """Share of pixels that differ visibly from their 3x3 median: ~0 for clean flat art,
    large for JPEG/scan noise. (Genuine edges contribute only a thin, constant fringe.)"""
    med = cv2.medianBlur(rgb, 3).astype(np.int16)
    diff = np.abs(rgb.astype(np.int16) - med).max(axis=2)
    if alpha is not None and (alpha > 250).any():
        diff = diff[alpha > 250]
    return float((diff > 6).mean())


def load_image(path: Path | str, cfg: Config) -> Loaded:
    im = open_rgba(path)
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
