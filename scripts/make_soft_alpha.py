"""Generate soft-alpha fixtures for the nonuniform/soft-alpha + shadow case (R7d).

    python scripts/make_soft_alpha.py [outdir]           # default: samples/fixtures

Flat-region opacity support (`pipeline._opacity` + `segment._faint_objects`) models a
translucent object with ONE opacity measured from its interior: a 50 % overlay, a tinted
glass panel, a faint watermark. That is correct on ANY background, because a single flat
coverage `a` composites as `color*a + bg*(1-a)` identically to the source for every `bg`.

A *nonuniform* / *feathered* alpha (a radial alpha fade, a soft drop shadow) has no hard
silhouette boundary: alpha ramps continuously from opaque to transparent. A single flat
region with one opacity can only match one coverage value, so it cannot composite
correctly on two different backgrounds at once -- and `_faint_objects` deliberately admits
a faint region only when its interior alpha "sits at one steady level" (90th-percentile
deviation <= 8), so a continuously-ramping alpha keeps its old binary-threshold treatment.

These fixtures make that boundary measurable:

  uniform_overlay    one flat 50 %-alpha panel          -> SUPPORTED (SSIM ~1.0 on BOTH bg)
  feathered_disc     a radial alpha fade (no boundary)  -> LIMIT (one opacity cannot match
                                                            both backgrounds)
  soft_shadow_card   opaque card + soft translucent      -> LIMIT (the soft shadow band)
                     drop shadow (varying alpha)

Writes <out>/<name>.png (RGBA, with a real varying alpha channel). Deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

H = W = 300


def uniform_overlay() -> np.ndarray:
    """One flat panel at a steady 50 % alpha: the SUPPORTED flat-region-opacity case."""
    img = np.zeros((H, W, 4), np.uint8)
    img[60:240, 60:240] = (40, 90, 210, 128)
    return img


def feathered_disc() -> np.ndarray:
    """A red disc whose alpha fades radially from opaque centre to transparent rim -- a
    nonuniform alpha with no hard boundary (the archetypal R7d LIMIT case)."""
    yy, xx = np.mgrid[:H, :W]
    r = np.hypot(xx - 150, yy - 150)
    alpha = np.clip(255 * (1 - (r - 40) / 80), 0, 255).astype(np.uint8)
    img = np.zeros((H, W, 4), np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = 220, 40, 40
    img[..., 3] = alpha
    return img


def soft_shadow_card() -> np.ndarray:
    """An opaque card over a soft translucent drop shadow (a Gaussian-blurred alpha band):
    the shadow's alpha varies continuously, the card is opaque -> a mixed R7d case."""
    sh = np.zeros((H, W), np.float32)
    sh[90:250, 90:250] = 1.0
    sh = gaussian_filter(sh, 12)
    img = np.zeros((H, W, 4), np.uint8)
    img[..., 3] = np.clip(sh * 160, 0, 255).astype(np.uint8)   # black soft shadow
    img[70:200, 70:200] = (240, 200, 60, 255)                  # opaque card on top
    return img


FIXTURES = {
    "soft_uniform_overlay": uniform_overlay,
    "soft_feathered_disc": feathered_disc,
    "soft_shadow_card_fx": soft_shadow_card,
}


def write(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, fn in FIXTURES.items():
        png = out / f"{name}.png"
        Image.fromarray(fn(), "RGBA").save(png)
        paths.append(png)
    return paths


if __name__ == "__main__":
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "samples/fixtures"
    for p in write(outdir):
        print(f"wrote {p}")
