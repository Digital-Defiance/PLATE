"""Generate the CONTROL test images: synthetic PNGs of increasing complexity,
each paired with a known ground-truth contract (see CONTROLS in this module).

    python scripts/make_controls.py [outdir]     # default outdir: samples/controls

Unlike scripts/make_samples.py (bench fixtures), these are a *regression suite*:
every image has a declared, machine-checkable set of objects we expect PLATE to
recover (counts, primitive types, params within tolerance, layer names, paint
order, nesting). tests/test_controls.py asserts against this contract on the
structured Result, and keeps a soft golden-SVG diff.

Tiers:
  T1 trivial  - one primitive at a time (sanity).
  T2 simple   - a few overlapping primitives, known stacking order.
  T3 moderate - nesting, a ring/annulus, a rotated ellipse.
  T4 complex  - a mini "badge/logo": many mixed primitives + background layer.
  T5 hard     - curved non-primitive (Bezier), near-limit polygon, amodal completion.

Coordinates below are in SOURCE pixels. These canvases are small (< work_size),
so PLATE runs at scale ~= 1 and SVG coords are approximately source coords; the
test tolerances absorb the sub-pixel-centre offset and anti-aliasing.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4  # supersampling for anti-aliasing (match make_samples.py)

WHITE = (255, 255, 255, 255)


def _canvas(w, h, bg=WHITE):
    im = Image.new("RGBA", (w * SS, h * SS), bg)
    return im, ImageDraw.Draw(im)


def _finish(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


def S(v):
    return [c * SS for c in v] if isinstance(v, (list, tuple)) else v * SS


# ---------------------------------------------------------------------------
# T1 - trivial: one primitive each
# ---------------------------------------------------------------------------

def t1_circle():
    im, d = _canvas(300, 300)
    d.ellipse(S([90, 90, 210, 210]), fill=(210, 50, 50, 255))   # cx150 cy150 r60
    return _finish(im, 300, 300)


def t1_rect():
    im, d = _canvas(300, 240)
    d.rectangle(S([70, 60, 230, 180]), fill=(40, 110, 200, 255))  # 160x120 @ (150,120)
    return _finish(im, 300, 240)


# ---------------------------------------------------------------------------
# T2 - simple: overlapping primitives, known z-order (bottom -> top)
# ---------------------------------------------------------------------------

def t2_two_circles():
    im, d = _canvas(360, 240)
    d.ellipse(S([40, 60, 180, 200]), fill=(230, 160, 20, 255))    # gold, bottom; cx110 cy130 r70
    d.ellipse(S([180, 60, 320, 200]), fill=(40, 140, 70, 255))    # green, top;   cx250 cy130 r70
    return _finish(im, 360, 240)


def t2_circle_on_rect():
    im, d = _canvas(340, 300)
    d.rectangle(S([50, 60, 290, 240]), fill=(60, 70, 90, 255))    # slate rect, bottom
    d.ellipse(S([130, 90, 250, 210]), fill=(240, 80, 60, 255))    # red circle on top; cx190 cy150 r60
    return _finish(im, 340, 300)


# ---------------------------------------------------------------------------
# T3 - moderate: nesting, ring, rotated ellipse
# ---------------------------------------------------------------------------

def t3_nested():
    """A big rect with a smaller circle fully inside it (containment)."""
    im, d = _canvas(360, 360)
    d.rectangle(S([60, 60, 300, 300]), fill=(30, 60, 120, 255))   # navy outer rect
    d.ellipse(S([130, 130, 230, 230]), fill=(250, 210, 40, 255))  # gold circle inside; cx180 cy180 r50
    return _finish(im, 360, 360)


def t3_ring():
    """Annulus on a transparent canvas -> ring (two circles, even-odd)."""
    im, d = _canvas(300, 300, (0, 0, 0, 0))
    d.ellipse(S([50, 50, 250, 250]), fill=(200, 40, 60, 255))     # outer r100 @ (150,150)
    d.ellipse(S([110, 110, 190, 190]), fill=(0, 0, 0, 0))         # hole r40
    return _finish(im, 300, 300)


def t3_rotated_ellipse():
    """A tall ellipse rotated ~30deg -> ellipse primitive with angle, rx<ry."""
    big = 4
    w = h = 320
    im = Image.new("RGBA", (w * big, h * big), WHITE)
    d = ImageDraw.Draw(im)
    # draw an axis-aligned tall ellipse on its own layer, then rotate the layer
    lyr = Image.new("RGBA", (w * big, h * big), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lyr)
    cx, cy = w * big / 2, h * big / 2
    rx, ry = 55 * big, 100 * big       # rx < ry (tall)
    ld.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(120, 60, 180, 255))
    lyr = lyr.rotate(30, resample=Image.BICUBIC, center=(cx, cy))
    im = Image.alpha_composite(im, lyr)
    return im.resize((w, h), Image.LANCZOS)


# ---------------------------------------------------------------------------
# T4 - complex: mini badge/logo, many mixed primitives + background layer
# ---------------------------------------------------------------------------

def t4_badge():
    im, d = _canvas(400, 400, (245, 242, 232, 255))               # cream background
    d.ellipse(S([30, 30, 370, 370]), fill=(20, 40, 90, 255))      # navy disc
    d.rounded_rectangle(S([120, 150, 280, 230]), radius=18 * SS,  # gold plaque (rrect)
                        fill=(240, 180, 30, 255))
    d.rectangle(S([150, 260, 250, 290]), fill=(200, 60, 50, 255)) # red bar
    d.ellipse(S([90, 180, 120, 210]), fill=(220, 220, 230, 255))  # left dot
    d.ellipse(S([280, 180, 310, 210]), fill=(220, 220, 230, 255)) # right dot
    return _finish(im, 400, 400)


# ---------------------------------------------------------------------------
# T5 - hard: curved non-primitive, near-limit polygon, amodal completion
# ---------------------------------------------------------------------------

def t5_blob():
    """A smooth closed curve that is NOT a primitive -> must stay a Bezier path."""
    im, d = _canvas(320, 320)
    cx, cy = 160, 160
    pts = []
    import random
    rnd = random.Random(7)
    n = 10
    radii = [70 + 35 * (0.5 - rnd.random()) for _ in range(n)]
    for i in range(n * 8):                      # dense sampling -> smooth outline
        a = 2 * math.pi * i / (n * 8)
        seg = (i / 8) % n
        r = radii[int(seg)] * 0.6 + radii[int(seg) - 1] * 0.4
        r += 18 * math.sin(a * 3)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(S([c for p in pts for c in p]), fill=(30, 150, 160, 255))
    return _finish(im, 320, 320)


def t5_hexagon():
    """A regular hexagon -> polygon primitive with 6 vertices."""
    im, d = _canvas(300, 300)
    cx, cy, r = 150, 150, 110
    pts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
            cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
    d.polygon(S([c for p in pts for c in p]), fill=(200, 120, 40, 255))
    return _finish(im, 300, 300)


def t5_occluded_circle():
    """A circle whose right half is hidden by a rect -> amodal completion (1 circle)."""
    im, d = _canvas(360, 360)
    d.ellipse(S([60, 90, 240, 270]), fill=(214, 40, 40, 255))     # circle cx150 cy180 r90
    d.rectangle(S([150, 40, 320, 320]), fill=(30, 70, 190, 255))  # rect covers right half
    return _finish(im, 360, 360)


CONTROLS = {
    # T1
    "t1_circle": t1_circle,
    "t1_rect": t1_rect,
    # T2
    "t2_two_circles": t2_two_circles,
    "t2_circle_on_rect": t2_circle_on_rect,
    # T3
    "t3_nested": t3_nested,
    "t3_ring": t3_ring,
    "t3_rotated_ellipse": t3_rotated_ellipse,
    # T4
    "t4_badge": t4_badge,
    # T5
    "t5_blob": t5_blob,
    "t5_hexagon": t5_hexagon,
    "t5_occluded_circle": t5_occluded_circle,
}


def main(outdir="samples/controls"):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in CONTROLS.items():
        fn().save(out / f"{name}.png")
        print("wrote", out / f"{name}.png")


if __name__ == "__main__":
    main(*sys.argv[1:2])
