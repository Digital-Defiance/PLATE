"""Stage 4: mask -> smooth, minimal-anchor Bezier path data.

Pipeline per mask: edge-replicate at the frame -> light Gaussian blur -> sub-pixel
marching squares at 0.5 -> corner detection / Schneider fit (see bezier.py).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi

from ..bezier import contour_to_beziers, is_flat
from ..config import Config
from ..geometry import contours_xy, fit_circle, poly_area
from ..masks import Mask


def mask_contours(mask: Mask, canvas: tuple[int, int], sigma: float) -> list[np.ndarray]:
    """Sub-pixel contours (x, y; pixel-centre coords) clamped to the canvas frame."""
    H, W = canvas
    pad = int(np.ceil(3 * sigma)) + 3
    wy0, wx0 = mask.y0 - pad, mask.x0 - pad
    h, w = mask.a.shape
    win = np.zeros((h + 2 * pad, w + 2 * pad), np.float32)
    win[pad:pad + h, pad:pad + w] = mask.a
    # shapes touching the frame must keep going past it so the blur doesn't pull edges inward
    for side, cond in (("t", mask.y0 <= 0), ("l", mask.x0 <= 0),
                       ("b", mask.y0 + h >= H), ("r", mask.x0 + w >= W)):
        if not cond:
            continue
        if side == "t":
            win[:pad, :] = win[pad:pad + 1, :]
        elif side == "b":
            win[pad + h:, :] = win[pad + h - 1:pad + h, :]
        elif side == "l":
            win[:, :pad] = win[:, pad:pad + 1]
        else:
            win[:, pad + w:] = win[:, pad + w - 1:pad + w]
    if sigma > 0:
        win = ndi.gaussian_filter(win, sigma)
    out = []
    for c in contours_xy(win, 0.5):
        c = c + [wx0, wy0]
        c[:, 0] = np.clip(c[:, 0], -0.5, W - 0.5)
        c[:, 1] = np.clip(c[:, 1], -0.5, H - 0.5)
        if len(c) >= 8 and abs(poly_area(c)) >= 4:
            out.append(c)
    return out


def _fmt(v: float, prec: int) -> str:
    s = f"{v:.{prec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def mask_to_path(mask: Mask, canvas: tuple[int, int], cfg: Config, scale: float):
    """Returns (d, anchor_count, evenodd). Coordinates in SVG (source-image) units."""
    sigma = max(cfg.smooth * scale, 0.45)
    tol = max(cfg.simplify * scale, 0.15)
    conts = mask_contours(mask, canvas, sigma)
    prec = cfg.path_precision

    def P(p):
        return f"{_fmt((p[0] + 0.5) / scale, prec)} {_fmt((p[1] + 0.5) / scale, prec)}"

    # The largest contour is the outer silhouette; the rest are holes. A hole that
    # is a near-perfect circle (a punched round perforation) is far more compact and
    # more editable as two SVG arcs (4 anchors) than a long Bézier chain, and stays
    # exactly round under resize. Snap only interior holes, only on a tight circle
    # fit, so non-circular holes and the outer contour keep their Bézier tracing.
    outer_idx = max(range(len(conts)), key=lambda i: abs(poly_area(conts[i]))) if conts else -1
    hole_tol = max(0.35 * scale, 0.4)

    def circle_arc(c):
        if len(c) < 24:
            return None
        pr, rms, cov = fit_circle(c)
        if rms > hole_tol or cov < 6.1 or pr.rx < 2:  # ~350deg coverage, real radius
            return None
        x, y, rr = (pr.cx + 0.5) / scale, (pr.cy + 0.5) / scale, pr.rx / scale
        f = lambda v: _fmt(v, prec)
        return (f"M{f(x - rr)} {f(y)}A{f(rr)} {f(rr)} 0 1 0 {f(x + rr)} {f(y)}"
                f"A{f(rr)} {f(rr)} 0 1 0 {f(x - rr)} {f(y)}Z")

    d, anchors = [], 0
    for i, c in enumerate(conts):
        if i != outer_idx:
            arc = circle_arc(c)
            if arc is not None:
                d.append(arc)
                anchors += 4
                continue
        res = contour_to_beziers(c, tol, cfg.corner_threshold)
        if res is None:
            continue
        start, curves = res
        if not curves:
            continue
        d.append("M" + P(start))
        for cu in curves:
            if is_flat(cu):
                d.append("L" + P(cu[3]))
            else:
                d.append("C" + P(cu[1]) + " " + P(cu[2]) + " " + P(cu[3]))
            anchors += 1
        d.append("Z")
    return "".join(d), anchors, len(conts) > 1
