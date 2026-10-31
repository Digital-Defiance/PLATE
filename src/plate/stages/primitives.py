"""Stage 5: geometry (no AI). Replace a traced path with a true primitive when one fits.

A candidate is accepted when its mean boundary deviation (|xor| / perimeter, in px) is
below `snap_tolerance * sqrt(area)` (floor 0.7px). Order of preference, simplest first:
circle, ellipse, rectangle, rounded rectangle, polygon (<= 14 vertices).
"""
from __future__ import annotations

import cv2
import numpy as np

from ..config import Config
from ..geometry import (Prim, contours_xy, fit_circle, fit_ellipse, fit_rect, mean_deviation,
                        outer_contour, prim_polygon, raster_prim)
from ..masks import Mask


def normalize(pr: Prim) -> Prim:
    """Fold rotation into [0, 90) so axis-aligned shapes carry no transform."""
    if pr.kind in ("circle", "polygon"):
        return pr
    a = pr.angle % 180.0
    rx, ry = pr.rx, pr.ry
    if a >= 90.0:
        a -= 90.0
        rx, ry = ry, rx
    if a > 89.75:            # essentially a quarter turn: axes swap, no rotation
        a = 0.0
        rx, ry = ry, rx
    elif a < 0.25:
        a = 0.0
    pr.angle, pr.rx, pr.ry = a, rx, ry
    return pr


def _full_primitive_deviation(mask: np.ndarray, pr: Prim) -> float:
    """Measure the entire candidate, including parts outside the source crop.

    A fitted ellipse can be much wider than a rectangle and still resemble it
    when rasterized into that rectangle's bounding box. Comparing that clipped
    raster hides the added area that would appear in the emitted SVG.
    """
    if pr.kind in ("circle", "ellipse"):
        rx, ry = pr.rx, pr.rx if pr.kind == "circle" else pr.ry
        angle = np.deg2rad(pr.angle if pr.kind == "ellipse" else 0)
        dx = np.hypot(rx * np.cos(angle), ry * np.sin(angle))
        dy = np.hypot(rx * np.sin(angle), ry * np.cos(angle))
        bounds = np.array([pr.cx - dx, pr.cy - dy, pr.cx + dx, pr.cy + dy])
    else:
        points = prim_polygon(pr)
        bounds = np.r_[points.min(axis=0), points.max(axis=0)]
    if not np.isfinite(bounds).all():
        return float("inf")
    h, w = mask.shape
    x0, y0 = min(0, int(np.floor(bounds[0])) - 1), min(0, int(np.floor(bounds[1])) - 1)
    x1, y1 = max(w, int(np.ceil(bounds[2])) + 2), max(h, int(np.ceil(bounds[3])) + 2)
    # Snapping fits a complete silhouette, not an occluded fragment. Reject
    # degenerate fits before allocating an arbitrarily large comparison raster.
    if x1 - x0 > 2 * w or y1 - y0 > 2 * h:
        return float("inf")
    reference = np.pad(mask, ((-y0, y1 - h), (-x0, x1 - w)))
    candidate = raster_prim(pr, reference.shape, origin=(x0, y0))
    return mean_deviation(reference, candidate)


def snap(mask: Mask, cfg: Config) -> Prim | None:
    if mask.empty():
        return None
    if mask.area < 30:
        # Too few pixels to fit reliably, but a mask that fills its whole bounding box
        # IS exactly an axis-aligned rectangle (a tiny icon, a 1x1 image). Emit that
        # instead of letting the blurred contour tracer turn it into a stray lens.
        # One-pixel-wide survivors of speckle filtering are almost always antialias
        # fringes between shapes; keep dropping those (except a whole 1x1 image).
        h, w = mask.a.shape
        if mask.a.all() and (min(h, w) >= 2 or mask.area == 1):
            rect = Prim("rect", mask.x0 + (w - 1) / 2, mask.y0 + (h - 1) / 2, w / 2, h / 2)
            # A tiny filled blob can still be a genuine circle/ellipse (e.g. a small
            # route marker). Try fitting one with the SAME gates used on the normal
            # path, and prefer it only when it strictly beats the full-bbox rect on
            # full-primitive deviation (so ambiguous solid squares stay rects).
            tpad = 3
            ta = np.pad(mask.a, tpad)
            tconts = [c for c in contours_xy(ta) if len(c) >= 8]
            if len(tconts) == 1:
                tc = tconts[0]
                ttol = max(0.7, cfg.snap_tolerance * np.sqrt(float(mask.area)))
                # Rect in padded-array-local coords, for a like-for-like deviation compare.
                lrect = Prim("rect", tpad + (w - 1) / 2, tpad + (h - 1) / 2, w / 2, h / 2)
                rect_dev = _full_primitive_deviation(ta, lrect)
                pc, _rms, cov = fit_circle(tc)
                cand = None
                if cov > 5.5:
                    dev = _full_primitive_deviation(ta, pc)
                    if dev <= ttol and dev < rect_dev:
                        cand = pc
                if cand is None:
                    e = fit_ellipse(tc)
                    if e and e[2] > 5.5:
                        dev = _full_primitive_deviation(ta, e[0])
                        if dev <= ttol and dev < rect_dev:
                            cand = e[0]
                if cand is not None:
                    cand.cx += mask.x0 - tpad
                    cand.cy += mask.y0 - tpad
                    return normalize(cand)
            return rect
        return None
    pad = 3
    a = np.pad(mask.a, pad)
    conts = contours_xy(a)
    big = [c for c in conts if len(c) >= 8]
    if len(big) != 1:          # holes or fragments -> leave as a compound path
        return None
    c = big[0]
    area = float(mask.area)
    tol = max(0.7, cfg.snap_tolerance * np.sqrt(area))
    def ok(pr: Prim, strict: float = 1.0) -> bool:
        return _full_primitive_deviation(a, pr) <= tol * strict

    def finish(pr: Prim) -> Prim:
        pr.cx += mask.x0 - pad
        pr.cy += mask.y0 - pad
        if pr.pts is not None:
            pr.pts = pr.pts + [mask.x0 - pad, mask.y0 - pad]
        return normalize(pr)

    pc, rms, cov = fit_circle(c)
    if cov > 5.5 and ok(pc):
        return finish(pc)
    e = fit_ellipse(c)
    if e and e[2] > 5.5 and ok(e[0]):
        return finish(e[0])
    r = fit_rect(c)
    if r:
        pr = r[0]
        if ok(pr):
            return finish(pr)
        deficit = 4 * pr.rx * pr.ry - area
        if deficit > 0:
            rad = float(np.sqrt(deficit / (4 - np.pi)))
            if 1.5 <= rad <= min(pr.rx, pr.ry):
                rr = Prim("rrect", pr.cx, pr.cy, pr.rx, pr.ry, pr.angle, rad)
                if ok(rr):
                    return finish(rr)
    cf = c.astype(np.float32).reshape(-1, 1, 2)
    best = None
    for eps in np.geomspace(max(0.8, tol * 0.5), max(2.0, tol * 4.0), 10):
        pts = cv2.approxPolyDP(cf, float(eps), True).reshape(-1, 2).astype(float)
        if not 3 <= len(pts) <= 14:
            continue
        pg = Prim("polygon", pts=pts)
        if ok(pg, 0.45) and (best is None or len(pts) < len(best.pts)):
            best = pg
    if best is not None:
        return finish(best)
    return None


def snap_ring(mask: Mask, cfg: Config):
    """Annulus: exactly two contours, both circles -> [(cx, cy, r) outer, (cx, cy, r) hole]
    in mask-global pixel-centre coords, else None."""
    if mask.empty() or mask.area < 60:
        return None
    pad = 3
    a = np.pad(mask.a, pad)
    conts = [c for c in contours_xy(a) if len(c) >= 8]
    if len(conts) != 2:
        return None
    out = []
    for c in conts:
        pc, rms, cov = fit_circle(c)
        if cov < 5.5 or rms > max(0.7, cfg.snap_tolerance * np.sqrt(len(c)) * 2):
            return None
        out.append(pc)
    out.sort(key=lambda p: -p.rx)
    full = raster_prim(out[0], a.shape) & ~raster_prim(out[1], a.shape)
    tol = max(0.7, cfg.snap_tolerance * np.sqrt(mask.area))
    if mean_deviation(a, full) > tol:
        return None
    return [(p.cx + mask.x0 - pad, p.cy + mask.y0 - pad, p.rx) for p in out]
