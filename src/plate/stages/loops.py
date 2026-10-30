"""Pool disconnected thin arcs only when a shared loop is hidden by observed paint."""
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import least_squares

from ..geometry import Prim, contours_xy, fit_ellipse
from ..masks import Mask, crop_like, touches
from .complete import occludes
from .strokes import ClosedStroke, _chain, _coverage_field, _ellipse_distance, _refine, _thin


@dataclass
class Loop:
    ids: tuple[int, ...]
    stroke: ClosedStroke


def _arc(shape):
    if shape.grad is not None or shape.children or shape.vis.area < 100:
        return None
    a = np.pad(shape.vis.a, 1)
    if ndi.label(a, np.ones((3, 3)))[1] != 1 or np.any(ndi.binary_fill_holes(a) != a):
        return None
    radius = float(ndi.distance_transform_edt(a).max())
    if max(a.shape) < 8*radius:
        return None
    chain = _chain(_thin(a), radius)
    if chain is None or len(chain) < 12*radius:
        return None
    points, widths = _refine(chain, a, radius)
    trim = max(2, int(2*radius))
    core = widths[trim:-trim]
    if not len(core) or np.percentile(core, 10) < 2 or np.percentile(core, 90) > 1.35*np.percentile(core, 10):
        return None
    points += [shape.vis.x0-1, shape.vis.y0-1]
    # Two almost-straight marks do not constrain an ellipse's hidden curvature.
    u, v = points[8]-points[0], points[-1]-points[-9]
    turn = np.arccos(np.clip(u @ v/max(1e-9, np.linalg.norm(u)*np.linalg.norm(v)), -1, 1))
    if turn < np.deg2rad(30):
        return None
    return points[trim:-trim], float(np.median(core)), points[[0, -1]]


def recover(seg, roots, img, cfg):
    """Return one supported loop merge, leaving all ownership mutation to pipeline.

    Each seed fragment needs T-junction evidence at BOTH terminals. The complete
    model must preserve the observed arcs and every added pixel beyond a one-pixel
    raster fringe must lie under actual non-background artwork. Separate contour
    arrays never acquire artificial connecting tangents.
    """
    if not cfg.strokes or not cfg.complete_hidden:
        return None
    canvas = img.alpha.shape
    excluded = {sid for sid in roots if seg.shapes[sid].sil.area >= .6*np.prod(canvas)}
    arcs = []
    for shape in seg.shapes:
        if shape.id in excluded:
            continue
        data = _arc(shape)
        if data is not None:
            arcs.append((shape, *data))
    for left, right in combinations(arcs, 2):
        a, b = left[0], right[0]
        if a.parent != b.parent or a.color != b.color or max(left[2], right[2]) > 1.2*min(left[2], right[2]):
            continue
        ids = {a.id, b.id}
        points = np.vstack([left[1], right[1]])
        initial = fit_ellipse(points)
        if initial is None:
            continue
        pr, residual, coverage = initial
        width = (left[2]+right[2])/2
        if residual > .7 or coverage < np.pi or width > .15*min(pr.rx, pr.ry):
            continue
        # A local occluder must explain each observed termination. A background
        # surrounding a deliberately open arc supplies no T-junction proof.
        supported = True
        for shape, _, w, ends in (left, right):
            covers = [s for s in seg.shapes if s.id not in ids | excluded
                      and touches(shape.vis, s.vis, canvas, 2) and occludes(shape.vis, s.vis, canvas)]
            for end in ends:
                half = int(np.ceil(1.5*w))+2
                ref = Mask(np.zeros((2*half+1, 2*half+1), bool), int(end[1])-half, int(end[0])-half)
                yy, xx = np.indices(ref.a.shape)
                terminal = (xx+ref.x0-end[0])**2+(yy+ref.y0-end[1])**2 <= (1.5*w+2)**2
                if not any(np.any(crop_like(s.vis, ref) & terminal) for s in covers):
                    supported = False
                    break
            if not supported:
                break
        if not supported:
            continue
        # Fit the two free stroke edges, not just the skeleton estimate.
        q0 = np.array([pr.cx, pr.cy, pr.rx, pr.ry, np.deg2rad(pr.angle), width])
        foreign = (seg.rid >= 0) & ~np.isin(seg.rid, list(ids | excluded))
        near = ndi.binary_dilation(foreign, iterations=2)
        boundaries = []
        fields = {}
        for shape in (a, b):
            field = _coverage_field(np.pad(shape.vis.a, 6), shape.vis, 6, img, shape.color)
            fields[shape.id] = field
            contours = contours_xy(shape.vis.a) if field is None else contours_xy(field)
            origin = [shape.vis.x0, shape.vis.y0] if field is None else [shape.vis.x0-6, shape.vis.y0-6]
            for c in contours:
                c = c+origin
                xy = np.rint(c).astype(int)
                boundaries.append(c[~near[xy[:, 1], xy[:, 0]]])
        boundary = np.vstack(boundaries)
        if len(boundary) < 40:
            continue
        span = np.array([3, 3, 4, 4, .1, 1.5])
        fit = least_squares(lambda q: np.abs(_ellipse_distance(boundary, q[:5]))-q[5]/2,
                            q0, bounds=(q0-span, q0+span), max_nfev=60)
        q = fit.x
        if np.sqrt(np.mean(fit.fun**2)) > .35 or np.max(np.abs(fit.fun)) > .85:
            continue
        pr = Prim('ellipse', *q[:4], angle=np.rad2deg(q[4]))
        # Rasterize the ENTIRE fitted loop; hidden extents cannot be clipped to
        # the observed fragments' boxes or the image's boundaries.
        angle = q[4]
        rx = np.hypot(q[2]*np.cos(angle), q[3]*np.sin(angle))+q[5]/2+3
        ry = np.hypot(q[2]*np.sin(angle), q[3]*np.cos(angle))+q[5]/2+3
        x0, y0 = np.floor([q[0]-rx, q[1]-ry]).astype(int)
        x1, y1 = np.ceil([q[0]+rx, q[1]+ry]).astype(int)+1
        if x0 < 0 or y0 < 0 or x1 > canvas[1] or y1 > canvas[0]:
            continue
        yy, xx = np.indices((y1-y0, x1-x0))
        distance = np.abs(_ellipse_distance(np.c_[xx.ravel()+x0, yy.ravel()+y0], q[:5])).reshape(yy.shape)
        model = Mask(distance <= q[5]/2, y0, x0)
        # Reattach small fragments of this same loop only after its large arcs
        # established the geometry. Satellite discs must fit as whole objects.
        allowance = ndi.binary_dilation(model.a)
        for s in seg.shapes:
            if s.id in ids or s.parent != a.parent or s.color != a.color or s.children or s.grad is not None:
                continue
            if np.count_nonzero(crop_like(s.vis, model) & allowance) >= .99*s.vis.area:
                ids.add(s.id)
        observed = np.zeros(model.a.shape, bool)
        for sid in ids:
            observed |= crop_like(seg.shapes[sid].vis, model)
        foreign = (seg.rid >= 0) & ~np.isin(seg.rid, list(ids | excluded))
        cover = foreign[y0:y1, x0:x1]
        missing = model.a & ~observed
        # A one-pixel visible gap can fit within the binary raster tolerance.
        # Check the source's exposed stroke core as well: missing alpha or a
        # background colour is evidence of a real opening, however narrow.
        core = (distance < q[5]/2-1) & ~ndi.binary_dilation(cover, iterations=2)
        alpha = img.alpha[y0:y1, x0:x1]
        evidence = np.zeros(model.a.shape)
        for sid in ids:
            shape = seg.shapes[sid]
            field = fields.get(sid)
            if sid not in fields:
                field = _coverage_field(np.pad(shape.vis.a, 6), shape.vis, 6, img, shape.color)
            if field is not None:
                evidence = np.maximum(evidence, ndi.map_coordinates(
                    field, [yy+y0-shape.vis.y0+6, xx+x0-shape.vis.x0+6],
                    order=0, mode='constant'))
        # Tiny retained fragments can sit entirely among several background
        # colours, preventing a local unmixing estimate. Their owned solid cores
        # still have direct RGB evidence; allow collinear Lanczos overshoot, as
        # in _coverage_field, only on pixels already owned by these fragments.
        rgb = img.rgb[y0:y1, x0:x1].astype(float)
        bg = np.full(3, 255.) if np.mean(a.color) < 128 else np.zeros(3)
        delta = np.asarray(a.color)-bg
        projection = ((rgb-bg) @ delta)/max(1, delta @ delta)
        solid = (projection >= .9) & (np.linalg.norm(rgb-(bg+projection[..., None]*delta), axis=2) <= 12)
        evidence[observed & solid] = 1
        if np.any(core & ((alpha < 230) | (evidence < .9))):
            continue
        # Never complete through an exposed gap, or replace unrelated paint.
        if np.any(missing & ~cover & ~ndi.binary_dilation(observed)):
            continue
        free = ~cover
        if np.count_nonzero((model.a ^ observed) & free)/max(1, np.count_nonzero((model.a | observed) & free)) > .08:
            continue
        if np.any(observed & ~ndi.binary_dilation(model.a)) or observed.sum() < .3*model.area:
            continue
        return Loop(tuple(sorted(ids)), ClosedStroke(pr, float(q[5]), model, True))
    return None
