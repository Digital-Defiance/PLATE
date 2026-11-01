"""Tool adapters: each is `fn(src: Path, dst: Path) -> None` writing an SVG.

Built-in: plate, vtracer, vtracer-cutout, potrace-color (pure-Python potrace, k-colour stack).
External tools (Illustrator Image Trace, Vectorizer.AI, Inkscape, ...): export SVGs yourself as
`<external_dir>/<image-stem>.<tool-name>.svg`; `discover_external` picks them up.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..config import Config


def plate(src: Path, dst: Path, cfg: Config | None = None) -> None:
    from .. import pipeline
    dst.write_text(pipeline.run(src, cfg or Config()).svg, encoding="utf-8")


def vtracer_stacked(src: Path, dst: Path) -> None:
    import vtracer
    vtracer.convert_image_to_svg_py(str(src), str(dst), colormode="color", hierarchical="stacked", mode="spline")


def vtracer_cutout(src: Path, dst: Path) -> None:
    import vtracer
    vtracer.convert_image_to_svg_py(str(src), str(dst), colormode="color", hierarchical="cutout", mode="spline")


def potrace_color(src: Path, dst: Path, k: int = 8) -> None:
    """Classic Potrace workflow for colour: quantise to k colours, trace each colour layer, stack
    largest first. Needs `pip install potracer` (pure Python)."""
    import potrace
    im = Image.open(src).convert("RGB")
    q = im.quantize(colors=k, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    idx, pal = np.asarray(q), np.asarray(q.getpalette()[: 3 * k]).reshape(-1, 3)
    order = sorted(range(len(pal)), key=lambda c: -(idx == c).sum())
    h, w = idx.shape
    parts = []
    for c in order:
        m = idx == c
        if m.sum() < 20:
            continue
        d = []
        # potracer fills where the bitmap is False, so pass the inverted, padded mask; shift back by the pad
        P = lambda pt: f"{pt.x - 1:.2f} {pt.y - 1:.2f}"
        for curve in potrace.Bitmap(~np.pad(m, 1)).trace(turdsize=4, alphamax=1.0, opticurve=True, opttolerance=0.4):
            d.append("M" + P(curve.start_point))
            for seg in curve.segments:
                if seg.is_corner:
                    d.append("L" + P(seg.c) + "L" + P(seg.end_point))
                else:
                    d.append("C" + P(seg.c1) + " " + P(seg.c2) + " " + P(seg.end_point))
            d.append("Z")
        parts.append(f'<path fill="#{pal[c][0]:02x}{pal[c][1]:02x}{pal[c][2]:02x}" fill-rule="evenodd" d="{"".join(d)}"/>')
    dst.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                   + "".join(parts) + "</svg>", encoding="utf-8")


BUILTIN = {"plate": plate, "vtracer": vtracer_stacked, "vtracer-cutout": vtracer_cutout,
           "potrace-color": potrace_color}


def discover_external(folder: Path, stems: list[str]) -> dict[str, dict[str, Path]]:
    """{tool: {image_stem: svg_path}} from files named IMAGE.TOOL.svg."""
    out: dict[str, dict[str, Path]] = {}
    for p in sorted(folder.glob("*.svg")):
        for stem in stems:
            if p.name.startswith(stem + ".") and p.name.count(".") >= 2:
                tool = p.name[len(stem) + 1:-4]
                out.setdefault(tool, {})[stem] = p
                break
    return out
