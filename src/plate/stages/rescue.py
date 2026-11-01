"""Optional stage: rescue fine detail the flat-colour segmentation absorbed (cfg.rescue_detail).

Strokes only ~2 px wide (small text, hairlines) never reach a clean flat colour after
resampling or JPEG compression, so segmentation folds them into the surrounding region. For
each pixel with base colour b (the colour of the region it was assigned to) and each palette
colour c we measure how far along b -> c the pixel sits (alpha) and how far off that line it
is (rel); a pixel is ink of the best-fitting c when alpha > 0.45 and rel < 0.18. Ink next to an
existing region of the same colour (its anti-aliased fringe) or lying on a boundary between two
regions (a blend, not detail) is dropped; blobs of at least `rescue_min_area` px are traced as
one "Fine detail" group, a compound path per colour, painted on top.

Found on the Research Force logo: its 2 px tagline vanished completely without this pass.
Gradient-filled and translucent regions are excluded (their pixels legitimately differ from
the region's flat colour).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from ..config import Config
from ..masks import Mask
from ..scene import Loaded, Node, Segmentation
from .name import color_name
from .trace import mask_to_path


def find(img: Loaded, seg: Segmentation, min_area: int = 6,
         absorbable: set[int] | None = None, bridge_px: int = 6) -> tuple[list[tuple[tuple, np.ndarray]], set[int]]:
    """-> ([(colour, bool mask)] per palette colour, ids of small regions absorbed).

    Regions in `absorbable` (small, childless, flat) are fragments of the same fine detail the
    segmentation half-caught (e.g. pieces of tagline letters): their pixels join the ink and the
    region is reported so the caller can drop it - otherwise the fringe exclusion below would cut
    a gap around every fragment."""
    H, W = img.alpha.shape
    rid = seg.rid
    absorbable = absorbable or set()
    if rid.shape != (H, W) or not seg.shapes:
        return [], set()
    rgb = img.rgb.astype(np.float32)
    colors = np.array([s.color for s in seg.shapes], np.float32).reshape(-1, 3)
    flat = np.array([getattr(s, "grad", None) is None and getattr(s, "opacity", 1.0) >= 0.999
                     for s in seg.shapes], bool)
    valid_px = (rid >= 0) & (rid < len(seg.shapes)) & (img.alpha > 200)
    valid_px[valid_px] &= flat[rid[valid_px]]
    base = np.zeros((H, W, 3), np.float32)
    base[valid_px] = colors[rid[valid_px]]
    uniq = np.unique(colors[flat], axis=0) if flat.any() else np.zeros((0, 3), np.float32)
    best_rel = np.full((H, W), np.inf, np.float32)
    best_k = np.full((H, W), -1, np.int32)
    v = rgb - base
    for k, c in enumerate(uniq):
        u = c[None, None, :] - base
        un = np.linalg.norm(u, axis=2)
        with np.errstate(divide="ignore", invalid="ignore"):
            alpha = (v * u).sum(2) / (un ** 2)
            rel = np.linalg.norm(v - alpha[..., None] * u, axis=2) / un
        ok = valid_px & (un > 80) & (alpha > 0.45) & (rel < 0.18)
        better = ok & (rel < best_rel)
        best_rel[better], best_k[better] = rel[better], k
    small = np.zeros(len(seg.shapes) + 1, bool)
    for i in absorbable:
        if 0 <= i < len(seg.shapes):
            small[i] = True
    frag = valid_px.copy()
    frag[valid_px] = small[rid[valid_px]]
    # boundaries between two (non-fragment) regions: blends there are anti-aliasing, not detail
    rb = np.where(frag, -2, rid)
    border = np.zeros((H, W), bool)
    dx = (rb[:, 1:] != rb[:, :-1]) & (rb[:, 1:] != -2) & (rb[:, :-1] != -2)
    dy = (rb[1:, :] != rb[:-1, :]) & (rb[1:, :] != -2) & (rb[:-1, :] != -2)
    border[:, 1:] |= dx; border[:, :-1] |= dx; border[1:, :] |= dy; border[:-1, :] |= dy
    border = ndi.binary_dilation(border, iterations=2)
    out, absorbed = [], set()
    for k, c in enumerate(uniq):
        same = valid_px & (np.abs(base - c).sum(2) < 1.0)
        frag_c = same & frag
        real = same & ~frag
        raw = best_k == k
        ink = raw & ~ndi.binary_dilation(real, iterations=3)   # fringe of real regions
        ink |= frag_c
        lab, n = ndi.label(ink)
        if n == 0:
            continue
        idx = range(1, n + 1)
        sizes = ndi.sum(ink, lab, idx)
        on_border = ndi.sum(border, lab, idx)
        # A blob whose ink runs on unbroken into a real region of the same colour is that
        # region's own tapering tip (a narrow wedge whose last pixels fell below 50% coverage),
        # not separate detail and not a blend - so the border test below does not apply to it.
        # Painted alone it floats as a speck with a gap behind it (seen between the page lines
        # of the Research Force logo), so it is bridged back further down.
        rlab, _ = ndi.label(raw | real | frag_c)
        touching = np.unique(rlab[real])
        tip_px = ink & np.isin(rlab, touching[touching > 0])
        tips = set(np.unique(lab[tip_px]).tolist()) - {0}
        keep_ids = [i + 1 for i, (sz, bd) in enumerate(zip(sizes, on_border))
                    if min_area <= sz <= 0.02 * H * W and (bd <= 0.5 * sz or i + 1 in tips)]
        if keep_ids:
            keep = np.isin(lab, keep_ids)
            tip = keep & tip_px
            if tip.any():
                # add the ink and region pixels next to it, letting it overlap the region
                reach = ndi.binary_dilation(tip, iterations=bridge_px)
                keep |= reach & (raw | real | frag_c) & np.isin(rlab, np.unique(rlab[tip]))
            out.append((tuple(int(x) for x in c), keep))
            absorbed |= {int(r) for r in np.unique(rid[keep & frag_c])}
    return out, absorbed


def absorbable_ids(seg: Segmentation, canvas: tuple[int, int], scale: float) -> set[int]:
    """Small, childless, flat regions (fine-detail fragments) the rescue may absorb."""
    H, W = canvas
    limit = max(60.0, 0.00025 * H * W)
    return {s.id for s in seg.shapes
            if not s.children and not s.is_background and getattr(s, "grad", None) is None
            and s.vis is not None and s.vis.area <= limit}


def run(img: Loaded, seg: Segmentation, cfg: Config) -> tuple[Node | None, set[int]]:
    H, W = img.alpha.shape
    found, absorbed = find(img, seg, cfg.rescue_min_area, absorbable_ids(seg, (H, W), img.scale),
                           bridge_px=int(np.ceil(4 + 2 * max(cfg.smooth, 0.45) * img.scale)))
    if not found:
        return None, set()
    H, W = img.alpha.shape
    tcfg = cfg.merged(smooth=min(cfg.smooth, 0.4), simplify=min(cfg.simplify, 0.5),
                      edge_smooth=min(cfg.edge_smooth, 0.8), snap_primitives=False)
    kids = []
    for color, m in found:
        d, anchors, _ = mask_to_path(Mask.from_full(m), (H, W), tcfg, img.scale)
        if d:
            kids.append(Node(f"{color_name(color)} fine detail", "path", color, d=d, evenodd=True,
                             anchors=anchors))
    return (Node("Fine detail", "group", None, children=kids), absorbed) if kids else (None, set())
