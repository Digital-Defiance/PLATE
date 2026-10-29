"""Rendering helpers: SVG text -> RGBA array (cairosvg if installed)."""
from __future__ import annotations

import glob
import io
import os
import sys

import numpy as np
from PIL import Image


def cairo_lib_dirs() -> list[str]:
    """Candidate directories that may contain libcairo on this machine."""
    dirs: list[str] = []
    for prefix in (os.environ.get("HOMEBREW_PREFIX"), "/opt/homebrew", "/usr/local"):
        if prefix and glob.glob(os.path.join(prefix, "lib", "libcairo*.dylib")):
            dirs.append(os.path.join(prefix, "lib"))
    return dirs


def ensure_dyld_cairo() -> bool:
    """On macOS, cairocffi's dlopen does not search Homebrew's lib dir, and SIP
    strips DYLD_* from env inherited across protected binaries. The reliable fix
    is to have DYLD_FALLBACK_LIBRARY_PATH include the cairo dir BEFORE the Python
    process starts. This helper reports whether that is already the case (so the
    CLI can re-exec itself once with the var set). Returns True if no action is
    needed (non-macOS, or path already covers a cairo dir, or no cairo found)."""
    if sys.platform != "darwin":
        return True
    dirs = cairo_lib_dirs()
    if not dirs:
        return True  # cairo not installed; nothing we can do, renderer stays off
    current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    have = set(current.split(":")) if current else set()
    return all(d in have for d in dirs)


def have_renderer() -> bool:
    try:
        import cairosvg  # noqa: F401
        return True
    except Exception:
        return False


def render_svg(svg: str, size: tuple[int, int], background=(255, 255, 255)) -> np.ndarray:
    """Render to an (h, w, 3) uint8 array composited over `background`."""
    import cairosvg
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size[0], output_height=size[1])
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    bg = Image.new("RGBA", im.size, tuple(background) + (255,))
    return np.asarray(Image.alpha_composite(bg, im).convert("RGB"))
