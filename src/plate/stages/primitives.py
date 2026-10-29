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
                        outer_contour, raster_prim)
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


def snap(mask: Mask, cfg: Config) -> Prim | None:
    if mask.empty() or mask.area < 30:
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
    shape = a.shape

    def ok(pr: Prim, strict: float = 1.0) -> bool:
        return mean_deviation(a, raster_prim(pr, shape)) <= tol * strict

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
