"""Stage 3: amodal completion.

For a shape R that touches siblings C, decide whether R is partly hidden behind them and,
if so, reconstruct its full silhouette:

 1. Take R's external contours. Points near C are "occluded", points on the image frame are
    "frame", the rest are "free".
 2. Fit exact primitives (circle, ellipse, rectangle) to the free points.
 3. Otherwise bridge each occluded gap with a cubic Bezier that continues the tangents.
 4. Accept only if the reconstruction (a) still contains R, and (b) the area it adds lies
    inside the shapes we claim are hiding it. This test is what keeps tiles that merely sit
    side by side from being "completed" into each other.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import cv2
import numpy as np
from scipy import ndimage as ndi

from ..bezier import bez, resample_closed
from ..config import Config
from ..geometry import (
    SCALE,
    SHIFT,
    Prim,
    contours_xy,
    fit_circle,
    fit_ellipse,
    fit_rect,
    poly_area,
    raster_prim,
)
from ..masks import Mask, crop_like
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


def _fit_line(Q: np.ndarray):
    """Total-least-squares line through points Q: returns (centroid, unit direction)."""
    c = Q.mean(axis=0)
    _, _, vt = np.linalg.svd(Q - c)
    return c, vt[0]


def _line_dev(Q: np.ndarray, c: np.ndarray, d: np.ndarray) -> float:
    """Max perpendicular deviation of Q from the line (c, d)."""
    nrm = np.array([-d[1], d[0]])
    return float(np.abs((Q - c) @ nrm).max())


def _intersect(c1, d1, c2, d2):
    """Intersection of lines (c1,d1) and (c2,d2); None if near-parallel."""
    A = np.array([d1, -d2]).T
    det = A[0, 0] * A[1, 1] - A[0, 1] * A[1, 0]
    if abs(det) < 1e-6:
        return None
    s = np.linalg.solve(A, c2 - c1)
    return c1 + d1 * s[0]


def _split_straight(seg: np.ndarray, tol: float, min_len: int):
    """Split an ordered polyline into maximal near-straight runs and fit a line to each.

    A corner is where the outline direction changes sharply. We estimate a smoothed local
    direction with a fixed window and mark break points where it turns past a threshold; the
    spans between break points are the straight edges. This is O(n) and robust to the gently-
    rounded corners the pointwise angle test misses. Returns (centroid, unit_dir, start, end)
    for runs long and straight enough to anchor a line."""
    n = len(seg)
    if n < min_len:
        return []
    k = 5
    # turning angle at each interior point: angle between the backward and forward chords over
    # a +/-k window (same idea as find_corners), which reads a full corner as one sharp peak.
    turn = np.zeros(n)
    for t in range(k, n - k):
        a = seg[t] - seg[t - k]
        b = seg[t + k] - seg[t]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-6 or nb < 1e-6:
            continue
        turn[t] = np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1, 1)))
    # corner = local maximum of turning above threshold, suppressed within +/-k of a stronger one
    thr = 32.0
    cand = np.flatnonzero(turn >= thr)
    corners = []
    for i in cand:
        lo, hi = max(i - k, 0), min(i + k + 1, n)
        if turn[i] >= turn[lo:hi].max() - 1e-9 and all(abs(i - c) > k for c in corners):
            corners.append(int(i))
    breaks = [0] + corners + [n]
    out = []
    for a, b in itertools.pairwise(breaks):
        _emit_run(out, seg[a:b + 1] if b < n else seg[a:b], min_len, tol)
    return out


def _emit_run(runs: list, seg: np.ndarray, min_len: int, tol: float = 1.4):
    if len(seg) < min_len:
        return
    trim = 2 if len(seg) >= min_len + 4 else 0
    Q = seg[trim:len(seg) - trim] if trim else seg
    if len(Q) < 4:
        Q = seg
    c, d = _fit_line(Q)
    span = float(np.linalg.norm(Q[-1] - Q[0]))
    dev = _line_dev(Q, c, d)
    if span < 8.0 or dev > max(tol, 0.04 * span):
        return
    runs.append((c, d, Q[0], Q[-1]))


def _free_edge_runs(pts: np.ndarray, cls: np.ndarray, min_len: int = 6):
    """Partition the ordered contour's FREE portions into near-straight edges of a rectilinear
    shape. Each free run (a maximal span of cls==0 points between occluded gaps) is split into
    straight edges by an incremental line fit, so a run covering several visible edges with
    gently-rounded corners still yields one straight line per edge. Returns the edges as
    (centroid, unit_dir, start, end) in contour order; a gap between consecutive edges is an
    occluded (hidden) corner to be reconstructed by intersection."""
    n = len(pts)
    free = cls == 0
    if not free.any() or free.all() or n < 12:
        return []
    start = int(np.flatnonzero(~free)[0])    # rotate so a gap boundary is index 0
    rp = np.roll(pts, -start, axis=0)
    rf = np.roll(free, -start)
    runs = []
    i = 0
    while i < n:
        if not rf[i]:
            i += 1
            continue
        j = i
        while j < n and rf[j]:
            j += 1
        seg = rp[i:j]
        if len(seg) >= min_len:
            runs.extend(_split_straight(seg, tol=1.4, min_len=min_len))
        i = j
    return runs


def _merge_collinear(runs: list):
    """Merge consecutive free edges that are nearly collinear (same direction and lying on the
    same line) into one edge, so a single visible edge broken into fragments by contour noise
    does not create spurious short edges / false corners."""
    if len(runs) < 2:
        return runs
    out = list(runs)
    changed = True
    while changed and len(out) > 1:
        changed = False
        merged = []
        i = 0
        while i < len(out):
            if i + 1 < len(out):
                c1, d1, s1, e1 = out[i]
                c2, d2, s2, e2 = out[i + 1]
                nrm1 = np.array([-d1[1], d1[0]])
                if abs(np.dot(d1, d2)) > 0.985 and abs(np.dot(c2 - c1, nrm1)) < 1.6:
                    Q = np.array([s1, e1, s2, e2])
                    c, d = _fit_line(Q)
                    # endpoints farthest apart along the merged line
                    t = (Q - c) @ d
                    merged.append((c, d, Q[t.argmin()], Q[t.argmax()]))
                    i += 2
                    changed = True
                    continue
            merged.append(out[i])
            i += 1
        out = merged
    return out


def _free_edge_polygon(pts: np.ndarray, cls: np.ndarray):
    """Reconstruct a closed rectilinear polygon from partly-hidden free edges by extending
    the straight free edges and intersecting adjacent non-parallel ones to recover the hidden
    corners. Returns the polygon vertices (m, 2) or None when the free edges are too few /
    too occluded / ambiguous to determine the corners uniquely (R2 residual, state (b))."""
    runs = _free_edge_runs(pts, cls)
    runs = _merge_collinear(runs)
    if len(runs) < 2:
        return None
    verts = []
    bridged = 0
    m = len(runs)
    for i in range(m):
        c1, d1, s1, e1 = runs[i]
        c2, d2, s2, e2 = runs[(i + 1) % m]
        verts.append(s1)
        verts.append(e1)
        if abs(np.dot(d1, d2)) > 0.985:          # near-parallel: no unique corner
            continue
        x = _intersect(c1, d1, c2, d2)
        if x is None:
            continue
        # The reconstructed corner must be a forward continuation of both edges and lie within
        # a bounded reach of the gap ends, so a spurious far crossing (e.g. two edges that
        # actually belong to opposite sides of a long shape) is not invented as a corner.
        len1, len2 = np.linalg.norm(e1 - s1), np.linalg.norm(e2 - s2)
        reach = 1.5 * (len1 + len2) + 10.0
        gap = np.linalg.norm(s2 - e1)
        if np.linalg.norm(x - e1) <= reach and np.linalg.norm(x - s2) <= reach \
                and np.linalg.norm(x - e1) <= gap + reach:
            verts.append(x)
            bridged += 1
    if bridged == 0:                              # nothing reconstructed: not a completion
        return None
    out = [verts[0]]
    for v in verts[1:]:
        if np.linalg.norm(v - out[-1]) > 1e-6:
            out.append(v)
    poly = np.array(out, float)
    return poly if len(poly) >= 3 else None


def _free_edge_quad(pts: np.ndarray, cls: np.ndarray):
    """Reconstruct a quadrilateral (rect / rrect / rotated rect) from the free edges: group the
    straight free edges into two near-orthogonal direction families, fit one line to each of the
    four sides (the two extreme lines per family) and intersect them to get four clean corners.

    This is far more robust than chaining endpoints for a four-sided shape whose hidden corner(s)
    are behind an occluder, because each side line is fit from ALL its free points (both before
    and after the occluded gap) and the corner is their exact intersection. Returns the 4 corner
    vertices or None when the free edges do not form a clean two-family quadrilateral."""
    runs = _merge_collinear(_free_edge_runs(pts, cls))
    if len(runs) < 3:
        return None
    # cluster edges by direction (mod 180 deg): a quad has two orthogonal families
    dirs = np.array([r[1] for r in runs])
    ang = np.mod(np.degrees(np.arctan2(dirs[:, 1], dirs[:, 0])), 180.0)
    base = ang[int(np.argmax([np.linalg.norm(r[3] - r[2]) for r in runs]))]  # longest edge's angle
    da = np.abs((ang - base + 90) % 180 - 90)
    fam_a = [runs[i] for i in range(len(runs)) if da[i] <= 20.0]
    fam_b = [runs[i] for i in range(len(runs)) if 70.0 <= np.abs((ang[i] - base) % 180) <= 110.0]
    if not fam_a or not fam_b:
        return None
    # one representative line per family extreme: project edge centroids on the family normal
    def extremes(fam, normal):
        proj = [np.dot(r[0], normal) for r in fam]
        lo = fam[int(np.argmin(proj))]
        hi = fam[int(np.argmax(proj))]
        return (lo[0], lo[1]), (hi[0], hi[1])

    da_dir = fam_a[0][1]
    na = np.array([-da_dir[1], da_dir[0]])
    db_dir = fam_b[0][1]
    nb = np.array([-db_dir[1], db_dir[0]])
    a_lines = extremes(fam_a, nb)   # sides of family A are separated along B's direction? use nb
    b_lines = extremes(fam_b, na)
    # four corners = intersections of each A-line with each B-line, ordered into a quad
    corners = []
    for (ca, dira) in a_lines:
        for (cb, dirb) in b_lines:
            x = _intersect(ca, dira, cb, dirb)
            if x is None:
                return None
            corners.append(x)
    if len(corners) != 4:
        return None
    quad = np.array(corners, float)
    # order the 4 corners by angle around their centroid to form a simple (non-crossing) quad
    ctr = quad.mean(axis=0)
    order = np.argsort(np.arctan2(quad[:, 1] - ctr[1], quad[:, 0] - ctr[0]))
    quad = quad[order]
    # Guard: the reconstructed quad must actually contain the free observation points (otherwise
    # the two-family clustering picked the wrong lines - e.g. a star/ngon, not a rectangle). This
    # keeps the quad path from proposing a garbage shape that `evaluate` would only reject.
    all_free = pts[cls == 0]
    if len(all_free) and _frac_inside(quad, all_free) < 0.9:
        return None
    return quad


def _frac_inside(poly: np.ndarray, test: np.ndarray, pad: float = 2.0) -> float:
    """Fraction of ``test`` points lying inside (or within ``pad`` px of) the polygon."""
    poly32 = poly.astype(np.float32)
    inside = np.array([cv2.pointPolygonTest(poly32, (float(x), float(y)), True)
                       for x, y in test])
    return float((inside >= -pad).mean())


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


def _outlines(mask: np.ndarray) -> list[np.ndarray]:
    """All external outlines, keeping component boundaries separate."""
    # find_contours orients foreground outlines positively and hole boundaries
    # negatively. Filtering by winding avoids a hole-fill pass for every neighbour.
    return [resample_closed(c, 1.0) for c in contours_xy(mask) if len(c) >= 12 and poly_area(c) > 0]


def _component_junctions(contours, near, frame):
    out, start = [], 0
    for contour in contours:
        end = start + len(contour)
        out.extend(_junctions(contour, near[start:end], frame[start:end]))
        start = end
    return out


def occludes(mask: Mask, cover: Mask, canvas: tuple[int, int]) -> bool:
    """Relative T-junction evidence without requiring a completed primitive."""
    y0, x0 = min(mask.y0, cover.y0)-3, min(mask.x0, cover.x0)-3
    y1, x1 = max(mask.bbox[2], cover.bbox[2])+3, max(mask.bbox[3], cover.bbox[3])+3
    ref = Mask(np.zeros((y1-y0, x1-x0), bool), y0, x0)
    R, C = crop_like(mask, ref), crop_like(cover, ref)
    rc, cc = _outlines(R), _outlines(C)
    if not rc or not cc:
        return False

    def junctions(contours, neighbour):
        p = np.vstack(contours)
        x = np.clip(np.round(p[:, 0]).astype(int), 0, x1-x0-1)
        y = np.clip(np.round(p[:, 1]).astype(int), 0, y1-y0-1)
        near = ndi.binary_dilation(neighbour, structure=np.ones((3, 3), bool), iterations=2)
        frame = ((p[:, 0]+x0 <= -.4) | (p[:, 1]+y0 <= -.4)
                 | (p[:, 0]+x0 >= canvas[1]-.6) | (p[:, 1]+y0 >= canvas[0]-.6))
        return _component_junctions(contours, near[y, x], frame)

    return _occludes(junctions(rc, C), junctions(cc, R)) >= 15


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
    # coverage by ALL touching neighbours (before the 15-deg paint-order filter below). Used
    # ONLY by the new free-edge candidate to test "is the recovered region actually hidden"
    # against every neighbour, not only the ones that produced a T-junction at R's contour -
    # a stacked corner is often covered by a sibling that gives R no local junction. The 15-deg
    # test still governs paint order (the `above` set) and the existing candidates are untouched.
    Cm_all, Cv_all = Cm.copy(), Cv.copy()
    contours = _outlines(Rm)
    if not contours:
        return None
    cont = np.vstack(contours)   # pool free points, never connect separate contour tangents

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
        outlines = _outlines(Om)
        if not outlines:
            continue
        oc = np.vstack(outlines)
        ofr = ((oc[:, 0] + x0) <= -0.4) | ((oc[:, 1] + y0) <= -0.4) | \
              ((oc[:, 0] + x0) >= W - 0.6) | ((oc[:, 1] + y0) >= H - 0.6)
        oxi = np.clip(np.round(oc[:, 0]).astype(int), 0, shp[1] - 1)
        oyi = np.clip(np.round(oc[:, 1]).astype(int), 0, shp[0] - 1)
        On = ndi.binary_dilation(Om, structure=se, iterations=2)
        jR = _component_junctions(contours, On[yi, xi], frame)
        jO = _component_junctions(outlines, Rn[oyi, oxi], ofr)
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

    def evaluate(P: np.ndarray, prim: Prim | None, fit_quality: float = float("inf"),
                 cover_m: np.ndarray | None = None, cover_v: np.ndarray | None = None,
                 cover_pad: int = 0, seam_core: bool = False):
        # cover_pad dilates the occluder coverage masks by a pixel before the coverage test.
        # It absorbs the sub-pixel rasterisation seam between a reconstructed primitive's edge
        # and the occluder silhouettes (the "rasterised perimeter dominates the extra area"
        # artefact): the floor FRACTIONS are unchanged, only the 1px boundary double-count is
        # removed. Used only by the free-edge candidate; the existing paths pass cover_pad=0.
        covM = Cm if cover_m is None else cover_m
        covV = Cv if cover_v is None else cover_v
        if cover_pad > 0:
            covM = ndi.binary_dilation(covM, structure=se, iterations=cover_pad)
            covV = ndi.binary_dilation(covV, structure=se, iterations=cover_pad)
        # Check the actual fitted model before restoring small raster residuals.
        # Once unioned with Rm, containment is tautological; accepting such a fit
        # could emit a primitive that drops a substantial part of the observation.
        if (Rm & ~P).sum() > 0.03 * area:
            return None
        P = P | Rm
        extra = P & ~Rm
        ne = int(extra.sum())
        if ne < min_extra:
            return None
        # The recovered ("extra") region must lie under the shapes we claim hide R:
        # this is what stops a shape merely sitting beside a neighbour from being
        # "completed" into it. A clean primitive fit (low RMS, wide arc) is strong
        # geometric evidence of the true silhouette, so when the occluder is a same-
        # size neighbour that does not fully cover R's hidden half, a small sliver of
        # the recovered area legitimately pokes past the occluder. Relax the
        # occluder-coverage floor for a well-fit primitive; keep it strict for the
        # Bézier bridge and weak fits (which otherwise win by hugging the occluder
        # and emitting a drifted, undersized silhouette).
        trusted = prim is not None and fit_quality >= 0.0 and fit_quality <= 0.5 * tol
        cm_floor = 0.85 if trusted else 0.9
        cv_floor = 0.65 if trusted else 0.7
        # R7b (pixel-boundary evaluation, rectilinear only): for a RECT candidate the occluder-
        # coverage floor must judge whether the reconstructed hidden REGION lies under the
        # occluders, but `extra`'s rasterised 1px PERIMETER is a boundary artefact whose pixel
        # count grows with the rect's edge length, not its area. For a thin occluded bar that
        # perimeter becomes an area-independent constant that dominates the fraction (measured:
        # ~130 uncovered perimeter px, 0 interior, at every bar height), so a perfectly-fit rect
        # (RMS<<tol) whose hidden core is 100% under the occluder is wrongly rejected as the bar
        # narrows. When seam_core is set (rect candidates only) evaluate the fraction on the
        # eroded INTERIOR of extra while it is substantial, so the seam no longer dominates. The
        # floor FRACTIONS and the occluder set (Cm/Cv) are unchanged, and ne/min_extra/`above`
        # still use the full extra. Curved candidates keep the full-extra test unchanged (a thin
        # fragment can fit a spurious narrow ellipse, which the perimeter-inclusive floor rejects
        # and which this correction must not admit). A side-by-side neighbour still fails: its
        # extra interior is not under the occluder, so its core coverage is low too.
        if int((extra & covM).sum()) < cm_floor * ne or int((extra & covV).sum()) < cv_floor * ne:
            # The full-extra coverage test failed. For a RECT candidate this can be the thin-bar
            # seam artefact (see seam_core note): the hidden region is genuinely under the
            # occluder but `extra`'s rasterised 1px PERIMETER - an area-independent constant that
            # dominates a narrow band - pushes the fraction below the floor. Only when the extra
            # is actually a thin band (its perimeter is a large share of its area, >=25%) AND its
            # eroded INTERIOR is essentially fully under the occluders do we accept: a normal-
            # thickness rect has a small perimeter share so it keeps the strict full-extra test
            # unchanged, and a side-by-side neighbour fails - its interior is not covered either.
            core = ndi.binary_erosion(extra) if seam_core else np.zeros_like(extra)
            nc = int(core.sum())
            perim_frac = 1.0 - nc / ne if ne else 1.0
            # Admit ONLY when the thin band's interior is essentially FULLY under the occluders
            # (a genuine thin occluded bar measures ~1.0 interior coverage). A near-complete
            # floor of 0.98 - far above the 0.85/0.65 shape floors - keeps this correction to
            # the seam artefact alone: a partly-visible or side-by-side thin feature, whose
            # interior pokes past the occluder, is still rejected, so no shipped art changes.
            if not (seam_core and perim_frac >= 0.25 and nc >= min_extra
                    and int((core & covM).sum()) >= 0.98 * nc
                    and int((core & covV).sum()) >= 0.98 * nc):
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
        best = evaluate(raster_prim(r[0], shp), r[0], r[1])
    if best is None and not cfg.snap_primitives is False:
        e = fit_ellipse(F)
        if e and e[1] <= tol and e[2] >= np.deg2rad(140) and max(e[0].rx, e[0].ry) < 4 * max(H, W):
            best = evaluate(raster_prim(e[0], shp), e[0], e[1])
    if best is None:
        q = fit_rect(F)
        if q and q[1] <= tol:
            best = evaluate(raster_prim(q[0], shp), q[0], q[1], seam_core=True)
    # Free-edge line-intersection reconstruction for partly-hidden rectilinear shapes.
    # When the hidden corner is behind an occluder, fit_rect's minAreaRect seed is biased by
    # the cut and its RMS exceeds tol. Extending the straight free edges and intersecting the
    # adjacent non-parallel ones reconstructs the hidden corner(s); the reconstructed polygon
    # is then re-fit (clean <rect> when it is axis-aligned, else a polygon Prim) and judged by
    # the SAME unchanged evaluate gates - this is a new candidate, not a tolerance relaxation.
    if best is None and len(contours) == 1:
        # (1) quadrilateral reconstruction (rect / rrect / rotated rect): fit the four side
        #     lines from all free points and intersect them for clean corners, then re-fit as a
        #     rect so an axis-aligned shape emits a native <rect>.
        quad = _free_edge_quad(cont, cls)
        if quad is not None:
            # Fit the rect to the free observation points plus the reconstructed corners, so the
            # robust median edge-refinement in fit_rect snaps the visible edges to the real data
            # while the reconstructed corners pin the hidden extent (tighter than the 4 corners
            # alone, which matters for near-threshold IoU matches).
            fr = fit_rect(np.vstack([F, quad]))
            if fr and fr[1] <= tol:
                best = evaluate(raster_prim(fr[0], shp), fr[0], fr[1],
                                cover_m=Cm_all, cover_v=Cv_all, cover_pad=1)
            if best is None:
                fr = fit_rect(quad)
                if fr and fr[1] <= tol:
                    best = evaluate(raster_prim(fr[0], shp), fr[0], fr[1],
                                    cover_m=Cm_all, cover_v=Cv_all, cover_pad=1)
            if best is None:
                pr = Prim("polygon", pts=quad.astype(float))
                best = evaluate(raster_prim(pr, shp), pr, float("inf"),
                                cover_m=Cm_all, cover_v=Cv_all, cover_pad=1)
        # (2) general convex/rectilinear polygon reconstruction by chaining free edges.
        if best is None:
            poly = _free_edge_polygon(cont, cls)
            if poly is not None:
                fr = fit_rect(poly)
                if fr and fr[1] <= tol:
                    best = evaluate(raster_prim(fr[0], shp), fr[0], fr[1],
                                    cover_m=Cm_all, cover_v=Cv_all, cover_pad=1)
                if best is None and len(poly) >= 3:
                    pr = Prim("polygon", pts=poly.astype(float))
                    best = evaluate(raster_prim(pr, shp), pr, float("inf"),
                                    cover_m=Cm_all, cover_v=Cv_all, cover_pad=1)
    if best is None and len(contours) == 1:
        poly = _bridge(cont, cls)
        if poly is not None and len(poly) > 8:
            img = np.zeros(shp, np.uint8)
            cv2.fillPoly(img, [np.round(poly * SCALE).astype(np.int32)], 1, cv2.LINE_8, SHIFT)
            best = evaluate(img.astype(bool), None)
    return best
