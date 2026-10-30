"""Stage 2: containment tree, occlusion analysis and paint order.

* parent(B) = smallest shape whose hole-filled silhouette contains B  -> nested groups
* siblings that touch are analysed for occlusion (stage 3 completes hidden parts and
  tells us who hides whom) -> paint order via topological sort
* lower siblings get a small "bleed" under their neighbours so no hairline seams appear
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from ..config import Config
from ..masks import Mask, contains, touches, crop_like
from ..scene import Segmentation, Shape
from .complete import try_complete


def _silhouettes(shapes: list[Shape], transparent: np.ndarray) -> None:
    for s in shapes:
        f = s.vis.filled()
        y0, x0 = f.y0, f.x0
        h, w = f.a.shape
        tr = transparent[y0:y0 + h, x0:x0 + w]
        vis = s.vis.to_full(transparent.shape)[y0:y0 + h, x0:x0 + w]
        a = f.a & ~tr
        # A hole-fill normally keeps pixels this shape is painted *behind* (a later
        # sibling/child draws over them). But a genuine perforation that merely
        # contains a floating opaque island (e.g. a plate hole with a disc inside)
        # must stay a hole. `& ~tr` re-opens the transparent part, yet the island's
        # own opaque footprint survives as this colour and leaves a stray component.
        # Examine each hole-filled region (before transparency is removed): if it is
        # predominantly transparent it is a real perforation, so drop its few opaque
        # island pixels too. Regions that are mostly opaque (this shape genuinely sits
        # behind another) are left filled, so paint-order coverage is unaffected.
        filled_region = f.a & ~vis
        if filled_region.any():
            lbl, n = ndi.label(filled_region)
            for k in range(1, n + 1):
                comp = lbl == k
                if (comp & tr).sum() > 0.5 * comp.sum():
                    a = a & ~comp
        s.sil = Mask(a, y0, x0)
        s.full = Mask(a.copy(), y0, x0)


def _assign_parents(shapes: list[Shape]) -> None:
    if not shapes:
        return
    bb = np.array([s.sil.bbox for s in shapes])
    for B in shapes:
        b = B.vis.bbox
        ok = (bb[:, 0] <= b[0]) & (bb[:, 1] <= b[1]) & (bb[:, 2] >= b[2]) & (bb[:, 3] >= b[3])
        best = None
        for i in np.flatnonzero(ok):
            A = shapes[i]
            if A.id == B.id:
                continue
            if (A.sil.area, A.id) <= (B.sil.area, B.id):
                continue
            if contains(A.sil, B.vis):
                if best is None or (A.sil.area, A.id) < (best.sil.area, best.id):
                    best = A
        B.parent = best.id if best else None
    for s in shapes:
        s.children = []
    for s in shapes:
        if s.parent is not None:
            shapes[s.parent].children.append(s.id)


def _toposort(ids: list[int], edges: set[tuple[int, int]], shapes: list[Shape]) -> list[int]:
    """edges (a, b): a is painted before b. Larger shapes first when unconstrained."""
    remaining = set(ids)
    out: list[int] = []
    edges = {e for e in edges if e[0] in remaining and e[1] in remaining}
    key = lambda i: (-shapes[i].sil.area, i)
    while remaining:
        ready = [i for i in remaining if not any(e[1] == i for e in edges)]
        if not ready:  # cycle: break by dropping incoming edges of the largest shape
            victim = min(remaining, key=key)
            edges = {e for e in edges if e[1] != victim}
            continue
        nxt = min(ready, key=key)
        out.append(nxt)
        remaining.discard(nxt)
        edges = {e for e in edges if e[0] != nxt}
    return out


def merge_fragments(seg: Segmentation, transparent: np.ndarray, cfg: Config) -> Segmentation:
    """Reunite flat siblings only when a supported primitive explains their union.

    Same colour supplies candidates, not permission to merge. The shared outline
    must preserve every visible fragment and add hidden area beneath neighbours
    established by the relative T-junction test. Rebuild order after each merge.
    """
    if not cfg.complete_hidden:
        return seg
    H, W = transparent.shape
    groups: dict[tuple, list[Shape]] = {}
    for s in seg.shapes:
        if s.grad is None:
            groups.setdefault((s.parent, s.color), []).append(s)
    for (parent, color), members in groups.items():
        if len(members) < 2:
            continue
        ids = {s.id for s in members}
        visible = np.zeros((H, W), bool)
        for s in members:
            visible |= s.vis.to_full((H, W))
        vis = Mask.from_full(visible)
        sil = Mask.from_full(vis.filled().to_full((H, W)) & ~transparent)
        joint = Shape(members[0].id, color, vis, sil, sil=sil)
        covers = [s for s in seg.shapes if s.id not in ids and s.parent == parent
                  and touches(sil, s.sil, (H, W), 2)]
        comp = try_complete(joint, covers, H, W, cfg)
        if comp is None or comp.prim is None:
            continue
        shapes = [joint if s.id == joint.id else s for s in seg.shapes
                  if s.id == joint.id or s.id not in ids]
        return seg.rebuilt(shapes)
    return seg


def build(seg: Segmentation, transparent: np.ndarray, cfg: Config) -> list[int]:
    """Fills parent/children/full/draw on seg.shapes; returns root-level ids in paint order."""
    shapes = seg.shapes
    H, W = transparent.shape
    _silhouettes(shapes, transparent)
    _assign_parents(shapes)
    roots: list[int] = []

    groups: dict[int | None, list[int]] = {}
    for s in shapes:
        groups.setdefault(s.parent, []).append(s.id)

    for parent, sib in groups.items():
        edges: set[tuple[int, int]] = set()
        if cfg.complete_hidden and len(sib) > 1:
            for rid in sorted(sib, key=lambda i: shapes[i].sil.area):
                R = shapes[rid]
                C = [shapes[o] for o in sib if o != rid and touches(R.sil, shapes[o].sil, (H, W), 2)]
                if not C:
                    continue
                comp = try_complete(R, C, H, W, cfg)
                if comp is None:
                    continue
                R.full, R.prim, R.completed = comp.full, comp.prim, True
                for o in comp.above:
                    edges.add((rid, o))
        order = _toposort(sib, edges, shapes)
        # bleed: a shape extends ~1px *only where a later neighbour covers it*, so seams
        # can't show the background through. Free edges are untouched.
        r = int(round(cfg.bleed))
        for pos, rid in enumerate(order):
            R = shapes[rid]
            R.draw = R.full
            later = [shapes[o] for o in order[pos + 1:] if touches(R.full, shapes[o].full, (H, W), 2)]
            if r > 0 and later and R.prim is None:
                D = R.full.dilated(r, (H, W))
                cover = np.zeros(D.a.shape, bool)
                for o in later:
                    cover |= crop_like(o.full, D)
                ring = D.a & cover & ~crop_like(R.full, D)
                if ring.any():
                    R.draw = Mask(D.a & (cover | crop_like(R.full, D)), D.y0, D.x0)
                    R.bleed = float(r)
        if parent is None:
            roots = order
        else:
            shapes[parent].children = order
    return roots
