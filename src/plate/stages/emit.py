"""Stage 6: Node tree -> SVG text with Illustrator-friendly structure.

Top-level groups become Illustrator layers, nested groups become sub-layers. Names are
written three ways because importers disagree: a sanitised `id` (Illustrator reads this),
`data-name` (Illustrator round-trip attribute) and `inkscape:label` (Inkscape).
"""
from __future__ import annotations

import re
from xml.sax.saxutils import escape, quoteattr

import numpy as np

from ..scene import Node

_ID_BAD = re.compile(r"[^A-Za-z0-9_\-]")


def _hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*[int(v) for v in rgb])


def _num(v: float, prec: int) -> str:
    s = f"{v:.{prec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class _Ids:
    def __init__(self):
        self.used: set[str] = set()

    def make(self, name: str) -> str:
        base = _ID_BAD.sub("_", name.strip().replace(" ", "_")) or "Layer"
        if base[0].isdigit():
            base = "_" + base
        cand, i = base, 1
        while cand in self.used:
            i += 1
            cand = f"{base}_{i}"
        self.used.add(cand)
        return cand


def _label(n: Node, ids: _Ids, cfg_layers: bool, top: bool) -> str:
    if not cfg_layers:
        return ""
    attrs = f' id="{ids.make(n.name)}" data-name={quoteattr(n.name)} inkscape:label={quoteattr(n.name)}'
    if top and n.kind == "group":
        attrs += ' inkscape:groupmode="layer"'
    return attrs


def _rot(p: dict, prec: int) -> str:
    a = p.get("angle", 0.0)
    return "" if abs(a) < 1e-6 else f' transform="rotate({_num(a, 3)} {_num(p["cx"], prec)} {_num(p["cy"], prec)})"'


def node_svg(n: Node, ids: _Ids, prec: int, layers: bool, grads: list, depth: int = 0,
             top: bool = False) -> list[str]:
    pad = "  " * (depth + 1)
    lab = _label(n, ids, layers, top)
    if n.kind == "group":
        out = [f"{pad}<g{lab}>"]
        for c in n.children:
            out += node_svg(c, ids, prec, layers, grads, depth + 1)
        out.append(f"{pad}</g>")
        return out
    # a gradient id is minted AFTER _label (so existing layer ids stay byte-identical) and
    # ALWAYS from the shared _Ids, independent of cfg.illustrator_layers -- a fill="url(#id)"
    # reference needs a live <defs> target regardless of whether elements carry their own id.
    if n.grad is not None:
        gid = ids.make(f"{n.name} gradient")
        grads.append((gid, n.grad))
        fill = f' fill="url(#{gid})"'
    else:
        fill = f' fill="{_hex(n.color)}"'
    if n.stroke_width is not None and n.kind in ("circle", "ellipse"):
        fill = f' fill="none" stroke="{_hex(n.color)}" stroke-width="{_num(n.stroke_width, prec)}"'
    p = n.params
    N = lambda v: _num(v, prec)
    if n.kind == "path":
        if n.stroke_width is not None:
            return [f'{pad}<path{lab} d="{n.d}" fill="none" stroke="{_hex(n.color)}" '
                    f'stroke-width="{N(n.stroke_width)}" stroke-linecap={quoteattr(n.stroke_linecap)} '
                    f'stroke-linejoin={quoteattr(n.stroke_linejoin)}/>']
        rule = ' fill-rule="evenodd"' if n.evenodd else ""
        return [f'{pad}<path{lab} d="{n.d}"{fill}{rule}/>']
    if n.kind == "circle":
        return [f'{pad}<circle{lab} cx="{N(p["cx"])}" cy="{N(p["cy"])}" r="{N(p["r"])}"{fill}/>']
    if n.kind == "ellipse":
        return [f'{pad}<ellipse{lab} cx="{N(p["cx"])}" cy="{N(p["cy"])}" rx="{N(p["rx"])}" '
                f'ry="{N(p["ry"])}"{fill}{_rot(p, prec)}/>']
    if n.kind in ("rect", "rrect"):
        rr = f' rx="{N(p["r"])}" ry="{N(p["r"])}"' if n.kind == "rrect" else ""
        return [f'{pad}<rect{lab} x="{N(p["cx"] - p["rx"])}" y="{N(p["cy"] - p["ry"])}" '
                f'width="{N(2 * p["rx"])}" height="{N(2 * p["ry"])}"{rr}{fill}{_rot(p, prec)}/>']
    if n.kind == "polygon":
        pts = " ".join(f"{N(x)},{N(y)}" for x, y in p["pts"])
        return [f'{pad}<polygon{lab} points="{pts}"{fill}/>']
    raise ValueError(n.kind)


def _grad_svg(gid: str, g, prec: int) -> list[str]:
    N = lambda v: _num(v, prec)
    stops = [f'    <stop offset="{N(s.offset)}" stop-color="{_hex(s.rgb)}"/>' for s in g.stops]
    if g.kind == "linear":
        sx, sy = g.start
        ex, ey = g.end
        head = (f'  <linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                f'x1="{N(sx)}" y1="{N(sy)}" x2="{N(ex)}" y2="{N(ey)}">')
        return [head, *stops, "  </linearGradient>"]
    cx, cy = g.center
    foc = f' fx="{N(g.focal[0])}" fy="{N(g.focal[1])}"' if g.focal is not None else ""
    head = (f'  <radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
            f'cx="{N(cx)}" cy="{N(cy)}" r="{N(g.radius)}"{foc}>')
    return [head, *stops, "  </radialGradient>"]


def write_svg(nodes: list[Node], size: tuple[int, int], prec: int = 2, layers: bool = True) -> str:
    w, h = size
    ids = _Ids()
    grads: list = []
    body: list[str] = []
    for n in nodes:
        body += node_svg(n, ids, prec, layers, grads, 0, top=True)
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">')
    # a single <defs> is emitted ONLY when at least one gradient exists, so flat art is
    # byte-identical (no empty <defs> line). It appears textually before the body but is
    # BUILT from ids allocated during the body walk above.
    defs: list[str] = []
    if grads:
        defs.append("  <defs>")
        for gid, g in grads:
            defs += _grad_svg(gid, g, prec)
        defs.append("  </defs>")
    return "\n".join(['<?xml version="1.0" encoding="UTF-8"?>', head, *defs, *body, "</svg>", ""])
