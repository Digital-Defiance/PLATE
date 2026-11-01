"""Schneider's least-squares cubic Bezier fitting ("An Algorithm for Automatically Fitting
Digitized Curves", Graphics Gems I), plus corner detection for closed contours."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else np.array([1.0, 0.0])


def _chord_param(P):
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    return d / d[-1] if d[-1] > 0 else np.linspace(0, 1, len(P))


def bez(c, t):
    t = np.asarray(t)[:, None]
    m = 1 - t
    return m ** 3 * c[0] + 3 * m * m * t * c[1] + 3 * m * t * t * c[2] + t ** 3 * c[3]


def _d1(c, t):
    t = np.asarray(t)[:, None]
    m = 1 - t
    return 3 * (m * m * (c[1] - c[0]) + 2 * m * t * (c[2] - c[1]) + t * t * (c[3] - c[2]))


def _d2(c, t):
    t = np.asarray(t)[:, None]
    m = 1 - t
    return 6 * (m * (c[2] - 2 * c[1] + c[0]) + t * (c[3] - 2 * c[2] + c[1]))


def _generate(P, u, t1, t2):
    p0, p3 = P[0], P[-1]
    b0, b1, b2, b3 = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
    A1, A2 = t1[None, :] * b1[:, None], t2[None, :] * b2[:, None]
    C00, C01, C11 = (A1 * A1).sum(), (A1 * A2).sum(), (A2 * A2).sum()
    tmp = P - (p0[None, :] * (b0 + b1)[:, None] + p3[None, :] * (b2 + b3)[:, None])
    X0, X1 = (A1 * tmp).sum(), (A2 * tmp).sum()
    det = C00 * C11 - C01 * C01
    if abs(det) > 1e-12:
        a1, a2 = (X0 * C11 - X1 * C01) / det, (C00 * X1 - C01 * X0) / det
    else:
        a1 = a2 = 0.0
    seg = np.linalg.norm(p3 - p0)
    if a1 < 1e-6 * seg or a2 < 1e-6 * seg:
        a1 = a2 = seg / 3
    return np.array([p0, p0 + t1 * a1, p3 + t2 * a2, p3])


def _max_err(P, c, u):
    d = bez(c, u) - P
    e = (d * d).sum(1)
    i = int(e.argmax())
    return float(e[i]), i


def _reparam(c, P, u):
    d = bez(c, u) - P
    d1, d2 = _d1(c, u), _d2(c, u)
    num = (d * d1).sum(1)
    den = (d1 * d1).sum(1) + (d * d2).sum(1)
    out = u.copy()
    m = np.abs(den) > 1e-12
    out[m] = u[m] - num[m] / den[m]
    return np.clip(out, 0, 1)


def _fit(P, t1, t2, err2, depth=0):
    n = len(P)
    if n == 2:
        d = np.linalg.norm(P[1] - P[0]) / 3
        return [np.array([P[0], P[0] + t1 * d, P[1] + t2 * d, P[1]])]
    u = _chord_param(P)
    c = _generate(P, u, t1, t2)
    e, split = _max_err(P, c, u)
    if e < err2:
        return [c]
    if e < err2 * 16:
        for _ in range(12):
            u = _reparam(c, P, u)
            c = _generate(P, u, t1, t2)
            e, split = _max_err(P, c, u)
            if e < err2:
                return [c]
    if depth > 40 or n < 4:
        return [c]
    if split <= 0 or split >= n - 1:
        split = n // 2
    tc = _norm(P[split - 1] - P[split + 1])
    return _fit(P[:split + 1], t1, tc, err2, depth + 1) + _fit(P[split:], -tc, t2, err2, depth + 1)


def _dedupe(P):
    keep = np.r_[True, np.linalg.norm(np.diff(P, axis=0), axis=1) > 1e-9]
    return P[keep]


def fit_open(P, tol, t1=None, t2=None):
    """Fit an open polyline; returns a list of (4, 2) cubic control arrays."""
    P = _dedupe(np.asarray(P, float))
    n = len(P)
    if n < 2:
        return []
    k = min(4, n - 1)
    if t1 is None:
        t1 = _norm(P[k] - P[0])
    if t2 is None:
        t2 = _norm(P[-1 - k] - P[-1])
    return _fit(P, t1, t2, tol * tol)


def is_flat(c, tol=0.12) -> bool:
    ch = c[3] - c[0]
    L = np.linalg.norm(ch)
    if L < 1e-9:
        return False
    nrm = np.array([-ch[1], ch[0]]) / L
    return abs(np.dot(c[1] - c[0], nrm)) < tol and abs(np.dot(c[2] - c[0], nrm)) < tol


# --------------------------------------------------------------------- contours
def resample_closed(P, step=1.0):
    P = np.asarray(P, float)
    if np.linalg.norm(P[0] - P[-1]) < 1e-9:
        P = P[:-1]
    Q = np.vstack([P, P[:1]])
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    s = np.r_[0, np.cumsum(seg)]
    total = s[-1]
    if total < step * 3:
        return P
    n = max(int(round(total / step)), 8)
    t = np.linspace(0, total, n, endpoint=False)
    return np.c_[np.interp(t, s, Q[:, 0]), np.interp(t, s, Q[:, 1])]


def find_corners(P, angle_deg, k=4):
    """Indices of corner points on a closed, ~1px-resampled contour."""
    n = len(P)
    if n < 4 * k:
        return []
    a = P - np.roll(P, k, axis=0)
    b = np.roll(P, -k, axis=0) - P
    cosang = (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12)
    turn = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
    cand = np.flatnonzero(turn >= angle_deg)
    corners = []
    for i in cand:
        win = [(i + j) % n for j in range(-k, k + 1)]
        if turn[i] >= turn[win].max() - 1e-9 and all(min((i - c) % n, (c - i) % n) > k for c in corners):
            corners.append(int(i))
    return sorted(corners)


def _line_fit(Q):
    c = Q.mean(0)
    _, _, vt = np.linalg.svd(Q - c)
    return c, vt[0]


def refine_corner(P, i, k_in=3, k_out=12):
    """Intersect the two straight-ish sides meeting at corner i; falls back to P[i]."""
    n = len(P)
    left = np.array([P[(i - j) % n] for j in range(k_in, k_out)])
    right = np.array([P[(i + j) % n] for j in range(k_in, k_out)])
    if len(left) < 4:
        return P[i]
    (c1, d1), (c2, d2) = _line_fit(left), _line_fit(right)
    # straightness gate: both sides must actually be lines
    for Q, (c, d) in ((left, (c1, d1)), (right, (c2, d2))):
        nrm = np.array([-d[1], d[0]])
        if np.abs((Q - c) @ nrm).max() > 0.45:
            return P[i]
    A = np.array([d1, -d2]).T
    if abs(np.linalg.det(A)) < 1e-3:
        return P[i]
    s = np.linalg.solve(A, c2 - c1)
    X = c1 + d1 * s[0]
    return X if np.linalg.norm(X - P[i]) < 2.5 else P[i]


def smooth_open(pts: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian-smooth an open polyline (~1 px spacing) with both end points pinned exactly."""
    n = len(pts)
    if sigma < 0.3 or n < 5:
        return pts
    r = min(int(np.ceil(4 * sigma)) + 1, n - 1)
    left = 2 * pts[0] - pts[1:r + 1][::-1]            # odd reflection keeps the ends in place
    right = 2 * pts[-1] - pts[-r - 1:-1][::-1]
    ext = np.vstack([left, pts, right])
    out = gaussian_filter1d(ext, sigma, axis=0, mode="nearest")[r:r + n]
    out[0], out[-1] = pts[0], pts[-1]
    return out


STRAIGHT_RATIO = 0.008   # a run is straight if it bows < 0.8% of its length (noise, not curvature)


def _straight(pts: np.ndarray, tol: float) -> bool:
    ch = pts[-1] - pts[0]
    L = np.linalg.norm(ch)
    if L < 4 * max(tol, 1.0):
        return False
    nrm = np.array([-ch[1], ch[0]]) / L
    return float(np.abs((pts - pts[0]) @ nrm).max()) <= max(tol, STRAIGHT_RATIO * L)


def _line_curve(p0, p1):
    d = p1 - p0
    return np.array([p0, p0 + d / 3, p0 + 2 * d / 3, p1])


def _restore_reference_corners(P, Pd, corners, reference, k, limit):
    """Refine existing sharp corners from unblurred geometry, with the same line-fit gates."""
    R = resample_closed(reference, 1.0)
    kin, kout = max(3, k - 1), max(12, 3 * k)
    if len(R) < max(4 * k, 2 * kout + 2):
        return P
    Rd = gaussian_filter1d(R, 1.0, axis=0, mode="wrap")

    def winding(points):
        return np.sign(np.sum(points[:, 0] * np.roll(points[:, 1], -1)
                              - points[:, 1] * np.roll(points[:, 0], -1)))

    rw, pw = winding(Rd), winding(Pd)
    targets = []
    for j in find_corners(Rd, 90, k):
        point = refine_corner(Rd, j, kin, kout)
        if np.array_equal(point, Rd[j]):
            continue  # unsupported/curved flanks: refine_corner kept its fallback
        u, v = Rd[j] - Rd[(j - k) % len(Rd)], Rd[(j + k) % len(Rd)] - Rd[j]
        direction = point - (Rd[(j - k) % len(Rd)] + Rd[(j + k) % len(Rd)]) / 2
        if np.linalg.norm(direction) < 1:
            continue
        targets.append((point, _norm(direction), np.sign((u[0] * v[1] - u[1] * v[0]) * rw)))
    used = set()
    for i in corners:
        u, v = Pd[i] - Pd[(i - k) % len(Pd)], Pd[(i + k) % len(Pd)] - Pd[i]
        if u @ v > 0:
            continue  # only turns of at least 90 degrees
        side = np.sign((u[0] * v[1] - u[1] * v[0]) * pw)
        candidates = [(np.linalg.norm(point - P[i]), j, point, direction)
                      for j, (point, direction, sign) in enumerate(targets)
                      if j not in used and sign == side]
        if not candidates:
            continue
        distance, j, point, direction = min(candidates, key=lambda item: item[0])
        if distance <= limit and (point - P[i]) @ direction > 0.25:
            P[i] = point
            used.add(j)
    return P


def contour_to_beziers(P, tol, corner_deg, smooth_px: float = 0.0, straighten: bool = False,
                       corner_k: int = 4, corner_reference=None, reference_limit: float = 2.5):
    """Closed contour (N, 2) -> (start_point, [cubic ctrl arrays], closed=True).
    Corners are detected and kept sharp; smooth stretches are fit with Schneider.

    Optional clean-line mode (all off by default, so default output is unchanged):
      smooth_px  Gaussian sigma ALONG the outline between corners, ends pinned (working px);
                 corners are then detected on a lightly smoothed copy.
      straighten corner-to-corner runs that bow < STRAIGHT_RATIO of their length -> exact lines.
      corner_k   half-window (samples) of the corner detector; scale it with `upscale`.
      corner_reference  optional matching unblurred contour for bounded sharp-tip recovery.
                        Does not introduce new corners or change the contour topology."""
    P = resample_closed(P, 1.0)
    n = len(P)
    if n < 6:
        return None
    clean = smooth_px >= 0.3 or straighten or corner_k != 4
    Pd = gaussian_filter1d(P, 1.0, axis=0, mode="wrap") if (clean and n > 12) else P
    corners = find_corners(Pd, corner_deg, corner_k)
    if corners:
        P = P.copy()
        for i in corners:
            P[i] = refine_corner(Pd, i, k_in=max(3, corner_k - 1), k_out=max(12, 3 * corner_k)) if clean \
                else refine_corner(P, i)
        if clean and corner_reference is not None:
            P = _restore_reference_corners(P, Pd, corners, corner_reference, corner_k, reference_limit)
        segs = []
        for a, b in zip(corners, corners[1:] + [corners[0] + n]):
            idx = [(j % n) for j in range(a, b + 1)]
            pts = P[idx]
            if len(pts) > 8:  # drop samples sitting on the rounded apex
                pts = np.vstack([pts[:1], pts[2:-2], pts[-1:]])
            if clean:
                pts = smooth_open(pts, smooth_px)
                if straighten and _straight(pts, 0.6 * tol):
                    segs.append([_line_curve(pts[0], pts[-1])])
                    continue
            segs.append(fit_open(pts, tol))
        curves = [c for s in segs for c in s]
        return P[corners[0]], curves
    # smooth closed loop: two halves with shared tangents (G1)
    if smooth_px >= 0.3:
        P = gaussian_filter1d(P, smooth_px, axis=0, mode="wrap")
    h = n // 2
    ta = _norm(P[1] - P[-1])
    tb = _norm(P[(h + 1) % n] - P[h - 1])
    first = fit_open(P[:h + 1], tol, ta, -tb)
    second = fit_open(np.vstack([P[h:], P[:1]]), tol, tb, -ta)
    return P[0], first + second
