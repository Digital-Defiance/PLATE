"""Generate synthetic flat-art test images with known geometry (anti-aliased).

    python scripts/make_samples.py [outdir]

Ground truth for the key cases lives in GROUND_TRUTH and is used by the tests.
"""
from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SS = 4  # supersampling for anti-aliasing

# name -> list of dicts describing true objects (full, un-occluded geometry)
GROUND_TRUTH = {
    "overlap": [dict(kind="circle", cx=200, cy=210, r=100, color=(214, 40, 40))],
    "stack3": [
        dict(kind="circle", cx=170, cy=170, r=90, color=(230, 160, 20)),
        dict(kind="circle", cx=250, cy=170, r=90, color=(40, 140, 70)),
        dict(kind="circle", cx=210, cy=240, r=90, color=(40, 90, 200)),
    ],
}


def _canvas(w, h, bg=(255, 255, 255, 255)):
    im = Image.new("RGBA", (w * SS, h * SS), bg)
    return im, ImageDraw.Draw(im)


def _finish(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


def S(v):  # scale helper for coordinates
    return [c * SS for c in v] if isinstance(v, (list, tuple)) else v * SS


def overlap():
    im, d = _canvas(400, 400)
    d.ellipse(S([100, 110, 300, 310]), fill=(214, 40, 40, 255))        # circle, partly hidden
    d.rectangle(S([190, 60, 340, 230]), fill=(30, 70, 190, 255))       # square on top
    return _finish(im, 400, 400)


def stack3():
    im, d = _canvas(420, 420)
    d.ellipse(S([80, 80, 260, 260]), fill=(230, 160, 20, 255))
    d.ellipse(S([160, 80, 340, 260]), fill=(40, 140, 70, 255))
    d.ellipse(S([120, 150, 300, 330]), fill=(40, 90, 200, 255))
    return _finish(im, 420, 420)


def badge():
    im, d = _canvas(600, 600, (245, 242, 232, 255))
    d.ellipse(S([20, 20, 580, 580]), fill=(20, 40, 90, 255))
    d.ellipse(S([60, 60, 540, 540]), outline=(245, 242, 232, 255), width=14 * SS)
    cx, cy, ro, ri = 300, 290, 150, 62
    pts = []
    for i in range(10):
        r = ro if i % 2 == 0 else ri
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(S([c for p in pts for c in p]), fill=(240, 180, 30, 255))
    d.rounded_rectangle(S([170, 470, 430, 505]), radius=8 * SS, fill=(245, 242, 232, 255))
    d.rectangle(S([210, 515, 390, 530]), fill=(200, 60, 50, 255))
    d.ellipse(S([115, 285, 145, 315]), fill=(200, 60, 50, 255))
    d.ellipse(S([455, 285, 485, 315]), fill=(200, 60, 50, 255))
    return _finish(im, 600, 600)


def face():
    im, d = _canvas(500, 500)
    d.ellipse(S([40, 40, 460, 460]), fill=(250, 205, 40, 255))
    for ex in (170, 330):
        d.ellipse(S([ex - 34, 170 - 50, ex + 34, 170 + 50]), fill=(40, 30, 30, 255))
        d.ellipse(S([ex - 12, 150 - 14, ex + 6, 150 + 4]), fill=(255, 255, 255, 255))
    d.pieslice(S([130, 220, 370, 400]), 0, 180, fill=(150, 30, 30, 255))
    d.pieslice(S([160, 300, 340, 410]), 0, 180, fill=(235, 120, 130, 255))
    return _finish(im, 500, 500)


def donut_alpha():
    im, d = _canvas(400, 400, (0, 0, 0, 0))
    d.ellipse(S([40, 40, 260, 260]), fill=(200, 40, 60, 255))
    d.ellipse(S([100, 100, 200, 200]), fill=(0, 0, 0, 0))
    d.polygon(S([230, 380, 380, 380, 305, 250]), fill=(30, 100, 200, 255))
    return _finish(im, 400, 400)


def ui_card():
    im, d = _canvas(520, 360, (236, 240, 245, 255))
    d.rounded_rectangle(S([30, 30, 490, 330]), radius=28 * SS, fill=(255, 255, 255, 255))
    d.ellipse(S([60, 60, 140, 140]), fill=(60, 120, 230, 255))
    d.rounded_rectangle(S([160, 70, 400, 90]), radius=10 * SS, fill=(40, 50, 70, 255))
    d.rounded_rectangle(S([160, 105, 330, 120]), radius=7 * SS, fill=(170, 180, 195, 255))
    d.rounded_rectangle(S([60, 260, 260, 310]), radius=25 * SS, fill=(60, 120, 230, 255))
    return _finish(im, 520, 360)


def noisy_badge():
    rng = np.random.default_rng(1)
    base = badge().convert("RGB")
    a = np.asarray(base).astype(np.float32)
    a = np.clip(a + rng.normal(0, 4.0, a.shape), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "JPEG", quality=72)
    buf.seek(0)
    return Image.open(buf).convert("RGBA")


def shaded():
    w = h = 400
    yy, xx = np.mgrid[0:h, 0:w]
    bg = np.stack([200 - yy * 0.1, 220 - yy * 0.1, 255 - yy * 0.2], -1)
    r = np.hypot(xx - 170, yy - 170) / 150
    sphere = np.clip(1.15 - r, 0, 1)[..., None] * np.array([255, 120, 60])
    m = (r < 1)[..., None]
    out = np.where(m, sphere + 40, bg)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")


SAMPLES = {
    "overlap": overlap, "stack3": stack3, "badge": badge, "face": face,
    "donut_alpha": donut_alpha, "ui_card": ui_card, "noisy_badge": noisy_badge, "shaded": shaded,
}


def main(outdir="samples"):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in SAMPLES.items():
        fn().save(out / f"{name}.png")
        print("wrote", out / f"{name}.png")


if __name__ == "__main__":
    main(*sys.argv[1:2])
