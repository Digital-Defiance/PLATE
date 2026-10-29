"""Stage 3: amodal completion.

For a shape R that touches siblings C, decide whether R is partly hidden behind them and,
if so, reconstruct its full silhouette:

 1. Take R's outer contour. Points near C are "occluded", points on the image frame are
    "frame", the rest are "free".
 2. Fit exact primitives (circle, ellipse, rectangle) to the free points.
 3. Otherwise bridge each occluded gap with a cubic Bezier that continues the tangents.
 4. Accept only if the reconstruction (a) still contains R, and (b) the area it adds lies
    inside the shapes we claim are hiding it. This test is what keeps tiles that merely sit
    side by side from being "completed" into each other.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage as ndi

from ..bezier import bez, resample_closed
from ..config import Config
from ..geometry import (Prim, fit_circle, fit_ellipse, fit_rect, mean_deviation,
                        outer_contour, raster_prim, SCALE, SHIFT)
from ..masks import Mask
from ..scene import Shape


@dataclass
class Completion:
    full: Mask
    prim: Prim | None
    above: list[int]          # ids of shapes that hide part of R (R is below these)
    extra_px: int


def _paste(m: Mask, shape, origin):
    ox, oy = origin
    out = np.zeros(shape, bool)
    y0, x0 = m.y0 - oy, m.x0 - ox
    h, w = m.a.shape
    ys, xs = max(y0, 0), max(x0, 0)
    ye, xe = min(y0 + h, shape[0]), min(x0 + w, shape[1])
    if ye > ys and xe > xs:
        out[ys:ye, xs:xe] = m.a[ys - y0:ye - y0, xs - x0:xe - x0]
    return out


def _norm(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([1.0, 0.0])


def _bridge(pts: np.ndarray, cls: np.ndarray):
    """Replace each occluded run by a tangent-continuous cubic. Returns polygon or None."""
    n = len(pts)
    free_idx = np.flatnonzero(cls != 2)
    if free_idx.size == 0:
        return None
    s = int(free_idx[0])
    pts, cls = np.roll(pts, -s, axis=0), np.roll(cls, -s)
    out, i = [], 0
    while i < n:
        if cls[i] != 2:
            out.append(pts[i])
            i += 1
            continue
        j = i
        while j < n and cls[j] == 2:
            j += 1
        p0, p1 = pts[i - 1], pts[j % n]
        t0 = _norm(p0 - pts[max(i - 1 - 10, 0)])
        t1 = _norm(pts[min(j + 10, n - 1)] - p1) if j < n else _norm(pts[min(10, n - 1)] - p1)
        h = 0.37 * np.linalg.norm(p1 - p0)
        ctrl = np.array([p0, p0 + t0 * h, p1 - t1 * h, p1])
        out.extend(bez(ctrl, np.linspace(0, 1, 40)[1:-1]))
        i = j
    return np.array(out)


def _turn_at(pts: np.ndarray, i: int, k: int) -> float:
    n = len(pts)
    v1 = pts[i % n] - pts[(i - k) % n]
    v2 = pts[(i + k) % n] - pts[i % n]
    c = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-12)
    return float(np.degrees(np.arccos(np.clip(c, -1, 1))))


def _side_tangent(pts: np.ndarray, t: int, direction: int, m: int = 8, skip: int = 0):
    """Unit tangent at the junction point extrapolated from a quadratic fit to the m points
    on one side (direction=+1 forward along the contour, -1 backward). Result points in
    the direction of travel."""
    n = len(pts)
    idx = [(t + direction * (skip + j)) % n for j in range(m)]
    Q = pts[idx]
    ds = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))] + skip
    deg = 2 if m >= 6 else 1
    gx = np.polyfit(ds, Q[:, 0], deg)
    gy = np.polyfit(ds, Q[:, 1], deg)
    d = np.array([gx[-2], gy[-2]])            # derivative at s=0 wrt distance from junction
    d = d / (np.linalg.norm(d) + 1e-12)
    return d * direction                      # backward side: flip to travel direction


def _runs(m: np.ndarray):
    """Circular runs of True in a boolean array as (start, end) inclusive index pairs."""
    n = len(m)
    if m.all() or not m.any():
        return []
    starts = [i for i in range(n) if m[i] and not m[i - 1]]
    runs = []
    for s0 in starts:
        e = s0
        while m[(e + 1) % n]:
            e += 1
        runs.append((s0, e))
    return runs


def _angle(u: np.ndarray, v: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v), -1, 1))))


def _junctions(pts: np.ndarray, near: np.ndarray, frame: np.ndarray, m: int = 5, skip: int = 2):
    """Ends of each contact run along an outline: (point, corner angle in deg).
    Corner angle = angle between the outline tangents extrapolated from each side."""
    n = len(pts)
    out = []
    for s0, e in _runs(near & ~frame):
        if (e - s0) % n + 1 < 6:
            continue
        for t in ((s0 - 1) % n, e % n):
            u = (t + 1) % n
            if frame[t] or frame[u]:
                continue                       # cut by the image frame: no evidence
            ang = _angle(_side_tangent(pts, t, -1, m, skip), _side_tangent(pts, u, +1, m, skip))
            out.append(((pts[t] + pts[u]) / 2, ang))
    return out


def _occludes(jR, jO, reach: float = 8.0) -> float:
    """Mean over shared junctions of (R's corner angle - O's corner angle).
    At a T-junction the hidden shape's outline ends (big angle) while the occluder's flows
    on (small angle). Positive and large => O hides R. Antisymmetric, so side-by-side
    tiles (equal corners) and shapes lying on top both score <= 0."""
    diffs = []
    for p, a in jR:
        if not jO:
            break
        d = [np.linalg.norm(p - q) for q, _ in jO]
        i = int(np.argmin(d))
        if d[i] <= reach:
            diffs.append(a - jO[i][1])
    return float(np.mean(diffs)) if diffs else -999.0


def try_complete(R: Shape, C: list[Shape], H: int, W: int, cfg: Config) -> Completion | None:
    boxes = [R.sil.bbox] + [c.sil.bbox for c in C]
    y0 = max(min(b[0] for b in boxes) - 2, 0)
    x0 = max(min(b[1] for b in boxes) - 2, 0)
    y1 = min(max(b[2] for b in boxes) + 2, H)
    x1 = min(max(b[3] for b in boxes) + 2, W)
    shp, origin = (y1 - y0, x1 - x0), (x0, y0)

    Rm = _paste(R.sil, shp, origin)
    Cm = np.zeros(shp, bool)       # occluder silhouettes (incl. their children)
    Cv = np.zeros(shp, bool)       # occluder *visible* pixels only
    for c in C:
        Cm |= _paste(c.sil, shp, origin)
        Cv |= _paste(c.vis, shp, origin)
    cont = outer_contour(Rm)
    if cont is None or len(cont) < 12:
        return None
    cont = resample_closed(cont, 1.0)   # uniform spacing makes window sizes meaningful

    xi = np.clip(np.round(cont[:, 0]).astype(int), 0, shp[1] - 1)
    yi = np.clip(np.round(cont[:, 1]).astype(int), 0, shp[0] - 1)
    gx, gy = cont[:, 0] + x0, cont[:, 1] + y0
    frame = (gx <= -0.4) | (gy <= -0.4) | (gx >= W - 0.6) | (gy >= H - 0.6)

    # which neighbours really hide part of R? Compare outline flow at each shared junction.
    se = np.ones((3, 3), bool)
    Rn = ndi.binary_dilation(Rm, structure=se, iterations=2)
    real = []
    for c in C:
        Om = _paste(c.sil, shp, origin)
        oc = outer_contour(Om)
        if oc is None or len(oc) < 12:
            continue
        oc = resample_closed(oc, 1.0)
        ofr = ((oc[:, 0] + x0) <= -0.4) | ((oc[:, 1] + y0) <= -0.4) | \
              ((oc[:, 0] + x0) >= W - 0.6) | ((oc[:, 1] + y0) >= H - 0.6)
        oxi = np.clip(np.round(oc[:, 0]).astype(int), 0, shp[1] - 1)
        oyi = np.clip(np.round(oc[:, 1]).astype(int), 0, shp[0] - 1)
        On = ndi.binary_dilation(Om, structure=se, iterations=2)
        jR = _junctions(cont, On[yi, xi], frame)
        jO = _junctions(oc, Rn[oyi, oxi], ofr)
        if _occludes(jR, jO) >= 15.0:
            real.append(c)
    if not real:
        return None
    C = real
    Cm = np.zeros(shp, bool)
    Cv = np.zeros(shp, bool)
    for c in C:
        Cm |= _paste(c.sil, shp, origin)
        Cv |= _paste(c.vis, shp, origin)
    near = ndi.binary_dilation(Cm, structure=se, iterations=2)
    cls = np.where(frame, 1, np.where(near[yi, xi], 2, 0))
    n_occl, n_free = int((cls == 2).sum()), int((cls == 0).sum())
    if n_occl < 4 or n_free < max(10, 0.2 * len(cont)):
        return None
    F = cont[cls == 0]

    area = float(R.sil.area)
    tol = max(0.9, 1.5 * cfg.snap_tolerance * np.sqrt(area))
    min_extra = max(10, int(0.004 * area))

    def evaluate(P: np.ndarray, prim: Prim | None):
        P = P | Rm
        extra = P & ~Rm
        ne = int(extra.sum())
        if ne < min_extra:
            return None
        if (Rm & ~P).sum() > 0.03 * area:
            return None
        if int((extra & Cm).sum()) < 0.9 * ne or int((extra & Cv).sum()) < 0.7 * ne:
            return None
        if P.sum() > (8 if prim is not None else 4) * area:
            return None
        above = []
        for c in C:
            ov = int((extra & _paste(c.sil, shp, origin)).sum())
            if ov >= max(6, 0.08 * ne):
                above.append(c.id)
        if not above:
            return None
        ys, xs = np.nonzero(P)
        full = Mask(P[ys.min():ys.max() + 1, xs.min():xs.max() + 1], ys.min() + y0, xs.min() + x0)
        gp = None
        if prim is not None:
            gp = Prim(prim.kind, prim.cx + x0, prim.cy + y0, prim.rx, prim.ry, prim.angle, prim.r,
                      None if prim.pts is None else prim.pts + [x0, y0])
        return Completion(full=full, prim=gp, above=above, extra_px=ne)

    best: Completion | None = None
    r = fit_circle(F)
    if r[1] <= tol and r[2] >= np.deg2rad(100) and r[0].rx < 4 * max(H, W):
        best = evaluate(raster_prim(r[0], shp), r[0])
    if best is None and not cfg.snap_primitives is False:
        e = fit_ellipse(F)
        if e and e[1] <= tol and e[2] >= np.deg2rad(140) and max(e[0].rx, e[0].ry) < 4 * max(H, W):
            best = evaluate(raster_prim(e[0], shp), e[0])
    if best is None:
        q = fit_rect(F)
        if q and q[1] <= tol:
            best = evaluate(raster_prim(q[0], shp), q[0])
    if best is None:
        poly = _bridge(cont, cls)
        if poly is not None and len(poly) > 8:
            img = np.zeros(shp, np.uint8)
            cv2.fillPoly(img, [np.round(poly * SCALE).astype(np.int32)], 1, cv2.LINE_8, SHIFT)
            best = evaluate(img.astype(bool), None)
    return best
