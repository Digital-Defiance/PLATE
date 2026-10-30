"""Pool a long open arc and its small exposed cap across a proven closed stroke."""
from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import least_squares

from ..geometry import contours_xy
from ..masks import Mask, crop_like, touches
from .strokes import (Stroke, fit_closed, _chain, _thin, _refine,
                      _curve_distance, _coverage_field, _flat_terminal)


@dataclass
class RecoveredCurve:
    ids: tuple[int, int]
    stroke: Stroke


def fit_fragmented_curve(main, tail, cfg, overlay, img=None, color=None):
    """Validate the complete curve, rather than joining same-colour neighbours.

    The caller proves that overlay is a later native closed stroke. Both masks
    retain disjoint visible ownership; the fitted tube must explain their free
    contours and cannot infer an exposed gap or a long hidden continuation.
    """
    if not cfg.strokes or not cfg.complete_hidden or main.area < 80 or tail.area < 6:
        return None
    if tail.area > .15*main.area:
        return None
    for mask in (main, tail):
        a = np.pad(mask.a, 1)
        if ndi.label(a)[1] != 1 or np.any(ndi.binary_fill_holes(a) != a):
            return None
    a = np.pad(main.a, 1)
    radius = float(ndi.distance_transform_edt(a).max())
    if max(a.shape) < 8*radius or main.area+tail.area < 20*radius*radius:
        return None
    points = _chain(_thin(a), radius)
    if points is None or len(points) < 12*radius:
        return None
    points, widths = _refine(points, a, radius)
    trim = max(2, int(2*radius))
    # Sections cut by the overlay are not measurements of the stroke's width.
    seed_ref = Mask(a, main.y0-1, main.x0-1)
    separation = ndi.distance_transform_edt(~crop_like(overlay, seed_ref))
    clear = ndi.map_coordinates(separation, [points[:, 1], points[:, 0]], order=1, mode='constant') > radius+2
    core = widths[trim:-trim][clear[trim:-trim]]
    if len(core) < 12 or np.percentile(core, 10) < 2 or np.percentile(core, 90) > 1.35*np.percentile(core, 10):
        return None
    width = float(np.median(core))
    points += [main.x0-1, main.y0-1]
    y, x = np.nonzero(tail.a)
    cap = np.array([x.mean()+tail.x0, y.mean()+tail.y0])
    if np.linalg.norm(points[0]-cap) < np.linalg.norm(points[-1]-cap):
        points = points[::-1]
    if np.linalg.norm(points[-1]-cap) > 1.5*width:
        return None
    low = np.minimum([main.x0, main.y0], [tail.x0, tail.y0])-int(np.ceil(2*width))-3
    high = np.maximum([main.bbox[3], main.bbox[2]], [tail.bbox[3], tail.bbox[2]])+int(np.ceil(2*width))+3
    ref = Mask(np.zeros(tuple((high-low)[::-1]), bool), low[1], low[0])
    cover = crop_like(overlay, ref)
    yy, xx = np.indices(ref.a.shape)
    end_distance = [np.hypot(xx+ref.x0-end[0], yy+ref.y0-end[1]) for end in points[[0, -1]]]
    if np.any(cover & (end_distance[0] < width)) or not np.any(cover & (end_distance[1] < width)):
        return None
    observed = crop_like(main, ref) | crop_like(tail, ref)
    if ndi.label(observed)[1] != 2:
        return None
    boundaries = []
    for mask, halo in ((main, 2), (tail, 1)):
        boundary = contours_xy(mask.a)[0]+[mask.x0, mask.y0]
        local = np.rint(boundary-low).astype(int)
        free = boundary[~ndi.binary_dilation(cover, iterations=halo)[local[:, 1], local[:, 0]]]
        if len(free) < (40 if mask is main else 3):
            return None
        boundaries.append(free)
    free = np.vstack(boundaries)
    u = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    u /= u[-1]
    basis = np.c_[(1-u)**3, 3*(1-u)**2*u, 3*(1-u)*u**2, u**3]
    curve = np.linalg.lstsq(basis, points, rcond=None)[0]
    delta = cap-curve[-1]
    curve[-1] += delta
    curve[-2] += .6*delta
    initial = np.r_[curve.ravel(), width]
    span = np.r_[np.full(8, min(4., width/2)), min(1.5, width/4)]
    fit = least_squares(lambda q: _curve_distance(q[:8].reshape(4, 2), free)-q[8]/2,
                        initial, bounds=(initial-span, initial+span), max_nfev=80)
    if np.sqrt(np.mean(fit.fun**2)) > .35 or np.max(np.abs(fit.fun)) > .85:
        return None
    curve, width = fit.x[:8].reshape(4, 2), float(fit.x[8])
    if _flat_terminal(boundaries[0], [curve], width, tolerance=.3, front_fraction=.1):
        return None
    field = _coverage_field(np.pad(main.a, 6), main, 6, img, color)
    source = [] if field is None else contours_xy(field)
    if len(source) == 1:
        boundary = source[0]+[main.x0-6, main.y0-6]
        local = np.rint(boundary-low).astype(int)
        near = ndi.binary_dilation(cover, iterations=2)
        if _flat_terminal(boundary[~near[local[:, 1], local[:, 0]]], [curve], width, tolerance=.15):
            return None
    distances = _curve_distance(curve, np.c_[xx.ravel()+low[0], yy.ravel()+low[1]]).reshape(ref.a.shape)
    predicted = distances <= width/2
    exposed = ~cover
    missing = predicted & ~observed
    iou = np.count_nonzero(predicted & observed & exposed)/max(1, np.count_nonzero((predicted | observed) & exposed))
    clear_core = (distances < width/2-1) & ~ndi.binary_dilation(cover)
    crossing_halo = ndi.binary_dilation(cover, iterations=2)
    # Quantized crossing fringes can fall outside both binary masks. Actual
    # exposed stroke cores still need source evidence, even within that halo.
    if img is not None and color is not None:
        source_core = (distances < width/2-1) & exposed & missing
        y, x = np.nonzero(source_core)
        gy, gx = y+low[1], x+low[0]
        if (np.any(gy < 0) or np.any(gx < 0) or np.any(gy >= img.alpha.shape[0]) or np.any(gx >= img.alpha.shape[1])
                or np.any(img.alpha[gy, gx] < 230)
                or np.any(np.linalg.norm(img.rgb[gy, gx].astype(float)-color, axis=1) > 35)):
            return None
    if (iou < .95 or np.any(missing & exposed & ~ndi.binary_dilation(observed) & ~crossing_halo)
            or np.any(clear_core & ~observed) or np.any(observed & ~ndi.binary_dilation(predicted))
            or np.count_nonzero(missing & cover) < width
            or np.count_nonzero(missing & cover) > min(3*width*width, .3*predicted.sum())):
        return None
    return Stroke([curve], width, Mask(predicted, low[1], low[0]), True, (overlay,))


def recover(seg, roots, img, cfg, known_loops):
    """Return one supported sibling merge; pipeline rebuilds ownership afterwards."""
    if not cfg.strokes or not cfg.complete_hidden:
        return None
    def paint(ids):
        for sid in ids:
            yield sid
            yield from paint(seg.shapes[sid].children)
    rank = {sid: i for i, sid in enumerate(paint(roots))}
    candidates = [s for s in seg.shapes if s.grad is None and not s.children]
    pairs = [(a, b) for a in candidates for b in candidates
             if a.id != b.id and a.color == b.color and a.parent == b.parent
             and a.vis.area >= 80 and 6 <= b.vis.area <= .15*a.vis.area]
    if not pairs:
        return None
    closed = []
    for s in seg.shapes:
        if s.grad is not None or s.sil.area >= .6*seg.rid.size:
            continue
        if s.vis in known_loops or fit_closed(s.full, cfg, img, s.color,
                                              [o.vis for o in seg.shapes if rank[o.id] > rank[s.id]]) is not None:
            closed.append(s)
    for a, b in pairs:
        for cover in closed:
            if cover.id in (a.id, b.id) or rank[cover.id] <= max(rank[a.id], rank[b.id]):
                continue
            if not touches(a.vis, cover.vis, seg.rid.shape, 2) or not touches(b.vis, cover.vis, seg.rid.shape, 2):
                continue
            fitted = fit_fragmented_curve(a.vis, b.vis, cfg, cover.vis, img, a.color)
            if fitted is not None:
                return RecoveredCurve((a.id, b.id), fitted)
    return None
