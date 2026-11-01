"""Stage 2: containment tree, occlusion analysis and paint order.

* parent(B) = smallest shape whose hole-filled silhouette contains B  -> nested groups
* siblings that touch are analysed for occlusion (stage 3 completes hidden parts and
  tells us who hides whom) -> paint order via topological sort
* lower siblings get a small "bleed" under their neighbours so no hairline seams appear
"""
from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np
from scipy import ndimage as ndi

from ..config import Config
from ..geometry import Prim, fit_circle, raster_prim
from ..masks import Mask, contains, touches, crop_like, inter_area
from ..scene import Segmentation, Shape
from .complete import occludes, try_complete


def _silhouettes(shapes: list[Shape], transparent: np.ndarray) -> None:
    for s in shapes:
        f = s.vis.filled()
        y0, x0 = f.y0, f.x0
        h, w = f.a.shape
        tr = transparent[y0:y0 + h, x0:x0 + w]
        vis = s.vis.to_full(transparent.shape)[y0:y0 + h, x0:x0 + w]
        a = f.a & ~tr
        # A hole-fill normally keeps pixels this shape is painted *behind* (a later
        # sibling/child draws over them). But a genuine perforation that merely
        # contains a floating opaque island (e.g. a plate hole with a disc inside)
        # must stay a hole. `& ~tr` re-opens the transparent part, yet the island's
        # own opaque footprint survives as this colour and leaves a stray component.
        # Examine each filled region before removing transparency. A majority
        # transparent region is a perforation, but so is one with a clear alpha
        # void surrounded mostly by opaque artwork. A fully opaque cover gives
        # no such evidence. Erosion distinguishes a clear void from a thin
        # antialias fringe, which must not reopen the whole painted interior.
        filled_region = f.a & ~vis
        if filled_region.any():
            lbl, n = ndi.label(filled_region)
            for k in range(1, n + 1):
                comp = lbl == k
                alpha_void = comp & tr
                clear_void = alpha_void.any() and ndi.binary_erosion(alpha_void, iterations=2).any()
                if alpha_void.sum() > 0.5 * comp.sum() or clear_void:
                    a = a & ~comp
        s.sil = Mask(a, y0, x0)
        s.full = Mask(a.copy(), y0, x0)
        if s.verified_prim is not None:
            model = raster_prim(s.verified_prim, transparent.shape) | s.vis.to_full(transparent.shape)
            s.sil = s.full = Mask.from_full(model)
            s.prim, s.completed = s.verified_prim, True


def _assign_parents(shapes: list[Shape]) -> None:
    if not shapes:
        return
    bb = np.array([s.sil.bbox for s in shapes])
    for B in shapes:
        b = B.vis.bbox
        ok = (bb[:, 0] <= b[0]) & (bb[:, 1] <= b[1]) & (bb[:, 2] >= b[2]) & (bb[:, 3] >= b[3])
        best = None
        for i in np.flatnonzero(ok):
            A = shapes[i]
            if A.id == B.id:
                continue
            if (A.sil.area, A.id) <= (B.sil.area, B.id):
                continue
            if contains(A.sil, B.vis):
                if best is None or (A.sil.area, A.id) < (best.sil.area, best.id):
                    best = A
        B.parent = best.id if best else None
    for s in shapes:
        s.children = []
    for s in shapes:
        if s.parent is not None:
            shapes[s.parent].children.append(s.id)


def _toposort(ids: list[int], edges: set[tuple[int, int]], shapes: list[Shape], stable=False) -> list[int]:
    """edges (a, b): a is painted before b. Larger shapes first when unconstrained."""
    remaining = set(ids)
    out: list[int] = []
    edges = {e for e in edges if e[0] in remaining and e[1] in remaining}
    positions = {sid: i for i, sid in enumerate(ids)}
    key = positions.__getitem__ if stable else lambda i: (-shapes[i].sil.area, i)
    while remaining:
        ready = [i for i in remaining if not any(e[1] == i for e in edges)]
        if not ready:  # cycle: break by dropping incoming edges of the largest shape
            victim = min(remaining, key=key)
            edges = {e for e in edges if e[1] != victim}
            continue
        nxt = min(ready, key=key)
        out.append(nxt)
        remaining.discard(nxt)
        edges = {e for e in edges if e[0] != nxt}
    return out


def merge_fragments(seg: Segmentation, transparent: np.ndarray, cfg: Config) -> Segmentation:
    """Reunite redundant parent islands or supported flat sibling fragments.

    Same colour supplies candidates, not permission to merge. The shared outline
    must preserve every visible fragment and add hidden area beneath neighbours
    established by the relative T-junction test. Rebuild order after each merge.
    """
    if not cfg.complete_hidden:
        return seg
    H, W = transparent.shape
    painted_interiors = {}

    def painted_inside(shape, earlier=False):
        key = shape.id, earlier
        if key not in painted_interiors:
            primitive = shape.prim
            if cfg.snap_primitives and primitive is None:
                from .primitives import snap
                primitive = snap(shape.full, cfg)
            if cfg.snap_primitives and primitive is not None:
                painted = raster_prim(primitive, (H, W))
                # OpenCV's inclusive raster edge plus antialias coverage can
                # account for two border rows; interior overpainting cannot.
                model = Mask.from_full(ndi.binary_erosion(painted, iterations=2))
            elif earlier:
                # Confident stroke geometry ignores filled-path bleed. Otherwise
                # preserve islands that may repair a traced curve's fringe.
                stroke = None
                if cfg.strokes and shape.grad is None:
                    from .strokes import fit_stroke
                    stroke = fit_stroke(shape.full, cfg)
                if stroke is not None:
                    model = Mask.from_full(ndi.binary_erosion(stroke.full.to_full((H, W)), iterations=2))
                else:
                    tolerance = max(1, int(np.ceil(cfg.simplify+cfg.smooth)))
                    model = (shape.draw or shape.full).dilated(tolerance, (H, W))
            else:
                model = Mask.from_full(ndi.binary_erosion(shape.full.to_full((H, W)), iterations=2))
            painted_interiors[key] = model
        return painted_interiors[key]

    for child in seg.shapes:
        if child.parent is None or child.children or child.grad is not None:
            continue
        parent = seg.shapes[child.parent]
        if parent.grad is not None or parent.color != child.color or not contains(parent.full, child.full, 1.):
            continue

        def paints_over(ids):
            for i in ids:
                s = seg.shapes[i]
                if (inter_area(s.full, child.full) or inter_area(painted_inside(s, earlier=True), child.full)
                        or paints_over(s.children)):
                    return True
            return False

        # A same-colour child can repaint an earlier completed sibling. It is
        # redundant only when moving its visible ownership to the parent cannot
        # expose that sibling. Restricted bleed is recomputed after regrouping.
        earlier = parent.children[:parent.children.index(child.id)]
        if paints_over(earlier):
            continue
        # Silhouette filling can retain raster residuals outside the primitive
        # that will actually be emitted. Only merge an island safely inside that
        # painted model; a boundary island may repair an imperfect parent fit.
        if not contains(painted_inside(parent), child.full, 1.):
            continue
        visible = Mask.from_full(parent.vis.to_full((H, W)) | child.vis.to_full((H, W)))
        shapes = [replace(s, vis=visible) if s.id == parent.id else s
                  for s in seg.shapes if s.id != child.id]
        return seg.rebuilt(shapes)
    groups: dict[tuple, list[Shape]] = {}
    for s in seg.shapes:
        if s.grad is None:
            groups.setdefault((s.parent, s.color), []).append(s)
    for (parent, color), members in groups.items():
        if len(members) < 2:
            continue
        ids = {s.id for s in members}
        visible = np.zeros((H, W), bool)
        for s in members:
            visible |= s.vis.to_full((H, W))
        vis = Mask.from_full(visible)
        sil = Mask.from_full(vis.filled().to_full((H, W)) & ~transparent)
        joint = Shape(members[0].id, color, vis, sil, sil=sil)
        covers = [s for s in seg.shapes if s.id not in ids and s.parent == parent
                  and touches(sil, s.sil, (H, W), 2)]
        comp = try_complete(joint, covers, H, W, cfg)
        if comp is None or comp.prim is None:
            continue
        shapes = [joint if s.id == joint.id else s for s in seg.shapes
                  if s.id == joint.id or s.id not in ids]
        return seg.rebuilt(shapes)
    merged = _merge_compound_siblings(seg, transparent, cfg)
    if merged is not seg:
        return merged
    return seg


def merge_ring_ellipses(seg: Segmentation, transparent: np.ndarray, cfg: Config) -> Segmentation:
    """Reunite an interrupted ELLIPTICAL stroke ring left split by every earlier pass.

    Runs AFTER loops.recover/curves so it never pre-empts the rings those stages
    already reunite (keeping their geometry and paint order intact). Same strict
    admission as the compound-sibling circle arm (shared 15deg occluder clusters,
    >=160deg arc, tight scale-keyed RMS) plus the ellipse-specific defences in
    `_fit_ring_ellipse`. Returns a rebuilt segmentation on the first reunion, else
    `seg` unchanged.
    """
    if not cfg.complete_hidden:
        return seg
    return _merge_compound_siblings(seg, transparent, cfg, rings=True)


def _cluster_by_shared_occluder(ids: list[int], occ: dict[int, set[int]]) -> list[list[int]]:
    """Union-find groups of ids whose occluder sets intersect (one shape over both)."""
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            if occ[ids[a]] & occ[ids[b]]:
                parent[find(ids[a])] = find(ids[b])
    groups: dict[int, list[int]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _merge_compound_siblings(seg: Segmentation, transparent: np.ndarray,
                             cfg: Config, rings: bool = False) -> Segmentation:
    """Reunite same-colour sibling fragments of ONE compound object that no primitive fit.

    Runs only after the parent-island and flat-pool branches have had their turn, so
    existing behaviour is untouched. A genuine compound object (an interrupted ring, a
    glyph split by crossing strokes) leaves same-colour fragments that each sit under
    the SAME intervening occluder and whose outer boundaries continue the same circle.
    The admission evidence is the SAME the existing passes require -- the relative
    T-junction test (`complete.occludes`, 15 deg) supplies the occlusion link, and the
    exact-circle fit used by completion supplies the geometric continuation -- so no gate
    is relaxed. Side-by-side tiles (no shared occluder, no common circle) and distinct
    neighbouring arcs (poor common-circle fit) are rejected. The merged result is a
    compound path; a primitive fit is NOT required for this path.
    """
    H, W = transparent.shape
    groups: dict[tuple, list[Shape]] = {}
    for s in seg.shapes:
        if s.grad is None:
            groups.setdefault((s.parent, s.color), []).append(s)
    for (parent, color), members in groups.items():
        if len(members) < 2:
            continue
        member_ids = {s.id for s in members}
        # occluders of each fragment: a non-member whose outline flows past this
        # fragment at their shared boundary (the owner-blessed relative T-junction test).
        occ: dict[int, set[int]] = {}
        for m in members:
            found = set()
            for o in seg.shapes:
                if o.id in member_ids or o.id == m.id:
                    continue
                if touches(m.vis, o.vis, (H, W), 3) and occludes(m.vis, o.vis, (H, W)):
                    found.add(o.id)
            occ[m.id] = found
        # link fragments that share an occluder (same thing is painted over both)
        clusters = _cluster_by_shared_occluder([m.id for m in members], occ)
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            frag = {m.id: m for m in members}
            # A genuine interrupted fragment is NOT already a finished object. If any
            # member snaps to a closed curved/boxed primitive on its own it is a
            # complete shape, not a sliver of a larger one, so leave the group alone.
            if cfg.snap_primitives:
                from .primitives import snap
                complete_member = False
                for cid in cluster:
                    pr = snap(frag[cid].full, cfg)
                    if pr is not None and pr.kind in ("circle", "ellipse", "rect", "rrect"):
                        complete_member = True
                        break
                if complete_member:
                    continue
            # common-circle continuation: the fragments' outer (convex) boundary must
            # lie on one circle. This is the exact-circle fit completion already trusts;
            # distinct arcs (light orbit arcs) or glyphs that merely share an occluder
            # fail it. Normalise the RMS by the radius because disjoint arcs enclose no
            # area (the area-keyed completion tolerance does not apply to open arcs).
            vis = np.zeros((H, W), bool)
            for cid in cluster:
                vis |= frag[cid].vis.to_full((H, W))
            ys, xs = np.nonzero(vis)
            pts = np.c_[xs, ys].astype(np.float32)
            if len(pts) < 8:
                continue
            hull = cv2.convexHull(pts).reshape(-1, 2).astype(np.float64)
            if len(hull) < 5:
                continue
            circ, rms, cov = fit_circle(hull)
            radius = circ.rx
            # The union keeps every member's visible pixels, so no ownership moves and
            # no earlier sibling is uncovered (`rebuilt` asserts this). Merge into one
            # compound shape keyed on the lowest member id.
            first = min(cluster)
            vmask = Mask.from_full(vis)
            cset = set(cluster)
            if radius >= 1 and rms <= 0.02 * radius and cov >= np.deg2rad(160):
                # Circle continuation (unchanged behaviour): emit a compound path.
                joint = Shape(first, color, vmask, vmask, sil=vmask)
                shapes = [joint if s.id == first else s for s in seg.shapes
                          if s.id == first or s.id not in cset]
                return seg.rebuilt(shapes)
            if not rings:
                continue
            # Circle fit rejected. An interrupted ELLIPTICAL ring (same colour arcs
            # on one elongated ellipse that a circle cannot describe) is admitted
            # only through an equally strict fallback: a tight ellipse edge fit,
            # the same >=160deg arc minimum, plausible/non-degenerate axes and a
            # sanitised angle. No circle-arm gate is relaxed; the cluster already
            # carries the shared-occluder (15deg T-junction) evidence. This runs only
            # in the dedicated post-loop ring pass (`rings=True`), AFTER loops.recover
            # has reunited the rings it supports, so loops.recover's results (and their
            # paint order) are never pre-empted. The cover = painted non-member pixels;
            # the ring may only close across pixels under that cover, never across a
            # transparent/background gap (a genuinely open ring stays open).
            cover = (seg.rid >= 0) & ~np.isin(seg.rid, list(cset))
            stroke = _fit_ring_ellipse(vis, H, W, cover)
            if stroke is None:
                continue
            joint = Shape(first, color, vmask, vmask, sil=vmask)
            joint.closed_stroke = stroke
            shapes = [joint if s.id == first else s for s in seg.shapes
                      if s.id == first or s.id not in cset]
            return seg.rebuilt(shapes)
    return seg


def _fit_ring_ellipse(vis: np.ndarray, H: int, W: int, cover: np.ndarray | None = None):
    """Refine a native elliptical stroke ring from pooled same-colour arc pixels.

    Returns a ``strokes.ClosedStroke`` (prim = fitted ellipse, constant width, full =
    the rasterised whole ring) only when the fit is tight, the arc coverage reaches
    the circle arm's 160deg floor, the axes are plausible/elongated/non-degenerate and
    the cv2 angle sanitises cleanly. Otherwise ``None`` (reject, as strict as the
    circle arm). Contaminated pooled hulls (same-colour debris) fail the RMS/axis
    gates; those fragments are already kept in singleton clusters upstream.
    """
    from scipy.optimize import least_squares

    from ..geometry import contours_xy, fit_ellipse
    from .strokes import ClosedStroke, _ellipse_distance

    ys, xs = np.nonzero(vis)
    pts = np.c_[xs, ys].astype(np.float32)
    if len(pts) < 8:
        return None
    hull = cv2.convexHull(pts).reshape(-1, 2).astype(np.float64)
    if len(hull) < 5:
        return None
    initial = fit_ellipse(hull)
    if initial is None:
        return None
    pr, hull_rms, cov = initial
    rx, ry = float(pr.rx), float(pr.ry)
    lo_axis, hi_axis = min(rx, ry), max(rx, ry)
    # Gate the hull fit as tightly as the circle arm (RMS keyed to the ellipse's
    # own scale) and demand the same minimum covered arc.
    if hull_rms > 0.02 * lo_axis or cov < np.deg2rad(160):
        return None
    # Plausibility: non-degenerate minor axis, bounded major axis within the scene,
    # and genuinely elongated (a near-circle belongs to the circle arm, not here).
    if lo_axis < 2.0 or hi_axis > 0.75 * max(H, W) or lo_axis / hi_axis > 0.9:
        return None
    # Sanitise the cv2 angle (a garbage >180deg angle was observed on raw pooled
    # hulls); fold into [0,180). A finite centre is required.
    angle = float(pr.angle) % 180.0
    if not (np.isfinite(pr.cx) and np.isfinite(pr.cy) and np.isfinite(rx) and np.isfinite(ry)):
        return None
    # Reject two CONGRUENT OFFSET ellipses posing as one interrupted ring. A pooled
    # single-ellipse fit cannot tell a genuine ring (whose arcs share one centre)
    # from two near-complete ellipses of the same shape placed side by side (which
    # share an occluder and a plausible common hull but are distinct objects). When
    # two fragments EACH independently determine a confident ellipse (ample arc,
    # tight fit) with matching axes but centres offset by a real fraction of the
    # minor axis, they are duplicates, not fragments -- refuse (as the later
    # loops.recover arc-compatibility test would). Genuine ring fragments are either
    # short (no confident solo fit) or share one centre.
    confident = []
    lbl, ncomp = ndi.label(vis)
    for k in range(1, ncomp + 1):
        comp = lbl == k
        if comp.sum() < 60:
            continue
        cy, cx = np.nonzero(comp)
        chull = cv2.convexHull(np.c_[cx, cy].astype(np.float32)).reshape(-1, 2).astype(np.float64)
        if len(chull) < 5:
            continue
        fe = fit_ellipse(chull)
        if fe is None:
            continue
        fpr, frms, fcov = fe
        if fcov >= np.deg2rad(140) and frms <= 1.0:
            confident.append(fpr)
    for a in range(len(confident)):
        for b in range(a + 1, len(confident)):
            ea, eb = confident[a], confident[b]
            amin, amaj = min(ea.rx, ea.ry), max(ea.rx, ea.ry)
            bmin, bmaj = min(eb.rx, eb.ry), max(eb.rx, eb.ry)
            congruent = (abs(amin - bmin) <= 0.12 * max(amin, bmin)
                         and abs(amaj - bmaj) <= 0.12 * max(amaj, bmaj))
            sep = float(np.hypot(ea.cx - eb.cx, ea.cy - eb.cy))
            if congruent and sep > 0.15 * (amin + bmin) / 2:
                return None
    # Seed a stroke model and refine against the observed arc boundary. Width from
    # the visible arc thickness (twice the median distance-transform ridge).
    dt = ndi.distance_transform_edt(vis)
    width0 = float(2 * np.median(dt[vis]))
    if not np.isfinite(width0) or width0 < 1.0:
        return None
    boundary = np.vstack([c for c in contours_xy(vis)]) if contours_xy(vis) else None
    if boundary is None or len(boundary) < 40:
        return None
    q0 = np.array([pr.cx, pr.cy, rx, ry, np.deg2rad(angle), width0])
    span = np.array([3, 3, 4, 4, .15, 3])
    lower, upper = q0 - span, q0 + span
    lower[2:4] = np.maximum(lower[2:4], .5)
    lower[-1] = max(1., lower[-1])
    fit = least_squares(lambda q: np.abs(_ellipse_distance(boundary, q[:5])) - q[5] / 2,
                        q0, bounds=(lower, upper), max_nfev=80)
    q = fit.x
    width = float(q[5])
    rms = float(np.sqrt(np.mean(fit.fun ** 2)))
    # Final defensive gate on the refined stroke (thicker 5-8px orbit strokes than
    # loops.py's thin arcs, so .9 / 2*width mirror its .35 / .85 scaled up).
    if rms > 0.9 or float(np.max(np.abs(fit.fun))) > 2 * width:
        return None
    rxf, ryf = float(q[2]), float(q[3])
    if min(rxf, ryf) < 2.0 or max(rxf, ryf) > 0.75 * max(H, W) or min(rxf, ryf) / max(rxf, ryf) > 0.9:
        return None
    # Rasterise the ENTIRE ring; reject if its extent leaves the canvas.
    phi = q[4]
    ext_x = np.hypot(q[2] * np.cos(phi), q[3] * np.sin(phi)) + width / 2 + 3
    ext_y = np.hypot(q[2] * np.sin(phi), q[3] * np.cos(phi)) + width / 2 + 3
    x0, y0 = np.floor([q[0] - ext_x, q[1] - ext_y]).astype(int)
    x1, y1 = (np.ceil([q[0] + ext_x, q[1] + ext_y]).astype(int) + 1)
    if x0 < 0 or y0 < 0 or x1 > W or y1 > H:
        return None
    yy, xx = np.indices((y1 - y0, x1 - x0))
    dist = np.abs(_ellipse_distance(np.c_[xx.ravel() + x0, yy.ravel() + y0], q[:5])).reshape(yy.shape)
    full = Mask(dist <= width / 2, y0, x0)
    # Never close the ring across an EXPOSED gap. The reconstructed stroke CORE (well
    # inside the band) must, wherever it is not observed, lie under an occluder
    # (painted non-member pixel). A core pixel that is neither observed nor covered
    # marks a genuine opening -- a transparent/background gap the artist left open --
    # so refuse. This mirrors loops.recover's exposed-core guard; a ring interrupted
    # only by occluders completes, an open ring (even a 1px slit) stays open. The
    # occluder set is dilated by 2px to tolerate the raster fringe at a real
    # T-junction, but a transparent slit is not adjacent to any occluder.
    if cover is not None:
        observed = vis[y0:y1, x0:x1]
        cov = ndi.binary_dilation(cover[y0:y1, x0:x1], iterations=2)
        core = dist <= width / 2 - 1
        exposed = core & ~observed & ~cov
        if exposed.any():
            return None
    ring_prim = Prim("ellipse", float(q[0]), float(q[1]), rxf, ryf, angle=np.rad2deg(q[4]))
    return ClosedStroke(ring_prim, width, full, True)


def build(seg: Segmentation, transparent: np.ndarray, cfg: Config) -> list[int]:
    """Fills parent/children/full/draw on seg.shapes; returns root-level ids in paint order."""
    shapes = seg.shapes
    H, W = transparent.shape
    _silhouettes(shapes, transparent)
    _assign_parents(shapes)
    # A unified gradient can be visible on both sides of a foreground ring.
    # Its centre is ancestor paint, not a separate child that will repaint a
    # hole-filled foreground disc. Preserve those observed gradient openings.
    reopened = False
    for s in shapes:
        if s.parent is None or shapes[s.parent].grad is None or s.verified_prim is not None:
            continue
        parent = crop_like(shapes[s.parent].vis, s.vis)
        holes, count = ndi.label(s.vis.filled().a & ~s.vis.a)
        keep = s.full.a.copy()
        opened = False
        for k in range(1, count+1):
            hole = holes == k
            if ndi.binary_erosion(hole & parent, iterations=2).any():
                ref = Mask(hole, s.vis.y0, s.vis.x0)
                keep &= ~crop_like(ref, s.full)
                reopened = True
                opened = True
        s.full = s.sil = Mask(keep, s.full.y0, s.full.x0)
        if opened:
            s.prim, s.completed = None, False
    if reopened:
        _assign_parents(shapes)
    roots: list[int] = []

    groups: dict[int | None, list[int]] = {}
    for s in shapes:
        groups.setdefault(s.parent, []).append(s.id)

    for parent, sib in groups.items():
        edges: set[tuple[int, int]] = set()
        if cfg.complete_hidden and len(sib) > 1:
            for rid in sorted(sib, key=lambda i: shapes[i].sil.area):
                R = shapes[rid]
                C = [shapes[o] for o in sib if o != rid and touches(R.sil, shapes[o].sil, (H, W), 2)]
                if R.verified_prim is not None:
                    for c in C:
                        if inter_area(R.full, c.vis) >= 6:
                            edges.add((rid, c.id))
                    continue
                if not C:
                    continue
                comp = try_complete(R, C, H, W, cfg)
                if comp is None:
                    continue
                R.full, R.prim, R.completed = comp.full, comp.prim, True
                for o in comp.above:
                    edges.add((rid, o))
        order = _toposort(sib, edges, shapes)
        # bleed: a shape extends ~1px *only where a later neighbour covers it*, so seams
        # can't show the background through. Free edges are untouched.
        r = int(round(cfg.bleed))
        for pos, rid in enumerate(order):
            R = shapes[rid]
            R.draw = R.full
            later = [shapes[o] for o in order[pos + 1:] if touches(R.full, shapes[o].full, (H, W), 2)]
            if r > 0 and later and R.prim is None:
                D = R.full.dilated(r, (H, W))
                cover = np.zeros(D.a.shape, bool)
                for o in later:
                    cover |= crop_like(o.full, D)
                ring = D.a & cover & ~crop_like(R.full, D)
                if ring.any():
                    R.draw = Mask(D.a & (cover | crop_like(R.full, D)), D.y0, D.x0)
                    R.bleed = float(r)
        if parent is None:
            roots = order
        else:
            shapes[parent].children = order
    return roots
