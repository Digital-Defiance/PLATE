"""Synthetic bake-off corpus with exact ground truth.

Each scene is a stack of known objects (bottom -> top). We render the PNG with cairo and keep:
  * truth/<name>.json  objects (kind, params, colour, z), background flag
  * truth/<name>.svg   the ground-truth layered SVG
Masks (full silhouette = what the object looks like with nothing on top; visible = after
occlusion) are recomputed from the JSON by `load_truth`, so the JSON is the single source.
Seeded: the same seed always gives the same corpus.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

SIZE = 512
PALETTE = [(214, 40, 40), (230, 160, 20), (40, 140, 70), (40, 90, 200), (120, 60, 160), (20, 40, 90),
           (240, 200, 40), (30, 160, 170), (230, 110, 140), (90, 60, 40), (30, 30, 30), (245, 242, 232)]


def _hex(c):
    return "#{:02x}{:02x}{:02x}".format(*c)


def obj_svg(o: dict) -> str:
    f = f'fill="{_hex(o["color"])}"'
    k, p = o["kind"], o
    if k == "circle":
        return f'<circle cx="{p["cx"]:.2f}" cy="{p["cy"]:.2f}" r="{p["r"]:.2f}" {f}/>'
    if k == "ellipse":
        return (f'<ellipse cx="{p["cx"]:.2f}" cy="{p["cy"]:.2f}" rx="{p["rx"]:.2f}" ry="{p["ry"]:.2f}" '
                f'transform="rotate({p["angle"]:.2f} {p["cx"]:.2f} {p["cy"]:.2f})" {f}/>')
    if k in ("rect", "rrect"):
        rr = f' rx="{p["r"]:.2f}"' if k == "rrect" else ""
        return (f'<rect x="{p["cx"]-p["w"]/2:.2f}" y="{p["cy"]-p["h"]/2:.2f}" width="{p["w"]:.2f}" '
                f'height="{p["h"]:.2f}"{rr} transform="rotate({p["angle"]:.2f} {p["cx"]:.2f} {p["cy"]:.2f})" {f}/>')
    if k == "polygon":
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in p["pts"])
        return f'<polygon points="{pts}" {f}/>'
    raise ValueError(k)


def scene_svg(objs: list[dict], only: int | None = None, upto: int | None = None) -> str:
    body = [obj_svg(o) for i, o in enumerate(objs)
            if (only is None or i == only) and (upto is None or i < upto)]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
            f'viewBox="0 0 {SIZE} {SIZE}">' + "".join(body) + "</svg>")


def render_mask(svg: str) -> np.ndarray:
    import io

    import cairosvg
    from PIL import Image
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=SIZE, output_height=SIZE)
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))[..., 3] > 127


def load_truth(path: Path) -> dict:
    """-> {'objects': [...], 'full': [bool masks], 'visible': [bool masks]} (index 0 = background)."""
    objs = json.loads(Path(path).read_text())["objects"]
    full = [render_mask(scene_svg(objs, only=i)) for i in range(len(objs))]
    visible, above = [None] * len(objs), np.zeros((SIZE, SIZE), bool)
    for i in range(len(objs) - 1, -1, -1):
        visible[i] = full[i] & ~above
        above |= full[i]
    return dict(objects=objs, full=full, visible=visible)


def _star(cx, cy, R, r, n, rot):
    return [(cx + (R if i % 2 == 0 else r) * math.cos(rot + i * math.pi / n),
             cy + (R if i % 2 == 0 else r) * math.sin(rot + i * math.pi / n)) for i in range(2 * n)]


def _ngon(cx, cy, R, n, rot):
    return [(cx + R * math.cos(rot + i * 2 * math.pi / n), cy + R * math.sin(rot + i * 2 * math.pi / n))
            for i in range(n)]


def _random_object(rng, color):
    kind = rng.choice(["circle", "circle", "ellipse", "rect", "rrect", "polygon"])
    cx, cy = rng.uniform(110, SIZE - 110, 2)
    o = dict(kind=kind, cx=float(cx), cy=float(cy), color=list(color))
    if kind == "circle":
        o["r"] = float(rng.uniform(40, 110))
    elif kind == "ellipse":
        o.update(rx=float(rng.uniform(40, 110)), ry=float(rng.uniform(25, 80)), angle=float(rng.choice([0, 0, 30, 90, 135])))
    elif kind in ("rect", "rrect"):
        o.update(w=float(rng.uniform(70, 220)), h=float(rng.uniform(60, 180)), angle=float(rng.choice([0, 0, 0, 20])),
                 r=float(rng.uniform(10, 30)) if kind == "rrect" else 0.0)
    else:
        n, rot = int(rng.integers(3, 7)), float(rng.uniform(0, 6.28))
        R = float(rng.uniform(55, 115))
        pts = _star(cx, cy, R, R * 0.45, int(rng.integers(4, 7)), rot) if rng.random() < 0.4 else _ngon(cx, cy, R, n, rot)
        o["pts"] = [[float(x), float(y)] for x, y in pts]
    return o


def make_scene(rng) -> list[dict]:
    bg = [(255, 255, 255), (245, 242, 232), (235, 238, 245), (30, 30, 40)][int(rng.integers(0, 4))]
    objs = [dict(kind="rect", cx=SIZE / 2, cy=SIZE / 2, w=float(SIZE), h=float(SIZE), angle=0.0, r=0.0,
                 color=list(bg), background=True)]
    n = int(rng.integers(3, 7))
    for _ in range(200):
        if len(objs) > n:
            break
        col = PALETTE[int(rng.integers(0, len(PALETTE)))]
        if sum(abs(a - b) for a, b in zip(col, objs[-1]["color"])) < 90 or list(col) == objs[0]["color"]:
            continue
        cand = _random_object(rng, col)
        trial = objs + [cand]
        try:
            render_mask(scene_svg(trial, only=len(trial) - 1))  # reject a candidate that won't render
        except Exception:                                   # noqa: BLE001
            continue
        # keep scenes honest: every object must stay clearly visible and inside the frame
        masks = [render_mask(scene_svg(trial, only=i)) for i in range(1, len(trial))]
        above = np.zeros((SIZE, SIZE), bool)
        ok = True
        for m in reversed(masks):
            vis = m & ~above
            above |= m
            if m.sum() < 2000 or vis.sum() < 0.35 * m.sum():
                ok = False
                break
        edge_ok = all(m[0].sum() + m[-1].sum() + m[:, 0].sum() + m[:, -1].sum() == 0 for m in masks)
        if ok and edge_ok:
            objs.append(cand)
    return objs


def make_corpus(out: Path, n: int = 24, seed: int = 1, noisy_every: int = 4) -> list[Path]:
    """Writes out/images/NAME.png (+ JPEG-noise variants) and out/truth/NAME.{json,svg}."""
    import io

    import cairosvg
    from PIL import Image
    rng = np.random.default_rng(seed)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "truth").mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        objs = make_scene(rng)
        jpg = bool(noisy_every) and i % noisy_every == noisy_every - 1     # same truth, JPEG-damaged input
        name = f"scene{i:02d}" + ("_jpg" if jpg else "")
        svg = scene_svg(objs)
        (out / "truth" / f"{name}.json").write_text(json.dumps(dict(objects=objs)))
        (out / "truth" / f"{name}.svg").write_text(svg)
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=SIZE, output_height=SIZE)
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if jpg:
            p = out / "images" / f"{name}.jpg"
            im.save(p, "JPEG", quality=55)
        else:
            p = out / "images" / f"{name}.png"
            im.save(p)
        paths.append(p)
    return paths
