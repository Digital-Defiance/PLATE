"""Primitive fitting and rasterisation.

Conventions: points are (x, y) in *pixel-centre* coordinates (pixel i sits at integer i).
`skimage.measure.find_contours(mask, 0.5)` yields contours in this convention, and
OpenCV's drawing calls use the same one, so fits and rasters agree. The SVG emitter
adds the +0.5 shift to reach SVG's pixel-corner convention.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from skimage import measure

SHIFT = 4
SCALE = 1 << SHIFT


@dataclass
class Prim:
    kind: str                    # circle | ellipse | rect | rrect | polygon
    cx: float = 0.0
    cy: float = 0.0
    rx: float = 0.0              # circle: radius; ellipse: semi-axis; rect/rrect: half width
    ry: float = 0.0              # ellipse: semi-axis; rect/rrect: half height
    angle: float = 0.0           # degrees, rotation of the rx axis
    r: float = 0.0               # rrect corner radius
    pts: np.ndarray | None = None  # polygon vertices (n, 2)

    def inflated(self, d: float) -> "Prim":
        if self.kind == "polygon":
            return self
        if self.kind == "circle":
            return replace(self, rx=self.rx + d, ry=self.rx + d)
        return replace(self, rx=self.rx + d, ry=self.ry + d, r=self.r + d if self.kind == "rrect" else 0)


@dataclass
class GradientStop:
    offset: float                    # 0..1 along the gradient axis
    rgb: tuple[int, int, int]


@dataclass
class GradientFill:
    kind: str                        # "linear" | "radial"
    stops: list[GradientStop]
    # linear geometry (working pixel-centre coords; SVG coords after _convert_grad):
    start: tuple[float, float] | None = None   # (x, y)
    end: tuple[float, float] | None = None     # (x, y)
    # radial geometry:
    center: tuple[float, float] | None = None  # (cx, cy)
    radius: float | None = None
    focal: tuple[float, float] | None = None   # (fx, fy), optional, None in v1


def contours_xy(mask: np.ndarray, level: float = 0.5) -> list[np.ndarray]:
    """Sub-pixel contours of a boolean mask as (x, y) arrays (padded so shapes touching
    the array edge still close)."""
    pad = np.pad(mask.astype(np.float32), 1)
    out = []
    for c in measure.find_contours(pad, level):
        out.append(np.c_[c[:, 1] - 1.0, c[:, 0] - 1.0])
    return out


def outer_contour(mask: np.ndarray) -> np.ndarray | None:
    cs = contours_xy(mask)
    if not cs:
        return None
    return max(cs, key=lambda c: abs(poly_area(c)))


def poly_area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


# ----------------------------------------------------------------------------- fits
def angular_coverage(angles: np.ndarray) -> float:
    """Radians of the circle spanned by the samples (2*pi minus the largest gap)."""
    a = np.sort(np.mod(angles, 2 * np.pi))
    if a.size < 2:
        return 0.0
    gaps = np.diff(np.r_[a, a[0] + 2 * np.pi])
    return float(2 * np.pi - gaps.max())


def fit_circle(p: np.ndarray):
    x, y = p[:, 0], p[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    sol = np.linalg.lstsq(A, x * x + y * y, rcond=None)[0]
    cx, cy = sol[0], sol[1]
    r = float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 1e-9)))
    res = least_squares(lambda q: np.hypot(x - q[0], y - q[1]) - q[2], [cx, cy, r])
    cx, cy, r = res.x
    rms = float(np.sqrt(np.mean(res.fun ** 2)))
    cov = angular_coverage(np.arctan2(y - cy, x - cx))
    return Prim("circle", cx, cy, rx=abs(r), ry=abs(r)), rms, cov


def _ellipse_samples(pr: Prim, n: int = 720) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    th = np.deg2rad(pr.angle)
    ex, ey = pr.rx * np.cos(t), pr.ry * np.sin(t)
    return np.c_[pr.cx + ex * np.cos(th) - ey * np.sin(th), pr.cy + ex * np.sin(th) + ey * np.cos(th)]


def fit_ellipse(p: np.ndarray):
    if len(p) < 6:
        return None
    (cx, cy), (w, h), ang = cv2.fitEllipse(p.astype(np.float32))
    pr = Prim("ellipse", cx, cy, rx=w / 2, ry=h / 2, angle=ang)
    if pr.rx < 0.5 or pr.ry < 0.5:
        return None
    d, _ = cKDTree(_ellipse_samples(pr)).query(p)
    th = np.deg2rad(ang)
    lx = (p[:, 0] - cx) * np.cos(th) + (p[:, 1] - cy) * np.sin(th)
    ly = -(p[:, 0] - cx) * np.sin(th) + (p[:, 1] - cy) * np.cos(th)
    cov = angular_coverage(np.arctan2(ly / pr.ry, lx / pr.rx))
    return pr, float(np.sqrt(np.mean(d ** 2))), cov


def fit_rect(p: np.ndarray):
    """Rectangle via minAreaRect, then refined: each side is moved to the *median* of the
    contour points that belong to it, so isolated stray pixels can't push edges around."""
    if len(p) < 4:
        return None
    (cx, cy), (w, h), ang = cv2.minAreaRect(p.astype(np.float32))
    if w < 1 or h < 1:
        return None
    for _ in range(3):
        th = np.deg2rad(ang)
        c, s = np.cos(th), np.sin(th)
        lx = (p[:, 0] - cx) * c + (p[:, 1] - cy) * s
        ly = -(p[:, 0] - cx) * s + (p[:, 1] - cy) * c
        d = np.stack([np.abs(lx - w / 2), np.abs(lx + w / 2), np.abs(ly - h / 2), np.abs(ly + h / 2)], 1)
        side, near = d.argmin(1), d.min(1) < max(2.0, 0.08 * min(w, h))
        sel = [near & (side == k) for k in range(4)]
        if min(m.sum() for m in sel) < 3:
            break
        xr, xl = np.median(lx[sel[0]]), np.median(lx[sel[1]])
        yt, yb = np.median(ly[sel[2]]), np.median(ly[sel[3]])
        ncx, ncy = (xr + xl) / 2, (yt + yb) / 2
        w, h = xr - xl, yt - yb
        cx, cy = cx + ncx * c - ncy * s, cy + ncx * s + ncy * c
    pr = Prim("rect", cx, cy, rx=w / 2, ry=h / 2, angle=ang)
    th = np.deg2rad(ang)
    lx = (p[:, 0] - cx) * np.cos(th) + (p[:, 1] - cy) * np.sin(th)
    ly = -(p[:, 0] - cx) * np.sin(th) + (p[:, 1] - cy) * np.cos(th)
    dd = np.abs(np.maximum(np.abs(lx) - pr.rx, np.abs(ly) - pr.ry))
    return pr, float(np.sqrt(np.mean(dd ** 2)))


# ----------------------------------------------------------------------- rasterise
def _rrect_poly(pr: Prim) -> np.ndarray:
    r = max(min(pr.r, pr.rx, pr.ry), 0.0)
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ccx, ccy = sx * (pr.rx - r), sy * (pr.ry - r)
        for a in np.linspace(a0, a0 + 90, 12):
            pts.append((ccx + r * np.cos(np.deg2rad(a)), ccy + r * np.sin(np.deg2rad(a))))
    pts = np.array(pts)
    th = np.deg2rad(pr.angle)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return pts @ R.T + [pr.cx, pr.cy]


def prim_polygon(pr: Prim) -> np.ndarray:
    """Vertex list describing the primitive (used for rasterising and for emitting)."""
    if pr.kind == "polygon":
        return pr.pts
    if pr.kind in ("circle", "ellipse"):
        return _ellipse_samples(pr, 180)
    if pr.kind == "rect":
        return cv2.boxPoints(((pr.cx, pr.cy), (2 * pr.rx, 2 * pr.ry), pr.angle))
    return _rrect_poly(pr)


def raster_prim(pr: Prim, shape: tuple[int, int], origin: tuple[int, int] = (0, 0)) -> np.ndarray:
    """Rasterise at sub-pixel precision into an (h, w) bool array; origin = (x0, y0)."""
    img = np.zeros(shape, np.uint8)
    ox, oy = origin
    if pr.kind == "circle":
        cv2.circle(img, (round((pr.cx - ox) * SCALE), round((pr.cy - oy) * SCALE)),
                   round(pr.rx * SCALE), 1, -1, cv2.LINE_8, SHIFT)
    elif pr.kind == "ellipse":
        cv2.ellipse(img, (round((pr.cx - ox) * SCALE), round((pr.cy - oy) * SCALE)),
                    (round(pr.rx * SCALE), round(pr.ry * SCALE)), pr.angle, 0, 360, 1, -1,
                    cv2.LINE_8, SHIFT)
    else:
        poly = prim_polygon(pr) - [ox, oy]
        cv2.fillPoly(img, [np.round(poly * SCALE).astype(np.int32)], 1, cv2.LINE_8, SHIFT)
    return img.astype(bool)


def mean_deviation(mask: np.ndarray, cand: np.ndarray) -> float:
    """Mean boundary deviation in px: |xor| / perimeter."""
    xor = int((mask ^ cand).sum())
    per = int((mask & ~cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)).sum())
    return xor / max(per, 1)


# ----------------------------------------------------------------- gradient fits
# Number of gradient stops EMITTED is fixed at GRAD_STOPS regardless of how many
# source bands a region had: we bin the per-pixel axis parameter u in [0,1] into
# GRAD_STOPS equal-width bins and take each non-empty bin's mean colour as a stop.
# This makes the emitted stop list well-defined for ANY admitted region (a region
# with the minimum bands and one with hundreds of bands both yield a valid,
# correctly-ordered <=GRAD_STOPS stop list). The minimum-bands admission gate
# (grad_min_bands) lives in stages/gradient.py and is INDEPENDENT of GRAD_STOPS:
# it counts *source* flat bands before fitting, while GRAD_STOPS counts *emitted*
# stops sampled from the fitted curve. The two numbers never need to match.
GRAD_STOPS = 7


def _luma(C: np.ndarray) -> np.ndarray:
    """Rec.601 luma of an (n, 3) float rgb array in 0..255 (inline, no segment import)."""
    return 0.299 * C[:, 0] + 0.587 * C[:, 1] + 0.114 * C[:, 2]


def _binned_stops(u: np.ndarray, C: np.ndarray):
    """Piecewise-linear stop curve from GRAD_STOPS equal-width bins over u in [0,1].

    Returns (offsets, colours, residual):
      offsets  : (m,) empirical pixel-mean u of each non-empty bin, sorted ascending
      colours  : (m, 3) mean rgb of each non-empty bin
      residual : RMS over all pixels of ||C - curve(u)|| / 255 (channel-averaged),
                 measured against the UNCLAMPED empirical offsets.
    """
    b = np.clip(np.floor(u * GRAD_STOPS).astype(int), 0, GRAD_STOPS - 1)
    offs, cols = [], []
    for k in range(GRAD_STOPS):
        m = b == k
        if not m.any():
            continue
        offs.append(float(u[m].mean()))
        cols.append(C[m].mean(axis=0))
    if not offs:
        return None
    offs = np.asarray(offs, float)
    cols = np.asarray(cols, float)
    order = np.argsort(offs)
    offs, cols = offs[order], cols[order]
    # residual against the piecewise-linear interpolation at empirical offsets
    pred = np.empty_like(C)
    for c in range(3):
        pred[:, c] = np.interp(u, offs, cols[:, c])
    residual = float(np.sqrt(np.mean((C - pred) ** 2)) / 255.0)
    return offs, cols, residual


def _stopcurve_eval(offs: np.ndarray, cols: np.ndarray, t: float) -> np.ndarray:
    """Interpolate the piecewise stop curve at a single parameter t in [0,1]."""
    return np.array([np.interp(t, offs, cols[:, c]) for c in range(3)])


def _finalize_stops(offs: np.ndarray, cols: np.ndarray) -> list[GradientStop]:
    """Cosmetic post-processing (runs AFTER the residual is computed): clamp the
    extreme offsets to exactly 0/1 so the gradient spans the full axis, then collapse
    consecutive near-identical stops (rgb delta < 2) to keep the SVG small."""
    offs = offs.copy()
    offs[0] = 0.0
    offs[-1] = 1.0
    stops: list[GradientStop] = []
    for o, c in zip(offs, cols):
        rgb = tuple(int(round(v)) for v in c)
        if stops and abs(stops[-1].offset - o) < 1e-9:
            continue
        if stops:
            pr, pg, pb = stops[-1].rgb
            if abs(pr - rgb[0]) + abs(pg - rgb[1]) + abs(pb - rgb[2]) < 2:
                continue
        stops.append(GradientStop(offset=float(o), rgb=rgb))
    if len(stops) < 2:                       # degenerate: force the two endpoints
        stops = [GradientStop(0.0, tuple(int(round(v)) for v in cols[0])),
                 GradientStop(1.0, tuple(int(round(v)) for v in cols[-1]))]
    return stops


def fit_linear_gradient(P: np.ndarray, C: np.ndarray) -> tuple["GradientFill", float]:
    """Fit a linear colour ramp. P=(n,2) pixel-centre coords, C=(n,3) rgb in 0..255.
    Returns (GradientFill, normalized_residual); residual inf when degenerate."""
    inf = (GradientFill("linear", []), float("inf"))
    if len(P) < 3:
        return inf
    mean_p = P.mean(axis=0)
    Q = P - mean_p
    L = _luma(C)
    Lh = L - L.mean()
    G = Q.T @ Q                               # 2x2
    det = G[0, 0] * G[1, 1] - G[0, 1] * G[1, 0]
    if abs(det) < 1e-6:
        return inf
    u_raw = np.linalg.solve(G, Q.T @ Lh)
    nrm = float(np.hypot(u_raw[0], u_raw[1]))
    if nrm < 1e-9:
        return inf
    u = u_raw / nrm
    t = Q @ u
    span = float(t.max() - t.min())
    if span < 1e-9:
        return inf
    th = (t - t.min()) / span
    binned = _binned_stops(th, C)
    if binned is None:
        return inf
    offs, cols, residual = binned
    start = tuple(mean_p + u * t.min())
    end = tuple(mean_p + u * t.max())
    stops = _finalize_stops(offs, cols)
    grad = GradientFill("linear", stops, start=(float(start[0]), float(start[1])),
                        end=(float(end[0]), float(end[1])))
    return grad, residual


def _radial_residual_vec(center: np.ndarray, P: np.ndarray, Lh: np.ndarray) -> np.ndarray:
    """Per-pixel VECTOR residual for the radial-centre search: observed (centred) luma
    minus a least-squares affine prediction from the normalized radius at `center`.
    least_squares needs a vector with Jacobian structure, NOT a scalar (must-fix #2)."""
    rho = np.hypot(P[:, 0] - center[0], P[:, 1] - center[1])
    rmax = float(rho.max())
    if rmax < 1e-9:
        return Lh
    rho = rho / rmax
    # best affine fit luma ~= a + b*rho (closed form), residual = observed - predicted
    A = np.c_[np.ones_like(rho), rho]
    coef, *_ = np.linalg.lstsq(A, Lh, rcond=None)
    return Lh - A @ coef


def fit_radial_gradient(P: np.ndarray, C: np.ndarray) -> tuple["GradientFill", float]:
    """Fit a radial colour ramp. P=(n,2) pixel-centre coords, C=(n,3) rgb in 0..255.
    Centre is seeded from lightness-weighted top/bottom decile centroids and refined
    with a bounded least_squares on a PER-PIXEL vector residual (must-fix #2).
    Returns (GradientFill, normalized_residual); residual inf when degenerate."""
    inf = (GradientFill("radial", []), float("inf"))
    if len(P) < 3:
        return inf
    L = _luma(C)
    Lh = L - L.mean()
    lo, hi = np.percentile(L, 10), np.percentile(L, 90)

    def _centroid(select, weight):
        if not select.any():
            return P.mean(axis=0)
        w = np.clip(weight[select], 1e-6, None)
        return np.array([np.sum(w * P[select, 0]) / w.sum(),
                         np.sum(w * P[select, 1]) / w.sum()])

    top = L >= hi                              # bright centre candidate
    bot = L <= lo                              # dark centre candidate
    cand = [_centroid(top, L - L.min()), _centroid(bot, L.max() - L)]

    best = None
    for c0 in cand:
        try:
            sol = least_squares(_radial_residual_vec, c0, args=(P, Lh), max_nfev=30)
            center = sol.x
        except Exception:                      # noqa: BLE001 - solver blow-up -> skip
            center = c0
        rho = np.hypot(P[:, 0] - center[0], P[:, 1] - center[1])
        rmax = float(rho.max())
        if rmax < 1.0:
            continue
        rho_hat = rho / rmax
        binned = _binned_stops(rho_hat, C)
        if binned is None:
            continue
        offs, cols, residual = binned
        if best is None or residual < best[0]:
            best = (residual, center, rmax, offs, cols)
    if best is None:
        return inf
    residual, center, rmax, offs, cols = best
    stops = _finalize_stops(offs, cols)
    grad = GradientFill("radial", stops, center=(float(center[0]), float(center[1])),
                        radius=float(rmax))
    return grad, residual
