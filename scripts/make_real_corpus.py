"""Author a messy, realistic evaluation corpus of PNGs for `plate bench`.

This is EVALUATION tooling, not a quality gate. It deterministically authors
~14 deliberately messy PNGs into ``samples/real/`` exercising the real-world
stress axes PLATE was NOT tuned against: smooth multi-stop gradients, soft
radial shading, soft drop shadows / feathered edges / blur, mild sensor-style
noise and JPEG-like block artifacts, anti-aliased small text and thin strokes,
busy palettes (>16 colours) with near-duplicate colours, non-square / extreme
aspect ratios, overlapping semi-transparent shapes, and off-white textured
backgrounds.

Everything is authored in-repo (MIT), reproducible, and redistributable. No
new dependencies (numpy / PIL / cairosvg / scipy only), no new fonts (letter
glyphs are reused from ``make_complex_scenes.GLYPHS`` as paths). The PLATE
pipeline is never invoked here and is not modified.

Run with the render extra:  python scripts/make_real_corpus.py [outdir]

Determinism: there are no wall-clock or global-RNG dependencies. Every
post-raster perturbation uses a fixed per-image seed from ``SEEDS`` via
``numpy.random.default_rng``, so re-running yields byte-identical PNGs.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from make_complex_scenes import (
    CREAM,
    GOLD,
    MINT,
    NAVY,
    ORANGE,
    RED,
    TEAL,
    Scene,
    circle_subpath,
    star,
)
from PIL import Image
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parents[1]

# Fixed per-image seeds so post-raster noise/jpeg/texture stay deterministic.
SEEDS = {
    "real_sunset_gradient": 101,
    "real_radial_orb": 102,
    "real_soft_shadow_card": 103,
    "real_sensor_noise_badge": 104,
    "real_jpeg_artifacts": 105,
    "real_thin_strokes_type": 106,
    "real_busy_palette": 107,
    "real_near_duplicate_swatches": 108,
    "real_panorama_banner": 109,
    "real_tall_poster": 110,
    "real_translucent_overlaps": 111,
    "real_textured_bg": 112,
    "real_glow_logo": 113,
    "real_mixed_mess": 114,
}


# --------------------------------------------------------------------------- #
# In-script authoring helpers (NOT pipeline changes).                         #
# --------------------------------------------------------------------------- #
def grad_multi(scene: Scene, name: str, kind: str, stops, **coords) -> str:
    """Emit an N-stop linear/radial gradient and return its ``url(#...)``.

    ``stops`` is a sequence of ``(offset, color)`` or ``(offset, color, opacity)``
    tuples. ``kind`` is ``"linearGradient"`` or ``"radialGradient"``.
    """
    defs = scene.root.find("defs")
    if defs is None:
        defs = ET.Element("defs")
        scene.root.insert(0, defs)
    grad = ET.SubElement(defs, kind, id=name, gradientUnits="userSpaceOnUse",
                         **{k: str(v) for k, v in coords.items()})
    for stop in stops:
        offset, color = stop[0], stop[1]
        attrs = {"offset": str(offset), "stop-color": color}
        if len(stop) > 2:
            attrs["stop-opacity"] = str(stop[2])
        ET.SubElement(grad, "stop", **attrs)
    return f"url(#{name})"


def _lanczos(svg: str, w: int, h: int) -> np.ndarray:
    """Render an authored SVG at 4x and Lanczos-downsample to (w, h) RGBA."""
    import cairosvg

    png = cairosvg.svg2png(bytestring=svg.encode(), scale=4)
    with Image.open(io.BytesIO(png)) as high:
        img = high.convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
    return np.asarray(img).astype(np.float32)


def soft_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian-blur RGB channels (keeps alpha), returning float32 RGBA."""
    out = arr.copy()
    for c in range(3):
        out[..., c] = gaussian_filter(arr[..., c], sigma=sigma)
    return out


def add_noise(arr: np.ndarray, rng: np.random.Generator, sigma: float) -> np.ndarray:
    """Add deterministic gaussian sensor-style noise to the RGB channels."""
    noise = rng.normal(0.0, sigma, size=arr[..., :3].shape).astype(np.float32)
    out = arr.copy()
    out[..., :3] = out[..., :3] + noise
    return out


def jpeg_like(arr: np.ndarray, rng: np.random.Generator, strength: float = 14.0) -> np.ndarray:
    """Cheap JPEG-like artifact: quantize 8x8 blocks toward their mean plus a
    small deterministic per-block jitter, producing blockiness and ringing-ish
    banding without any codec dependency."""
    out = arr.copy()
    h, w = out.shape[:2]
    for by in range(0, h, 8):
        for bx in range(0, w, 8):
            block = out[by:by + 8, bx:bx + 8, :3]
            mean = block.mean(axis=(0, 1), keepdims=True)
            jitter = rng.uniform(-strength, strength, size=(1, 1, 3)).astype(np.float32)
            out[by:by + 8, bx:bx + 8, :3] = mean + (block - mean) * 0.45 + jitter
    return out


def paper_texture(arr: np.ndarray, rng: np.random.Generator, amount: float = 10.0,
                  sigma: float = 1.4) -> np.ndarray:
    """Overlay a soft off-white paper-grain texture onto the RGB channels."""
    grain = rng.normal(0.0, amount, size=arr[..., :3].shape).astype(np.float32)
    for c in range(3):
        grain[..., c] = gaussian_filter(grain[..., c], sigma=sigma)
    out = arr.copy()
    out[..., :3] = out[..., :3] + grain
    return out


def finalize(arr: np.ndarray, out_path: Path) -> None:
    """Clip to uint8 and save as RGBA PNG (no metadata => reproducible bytes)."""
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA")
    img.save(out_path)


# --------------------------------------------------------------------------- #
# Extra authored colours for busy / near-duplicate palettes.                  #
# --------------------------------------------------------------------------- #
BUSY = [
    "#c0392b", "#e74c3c", "#d35400", "#e67e22", "#f39c12", "#f1c40f",
    "#27ae60", "#2ecc71", "#16a085", "#1abc9c", "#2980b9", "#3498db",
    "#8e44ad", "#9b59b6", "#34495e", "#2c3e50", "#7f8c8d", "#95a5a6",
    "#d98880", "#f5b7b1",
]
NEAR_DUP = [
    "#3b7dd8", "#3c7ed8", "#3a7cd7", "#3d7fd9", "#3b7dd6",
    "#c94f3a", "#ca503b", "#c84e39", "#cb513c", "#c74d38",
    "#2f9e5c", "#309f5d", "#2e9d5b", "#31a05e", "#2d9c5a",
    "#e7b85a", "#e8b95b", "#e6b759", "#e9ba5c", "#e5b658",
]


# --------------------------------------------------------------------------- #
# Scene authors. Each returns (Scene, native_w, native_h).                    #
# --------------------------------------------------------------------------- #
def sunset_gradient():
    w, h = 1000, 600
    s = Scene(w, h)
    sky = grad_multi(s, "sunset-sky", "linearGradient",
                     [("0", "#f8c97a"), ("0.35", "#ef9d5a"), ("0.6", "#d2694f"),
                      ("0.85", "#7a3b63"), ("1", "#2c2350")],
                     x1=0, y1=0, x2=0, y2=h)
    s.rect("sky", 0, 0, w, h, sky)
    glow = grad_multi(s, "sun-glow", "radialGradient",
                      [("0", "#fff3c0"), ("0.3", "#ffd776"), ("0.7", "#f2a24d"),
                       ("1", "#f2a24d", "0")],
                      cx=500, cy=330, r=230)
    s.circle("sun-glow", 500, 330, 230, glow)
    s.circle("sun-core", 500, 330, 70, "#fff0bf")
    sea = grad_multi(s, "sea", "linearGradient",
                     [("0", "#6a4b70"), ("0.5", "#3f3360"), ("1", "#241d44")],
                     x1=0, y1=430, x2=0, y2=h)
    s.rect("sea", 0, 430, w, 170, sea)
    s.add("ellipse", "sun-reflection", cx=500, cy=500, rx=60, ry=80, fill="#f2b770",
          fill_opacity="0.55")
    return s, w, h


def radial_orb():
    w, h = 700, 700
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#efeae0")
    shade = grad_multi(s, "orb-shade", "radialGradient",
                       [("0", "#dfe9f4"), ("0.25", "#9cb6d6"), ("0.6", "#4d6fa0"),
                        ("0.9", "#223a63"), ("1", "#101d36")],
                       cx=310, cy=300, r=270)
    s.circle("orb", 350, 350, 240, shade)
    hi = grad_multi(s, "orb-highlight", "radialGradient",
                    [("0", "#ffffff"), ("0.4", "#ffffff", "0.6"), ("1", "#ffffff", "0")],
                    cx=280, cy=270, r=120)
    s.add("ellipse", "orb-highlight", cx=280, cy=270, rx=110, ry=90, fill=hi)
    return s, w, h


def soft_shadow_card():
    w, h = 900, 600
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#e9e6df")
    # shadow authored as a solid dark rounded rect; blurred after rasterization.
    s.rect("card-shadow", 258, 196, 420, 260, "#2a2a2a", rx=26, fill_opacity="0.5")
    s.rect("card", 240, 170, 420, 260, "#ffffff", rx=22)
    s.rect("card-bar", 240, 170, 420, 60, TEAL, rx=22)
    s.word("FORM", 275, 260, 44, NAVY, "card-title")
    s.rect("card-line-1", 275, 330, 330, 12, "#d7d2c8", rx=6)
    s.rect("card-line-2", 275, 360, 260, 12, "#d7d2c8", rx=6)
    s.circle("card-dot", 610, 200, 14, GOLD)
    return s, w, h


def sensor_noise_badge():
    w, h = 640, 640
    s = Scene(w, h)
    bg = grad_multi(s, "badge-bg", "radialGradient",
                    [("0", "#f2efe6"), ("1", "#d7d0c0")], cx=320, cy=320, r=380)
    s.rect("background", 0, 0, w, h, bg)
    ring = grad_multi(s, "badge-ring", "linearGradient",
                      [("0", "#e9bc59"), ("0.5", "#b98f3d"), ("1", "#e9bc59")],
                      x1=120, y1=120, x2=520, y2=520)
    s.circle("badge-ring", 320, 320, 210, ring)
    s.circle("badge-face", 320, 320, 168, NAVY)
    s.add("polygon", "badge-star", points=star(320, 320, 120), fill=GOLD)
    s.circle("badge-center", 320, 320, 44, TEAL)
    return s, w, h


def jpeg_artifacts():
    w, h = 800, 600
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, CREAM)
    # Hard high-contrast edges on flat fills => JPEG ringing is pronounced.
    s.rect("block-navy", 60, 60, 320, 220, NAVY)
    s.rect("block-red", 420, 60, 320, 220, RED)
    s.rect("block-teal", 60, 320, 320, 220, TEAL)
    s.rect("block-orange", 420, 320, 320, 220, ORANGE)
    s.circle("overlay-dot-1", 400, 300, 90, GOLD)
    s.add("polygon", "overlay-tri", points="200,180 300,120 300,420 200,360", fill=MINT)
    s.stroke("edge-slash", "M60 540L740 60", "#ffffff", 6)
    return s, w, h


def thin_strokes_type():
    w, h = 1000, 500
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#f6f3ec")
    for i in range(18):
        x = 60 + i * 52
        s.stroke(f"hairline-{i + 1}", f"M{x} 70V200", NAVY if i % 2 else TEAL, 1.2)
    s.stroke("baseline-rule", "M60 240H940", "#b9b2a4", 1.5)
    s.word("SYSTEM", 70, 300, 34, NAVY, "small-type")
    s.word("DETFOR", 70, 370, 22, "#6c6457", "tiny-type")
    for i in range(10):
        s.stroke(f"tick-{i + 1}", f"M{70 + i * 90} 440V470", ORANGE, 2)
    return s, w, h


def busy_palette():
    w, h = 900, 700
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#f3f1ea")
    cols, rows = 6, 5
    cw, ch = w / cols, h / rows
    for r in range(rows):
        for c in range(cols):
            color = BUSY[(r * cols + c) % len(BUSY)]
            s.rect(f"tile-{r + 1}-{c + 1}", round(c * cw) + 6, round(r * ch) + 6,
                   round(cw) - 12, round(ch) - 12, color, rx=8)
    s.circle("accent-a", 230, 220, 54, "#ecf0f1", fill_opacity="0.8")
    s.circle("accent-b", 650, 470, 68, "#1b1b1b", fill_opacity="0.7")
    return s, w, h


def near_duplicate_swatches():
    w, h = 800, 800
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#efece4")
    cols, rows = 5, 4
    cw, ch = w / cols, h / rows
    for r in range(rows):
        for c in range(cols):
            color = NEAR_DUP[(r * cols + c) % len(NEAR_DUP)]
            s.rect(f"swatch-{r + 1}-{c + 1}", round(c * cw) + 10, round(r * ch) + 10,
                   round(cw) - 20, round(ch) - 20, color)
    return s, w, h


def panorama_banner():
    w, h = 1600, 400
    s = Scene(w, h)
    sky = grad_multi(s, "pano-sky", "linearGradient",
                     [("0", "#3aa0c9"), ("0.5", "#8ecae0"), ("1", "#e4f1f4")],
                     x1=0, y1=0, x2=0, y2=h)
    s.rect("sky", 0, 0, w, h, sky)
    for i in range(8):
        x = 120 + i * 200
        s.circle(f"motif-sun-{i + 1}", x, 150, 46, GOLD, fill_opacity="0.85")
        s.add("polygon", f"motif-hill-{i + 1}",
              points=f"{x - 140},400 {x},250 {x + 140},400", fill=TEAL if i % 2 else MINT)
    s.rect("foreground", 0, 350, w, 50, NAVY)
    return s, w, h


def tall_poster():
    w, h = 500, 1200
    s = Scene(w, h)
    wash = grad_multi(s, "poster-wash", "linearGradient",
                      [("0", "#edba68"), ("0.45", "#d17d79"), ("1", "#5c3b6b")],
                      x1=0, y1=0, x2=0, y2=h)
    s.rect("wash", 0, 0, w, h, wash)
    s.circle("disc", 250, 360, 170, CREAM, fill_opacity="0.9")
    s.word("FORM", 70, 220, 90, NAVY, "poster-title")
    s.word("STUDIO", 70, 980, 44, CREAM, "poster-footer")
    s.rect("footer-rule", 70, 1060, 360, 6, CREAM)
    return s, w, h


def translucent_overlaps():
    w, h = 800, 800
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#f4f1ea")
    s.circle("blob-cyan", 320, 330, 200, "#19b0c4", fill_opacity="0.55")
    s.circle("blob-magenta", 480, 330, 200, "#d6359a", fill_opacity="0.55")
    s.circle("blob-yellow", 400, 490, 200, "#f2c744", fill_opacity="0.55")
    s.add("polygon", "panel-navy", points="150,150 650,150 560,360 240,360", fill=NAVY,
          fill_opacity="0.4")
    return s, w, h


def textured_bg():
    w, h = 900, 600
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#efe8d8")
    s.rect("panel", 120, 110, 660, 380, "#faf6ec", rx=18)
    s.circle("mark", 300, 300, 92, TEAL)
    s.add("polygon", "mark-star", points=star(300, 300, 54), fill=CREAM)
    s.word("ROOT", 430, 250, 48, NAVY, "textured-title")
    s.rect("rule", 430, 320, 260, 10, ORANGE, rx=5)
    return s, w, h


def glow_logo():
    w, h = 760, 760
    s = Scene(w, h)
    s.rect("background", 0, 0, w, h, "#11131c")
    glow = grad_multi(s, "logo-glow", "radialGradient",
                      [("0", "#5ff0d8"), ("0.4", "#2bb6c8", "0.7"), ("1", "#2bb6c8", "0")],
                      cx=380, cy=330, r=260)
    s.circle("logo-glow", 380, 330, 260, glow)
    core = grad_multi(s, "logo-core", "radialGradient",
                      [("0", "#eafff8"), ("0.6", "#37c6b0"), ("1", "#14707f")],
                      cx=380, cy=330, r=150)
    s.add("polygon", "logo-mark", points=star(380, 330, 150), fill=core)
    s.word("ORBIT", 250, 560, 40, "#dff6ff", "glow-type")
    return s, w, h


def mixed_mess():
    w, h = 1100, 650
    s = Scene(w, h)
    wash = grad_multi(s, "mix-wash", "linearGradient",
                      [("0", "#f3d9a4"), ("0.4", "#e59a6c"), ("0.75", "#b65f7a"),
                       ("1", "#53406e")],
                      x1=0, y1=0, x2=w, y2=h)
    s.rect("wash", 0, 0, w, h, wash)
    # busy palette corner (>16 colours together with the gradient + type)
    for i, color in enumerate(BUSY[:16]):
        x = 40 + (i % 8) * 46
        y = 40 + (i // 8) * 46
        s.rect(f"chip-{i + 1}", x, y, 40, 40, color, rx=6)
    s.rect("card-shadow", 448, 236, 420, 300, "#1c1c1c", rx=24, fill_opacity="0.45")
    s.rect("card", 430, 210, 420, 300, "#fbfaf6", rx=20)
    s.circle("orb", 560, 330, 78, TEAL)
    s.add("polygon", "orb-star", points=star(560, 330, 44), fill=GOLD)
    s.word("STUDIO", 470, 430, 30, NAVY, "mix-type")
    for i in range(6):
        s.stroke(f"mix-hairline-{i + 1}", f"M{470 + i * 60} 470H{510 + i * 60}",
                 ORANGE, 1.4)
    ring = circle_subpath(240, 470, 120) + " " + circle_subpath(240, 470, 72)
    s.path("mix-ring", ring, NAVY, fill_rule="evenodd", fill_opacity="0.85")
    return s, w, h


SCENES = {
    "real_sunset_gradient": sunset_gradient,
    "real_radial_orb": radial_orb,
    "real_soft_shadow_card": soft_shadow_card,
    "real_sensor_noise_badge": sensor_noise_badge,
    "real_jpeg_artifacts": jpeg_artifacts,
    "real_thin_strokes_type": thin_strokes_type,
    "real_busy_palette": busy_palette,
    "real_near_duplicate_swatches": near_duplicate_swatches,
    "real_panorama_banner": panorama_banner,
    "real_tall_poster": tall_poster,
    "real_translucent_overlaps": translucent_overlaps,
    "real_textured_bg": textured_bg,
    "real_glow_logo": glow_logo,
    "real_mixed_mess": mixed_mess,
}


def _postprocess(name: str, arr: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Apply the per-image messiness effect(s) after rasterization."""
    if name == "real_sunset_gradient":
        return add_noise(arr, rng, 2.0)
    if name == "real_radial_orb":
        return add_noise(arr, rng, 1.5)
    if name == "real_soft_shadow_card":
        blurred = arr.copy()
        # Blur only the shadow band region for a localized soft shadow.
        blurred[150:480, 230:720] = soft_blur(arr[150:480, 230:720], sigma=7.0)[0:330, 0:490]
        return soft_blur(blurred, sigma=0.6)
    if name == "real_sensor_noise_badge":
        return add_noise(arr, rng, 11.0)
    if name == "real_jpeg_artifacts":
        return jpeg_like(arr, rng, strength=16.0)
    if name == "real_thin_strokes_type":
        return add_noise(arr, rng, 1.2)
    if name == "real_busy_palette":
        return add_noise(arr, rng, 1.5)
    if name == "real_near_duplicate_swatches":
        return add_noise(arr, rng, 2.5)
    if name == "real_panorama_banner":
        return add_noise(arr, rng, 1.5)
    if name == "real_tall_poster":
        return add_noise(arr, rng, 1.5)
    if name == "real_translucent_overlaps":
        return soft_blur(add_noise(arr, rng, 1.0), sigma=0.5)
    if name == "real_textured_bg":
        return paper_texture(arr, rng, amount=12.0, sigma=1.6)
    if name == "real_glow_logo":
        return soft_blur(arr, sigma=1.4)
    if name == "real_mixed_mess":
        out = soft_blur(arr, sigma=0.6)
        return add_noise(out, rng, 3.0)
    return arr


def main(outdir=None):
    out = Path(outdir) if outdir else ROOT / "samples" / "real"
    out.mkdir(parents=True, exist_ok=True)
    for name, author in SCENES.items():
        scene, w, h = author()
        arr = _lanczos(scene.svg(), w, h)
        rng = np.random.default_rng(SEEDS[name])
        arr = _postprocess(name, arr, rng)
        path = out / f"{name}.png"
        finalize(arr, path)
        print(path)


if __name__ == "__main__":
    main(*sys.argv[1:2])
