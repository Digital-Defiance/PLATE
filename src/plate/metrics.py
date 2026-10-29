"""Editability + fidelity metrics (see docs/METRICS.md). Pure functions over SVG text."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import numpy as np

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_SHAPES = {"path", "circle", "ellipse", "rect", "polygon", "polyline", "line"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _path_anchors(d: str) -> int:
    n = 0
    for cmd, args in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d):
        k = len(_NUM.findall(args))
        c = cmd.upper()
        n += {"M": 0, "Z": 0, "L": k // 2, "H": k, "V": k, "C": k // 6, "S": k // 4, "Q": k // 4,
              "T": k // 2, "A": 2 * (k // 7)}[c]   # an SVG arc becomes up to 2 Bezier segments
    return n


def analyze_svg(svg: str) -> dict:
    root = ET.fromstring(svg)
    shapes = prims = anchors = unnamed = groups = gradients = 0
    depth = [0]

    def walk(el, d):
        nonlocal shapes, prims, anchors, unnamed, groups, gradients
        t = _local(el.tag)
        if t in ("linearGradient", "radialGradient"):
            gradients += 1
        if t == "g":
            groups += 1
            depth[0] = max(depth[0], d + 1)
            if not (el.get("id") or el.get("data-name")):
                unnamed += 1
        elif t in _SHAPES:
            shapes += 1
            if not (el.get("id") or el.get("data-name")):
                unnamed += 1
            if t == "path":
                anchors += _path_anchors(el.get("d", ""))
            elif t in ("circle", "ellipse"):
                anchors += 4; prims += 1
            elif t == "rect":
                anchors += 8 if el.get("rx") else 4; prims += 1
            elif t == "polygon":
                anchors += len(_NUM.findall(el.get("points", ""))) // 2; prims += 1
        for c in el:
            walk(c, d + (t == "g"))

    walk(root, 0)
    return dict(shapes=shapes, groups=groups, layer_depth=depth[0], anchors=anchors,
                gradients=gradients,
                anchors_per_shape=round(anchors / max(shapes, 1), 2),
                primitive_ratio=round(prims / max(shapes, 1), 3),
                unnamed_ratio=round(unnamed / max(shapes + groups, 1), 3), bytes=len(svg.encode()))


def fidelity(svg: str, src_rgba: np.ndarray, bg=(255, 255, 255)) -> dict:
    """Render the SVG and compare to the source composited on `bg`. Needs cairosvg."""
    from .raster import render_svg
    h, w = src_rgba.shape[:2]
    ren = render_svg(svg, (w, h), bg).astype(np.float32)
    a = src_rgba[..., 3:4].astype(np.float32) / 255
    ref = src_rgba[..., :3].astype(np.float32) * a + np.array(bg, np.float32) * (1 - a)
    mae = float(np.abs(ren - ref).mean())
    out = dict(mae=round(mae, 3), psnr=round(float(20 * np.log10(255 / max(np.sqrt(((ren - ref) ** 2).mean()), 1e-6))), 2))
    try:
        from skimage.metrics import structural_similarity as ssim
        out["ssim"] = round(float(ssim(ref.astype(np.uint8), ren.astype(np.uint8), channel_axis=2)), 4)
    except Exception:                                   # noqa: BLE001
        pass
    return out
