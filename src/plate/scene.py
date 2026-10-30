"""Data model shared by the pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .geometry import GradientFill, Prim
from .masks import Mask


@dataclass
class Loaded:
    rgb: np.ndarray              # (H, W, 3) uint8 at working resolution
    alpha: np.ndarray            # (H, W) uint8
    orig_size: tuple[int, int]   # (w, h) of the source image
    scale: float                 # work px per source px


@dataclass
class Shape:
    id: int
    color: tuple[int, int, int]
    vis: Mask                    # pixels this shape visibly owns
    full: Mask                   # complete (hole-filled, amodal) silhouette
    sil: Mask | None = None      # hole-filled visible silhouette (before completion)
    bleed: float = 0.0           # px this shape extends under later neighbours
    parent: int | None = None
    children: list[int] = field(default_factory=list)   # paint order, bottom -> top
    prim: Prim | None = None     # exact primitive known from completion
    completed: bool = False      # hidden part was reconstructed
    draw: Mask | None = None     # mask actually traced (full + bleed)
    name: str = ""
    label: str = ""              # semantic hint from VLM/SAM
    is_background: bool = False
    grad: GradientFill | None = None  # smooth-ramp fill (linear/radial), None = flat


@dataclass
class Segmentation:
    rid: np.ndarray              # (H, W) int32 region id, -1 = transparent
    shapes: list[Shape]
    palette: np.ndarray          # (K, 3) uint8

    def rebuilt(self, shapes: list[Shape]) -> Segmentation:
        """Reindex merged visible regions and discard stale ordering/completion."""
        fresh = [replace(s, id=i, full=s.vis, sil=None, parent=None, children=[], prim=None,
                         completed=False, draw=None, bleed=0., is_background=False)
                 for i, s in enumerate(shapes)]
        rid = np.full(self.rid.shape, -1, np.int32)
        for s in fresh:
            visible = s.vis.to_full(rid.shape)
            assert np.all(rid[visible] == -1), "overlapping visible regions after merge"
            rid[visible] = s.id
        assert np.array_equal(rid >= 0, self.rid >= 0), "merge changed visible ownership"
        return Segmentation(rid, fresh, self.palette)


@dataclass
class Node:
    """Output tree node: a group or a drawable element, in SVG coordinates."""
    name: str
    kind: str                    # group | path | circle | ellipse | rect | polygon
    color: tuple[int, int, int] | None = None
    children: list["Node"] = field(default_factory=list)
    d: str = ""
    params: dict = field(default_factory=dict)
    evenodd: bool = False
    anchors: int = 0
    shape_id: int | None = None
    grad: GradientFill | None = None  # SVG-space gradient fill (set by _leaf), None = flat
    stroke_width: float | None = None
    stroke_linecap: str = "round"
    stroke_linejoin: str = "round"
