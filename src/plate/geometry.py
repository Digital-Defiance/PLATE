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
