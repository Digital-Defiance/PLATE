"""Browser glue for PLATE: a thin ``plate.web`` module shipped inside the wheel.

The conversion engine is never modified. This module only bridges raw uploaded
bytes to the unchanged ``pipeline.run`` entry point and exposes small pre-checks
the browser shell needs. It stays version-locked to the engine because it ships
in the same wheel.

Functions here run as pure CPython under the existing ``pytest`` suite and,
unchanged, inside Pyodide's in-memory filesystem (MEMFS) in the browser.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from .config import PRESETS, Config, load
from .imageio import (
    ImageLoadError,
    _is_jpeg,
    interior_noise_fraction,
    noise_fraction,
    open_rgba,
)

# Mirror of imageio.load_image's auto-denoise trigger: the global median-residual
# fraction catches heavy noise; the interior estimator catches mild uniform noise
# whose global fraction is masked by edge density.
NOISE_FRACTION_TRIGGER = 0.04

# Image formats the browser shell accepts and the engine's decoder handles. The
# extension (case-insensitive) selects the MEMFS target path so cv2.imread/Pillow
# pick the right format; an unrecognised extension is rejected rather than guessed.
RECOGNISED_EXTENSIONS = frozenset({"png", "jpg", "jpeg"})

# Surfaced before/at conversion when check_noise flags a compressed, noisy JPEG:
# hidden-object recovery is limited on such sources today (v0.2 robustness work).
BETA_JPEG_WARNING = (
    "beta: compressed JPEG detected; hidden-object recovery is limited on noisy "
    "JPEGs today, so some occluded shapes may not be fully reconstructed"
)


class NoiseCheckError(ValueError):
    """The uploaded image could not be decoded or resized for the noise pre-check."""


class ConvertError(ValueError):
    """The upload was empty or carried an unrecognised image extension."""


class ConfigError(ValueError):
    """An override map named an unknown preset or an unknown lever key."""


# UI lever name -> Config field. The browser shell may send either the camelCase
# names from the design's PlateConfig interface or the snake_case Config field
# names directly; both resolve to the same frozen Config field here. Only this
# curated subset is user-facing; every other lever keeps its engine default.
LEVER_MAP: dict[str, str] = {
    # numeric levers (camelCase + snake_case aliases)
    "maxColors": "max_colors",
    "max_colors": "max_colors",
    "simplify": "simplify",
    "smooth": "smooth",
    "upscale": "upscale",
    "workSize": "work_size",
    "work_size": "work_size",
    # boolean toggles
    "snapPrimitives": "snap_primitives",
    "snap_primitives": "snap_primitives",
    "strokes": "strokes",
    "gradients": "gradients",
    "removeBackground": "remove_background",
    "remove_background": "remove_background",
    # advanced LM Studio naming (off unless vlmUrl is a non-empty string)
    "vlmUrl": "vlm_url",
    "vlm_url": "vlm_url",
    "vlmModel": "vlm_model",
    "vlm_model": "vlm_model",
}

# Engine-sane inclusive [min, max] ranges for the numeric levers. Out-of-range
# values are clamped to the nearest bound (never rejected), per the design's
# validation rules. work_size tracks imageio.load_image's longest-side cap;
# simplify/smooth stay within the span the PRESETS already exercise and the
# field docstrings imply; max_colors spans a single flat colour to the richest
# preset palette.
NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "max_colors": (1, 256),
    "simplify": (0.0, 10.0),
    "smooth": (0.0, 10.0),
    "upscale": (1.0, 2.0),
    "work_size": (64, 8192),
}

# Levers that must stay integers after clamping (they are typed int on Config).
_INT_LEVERS = frozenset({"max_colors", "work_size"})


def _clamp_numeric(field: str, value) -> float | int:
    """Clamp ``value`` into ``NUMERIC_RANGES[field]`` and coerce to the field's
    numeric type. Clamps to the nearest bound rather than rejecting an out-of-range
    value, matching the design's validation rules."""
    lo, hi = NUMERIC_RANGES[field]
    clamped = min(max(float(value), lo), hi)
    return int(round(clamped)) if field in _INT_LEVERS else clamped


def build_config(overrides: dict | None = None) -> Config:
    """Resolve UI settings into a frozen :class:`Config`, mirroring the CLI's
    built-in defaults -> preset -> explicit-override load order.

    ``overrides`` is ``None`` or a dict whose keys are UI lever names (the
    camelCase names from the design's ``PlateConfig`` interface or the snake_case
    ``Config`` field names) plus the optional ``preset``. Returns a ``Config``
    equal to ``config.load(preset).merged(**clamped_levers)``.

    Numeric levers are clamped to their engine-sane range before ``Config.merged``
    (out-of-range values clamp to the nearest bound rather than being rejected).
    An unknown preset or unknown lever key raises :class:`ConfigError` rather than
    being silently ignored. LM Studio naming stays disabled unless ``vlmUrl`` is a
    non-empty, non-whitespace string.
    """
    overrides = dict(overrides or {})

    preset = overrides.pop("preset", None)
    if preset is not None and preset not in PRESETS:
        raise ConfigError(
            f"unknown preset {preset!r}; valid presets: {sorted(PRESETS)}"
        )

    levers: dict[str, object] = {}
    for key, value in overrides.items():
        field = LEVER_MAP.get(key)
        if field is None:
            raise ConfigError(
                f"unknown lever {key!r}; valid levers: {sorted(LEVER_MAP)}"
            )
        if field == "vlm_url":
            # Leave LM Studio naming disabled unless vlmUrl is a non-empty,
            # non-whitespace string; a blank/whitespace value keeps the engine
            # default empty endpoint (classical naming only).
            text = "" if value is None else str(value)
            if text.strip():
                levers[field] = text
            continue
        if field in NUMERIC_RANGES:
            levers[field] = _clamp_numeric(field, value)
        else:
            levers[field] = value

    # defaults -> preset -> explicit (clamped) overrides, exactly as config.load.
    return load(preset).merged(**levers)


def _work_resized(im: Image.Image, work_size: int) -> Image.Image:
    """Resize to the working resolution exactly as ``imageio.load_image`` does for
    the default (no-upscale) config: cap the longest side at ``work_size`` with
    LANCZOS; leave images already within the cap untouched."""
    w, h = im.size
    longest = max(w, h)
    if longest > work_size:
        scale = work_size / longest
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    return im


def check_noise(data: bytes, filename: str) -> dict:
    """Cheap pre-check so the UI can warn about compressed/noisy JPEGs before a
    full conversion, using the engine's own estimators and trigger.

    Decodes the uploaded bytes, resizes to the configured ``work_size`` (default
    ``Config.work_size``) and measures ``noise_fraction`` / ``interior_noise_fraction``
    exactly as ``imageio.load_image`` does, so the warning reflects whether the
    engine's auto-denoise would actually fire rather than a second heuristic.

    Returns ``{"noisy", "jpeg", "noise_fraction", "interior_noise"}`` on success.
    On a decode/resize failure it aborts estimation, leaves the uploaded image
    unchanged, and returns ``{"error": <message>}`` (no persisted file, no network
    I/O). The temporary decode path is removed in a ``finally`` on every path.
    """
    cfg = Config()
    # The engine's decoder (open_rgba) and JPEG-format probe (_is_jpeg) both read
    # from a path, including nuanced 16-bit PNG handling; reuse them verbatim via a
    # throwaway file so the noisy decision matches load_image byte for byte. In the
    # browser this temp path lives in Pyodide MEMFS (never touches disk); here and
    # there it is removed before returning so no uploaded image persists.
    ext = (Path(filename).suffix or ".png").lstrip(".").lower() or "png"
    tmp = tempfile.NamedTemporaryFile(prefix="plate-noise-", suffix=f".{ext}", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(data)
        tmp.close()
        im = open_rgba(tmp_path)
        jpeg = _is_jpeg(tmp_path)
        im = _work_resized(im, cfg.work_size)
        arr = np.asarray(im)
        rgb, alpha = arr[..., :3].copy(), arr[..., 3].copy()
        nf = noise_fraction(rgb, alpha)
        inf = interior_noise_fraction(rgb, alpha)
    except (ImageLoadError, ValueError, OSError) as e:
        return {"error": f"could not analyze image: {e}"}
    finally:
        try:
            tmp.close()
        except Exception:  # noqa: BLE001 - already closed on the success path
            pass
        tmp_path.unlink(missing_ok=True)
    noisy = nf > NOISE_FRACTION_TRIGGER or inf > cfg.interior_noise
    return {
        "noisy": bool(noisy),
        "jpeg": bool(jpeg),
        "noise_fraction": float(nf),
        "interior_noise": float(inf),
    }


def _extension_of(filename: str) -> str:
    """Return the recognised, lower-cased image extension of ``filename`` (without
    the dot), or raise :class:`ConvertError` if it is missing or unsupported. The
    extension (not the path) selects the MEMFS target so the decoder picks the
    right format; the engine's own byte-level validation still runs afterwards."""
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in RECOGNISED_EXTENSIONS:
        raise ConvertError(
            f"unsupported file extension {Path(filename).suffix!r}; "
            f"accepted types: {sorted(RECOGNISED_EXTENSIONS)}"
        )
    return ext


def _summarise_layers(nodes: list) -> list[dict]:
    """Summarise the pipeline's top-level nodes as the UI layer list, in the
    engine's bottom->top paint order. Each top-level node is a layer in the SVG
    (``emit.write_svg`` turns a top-level group into a layer and wraps a standalone
    top-level shape in a layer container), so one entry per top-level node mirrors
    exactly what the exported SVG contains. ``kind`` is ``"group"`` for a true
    group layer and ``"shape"`` for a standalone drawable promoted to its own layer."""
    layers: list[dict] = []
    for order_idx, node in enumerate(nodes):
        layers.append({
            "name": node.name,
            "kind": "group" if node.kind == "group" else "shape",
            "order": order_idx,
        })
    return layers


def convert_bytes(data: bytes, filename: str, overrides: dict | None = None) -> dict:
    """Convert raw uploaded image bytes to a layered SVG, running the *unchanged*
    engine exactly as the CLI does so the result is byte-identical for the same
    input and config. This is the single entry point the browser worker calls.

    ``data`` are the accepted image bytes; ``filename`` carries a recognised image
    extension (``.png``/``.jpg``/``.jpeg``, case-insensitive) which selects the
    MEMFS target ``/input.<ext>``; ``overrides`` is the UI settings map resolved by
    :func:`build_config` (defaults -> preset -> clamped levers).

    Returns a JSON-serialisable dict with exactly ``{"svg", "stats", "layers",
    "warnings"}``: ``svg`` is the exact text ``emit.write_svg`` produced; ``stats``
    mirrors ``Result.stats``; ``layers`` summarises the top-level layers in
    bottom->top paint order; ``warnings`` carries the beta JPEG notice when
    :func:`check_noise` reports both a JPEG source and a noisy image.

    No file persists after the call (the temporary MEMFS entry is removed in a
    ``finally`` on both success and failure) and the core path performs no network
    I/O. On empty bytes or a missing/unrecognised extension raises
    :class:`ConvertError`; on a decode failure the engine's own
    :class:`ImageLoadError` propagates unchanged (the worker turns either into a
    message-bearing, recoverable error event) -- engine validation is never bypassed.
    """
    if not data:
        raise ConvertError("empty file: no image bytes to convert")

    ext = _extension_of(filename)
    cfg = build_config(overrides)

    warnings: list[str] = []
    noise = check_noise(data, filename)
    if "error" not in noise and noise.get("jpeg") and noise.get("noisy"):
        warnings.append(BETA_JPEG_WARNING)

    # bytes -> MEMFS path the engine's decoder (Pillow + cv2.imread) can open, so
    # pipeline.run runs exactly as on the CLI. In the browser this lives in Pyodide
    # MEMFS and never touches disk; here it is a throwaway temp file. Removed in the
    # finally on every path so no uploaded image persists.
    tmp = tempfile.NamedTemporaryFile(prefix="plate-input-", suffix=f".{ext}", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(data)
        tmp.close()
        from . import pipeline  # imported here so plate.web stays importable without the full engine
        result = pipeline.run(tmp_path, cfg)
    finally:
        try:
            tmp.close()
        except Exception:  # noqa: BLE001 - already closed on the success path
            pass
        tmp_path.unlink(missing_ok=True)

    return {
        "svg": result.svg,
        "stats": {k: v for k, v in result.stats.items()},
        "layers": _summarise_layers(result.nodes),
        "warnings": warnings,
    }
