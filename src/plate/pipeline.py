"""Pipeline orchestration: image -> layered SVG."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Config
from .bezier import is_flat
from .geometry import GradientFill, GradientStop, Prim
from .imageio import load_image
from .masks import Mask
from .scene import Loaded, Node, Segmentation, Shape
from .stages import emit, name, order
from .stages.primitives import snap, snap_ring
from .stages.segment import segment
from .stages.trace import mask_to_path


@dataclass
class Result:
    svg: str
    nodes: list[Node]
    shapes: list[Shape]
    seg: Segmentation
    loaded: Loaded
    cfg: Config
    stats: dict = field(default_factory=dict)


def _convert_grad(grad: GradientFill, P, S) -> GradientFill:
    """Map a shape's gradient geometry from working pixel-centre coords into SVG coords.
    Positions go through P(v)=(v+0.5)/scale, lengths through S(v)=v/scale. Returns a
    FRESH GradientFill (never mutates the shape's descriptor); stops copied unchanged."""
    def pt(p):
        return None if p is None else (P(p[0]), P(p[1]))
    return GradientFill(
        kind=grad.kind,
        stops=[GradientStop(s.offset, s.rgb) for s in grad.stops],
        start=pt(grad.start), end=pt(grad.end),
        center=pt(grad.center),
        radius=None if grad.radius is None else S(grad.radius),
        focal=pt(grad.focal),
    )


def _closed_node(node, shape, stroke, scale):
    from .stages.primitives import normalize
    pr = normalize(stroke.prim)
    node.kind, node.evenodd, node.d = pr.kind, False, ""
    node.params = dict(cx=(pr.cx+.5)/scale, cy=(pr.cy+.5)/scale)
    if pr.kind == "circle":
        node.params["r"] = pr.rx/scale
    else:
        node.params.update(rx=pr.rx/scale, ry=pr.ry/scale, angle=pr.angle)
    node.stroke_width, node.anchors = stroke.width/scale, 4
    shape.full = shape.draw = stroke.full
    shape.completed |= stroke.completed


def _stroke_node(node, shape, stroke, scale, precision):
    node.kind, node.params, node.evenodd = "path", {}, False
    def number(value):
        text = f"{value:.{precision}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text
    curves = [(c+.5)/scale for c in stroke.curves]
    start = curves[0][0]
    parts = [f"M{number(start[0])} {number(start[1])}"]
    for curve in curves:
        if is_flat(curve):
            parts.append(f"L{number(curve[3, 0])} {number(curve[3, 1])}")
        else:
            parts.append("C"+" ".join(number(v) for v in curve[1:].ravel()))
    node.d = "".join(parts)
    node.stroke_width = stroke.width/scale
    node.anchors = len(curves)+1
    shape.full = shape.draw = stroke.full
    shape.completed |= stroke.completed


def _opacity(shape: Shape, alpha: np.ndarray) -> float:
    """Source opacity of a translucent shape (a 50% overlay, a tinted glass panel).
    Measured on the shape's interior so antialiased rims don't count; opaque shapes
    (every pixel 255) and shapes too thin to have an interior stay at 1.0."""
    from scipy import ndimage as ndi
    m = shape.vis
    y0, x0, y1, x1 = m.bbox
    a = alpha[y0:y1, x0:x1]
    inner = ndi.binary_erosion(m.a, iterations=2)
    if inner.sum() < 20:
        return 1.0
    level = float(np.median(a[inner]))
    return 1.0 if level >= 245 else round(level / 255.0, 3)


def _leaf(shape: Shape, canvas, cfg: Config, scale: float) -> Node | None:
    mask = shape.draw or shape.full
    if mask.empty():
        return None
    prim: Prim | None = None
    if cfg.snap_primitives:
        from .stages.primitives import normalize
        # exact primitive from completion if we have one; otherwise try to snap the silhouette
        prim = normalize(shape.prim) if shape.prim is not None else snap(shape.full, cfg)
    S = lambda v: v / scale
    P = lambda v: (v + 0.5) / scale
    node: Node | None = None
    if prim is not None:
        if prim.kind == "circle":
            node = Node("", "circle", shape.color, params=dict(cx=P(prim.cx), cy=P(prim.cy), r=S(prim.rx)),
                        anchors=4, shape_id=shape.id)
        elif prim.kind == "ellipse":
            node = Node("", "ellipse", shape.color, params=dict(cx=P(prim.cx), cy=P(prim.cy), rx=S(prim.rx),
                        ry=S(prim.ry), angle=prim.angle), anchors=4, shape_id=shape.id)
        elif prim.kind in ("rect", "rrect"):
            node = Node("", prim.kind, shape.color, params=dict(cx=P(prim.cx), cy=P(prim.cy), rx=S(prim.rx),
                        ry=S(prim.ry), angle=prim.angle, r=S(prim.r)),
                        anchors=4 if prim.kind == "rect" else 8, shape_id=shape.id)
        elif prim.kind == "polygon":
            pts = [(P(x), P(y)) for x, y in prim.pts]
            node = Node("", "polygon", shape.color, params=dict(pts=pts), anchors=len(pts), shape_id=shape.id)
    if node is None and cfg.snap_primitives and shape.prim is None:
        ring = snap_ring(shape.full, cfg)
        if ring is not None and not (shape.draw and shape.draw.area != shape.full.area):
            parts = []
            for cx, cy, r in ring:
                x, y, rr = P(cx), P(cy), S(r)
                f = lambda v: f"{v:.{cfg.path_precision}f}".rstrip("0").rstrip(".")
                parts.append(f"M{f(x - rr)} {f(y)}A{f(rr)} {f(rr)} 0 1 0 {f(x + rr)} {f(y)}"
                             f"A{f(rr)} {f(rr)} 0 1 0 {f(x - rr)} {f(y)}Z")
            node = Node("", "path", shape.color, d="".join(parts), evenodd=True, anchors=8,
                        shape_id=shape.id)
    if node is None:
        d, anchors, evenodd = mask_to_path(mask, canvas, cfg, scale)
        if not d:
            return None
        node = Node("", "path", shape.color, d=d, evenodd=evenodd, anchors=anchors, shape_id=shape.id)
    # single tail: every node kind carries its shape's gradient, converted to SVG coords
    if shape.grad is not None:
        node.grad = _convert_grad(shape.grad, P, S)
    return node


def _build_tree(shapes: list[Shape], roots: list[int], leaves: dict[int, Node], cfg: Config,
                canvas_area: int) -> list[Node]:
    def flat(sid: int) -> list[Node]:
        out = [leaves[sid]] if sid in leaves else []
        for c in shapes[sid].children:
            out += flat(c)
        return out

    def build(sid: int, depth: int) -> list[Node]:
        s = shapes[sid]
        leaf = leaves.get(sid)
        if not s.children:
            return [leaf] if leaf else []
        if depth >= cfg.group_depth:
            return flat(sid)
        kids: list[Node] = []
        for c in s.children:
            kids += build(c, depth + 1)
        if leaf is None:
            return kids
        g = Node("", "group", None, children=[leaf, *kids], shape_id=sid)
        return [g]

    nodes: list[Node] = []
    for rid in roots:
        s = shapes[rid]
        if cfg.group_depth <= 0:
            nodes += flat(rid)
        elif s.is_background:
            # background stays its own layer; its children become top-level layers
            if rid in leaves:
                nodes.append(leaves[rid])
            for c in s.children:
                nodes += build(c, 0)
        else:
            nodes += build(rid, 0)
    return nodes


def run(path: Path | str, cfg: Config | None = None, labels: dict[int, str] | None = None) -> Result:
    cfg = cfg or Config()
    t0 = time.time()
    img = load_image(path, cfg)
    H, W = img.alpha.shape
    seg = segment(img, cfg)
    if cfg.gradients:
        from .stages.gradient import detect
        seg = detect(seg, img, cfg)
    t1 = time.time()
    transparent = seg.rid == -1
    roots = order.build(seg, transparent, cfg)
    while cfg.complete_hidden:
        merged = order.merge_fragments(seg, transparent, cfg)
        if merged is seg and cfg.gradients:
            from .stages.gradient import merge_occluded
            merged = merge_occluded(seg, img, cfg)
        if merged is seg:
            break
        seg = merged
        roots = order.build(seg, transparent, cfg)
    loop_fits = {}
    curve_fits = {}
    if cfg.strokes and cfg.complete_hidden:
        from .stages.loops import recover
        while (loop := recover(seg, roots, img, cfg)) is not None:
            ids = set(loop.ids)
            visible = np.isin(seg.rid, loop.ids)
            vis = Mask.from_full(visible)
            first = seg.shapes[loop.ids[0]]
            joint = Shape(first.id, first.color, vis, vis)
            seg = seg.rebuilt([joint if s.id == first.id else s for s in seg.shapes
                               if s.id == first.id or s.id not in ids])
            roots = order.build(seg, transparent, cfg)
            loop_fits[vis] = loop.stroke
        from .stages.curves import recover as recover_curve
        while (curve := recover_curve(seg, roots, img, cfg, loop_fits)) is not None:
            ids = set(curve.ids)
            vis = Mask.from_full(np.isin(seg.rid, curve.ids))
            first = seg.shapes[curve.ids[0]]
            joint = Shape(first.id, first.color, vis, vis)
            seg = seg.rebuilt([joint if s.id == first.id else s for s in seg.shapes
                               if s.id == first.id or s.id not in ids])
            roots = order.build(seg, transparent, cfg)
            curve_fits[vis] = curve.stroke
        completed_fits = {**loop_fits, **curve_fits}
        # Every foreign observed region under a restored loop must paint above
        # it. Lift descendants to sibling constraints, preserving other order.
        edges = {}
        for s in seg.shapes:
            if s.vis not in completed_fits:
                continue
            stroke = completed_fits[s.vis]
            s.full = s.draw = stroke.full
            s.completed = True
            if s.vis in curve_fits:
                # Only the validated loop hides this open curve. Raster fringes
                # touching earlier artwork must not create new occluder edges.
                owners = {o.id for o in seg.shapes if o.vis in stroke.occluders}
            else:
                owners = set(np.unique(seg.rid[stroke.full.to_full((H, W))])) - {-1, s.id}
            for other in owners:
                above = seg.shapes[other]
                while above.parent != s.parent and above.parent is not None:
                    above = seg.shapes[above.parent]
                if above.parent == s.parent and above.id != s.id:
                    edges.setdefault(s.parent, set()).add((s.id, above.id))
        for parent, constraints in edges.items():
            ids = roots if parent is None else seg.shapes[parent].children
            ordered = order._toposort(ids, constraints, seg.shapes, stable=True)
            if parent is None:
                roots = ordered
            else:
                seg.shapes[parent].children = ordered
    t2 = time.time()
    shapes = seg.shapes

    # background = root shape covering most of the canvas
    for rid in roots:
        if shapes[rid].sil.area >= 0.6 * H * W:
            shapes[rid].is_background = True
            break

    leaves: dict[int, Node] = {}
    for s in shapes:
        node = _leaf(s, (H, W), cfg, img.scale)
        if node is not None:
            if s.vis in loop_fits:
                _closed_node(node, s, loop_fits[s.vis], img.scale)
            elif s.vis in curve_fits:
                _stroke_node(node, s, curve_fits[s.vis], img.scale, cfg.path_precision)
            node.opacity = _opacity(s, img.alpha)
            leaves[s.id] = node
    if cfg.strokes:
        from .stages.strokes import fit_closed, fit_straight, fit_stroke, fit_crossed_curve
        from .stages.complete import occludes
        from .masks import touches

        def paint_ids(ids):
            for sid in ids:
                yield sid
                yield from paint_ids(shapes[sid].children)

        rank = {sid: i for i, sid in enumerate(paint_ids(roots))}
        circles = []
        paint_edges = {}
        for sid, node in leaves.items():
            if node.kind == "circle":
                p = node.params
                circles.append((sid, shapes[sid].vis,
                                Prim("circle", p["cx"]*img.scale-.5, p["cy"]*img.scale-.5,
                                     p["r"]*img.scale, p["r"]*img.scale)))
        closed_fits = {}
        for sid, node in leaves.items():
            if node.grad is None and not shapes[sid].is_background and node.stroke_width is None:
                fitted = fit_closed(shapes[sid].full, cfg, img, shapes[sid].color,
                                    [shapes[other].vis for other in leaves if rank[other] > rank[sid]])
                if fitted is not None:
                    closed_fits[sid] = fitted
        closed_ids = set(closed_fits) | {sid for sid, node in leaves.items()
                                        if node.kind in ("circle", "ellipse") and node.stroke_width is not None}
        for sid, node in leaves.items():
            if node.grad is not None or shapes[sid].is_background or node.stroke_width is not None:
                continue
            closed = closed_fits.get(sid)
            if closed is not None:
                _closed_node(node, shapes[sid], closed, img.scale)
                continue
            if node.kind == "circle" or node.evenodd:
                continue
            covers = [(mask, prim) for other, mask, prim in circles if rank[other] > rank[sid]]
            # Area-based ordering can put a large hub before its small needle.
            # Try that sibling only with observed T-junction evidence, and change
            # paint order only if the full visible stroke reconstruction succeeds.
            straight_covers = covers + [(mask, prim) for other, mask, prim in circles
                                        if rank[other] < rank[sid] and shapes[other].parent == shapes[sid].parent
                                        and touches(shapes[sid].vis, mask, (H, W), 2)
                                        and occludes(shapes[sid].vis, mask, (H, W))]
            stroke = fit_straight(shapes[sid].full, cfg, img, shapes[sid].color, straight_covers)
            if stroke is None:
                curved_candidate = node.kind == "path"
                if node.kind == "polygon":
                    # Clean alpha contours can snap a genuine curve to a coarse
                    # polygon. Keep that curve eligible without reinterpreting
                    # the existing filled primitives on opaque artwork.
                    y0, x0, y1, x1 = shapes[sid].vis.bbox
                    curved_candidate = np.any(img.alpha[max(0, y0-2):min(H, y1+2),
                                                         max(0, x0-2):min(W, x1+2)] < 128)
                if curved_candidate:
                    stroke = fit_stroke(shapes[sid].full, cfg, covers, img, shapes[sid].color)
                if stroke is None and node.kind in ("path", "polygon"):
                    overlays = [shapes[other].vis for other in closed_ids if rank[other] > rank[sid]
                                and touches(shapes[sid].vis, shapes[other].vis, (H, W), 2)]
                    stroke = fit_crossed_curve(shapes[sid].vis, cfg, overlays, img, shapes[sid].color)
            if stroke is None:
                continue
            _stroke_node(node, shapes[sid], stroke, img.scale, cfg.path_precision)
            for mask in stroke.occluders:
                for other, cover, _ in circles:
                    if mask is cover and shapes[other].parent == shapes[sid].parent:
                        paint_edges.setdefault(shapes[sid].parent, set()).add((sid, other))
        for parent, edges in paint_edges.items():
            ids = roots if parent is None else shapes[parent].children
            ordered = order._toposort(ids, edges, shapes, stable=True)
            if parent is None:
                roots = ordered
            else:
                shapes[parent].children = ordered
    t3 = time.time()

    if cfg.remove_background:
        for s in shapes:
            if s.is_background:
                leaves.pop(s.id, None)
    tree = _build_tree(shapes, roots, leaves, cfg, H * W)

    # classical base names, then optional semantic overrides
    for n in leaves.values():
        s = shapes[n.shape_id]
        word = "stroke" if n.stroke_width is not None else name.KIND_WORD[n.kind]
        base = "Background" if s.is_background else f"{name.color_name(s.color)} {word}"
        n.name = base
    res = Result("", tree, shapes, seg, img, cfg)
    groups: list[dict] = []
    if cfg.name_layers and cfg.vlm_url:
        from . import vlm
        sem, groups = vlm.describe(res, cfg)
        labels = {**sem, **(labels or {})}
    if groups:
        from . import vlm
        tree = vlm.apply_groups(tree, groups)
    name.assign_names(tree, labels)

    svg = emit.write_svg(tree, img.orig_size, cfg.path_precision, cfg.illustrator_layers)
    stats = dict(shapes=len(leaves), completed=sum(s.completed for s in shapes),
                 anchors=sum(n.anchors for n in leaves.values()),
                 primitives=sum(n.kind != "path" for n in leaves.values()),
                 gradients=sum(n.grad is not None for n in leaves.values()),
                 strokes=sum(n.stroke_width is not None for n in leaves.values()),
                 t_segment=t1 - t0, t_order=t2 - t1, t_trace=t3 - t2, t_total=time.time() - t0)
    stats["vlm_names"] = len(labels or {})
    return Result(svg, tree, shapes, seg, img, cfg, stats)
