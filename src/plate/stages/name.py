"""Layer naming. Classical names are always produced ("Red circle", "Navy shape");
a vision-language model (see ../vlm.py) can then replace them with semantic ones."""
from __future__ import annotations

import cv2
import numpy as np

from ..scene import Node

_COLORS = [
    ("White", 255, 255, 255), ("Black", 0, 0, 0), ("Gray", 128, 128, 128),
    ("Light gray", 200, 200, 200), ("Dark gray", 64, 64, 64), ("Red", 220, 40, 40),
    ("Dark red", 140, 25, 25), ("Orange", 240, 140, 30), ("Yellow", 250, 220, 40),
    ("Gold", 240, 180, 30), ("Lime", 150, 210, 50), ("Green", 40, 150, 70),
    ("Dark green", 20, 90, 50), ("Teal", 20, 150, 150), ("Cyan", 40, 210, 230),
    ("Sky blue", 120, 180, 240), ("Blue", 40, 90, 210), ("Navy", 20, 40, 90),
    ("Purple", 130, 60, 170), ("Magenta", 210, 40, 150), ("Pink", 240, 140, 170),
    ("Brown", 120, 70, 40), ("Beige", 235, 225, 200), ("Cream", 245, 242, 232),
    ("Tan", 205, 170, 125), ("Coral", 240, 110, 90),
]
_names = [c[0] for c in _COLORS]
_lab = cv2.cvtColor(np.array([[c[1:] for c in _COLORS]], np.float32) / 255.0, cv2.COLOR_RGB2LAB)[0]

KIND_WORD = {"circle": "circle", "ellipse": "ellipse", "rect": "rectangle",
             "rrect": "rounded rectangle", "polygon": "polygon", "path": "shape"}


def color_name(rgb) -> str:
    lab = cv2.cvtColor(np.array([[rgb]], np.float32) / 255.0, cv2.COLOR_RGB2LAB)[0, 0]
    return _names[int(np.argmin(np.linalg.norm(_lab - lab, axis=1)))]


def assign_names(nodes: list[Node], overrides: dict[int, str] | None = None) -> None:
    """Depth-first naming with unique suffixes. `overrides` maps shape_id -> semantic name."""
    seen: dict[str, int] = {}

    def uniq(base: str) -> str:
        seen[base] = seen.get(base, 0) + 1
        return base if seen[base] == 1 else f"{base} {seen[base]}"

    def walk(n: Node):
        if n.kind != "group":
            base = (overrides or {}).get(n.shape_id) or n.name or "Shape"
            n.name = uniq(base)
        for c in n.children:
            walk(c)
        if n.kind == "group" and n.children:
            if n.name:                       # semantic group name from the VLM
                n.name = uniq(n.name)
            else:
                n.name = n.children[0].name.removesuffix(" base")

    for n in nodes:
        walk(n)
