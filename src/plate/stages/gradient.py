"""Gradient detection: merge thin flat bands that form one smooth ramp.

Runs BETWEEN segment() and order.build(). segment() posterizes a smooth colour ramp
(a shaded sphere, a gradient background) into many thin flat bands, one Shape per
palette step. This stage finds maximal sets of adjacent thin bands that together are
one smooth linear/radial ramp, replaces each confident set with a single Shape, and
attaches a GradientFill descriptor. Conservative: when unsure, leave bands as-is.

The returned Segmentation has a re-indexed (id == index) shapes list and a rebuilt rid
map; palette rides through unchanged.
"""
from __future__ import annotations

import numpy as np

from ..config import Config
from ..geometry import fit_linear_gradient, fit_radial_gradient
from ..masks import Mask, touches
from ..scene import Loaded, Segmentation, Shape
from . import segment as _segment

GRAD_FIT_SAMPLES = 20000


def _band_mean_rgb(s: Shape, img: Loaded, H: int, W: int) -> np.ndarray:
    full = s.vis.to_full((H, W))
    ys, xs = np.nonzero(full)
    return img.rgb[ys, xs].astype(np.float32).mean(axis=0)


def _lab_of(rgb: np.ndarray) -> np.ndarray:
    return _segment._lab(rgb.reshape(1, 1, 3).astype(np.uint8)).reshape(3)


def _single_object(members: list[Shape], H: int, W: int) -> bool:
    """True when the hole-filled union of member vis masks is one 4-connected region."""
    acc = np.zeros((H, W), bool)
    for b in members:
        acc |= b.vis.to_full((H, W))
    filled = Mask.from_full(acc).filled().to_full((H, W))
    from scipy import ndimage as ndi
    _, n = ndi.label(filled, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
    return n == 1


def _monotone_ok(members: list[Shape], u_mean: dict[int, float], means: dict[int, np.ndarray],
                 thresh: float) -> bool:
    """Per-channel cumulative backward step (in 0..255 units) must not exceed `thresh`."""
    ordered = sorted(members, key=lambda b: u_mean[b.id])
    seq = np.array([means[b.id] for b in ordered])          # (m, 3) in 0..255
    if len(seq) < 2:
        return True
    for c in range(3):
        col = seq[:, c]
        sign = 1.0 if (col[-1] - col[0]) >= 0 else -1.0
        back = 0.0
        for i in range(1, len(col)):
            back += max(0.0, -sign * (col[i] - col[i - 1]))
        if back > thresh:
            return False
    return True


def _find_components(seg: Segmentation, img: Loaded, cfg: Config) -> list[dict]:
    H, W = img.alpha.shape
    grad_min_px = round(cfg.grad_min_frac * H * W)
    grad_band_max_px = round(cfg.grad_band_max_frac * H * W)
    shapes = seg.shapes

    # per-band mean colour (rgb + Lab) cache
    means: dict[int, np.ndarray] = {}
    labs: dict[int, np.ndarray] = {}
    for s in shapes:
        if s.vis.empty():
            continue
        m = _band_mean_rgb(s, img, H, W)
        means[s.id] = m
        labs[s.id] = _lab_of(np.round(m).astype(np.uint8))

    thin = {s.id for s in shapes if (not s.vis.empty()) and s.vis.area <= grad_band_max_px}

    # adjacency graph over thin bands only (touches within gap=2)
    thin_shapes = [s for s in shapes if s.id in thin]
    adj: dict[int, set[int]] = {s.id: set() for s in thin_shapes}
    for i in range(len(thin_shapes)):
        a = thin_shapes[i]
        for j in range(i + 1, len(thin_shapes)):
            b = thin_shapes[j]
            if touches(a.vis, b.vis, (H, W), gap=2):
                adj[a.id].add(b.id)
                adj[b.id].add(a.id)

    claimed: set[int] = set()
    by_id = {s.id: s for s in shapes}
    components: list[dict] = []

    for seed in thin_shapes:
        if seed.id in claimed:
            continue
        # grow connected component through adjacency, admitting thin bands within grad_step_de
        comp_ids = [seed.id]
        stack = [seed.id]
        in_comp = {seed.id}
        while stack:
            cur = stack.pop()
            for nb in adj[cur]:
                if nb in in_comp or nb in claimed:
                    continue
                de = float(np.linalg.norm(labs[cur] - labs[nb]))
                if de <= cfg.grad_step_de:
                    in_comp.add(nb)
                    comp_ids.append(nb)
                    stack.append(nb)
        members = [by_id[i] for i in comp_ids]

        # cheap pre-fit gates
        if len(members) < cfg.grad_min_bands:
            continue
        total_px = sum(b.vis.area for b in members)
        if total_px < grad_min_px:
            continue
        if any(b.vis.area > grad_band_max_px for b in members):
            continue
        if not _single_object(members, H, W):
            continue

        # build the pooled visible-pixel sample for the fit
        acc = np.zeros((H, W), bool)
        for b in members:
            acc |= b.vis.to_full((H, W))
        ys, xs = np.nonzero(acc)
        P = np.c_[xs, ys].astype(float)
        C = img.rgb[ys, xs].astype(float)
        n = len(P)
        rng = np.random.default_rng(0)
        idx = rng.choice(n, GRAD_FIT_SAMPLES, replace=False) if n > GRAD_FIT_SAMPLES else np.arange(n)
        Pf, Cf = P[idx], C[idx]

        gl, rl = fit_linear_gradient(Pf, Cf)
        gr, rr = fit_radial_gradient(Pf, Cf)
        if rl <= rr:                           # ties -> linear (simpler model)
            grad, residual = gl, rl
        else:
            grad, residual = gr, rr

        # fit-space gates
        if residual > cfg.grad_max_residual:
            continue
        # monotonicity along the fitted axis
        u_mean = _axis_u_per_band(members, grad, img, H, W)
        if not _monotone_ok(members, u_mean, means, cfg.grad_max_residual * 255.0):
            continue

        # accept: representative solid colour = stop curve at u=0.5
        color = _stopcurve_color(grad, 0.5)
        for b in members:
            claimed.add(b.id)
        components.append({"members": members, "grad": grad, "color": color})

    return components


def _axis_u_per_band(members: list[Shape], grad, img: Loaded, H: int, W: int) -> dict[int, float]:
    """Mean axis parameter (t for linear, rho for radial) of each band's pixels."""
    out: dict[int, float] = {}
    if grad.kind == "linear":
        sx, sy = grad.start
        ex, ey = grad.end
        dx, dy = ex - sx, ey - sy
        den = dx * dx + dy * dy
        for b in members:
            full = b.vis.to_full((H, W))
            ys, xs = np.nonzero(full)
            if den < 1e-9:
                out[b.id] = 0.0
            else:
                t = ((xs - sx) * dx + (ys - sy) * dy) / den
                out[b.id] = float(np.mean(t))
    else:
        cx, cy = grad.center
        r = grad.radius or 1.0
        for b in members:
            full = b.vis.to_full((H, W))
            ys, xs = np.nonzero(full)
            rho = np.hypot(xs - cx, ys - cy) / r
            out[b.id] = float(np.mean(rho))
    return out


def _stopcurve_color(grad, t: float) -> tuple[int, int, int]:
    offs = np.array([s.offset for s in grad.stops], float)
    cols = np.array([s.rgb for s in grad.stops], float)
    if len(offs) == 1:
        rgb = cols[0]
    else:
        rgb = np.array([np.interp(t, offs, cols[:, c]) for c in range(3)])
    return tuple(int(round(v)) for v in rgb)


def detect(seg: Segmentation, img: Loaded, cfg: Config) -> Segmentation:
    """Merge groups of thin flat bands that form one smooth ramp into a single Shape
    carrying a GradientFill. Returns a NEW Segmentation with a re-indexed shapes list
    (id == index) and a rebuilt rid map; palette passes through unchanged."""
    H, W = img.alpha.shape
    components = _find_components(seg, img, cfg)

    survivors: list[Shape] = []
    claimed: set[int] = set()
    for comp in components:
        acc = np.zeros((H, W), bool)
        for b in comp["members"]:
            acc |= b.vis.to_full((H, W))
            claimed.add(b.id)
        merged_vis = Mask.from_full(acc)
        survivors.append(Shape(id=0, color=comp["color"], vis=merged_vis, full=merged_vis,
                               grad=comp["grad"]))
    for s in seg.shapes:
        if s.id not in claimed:
            survivors.append(s)

    new_rid = np.full((H, W), -1, np.int32)
    new_shapes: list[Shape] = []
    for i, s in enumerate(survivors):
        s.id = i                                # strict id == index invariant
        full = s.vis.to_full((H, W))
        ys, xs = np.nonzero(full)
        # regions are disjoint: no pixel is ever assigned to two different survivor ids
        assert np.all(new_rid[ys, xs] == -1), "gradient.detect: overlapping survivor regions"
        new_rid[ys, xs] = i
        new_shapes.append(s)
    return Segmentation(rid=new_rid, shapes=new_shapes, palette=seg.palette)
