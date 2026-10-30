"""Conservative constant-width stroke recovery using classical geometry."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import least_squares
from scipy.spatial import cKDTree

from ..bezier import bez, fit_open, _d1, _d2
from ..config import Config
from ..geometry import Prim, contours_xy, fit_circle, fit_ellipse, raster_prim, poly_area
from ..masks import Mask, crop_like, touches
from ..scene import Loaded


@dataclass
class Stroke:
    curves: list[np.ndarray]
    width: float
    full: Mask
    completed: bool = False
    occluders: tuple[Mask, ...] = ()


@dataclass
class ClosedStroke:
    prim: Prim
    width: float
    full: Mask
    completed: bool = False


def _ellipse_distance(points, q):
    """Signed Euclidean distance to an ellipse, near its boundary.

    SVG expands an ellipse along its normals; adding width to its axes does not
    describe that offset. Newton projection is stable here because candidates
    are thin rings and their two observed boundaries stay near the centreline.
    """
    cx, cy, rx, ry, angle = q
    c, s = np.cos(angle), np.sin(angle)
    dx, dy = points[:, 0]-cx, points[:, 1]-cy
    x, y = dx*c+dy*s, -dx*s+dy*c
    t = np.arctan2(y/ry, x/rx)
    for _ in range(8):
        ct, st = np.cos(t), np.sin(t)
        ex, ey = rx*ct-x, ry*st-y
        first = ex*(-rx*st)+ey*(ry*ct)
        second = (rx*st)**2+(ry*ct)**2-ex*rx*ct-ey*ry*st
        t -= np.clip(first/np.maximum(second, 1e-6), -.25, .25)
    distance = np.hypot(rx*np.cos(t)-x, ry*np.sin(t)-y)
    return distance*np.where((x/rx)**2+(y/ry)**2 >= 1, 1, -1)


def _longest_run(flags: np.ndarray) -> int:
    """Longest contiguous run of True in a CLOSED (circular) boolean sequence."""
    if not flags.any():
        return 0
    if flags.all():
        return int(flags.size)
    doubled = np.concatenate([flags, flags])
    best = run = 0
    for v in doubled:
        run = run + 1 if v else 0
        best = max(best, run)
    return min(best, int(flags.sum()))


def _boundary_ok(residual: np.ndarray, tol: float, max_frac: float = .05, max_run: int = 12) -> bool:
    """Accept a loop whose boundary deviates beyond `tol` only at a few SCATTERED
    points. A real notch, bite or variable-width defect produces a long CONTIGUOUS
    run of deviating samples (and also fails the separate footprint-XOR gate); busy
    crossings where the stroke overlaps other artwork produce sparse, isolated
    outliers. Reject when outliers are too common or clustered into an arc."""
    bad = np.abs(residual) > tol
    if not bad.any():
        return True
    return bad.mean() <= max_frac and _longest_run(bad) <= max_run


def fit_closed(mask: Mask, cfg: Config, img=None, color=None, covers=()) -> ClosedStroke | None:
    """Recover a thin circular/elliptical loop with two complete boundaries.

    Thick annuli remain compound fills. Local residual and full-footprint checks
    protect notches, off-centre holes and variable width, even when their total
    area error is small. Small bites may be reconstructed only beneath observed
    later-painted shapes; this is not an interrupted-arc completion algorithm.
    """
    if mask.area < 100 or ndi.label(mask.a, np.ones((3, 3)))[1] != 1:
        return None
    pad = 6
    a = np.pad(mask.a, pad)
    contours = contours_xy(a)
    if len(contours) != 2 or min(abs(poly_area(c)) for c in contours) < 100:
        return None
    outer, inner = sorted(contours, key=lambda c: -abs(poly_area(c)))
    circle_o, _, _ = fit_circle(outer)
    circle_i, _, _ = fit_circle(inner)
    # Avoid fitting large solid shapes and wide letter counters as strokes.
    initial_width = (abs(poly_area(outer))-abs(poly_area(inner)))/len(outer)
    if initial_width < 1.5 or initial_width > .15*circle_i.rx:
        return None
    ref = Mask(a, mask.y0-pad, mask.x0-pad)
    covered = np.zeros(a.shape, bool)
    xy_binary = np.rint(np.concatenate(contours)).astype(int)
    if cfg.complete_hidden:
        for cover in covers:
            local = crop_like(cover, ref)
            near = ndi.binary_dilation(local, iterations=2)
            # A painted interior touching an entire inner edge is a counter,
            # not evidence of a small object biting into the ring.
            if np.mean(near[xy_binary[:, 1], xy_binary[:, 0]]) <= .1:
                covered |= local
    near_cover = ndi.binary_dilation(covered, iterations=2)
    field = _coverage_field(a, mask, pad, img, color)
    reference = a
    if field is not None:
        soft = contours_xy(field)
        if len(soft) == 2:
            contours = soft
            reference = field >= .5
    boundary = np.concatenate(contours)
    xy = np.rint(boundary).astype(int)
    free = ~near_cover[xy[:, 1], xy[:, 0]]
    # A ring threaded through a busy composition (e.g. an orbit behind satellites,
    # a wordmark and a core) can have a large fraction of its boundary near later
    # shapes, yet its visible arcs still massively over-determine the ellipse. Trust
    # the fit when at least half the boundary is free; the residual and footprint
    # gates below (evaluated on the free boundary / free region) remain the real
    # guarantees against accepting a mostly-hidden sliver as a full loop.
    if free.mean() < .5:
        return None
    points = boundary[free]
    sample = points[::max(1, len(points)//1600)]

    def circle_distance(p, q):
        return np.hypot(p[:, 0]-q[0], p[:, 1]-q[1])-q[2]

    candidates = []
    q0 = [(circle_o.cx+circle_i.cx)/2, (circle_o.cy+circle_i.cy)/2,
          (circle_o.rx+circle_i.rx)/2, circle_o.rx-circle_i.rx]
    if q0[3] > 1:
        candidates.append(("circle", q0, circle_distance))
    ellipse = fit_ellipse(outer)
    if ellipse:
        pr = ellipse[0]
        q0 = [pr.cx, pr.cy, pr.rx-initial_width/2, pr.ry-initial_width/2,
              np.deg2rad(pr.angle), initial_width]
        if min(q0[2:4]) > 2:
            candidates.append(("ellipse", q0, _ellipse_distance))
    for kind, q0, distance in candidates:
        # Keep the fit local to the complete observed loop, and widths positive.
        span = np.array([2, 2, 3, 3] if kind == "circle" else [2, 2, 3, 3, .15, 3])
        lower, upper = np.array(q0)-span, np.array(q0)+span
        radii = slice(2, 3 if kind == "circle" else 4)
        lower[radii] = np.maximum(lower[radii], .5)
        lower[-1] = max(1., lower[-1])
        fit = least_squares(lambda q: np.abs(distance(sample, q[:-1]))-q[-1]/2,
                            q0, bounds=(lower, upper), max_nfev=80)
        q, width = fit.x[:-1], fit.x[-1]
        residual = np.abs(distance(points, q))-width/2
        # Overall tightness must hold (RMS), but allow a few SCATTERED points past
        # the max tolerance where the stroke crosses other artwork; a real notch is
        # a long contiguous deviating run and is rejected by _boundary_ok (and by the
        # footprint-XOR gate below).
        if np.sqrt(np.mean(residual**2)) > .35 or not _boundary_ok(residual, .85):
            continue
        radius = q[2] if kind == "circle" else min(q[2:4])
        if width > .15*radius:
            continue
        yy, xx = np.indices(a.shape)
        predicted = (np.abs(distance(np.c_[xx.ravel(), yy.ravel()], q)) <= width/2).reshape(a.shape)
        # No cropping of a candidate's outer footprint: it must fit in our pad.
        if predicted[:1].any() or predicted[-1:].any() or predicted[:, :1].any() or predicted[:, -1:].any():
            continue
        missing, extra = predicted & ~reference, reference & ~predicted
        uncovered = missing & ~covered
        # Stray pixels (prediction far from observation or vice versa) flag a real
        # geometric defect — a detached blob, a notch — but a thin stroke crossing
        # other artwork smears its boundary by a couple of px. Tolerate stray area
        # up to the observed max boundary deviation (3px dilation) PROVIDED it stays
        # a tiny fraction of the loop; the XOR gate still caps gross mismatch.
        tol_px = 3
        stray_missing = uncovered & ~ndi.binary_dilation(reference, iterations=tol_px)
        stray_extra = extra & ~ndi.binary_dilation(predicted, iterations=tol_px)
        stray_allow = .01 * np.count_nonzero(reference | predicted)
        if (np.count_nonzero((reference ^ predicted) & ~covered)/max(1, np.count_nonzero((reference | predicted) & ~covered)) > .06
                or np.count_nonzero(stray_missing) > stray_allow
                or np.count_nonzero(stray_extra) > stray_allow):
            continue
        # Validate every observed boundary, including points near occluders that
        # were excluded from fitting. Deviations there need actual cover pixels, or
        # must be sparse/scattered (busy crossings) rather than a clustered defect.
        residual = np.abs(distance(boundary, q))-width/2
        free_boundary = ~near_cover[xy[:, 1], xy[:, 0]]
        if not _boundary_ok(residual[free_boundary], .85):
            continue
        prim = Prim(kind, q[0]+ref.x0, q[1]+ref.y0, q[2],
                    q[2] if kind == "circle" else q[3],
                    0 if kind == "circle" else np.rad2deg(q[4]))
        full = Mask(predicted, ref.y0, ref.x0)
        return ClosedStroke(prim, width, full, bool(np.any(missing & covered & ~ndi.binary_dilation(reference))))
    return None


def _coverage_field(a, mask, pad, img, color):
    """Recover a subpixel edge from foreground/background coverage when supported.

    Binary masks can make short round and square caps identical. Keep the PNG's
    antialias signal, including alpha, rather than deciding from those bits alone.
    """
    if img is None or color is None:
        return None
    h, w = a.shape
    y0, x0 = mask.y0-pad, mask.x0-pad
    ys, xs = max(0, y0), max(0, x0)
    ye, xe = min(img.alpha.shape[0], y0+h), min(img.alpha.shape[1], x0+w)
    if ye <= ys or xe <= xs:
        return None
    rgb, alpha = np.zeros((h, w, 3)), np.zeros((h, w))
    rgb[ys-y0:ye-y0, xs-x0:xe-x0] = img.rgb[ys:ye, xs:xe]
    alpha[ys-y0:ye-y0, xs-x0:xe-x0] = img.alpha[ys:ye, xs:xe]/255
    # Sample beyond Lanczos' antialias/overshoot halo, not the immediate fringe.
    ring = ndi.binary_dilation(a, iterations=pad) & ~ndi.binary_dilation(a, iterations=3)
    if np.mean(alpha[ring] > .99) > .5:
        colors, counts = np.unique(rgb[ring & (alpha > .99)], axis=0, return_counts=True)
        if counts.max() < .35*counts.sum():
            return None
        background = colors[counts.argmax()]
    else:
        background = np.full(3, 255.) if np.mean(color) < 128 else np.zeros(3)
    delta = np.array(color)-background
    if delta @ delta < 100:
        return None
    projection = ((rgb-background) @ delta)/(delta @ delta)
    # Lanczos overshoot can exceed the foreground/background endpoints. Measure
    # colour consistency on the unclamped line so those pixels do not become holes.
    residual = np.linalg.norm(rgb-(background+projection[..., None]*delta), axis=2)
    coverage = np.clip(projection, 0, 1)*alpha*(residual <= 12)*ndi.binary_dilation(a, iterations=2)
    return coverage


def _line_distance(q, points, rounded):
    cx, cy, angle, length, radius = q
    axis = np.array([np.cos(angle), np.sin(angle)])
    delta = points-[cx, cy]
    along, across = delta @ axis, delta @ [-axis[1], axis[0]]
    if rounded:
        return np.hypot(np.maximum(abs(along)-length/2, 0), across)-radius
    d = np.c_[abs(along)-length/2, abs(across)-radius]
    return np.linalg.norm(np.maximum(d, 0), axis=1)+np.minimum(d.max(axis=1), 0)


def _fit_hidden_line(points, ends, cover, circle, mask, pad, img, width):
    """Fit free sides/cap while the other terminal stays under a supported hub."""
    origin = np.array([mask.x0-pad, mask.y0-pad])
    centre = np.array([circle.cx, circle.cy])-origin
    # Only the far terminal is observed; do not fit the artificial cut along the hub.
    ref = Mask(np.zeros(np.array(mask.a.shape)+2*pad, bool), mask.y0-pad, mask.x0-pad)
    near = ndi.binary_dilation(crop_like(cover, ref), structure=np.ones((3, 3), bool), iterations=2)
    ix = np.clip(np.round(points[:, 0]).astype(int), 0, near.shape[1]-1)
    iy = np.clip(np.round(points[:, 1]).astype(int), 0, near.shape[0]-1)
    free = points[~near[iy, ix]]
    if len(free) < 12:
        return None
    far = max(ends, key=lambda p: np.linalg.norm(p-centre))
    delta = far-centre
    angle, length = np.arctan2(delta[1], delta[0]), np.linalg.norm(delta)

    def model(parameters):
        theta, span, radius, offset = parameters
        axis = np.array([np.cos(theta), np.sin(theta)])
        start = centre+np.array([-axis[1], axis[0]])*offset
        return np.array([*(start+axis*span/2), theta, span, radius])

    initial = [angle, length, width/2, 0]
    lo = [angle-.2, max(1, length-2*width), .75, -1]
    hi = [angle+.2, length+2*width, width, 1]
    q = least_squares(lambda p: _line_distance(model(p), free, True), initial, bounds=(lo, hi)).x
    fitted = model(q)
    error = np.sqrt(np.mean(_line_distance(fitted, free, True)**2))
    if error > .15:
        return None
    square = least_squares(lambda p: _line_distance(model(p), free, False), q, bounds=(lo, hi)).x
    return fitted, model(square), free, error


def fit_straight(mask: Mask, cfg: Config, img: Loaded | None = None, color=None,
                 circles: Sequence[tuple[Mask, Prim]] = ()) -> Stroke | None:
    """Recover a straight round-capped stroke with at least one visible cap.

    Compete with square-ended rectangles and ellipses. A long rectangle's rounded
    replacement may have excellent global IoU, so cap-local evidence is mandatory.
    """
    if mask.empty() or mask.area < 20:
        return None
    pad = 6
    a = np.pad(mask.a, pad)
    if (ndi.binary_fill_holes(a) != a).any() or ndi.label(a)[1] != 1:
        return None
    ys, xs = np.nonzero(a)
    pixels = np.c_[xs, ys].astype(float)
    centre = pixels.mean(axis=0)
    _, vectors = np.linalg.eigh(np.cov(pixels.T))
    axis = vectors[:, -1]
    angle = np.arctan2(axis[1], axis[0])
    delta = pixels-centre
    length = float(np.ptp(delta @ axis)+1)
    width = float(np.ptp(delta @ [-axis[1], axis[0]])+1)
    if length < 2.5*width:
        return None
    contours = contours_xy(a)
    if len(contours) != 1:
        return None
    coverage = _coverage_field(a, mask, pad, img, color)
    cs = [] if coverage is None else contours_xy(coverage)
    coverage_points = cs[0] if len(cs) == 1 else None
    if (coverage_points is None and img is not None
            and any(touches(mask, cover, img.alpha.shape, 2) for cover, _ in circles)):
        # A hub fringe can leave a tiny detached coverage island. It is not part
        # of the observed line; retain the dominant external contour only.
        external = [c for c in cs if poly_area(c) >= .8*mask.area]
        if len(external) == 1:
            coverage_points = external[0]
    points = contours[0] if coverage_points is None else coverage_points
    lo = [centre[0]-width, centre[1]-width, angle-.3, .5, .75]
    hi = [centre[0]+width, centre[1]+width, angle+.3, 2*length, width]
    initial = [*centre, angle, max(1, length-width), width/2]
    q = least_squares(lambda q: _line_distance(q, points, True), initial, bounds=(lo, hi)).x
    fit_error = np.sqrt(np.mean(_line_distance(q, points, True)**2))
    initial[3] = length
    butt = least_squares(lambda q: _line_distance(q, points, False), initial, bounds=(lo, hi)).x
    axis = np.array([np.cos(q[2]), np.sin(q[2])])
    ends = q[:2] + np.array([-1, 1])[:, None]*axis*q[3]/2
    global_ends = ends+[mask.x0-pad, mask.y0-pad]
    contacts, blocked = [], False
    for index, end in enumerate(global_ends):
        for cover, circle in circles:
            if np.linalg.norm(end-[circle.cx, circle.cy]) > circle.rx+2*q[4]+2:
                continue
            half = int(np.ceil(2*q[4]))+2
            terminal = Mask(np.zeros((2*half+1, 2*half+1), bool),
                            int(np.floor(end[1]))-half, int(np.floor(end[0]))-half)
            if (ndi.binary_dilation(crop_like(mask, terminal), iterations=2)
                    & crop_like(cover, terminal)).any():
                blocked = True
                outward = (end-global_ends[1-index])/max(np.linalg.norm(end-global_ends[1-index]), 1e-9)
                delta = np.array([circle.cx, circle.cy])-end
                across = abs(float(outward[0]*delta[1]-outward[1]*delta[0]))
                if (img is not None and coverage_points is not None and delta @ outward > 0
                        and across <= q[4] and circle.rx >= q[4]+1):
                    from .complete import occludes
                    if not occludes(mask, cover, img.alpha.shape):
                        continue
                    contacts.append((index, np.linalg.norm(delta), cover, circle))
    hidden = None
    if blocked:
        if not cfg.complete_hidden or not contacts or len({c[0] for c in contacts}) != 1:
            return None
        _, _, cover, circle = min(contacts, key=lambda c: c[1])
        result = _fit_hidden_line(points, ends, cover, circle, mask, pad, img, 2*q[4])
        if result is None:
            return None
        q, butt, points, fit_error = result
        hidden = cover, circle
        axis = np.array([np.cos(q[2]), np.sin(q[2])])
        ends = q[:2]+np.array([-1, 1])[:, None]*axis*q[3]/2

    # Include the entire proposed capsule, including its width-search margin.
    low = np.minimum([0, 0], np.floor(ends.min(axis=0)-q[4]-2)).astype(int)
    high = np.maximum(a.shape[::-1], np.ceil(ends.max(axis=0)+q[4]+2)).astype(int)
    if np.any(high-low > 2*np.array(a.shape[::-1])+4):
        return None
    reference = np.pad(a, ((-low[1], high[1]-a.shape[0]), (-low[0], high[0]-a.shape[1])))
    yy, xx = np.indices(reference.shape)
    grid = np.c_[xx.ravel()+low[0], yy.ravel()+low[1]]
    best = None
    # Do not distort a well-supported subpixel edge to match quantized region
    # ownership. A near-half-covered diagonal row can flip an entire binary edge.
    lengths = (-.4, -.2, 0, .2, .4) if coverage_points is None else (0,)
    radii = (-.3, -.15, 0, .15, .3) if coverage_points is None else (0,)
    for dl in lengths:
        for dr in radii:
            candidate_q = q.copy()
            candidate_q[3] += dl
            candidate_q[4] += dr
            candidate = (_line_distance(candidate_q, grid, True) <= 0).reshape(reference.shape)
            xor = int((candidate ^ reference).sum())
            if best is None or xor < best[0]:
                best = xor, candidate_q, candidate
    xor, q, candidate = best
    observed, visible = reference, candidate
    occluded = np.zeros(reference.shape, bool)
    if hidden is not None:
        _, circle = hidden
        occluded = raster_prim(circle, reference.shape, origin=(mask.x0-pad+low[0], mask.y0-pad+low[1]))
        cover_ref = Mask(np.zeros(reference.shape, bool), mask.y0-pad+low[1], mask.x0-pad+low[0])
        occluded |= crop_like(hidden[0], cover_ref)
        observed, visible = reference & ~occluded, candidate & ~occluded
        distances = _line_distance(q, grid, True).reshape(reference.shape)
        # Check the entire exposed core, including pixels segmentation assigned
        # to an antialiased end cap. Extending that cap across a gap would make
        # partially covered pixels solid even if their binary label stayed equal.
        exposed_core = (distances < -1) & ~occluded
        if exposed_core.any():
            field = np.pad(coverage, ((-low[1], high[1]-a.shape[0]), (-low[0], high[0]-a.shape[1])))
            # The hub's antialias fringe may mix its colour with the stroke.
            # A true background gap cannot be explained by that colour pair.
            yy_c, xx_c = np.nonzero(hidden[0].a)
            hub_rgb = img.rgb[yy_c+hidden[0].y0, xx_c+hidden[0].x0]
            colors, counts = np.unique(hub_rgb, axis=0, return_counts=True)
            hub_color = colors[counts.argmax()].astype(float)
            d = np.array(color)-hub_color
            sample = grid[exposed_core.ravel()]+[mask.x0-pad, mask.y0-pad]
            x, y = sample[:, 0].astype(int), sample[:, 1].astype(int)
            if (x.min() < 0 or y.min() < 0 or x.max() >= img.alpha.shape[1] or y.max() >= img.alpha.shape[0]):
                return None
            rgb = img.rgb[y, x].astype(float)
            projection = (rgb-hub_color) @ d/max(float(d @ d), 1)
            amount = np.clip(projection, 0, 1)
            blend_error = np.linalg.norm(rgb-(hub_color+projection[:, None]*d), axis=1)
            supported = (field[exposed_core] >= .85) | ((amount >= .15) & (blend_error <= 12))
            if not supported.all() or (img.alpha[y, x] < 128).any():
                return None
    iou = (visible & observed).sum()/max(1, (visible | observed).sum())
    if iou < .97:
        # Reliable antialias contours can differ from the segmentation by one
        # partially covered row. Permit only subpixel boundary differences.
        distances = _line_distance(q, grid, True).reshape(reference.shape)
        added = visible & ~reference
        if (coverage_points is None or fit_error > .15 or distances[observed].max() > .75
                or (added.any() and ndi.distance_transform_edt(~reference)[added].max() > 1.5)):
            return None
    rectangle = (_line_distance(butt, grid, False) <= 0).reshape(reference.shape)
    if coverage_points is None and xor > (rectangle ^ reference).sum()+2:
        return None
    ellipse = fit_ellipse(points)
    if ellipse and fit_error >= .8*ellipse[1]:
        return None
    cap_points = points[abs((points-q[:2]) @ axis) >= q[3]/2-q[4]/2]
    if len(cap_points) < 6:
        return None
    round_error = np.sqrt(np.mean(_line_distance(q, cap_points, True)**2))
    square_error = np.sqrt(np.mean(_line_distance(butt, cap_points, False)**2))
    if round_error >= .8*square_error:
        return None
    ends = q[:2]+np.array([-1, 1])[:, None]*axis*q[3]/2+[mask.x0-pad, mask.y0-pad]
    curve = np.linspace(ends[0], ends[1], 4)
    full = Mask.from_full(candidate)
    full.x0 += int(low[0])+mask.x0-pad
    full.y0 += int(low[1])+mask.y0-pad
    return Stroke([curve], float(2*q[4]), full, hidden is not None, (hidden[0],) if hidden else ())


def _thin(mask):
    """Zhang–Suen thinning; numpy only, preserving the core dependency set."""
    a = np.pad(mask, 1).copy()
    while True:
        changed = False
        for phase in (0, 1):
            p = [a[:-2, 1:-1], a[:-2, 2:], a[1:-1, 2:], a[2:, 2:],
                 a[2:, 1:-1], a[2:, :-2], a[1:-1, :-2], a[:-2, :-2]]
            count = np.add.reduce(p, dtype=np.uint8)
            turns = np.add.reduce([~p[i] & p[(i+1) % 8] for i in range(8)], dtype=np.uint8)
            if phase == 0:
                corner = ~(p[0] & p[2] & p[4]) & ~(p[2] & p[4] & p[6])
            else:
                corner = ~(p[0] & p[2] & p[6]) & ~(p[0] & p[4] & p[6])
            remove = a[1:-1, 1:-1] & (count >= 2) & (count <= 6) & (turns == 1) & corner
            if remove.any():
                a[1:-1, 1:-1][remove] = False
                changed = True
        if not changed:
            return a[1:-1, 1:-1]


def _chain(skeleton, radius):
    coords = np.argwhere(skeleton)
    lookup = {tuple(point): i for i, point in enumerate(coords)}
    graph = {i: set() for i in range(len(coords))}
    for i, (y, x) in enumerate(coords):
        for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
            j = lookup.get((y+dy, x+dx))
            if j is None:
                continue
            if dy and dx and ((y, x+dx) in lookup or (y+dy, x) in lookup):
                continue  # no diagonal shortcuts across pixel staircases
            graph[i].add(j)
    # Prune short raster cap spurs, but retain/reject genuine junctions.
    for _ in range(8):
        remove = set()
        for start in [i for i, neighbours in graph.items() if len(neighbours) == 1]:
            run, prev, cur = [], None, start
            while len(run) <= radius:
                run.append(cur)
                nxt = graph[cur] - ({prev} if prev is not None else set())
                if len(nxt) != 1:
                    break
                prev, cur = cur, next(iter(nxt))
                if len(graph[cur]) != 2:
                    if len(graph[cur]) > 2 and len(run) <= radius:
                        remove.update(run)
                    break
        if not remove:
            break
        graph = {i: neighbours-remove for i, neighbours in graph.items() if i not in remove}
    ends = [i for i, neighbours in graph.items() if len(neighbours) == 1]
    if len(ends) != 2 or any(len(n) > 2 or not n for n in graph.values()):
        return None
    order, seen, prev, cur = [], set(), None, ends[0]
    while True:
        order.append(cur)
        seen.add(cur)
        nxt = graph[cur] - ({prev} if prev is not None else set())
        if not nxt:
            break
        prev, cur = cur, next(iter(nxt))
        if cur in seen:
            return None
    if len(order) != len(graph):
        return None
    return coords[order, ::-1].astype(float)


def _refine(points, mask, radius):
    """Centre cross-sections between their subpixel boundary crossings."""
    p = points.copy()
    offsets = np.linspace(-1.8*radius, 1.8*radius, max(25, int(radius*16)))
    step = offsets[1]-offsets[0]
    widths = np.zeros(len(p))
    for _ in range(2):
        smooth = ndi.gaussian_filter1d(p, 1, axis=0, mode="nearest")
        tangent = np.gradient(smooth, axis=0)
        normal = np.c_[-tangent[:, 1], tangent[:, 0]]
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-9)
        samples = p[:, None, :] + normal[:, None, :]*offsets[None, :, None]
        values = ndi.map_coordinates(mask.astype(float), [samples[..., 1], samples[..., 0]],
                                     order=1, mode="constant")
        inside = values >= 0.5
        lo = inside.argmax(axis=1)
        hi = len(offsets)-1-inside[:, ::-1].argmax(axis=1)
        valid = inside.any(axis=1) & (lo > 0) & (hi < len(offsets)-1)
        row = np.flatnonzero(valid)
        l, h = lo[row], hi[row]
        left = offsets[l]-step*(values[row, l]-.5)/np.maximum(values[row, l]-values[row, l-1], 1e-9)
        right = offsets[h]+step*(values[row, h]-.5)/np.maximum(values[row, h]-values[row, h+1], 1e-9)
        p[row] += normal[row]*((left+right)/2)[:, None]
        widths[row] = right-left
    return p, widths


def _flat_terminal(boundary, curves, width, tolerance=.12, front_fraction=.05):
    """Reject a confidently flat source cap before emitting a round-cap curve.

    Whole-shape IoU can hide the two missing corners of a long square-ended
    glyph. A straight front edge spanning most of the width is local evidence;
    the narrow front of a circular cap cannot satisfy that span test.
    """
    for curve, start in ((curves[0], True), (curves[-1], False)):
        end, inner = (curve[0], curve[1]) if start else (curve[-1], curve[-2])
        outward = end-inner
        outward /= max(np.linalg.norm(outward), 1e-9)
        delta = boundary-end
        along = delta @ outward
        cap = boundary[(along > .2*width) & (np.linalg.norm(delta, axis=1) < .9*width)]
        if len(cap) < 3:
            continue
        along = (cap-end) @ outward
        front = cap[along >= along.max()-max(.2, front_fraction*width)]
        if len(front) < 3:
            continue
        _, singular, axes = np.linalg.svd(front-front.mean(axis=0), full_matrices=False)
        if singular[-1]/np.sqrt(len(front)) <= tolerance and np.ptp(front @ axes[0]) >= .75*width:
            return True
    return False


def fit_stroke(mask: Mask, cfg: Config, circles: Sequence[tuple[Mask, Prim]] = (),
               img=None, color=None) -> Stroke | None:
    """Fit one round-cap/join curve; reject holes, junctions and taper.

    Circles must be later-painted occluders. An aligned terminal may continue to
    a circle's centre, but all added visible area must still fit the observation.
    """
    if mask.empty() or mask.area < 80:
        return None
    a = np.pad(mask.a, 1)
    if (ndi.binary_fill_holes(a) != a).any() or ndi.label(a)[1] != 1:
        return None
    radius = float(ndi.distance_transform_edt(a).max())
    if max(a.shape) < 8*radius or mask.area < 24*radius*radius:
        return None
    points = _chain(_thin(a), radius)
    if points is None or len(points) < 12*radius:
        return None
    points, widths = _refine(points, a, radius)
    trim = max(2, int(2*radius))
    core = widths[trim:-trim]
    core = core[core > 0]
    if not len(core):
        return None
    width = float(np.median(core))
    if width < 2 or np.percentile(core, 90) > 1.35*np.percentile(core, 10):
        return None
    # Remove the remaining one-pixel staircase along the tangent before fitting;
    # cross-section refinement already established the subpixel normal position.
    smoothed = ndi.gaussian_filter1d(points, 1, axis=0, mode="nearest")
    smoothed[[0, -1]] = points[[0, -1]]
    points = smoothed + [mask.x0-1, mask.y0-1]
    covers = []
    for end, inner in ((0, min(8, len(points)-1)), (-1, max(-9, -len(points)))):
        direction = points[end]-points[inner]
        direction /= max(np.linalg.norm(direction), 1e-9)
        choices = []
        for cover, circle in circles if cfg.complete_hidden else ():
            delta = np.array([circle.cx, circle.cy])-points[end]
            along = float(delta @ direction)
            across = abs(float(direction[0]*delta[1]-direction[1]*delta[0]))
            if along > 0 and np.linalg.norm(delta) <= circle.rx+1.5*width and across <= width/2:
                # Proximity alone is insufficient: a deliberate gap must not
                # become a connection. Require terminal contact through at most
                # the two-pixel antialias halo before inferring hidden geometry.
                half = int(np.ceil(1.5*width)) + 2
                terminal = Mask(np.zeros((2*half+1, 2*half+1), bool),
                                int(np.floor(points[end, 1]))-half,
                                int(np.floor(points[end, 0]))-half)
                contact = ndi.binary_dilation(crop_like(mask, terminal), iterations=2)
                if not (contact & crop_like(cover, terminal)).any():
                    continue
                choices.append((along, cover, circle))
        if choices:
            _, cover, circle = min(choices, key=lambda item: item[0])
            centre = np.array([[circle.cx, circle.cy]])
            points = np.vstack([centre, points]) if end == 0 else np.vstack([points, centre])
            covers.append(cover)
    curves = fit_open(points, min(cfg.simplify, 0.45))
    if not curves or len(curves) > 40:
        return None
    dense = np.vstack([bez(c, np.linspace(0, 1, max(8, int(np.linalg.norm(np.diff(c, axis=0), axis=1).sum()/0.3))))
                       for c in curves])
    low = np.minimum([mask.x0, mask.y0], np.floor(dense.min(axis=0)-width-2)).astype(int)
    high = np.maximum([mask.bbox[3], mask.bbox[2]], np.ceil(dense.max(axis=0)+width+2)).astype(int)
    w, h = high-low
    if w > 3*mask.a.shape[1]+4*radius or h > 3*mask.a.shape[0]+4*radius:
        return None
    reference = Mask(np.zeros((h, w), bool), low[1], low[0])
    observed = crop_like(mask, reference)
    occluded = np.zeros((h, w), bool)
    for cover in covers:
        occluded |= crop_like(cover, reference)
    yy, xx = np.indices((h, w))
    distances = cKDTree(dense).query(np.c_[xx.ravel()+low[0], yy.ravel()+low[1]])[0].reshape(h, w)
    best = None
    for candidate_width in np.arange(max(1, width-1), width+1.01, 0.25):
        candidate = distances <= candidate_width/2
        visible, expected = candidate & ~occluded, observed & ~occluded
        iou = (visible & expected).sum()/max(1, (visible | expected).sum())
        if best is None or iou > best[0]:
            best = (iou, candidate_width, candidate)
    if best[0] < 0.95:
        return None
    visible = best[2] & ~occluded
    expected = observed & ~occluded
    perimeter = (expected & ~ndi.binary_erosion(expected)).sum()
    deviation = (visible ^ expected).sum()/max(1, perimeter)
    if best[0] < 0.96 and deviation > 0.3:
        return None  # e.g. wide square-ended lettering is not a round-cap stroke
    field = _coverage_field(np.pad(mask.a, 6), mask, 6, img, color)
    source = [] if field is None else contours_xy(field)
    if len(source) == 1:
        boundary = source[0]+[mask.x0-6, mask.y0-6]
        if _flat_terminal(boundary, curves, best[1]):
            return None
    full = Mask.from_full(best[2])
    full.x0 += int(low[0])
    full.y0 += int(low[1])
    return Stroke(curves, float(best[1]), full, bool(covers))


def _curve_distance(curve, points):
    """Euclidean distance to a cubic, including its finite round-cap endpoints."""
    dense = bez(curve, np.linspace(0, 1, 100))
    t = cKDTree(dense).query(points)[1]/99
    for _ in range(6):
        delta = bez(curve, t)-points
        first, second = _d1(curve, t), _d2(curve, t)
        numerator = (delta*first).sum(axis=1)
        denominator = (first*first).sum(axis=1)+(delta*second).sum(axis=1)
        t = np.clip(t-numerator/np.maximum(denominator, 1e-8), 0, 1)
    return np.linalg.norm(bez(curve, t)-points, axis=1)


def fit_crossed_curve(mask: Mask, cfg: Config, overlays: Sequence[Mask] = (),
                      img=None, color=None) -> Stroke | None:
    """Fit a short curve whose terminal is clipped by a proven later closed stroke.

    The caller establishes the occluder's native loop geometry and paint order.
    Fit only free boundaries, keeping a visible round cap to constrain the model;
    every inferred exposed pixel must still match the original observation.
    """
    if not cfg.strokes or not cfg.complete_hidden or not overlays or mask.area < 80:
        return None
    a = np.pad(mask.a, 1)
    if ndi.label(a)[1] != 1 or np.any(ndi.binary_fill_holes(a) != a):
        return None
    radius = float(ndi.distance_transform_edt(a).max())
    if max(a.shape) < 8*radius or mask.area < 24*radius*radius:
        return None
    points = _chain(_thin(a), radius)
    if points is None or len(points) < 12*radius:
        return None
    points, widths = _refine(points, a, radius)
    trim = max(2, int(2*radius))
    core = widths[trim:-trim]
    if not len(core) or np.percentile(core, 10) < 2 or np.percentile(core, 90) > 1.35*np.percentile(core, 10):
        return None
    width = float(np.median(core))
    points += [mask.x0-1, mask.y0-1]
    # Keep the completion local; do not infer an unconstrained long hidden tail.
    pad = int(np.ceil(2*width))+3
    ref = Mask(np.zeros(tuple(np.array(mask.a.shape)+2*pad), bool), mask.y0-pad, mask.x0-pad)
    cover = np.zeros(ref.a.shape, bool)
    for overlay in overlays:
        cover |= crop_like(overlay, ref)
    yy, xx = np.indices(ref.a.shape)
    grid = np.c_[xx.ravel()+ref.x0, yy.ravel()+ref.y0]
    ends = points[[0, -1]]
    contact = [np.any(cover & (np.hypot(xx+ref.x0-end[0], yy+ref.y0-end[1]) < width)) for end in ends]
    if sum(contact) != 1:
        return None  # one exposed cap is needed; both hidden ends are ambiguous
    boundary = contours_xy(mask.a)[0]+[mask.x0, mask.y0]
    near = ndi.binary_dilation(cover, iterations=2)
    local = np.rint(boundary-[ref.x0, ref.y0]).astype(int)
    free = boundary[~near[local[:, 1], local[:, 0]]]
    if len(free) < 40 or len(free) < .65*len(boundary):
        return None
    distance = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    u = distance/distance[-1]
    basis = np.c_[(1-u)**3, 3*(1-u)**2*u, 3*(1-u)*u**2, u**3]
    curve = np.linalg.lstsq(basis, points, rcond=None)[0]
    initial = np.r_[curve.ravel(), width]
    span = np.r_[np.full(8, min(4., width/2)), min(1.5, width/4)]
    fit = least_squares(lambda q: _curve_distance(q[:8].reshape(4, 2), free)-q[8]/2,
                        initial, bounds=(initial-span, initial+span), max_nfev=80)
    if np.sqrt(np.mean(fit.fun**2)) > .35 or np.max(np.abs(fit.fun)) > .85:
        return None
    curve, width = fit.x[:8].reshape(4, 2), float(fit.x[8])
    if _flat_terminal(free, [curve], width, tolerance=.3, front_fraction=.1):
        return None
    # Subpixel source edges retain the corners that binary ownership may round
    # away on a short, oblique flat cap. Preserve that local negative evidence.
    field = _coverage_field(np.pad(mask.a, 6), mask, 6, img, color)
    source = [] if field is None else contours_xy(field)
    if len(source) == 1:
        boundary = source[0]+[mask.x0-6, mask.y0-6]
        local = np.rint(boundary-[ref.x0, ref.y0]).astype(int)
        free_source = boundary[~near[local[:, 1], local[:, 0]]]
        if _flat_terminal(free_source, [curve], width, tolerance=.15):
            return None
    distances = _curve_distance(curve, grid).reshape(ref.a.shape)
    predicted = distances <= width/2
    observed = crop_like(mask, ref)
    exposed = ~cover
    iou = np.count_nonzero(predicted & observed & exposed)/max(1, np.count_nonzero((predicted | observed) & exposed))
    missing = predicted & ~observed
    if (iou < .95 or np.any(missing & exposed & ~ndi.binary_dilation(observed))
            or np.any(observed & ~ndi.binary_dilation(predicted))
            or np.count_nonzero(missing & cover) < width
            or np.count_nonzero(missing & cover) > 2*width*width):
        return None
    return Stroke([curve], width, Mask(predicted, ref.y0, ref.x0), True)
