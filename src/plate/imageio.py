from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from scipy import ndimage as ndi

from .config import Config
from .scene import Loaded


class ImageLoadError(ValueError):
    """The input is missing, unreadable or not a supported image."""


def _to_8bit(im: Image.Image, *, bit_depth: int | None = None) -> Image.Image:
    """Pillow's convert() clips 16/32-bit integer and float pixels to 0..255, which
    turns a 16-bit grayscale PNG white. Scale those modes to 8-bit explicitly."""
    if im.mode not in ("I", "F") and not im.mode.startswith("I;16"):
        return im
    a = np.asarray(im, dtype=np.float64)
    top = float(a.max()) if a.size else 0.0
    if bit_depth == 16 or im.mode.startswith("I;16"):
        # A dark 16-bit image still uses the full declared 0..65535 range.
        # Mode I alone is ambiguous (e.g. 32-bit TIFF); its PNG depth is passed
        # explicitly before EXIF transpose drops the file-format metadata.
        a = a * (255.0 / 65535.0)
    elif im.mode == "F" and top <= 1.0:
        a = a * 255.0
    elif top > 255.0:
        a = a * (255.0 / max(65535.0, top))
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "L")


def _png16_rgba(path: Path, info: dict) -> Image.Image:
    """Keep full PNG samples through tRNS comparison, then normalize to 8 bits.

    Pillow has already discarded low bytes for multichannel 16-bit PNGs. OpenCV's
    unchanged decoder retains them; UNCHANGED also leaves EXIF rotation to us.
    """
    samples = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if samples is None or samples.dtype != np.uint16:
        raise ValueError('cannot decode 16-bit PNG at full sample depth')
    if samples.ndim == 2:
        rgb = np.repeat(samples[..., None], 3, axis=2)
        alpha = np.full_like(samples, 65535)
    elif samples.shape[2] == 2:
        rgb = np.repeat(samples[..., :1], 3, axis=2)
        alpha = samples[..., 1]
    elif samples.shape[2] in (3, 4):
        rgb = samples[..., 2::-1]  # BGR(A) -> RGB(A)
        alpha = samples[..., 3] if samples.shape[2] == 4 else np.full(samples.shape[:2], 65535, np.uint16)
    else:
        raise ValueError('unsupported 16-bit PNG channel layout')
    key = info.get('transparency')
    if isinstance(key, int):
        # libpng/OpenCV may return grayscale tRNS without an alpha channel.
        alpha = np.where(rgb[..., 0] == key, 0, 65535)
    elif isinstance(key, tuple):
        alpha = np.where(np.all(rgb == key, axis=2), 0, 65535)
    rgba = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = np.rint(rgb.astype(np.float64) / 257).astype(np.uint8)
    rgba[..., 3] = np.rint(alpha.astype(np.float64) / 257).astype(np.uint8)
    converted = Image.fromarray(rgba)
    converted.info.update(info)  # retain EXIF for the single orientation step below
    return converted


def open_rgba(path: Path | str) -> Image.Image:
    """Open any Pillow-readable image as 8-bit RGBA in its DISPLAYED orientation
    (EXIF rotation applied, as every image viewer shows it). Raises ImageLoadError
    with a readable message instead of a library traceback.

    PNG channels use their declared sample range (16-bit -> nearest 8-bit); tRNS
    is matched before reduction. ICC/gamma metadata is not colour-transformed.
    Animated inputs use the default/first image, not an animation reconstruction.
    """
    p = Path(path)
    if p.is_dir():
        raise ImageLoadError(f"{p} is a directory, not an image")
    if not p.exists():
        raise ImageLoadError(f"no such file: {p}")
    try:
        with Image.open(p) as im:
            depth, colour = None, None
            if im.format == 'PNG':
                # IHDR is fixed at the start; read the declared depth before
                # Pillow's mode conversion or EXIF copying discards that context.
                with p.open('rb') as stream:
                    header = stream.read(26)
                if len(header) != 26 or header[:8] != b'\x89PNG\r\n\x1a\n':
                    raise ValueError('incomplete PNG header')
                depth, colour = header[24], header[25]
            im.load()
            if depth == 16:
                im = _png16_rgba(p, im.info)
            elif colour == 0 and depth in (2, 4) and 'transparency' in im.info:
                # Pillow expands low-depth gray pixels to L but leaves tRNS in
                # the original sample range. Match the expanded key to the pixels.
                im.info['transparency'] = round(im.info['transparency'] * 255 / ((1 << depth)-1))
            im = ImageOps.exif_transpose(im)
            return _to_8bit(im).convert("RGBA")
    except Image.DecompressionBombError as e:
        raise ImageLoadError(f"{p} is too large to decode safely ({e})") from e
    except UnidentifiedImageError as e:
        raise ImageLoadError(f"{p} is not a recognised image format") from e
    except (OSError, SyntaxError, ValueError, cv2.error) as e:
        raise ImageLoadError(f"cannot read {p}: {e}") from e


def noise_fraction(rgb: np.ndarray, alpha: np.ndarray | None = None) -> float:
    """Share of pixels that differ visibly from their 3x3 median: ~0 for clean flat art,
    large for JPEG/scan noise. (Genuine edges contribute only a thin, constant fringe.)"""
    med = cv2.medianBlur(rgb, 3).astype(np.int16)
    diff = np.abs(rgb.astype(np.int16) - med).max(axis=2)
    if alpha is not None and (alpha > 250).any():
        diff = diff[alpha > 250]
    return float((diff > 6).mean())


def interior_noise_fraction(rgb: np.ndarray, alpha: np.ndarray | None = None) -> float:
    """Median-residual noise measured only in flat interiors, away from edges.

    `noise_fraction` is confounded by edge density: dense anti-aliased edges on clean art
    produce a large median-residual fraction without any real noise. Uniform Gaussian noise,
    by contrast, reaches deep into flat interiors while anti-aliased residual stays confined
    to thin fringes next to edges. Restricting the same `>6` residual test to pixels at least
    3px from any gradient edge isolates true mild noise (where the global fraction is masked
    by edges) from clean edge-dense art. Returns 0.0 when too few interior pixels remain to
    measure reliably (e.g. heavy noise where the global branch already fires)."""
    med = cv2.medianBlur(rgb, 3).astype(np.int16)
    diff = np.abs(rgb.astype(np.int16) - med).max(axis=2)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    edge = np.hypot(gx, gy) > 20
    interior = ndi.distance_transform_edt(~edge) >= 3
    if alpha is not None:
        interior &= alpha > 250
    if int(interior.sum()) < 100:
        return 0.0
    return float((diff[interior] > 6).mean())


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
        # The global fraction catches heavy noise; the interior estimator catches mild
        # uniform noise whose global fraction is masked by edge density. They complement:
        # fire on either so the sigma-2 "blind spot" between them no longer slips through.
        noisy = (noise_fraction(rgb, alpha) > 0.04
                 or interior_noise_fraction(rgb, alpha) > cfg.interior_noise)
        level = 2 if noisy else 0
    if level:
        # edge-preserving: bilateral keeps corners and small features that a median erases
        for _ in range(level):
            rgb = cv2.bilateralFilter(rgb, 9, 40, 5)
    return Loaded(rgb=rgb, alpha=alpha, orig_size=(w, h), scale=scale if scale != 1.0 else 1.0)
