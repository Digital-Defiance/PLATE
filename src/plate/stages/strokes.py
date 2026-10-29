"""Conservative open, constant-width stroke recovery using classical geometry."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from ..bezier import bez, fit_open
from ..config import Config
from ..geometry import Prim
from ..masks import Mask, crop_like


@dataclass
class Stroke:
    curves: list[np.ndarray]
    width: float
    full: Mask
    completed: bool = False


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


def fit_stroke(mask: Mask, cfg: Config, circles: Sequence[tuple[Mask, Prim]] = ()) -> Stroke | None:
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
        for cover, circle in circles:
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
    full = Mask.from_full(best[2])
    full.x0 += int(low[0])
    full.y0 += int(low[1])
    return Stroke(curves, float(best[1]), full, bool(covers))
