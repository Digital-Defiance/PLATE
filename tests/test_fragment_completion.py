"""Rejoin visible fragments only when geometry and occluders support the union."""
import cv2
import numpy as np
import pytest
from scipy import ndimage as ndi

from plate.config import Config
from plate.geometry import Prim, fit_circle, raster_prim
from plate.masks import Mask
from plate.scene import Segmentation, Shape
from plate.stages import complete, order


def _crossed_disc(covered=True):
    canvas = (160, 180)
    disc = raster_prim(Prim("circle", 90, 80, 50, 50), canvas)
    vertical, horizontal = np.zeros(canvas, bool), np.zeros(canvas, bool)
    vertical[10:150, 82:99] = True
    horizontal[72:89, 15:165] = True
    masks = [(disc & ~vertical & ~horizontal, (210, 40, 40))]
    if covered:
        masks.append((horizontal | vertical, (40, 70, 190)))
    occupied = np.logical_or.reduce([m for m, _ in masks])
    masks.append((~occupied, (255, 255, 255)))
    rid = np.full(canvas, -1, np.int32)
    shapes = []
    for region, color in masks:
        labels, count = ndi.label(region)
        for i in range(1, count + 1):
            mask = Mask.from_full(labels == i)
            s = Shape(len(shapes), color, mask, mask)
            rid[labels == i] = s.id
            shapes.append(s)
    seg = Segmentation(rid, shapes, np.array([color for _, color in masks], np.uint8))
    order.build(seg, rid < 0, Config())
    return seg, disc


def test_flat_fragments_recover_disc_in_paint_order():
    seg, target = _crossed_disc()
    original = seg
    while True:
        merged = order.merge_fragments(seg, seg.rid < 0, Config())
        if merged is seg:
            break
        assert len(merged.shapes) < len(seg.shapes)
        assert np.array_equal(merged.rid >= 0, original.rid >= 0)
        assert all(s.parent is None and s.prim is None for s in merged.shapes)
        seg = merged
        roots = order.build(seg, seg.rid < 0, Config())
    assert len(seg.shapes) == 3  # background, one full disc and its cross-shaped cover
    disc, = [s for s in seg.shapes if s.color == (210, 40, 40)]
    assert disc.completed and disc.prim.kind == "circle"
    recovered = disc.full.to_full(seg.rid.shape)
    assert (recovered & target).sum() / (recovered | target).sum() >= .97

    def painted(ids):
        for i in ids:
            yield seg.shapes[i].color
            yield from painted(seg.shapes[i].children)

    assert list(painted(roots)) == [(255, 255, 255), (210, 40, 40), (40, 70, 190)]


def test_same_colour_without_supported_cover_is_not_merged():
    seg, _ = _crossed_disc(covered=False)
    assert order.merge_fragments(seg, seg.rid < 0, Config()) is seg


def test_fragment_merge_respects_completion_switch():
    seg, _ = _crossed_disc()
    assert order.merge_fragments(seg, seg.rid < 0, Config(complete_hidden=False)) is seg


@pytest.mark.parametrize("problem", ["uncovered_gap", "outlier"])
def test_pooled_completion_keeps_hidden_area_and_containment_guards(problem):
    seg, _ = _crossed_disc()
    reds = [s for s in seg.shapes if s.color == (210, 40, 40)]
    canvas = seg.rid.shape
    observed = np.logical_or.reduce([s.vis.to_full(canvas) for s in reds])
    if problem == "outlier":
        # This extra visible component cannot be silently dropped by a good circle fit.
        observed[25:45, 150:170] = True
    vis = Mask.from_full(observed)
    shape = Shape(0, reds[0].color, vis, vis, sil=vis)
    covers = [s for s in seg.shapes if s.color not in (reds[0].color, (255, 255, 255))]
    if problem == "uncovered_gap":
        vertical = np.zeros(canvas, bool)
        vertical[10:150, 82:99] = True
        mask = Mask.from_full(vertical)
        covers = [Shape(1, (40, 70, 190), mask, mask, sil=mask)]
    assert complete.try_complete(shape, covers, *canvas, Config()) is None


def _interrupted_ring(cross=True, cover_color=(233, 188, 89)):
    """A navy ring crossed by a bar that breaks it into four co-circular arcs.

    With ``cross`` the bar is painted, so each arc is occluded by the SAME bar and
    the four arcs continue one circle -- a genuine compound ring. Without it the
    bar area is background and the arcs share no occluder.
    """
    canvas = (200, 200)
    outer = raster_prim(Prim("circle", 100, 100, 70, 70), canvas)
    inner = raster_prim(Prim("circle", 100, 100, 45, 45), canvas)
    ring = outer & ~inner
    bar = np.zeros(canvas, bool)
    bar[:, 92:108] = True
    bar[92:108, :] = True
    regions = [(ring & ~bar, (24, 46, 76))]
    if cross:
        regions.append((bar, cover_color))
    occupied = np.logical_or.reduce([m for m, _ in regions])
    regions.append((~occupied, (255, 255, 255)))
    rid = np.full(canvas, -1, np.int32)
    shapes = []
    for region, color in regions:
        labels, n = ndi.label(region)
        for i in range(1, n + 1):
            mask = Mask.from_full(labels == i)
            if mask.area < 6:
                continue
            s = Shape(len(shapes), color, mask, mask)
            rid[labels == i] = s.id
            shapes.append(s)
    seg = Segmentation(rid, shapes, np.array([c for _, c in regions], np.uint8))
    order.build(seg, rid < 0, Config())
    return seg


def _merge_to_stable(seg):
    cfg = Config()
    while True:
        merged = order.merge_fragments(seg, seg.rid < 0, cfg)
        if merged is seg:
            return seg
        assert np.array_equal(merged.rid >= 0, seg.rid >= 0)
        seg = merged
        order.build(seg, seg.rid < 0, cfg)


def test_compound_siblings_reunite_an_interrupted_ring():
    # Four same-colour arcs of one ring, each occluded by the crossing bar and all
    # lying on one circle, must merge into a single compound object even though no
    # primitive fits the open ring.
    seg = _interrupted_ring(cross=True)
    navy_before = [s for s in seg.shapes if s.color == (24, 46, 76)]
    assert len(navy_before) >= 4
    stable = _merge_to_stable(seg)
    navy_after = [s for s in stable.shapes if s.color == (24, 46, 76)]
    assert len(navy_after) == 1
    # every observed arc pixel is preserved by the union
    before = np.logical_or.reduce([s.vis.to_full(seg.rid.shape) for s in navy_before])
    assert np.array_equal(navy_after[0].vis.to_full(stable.rid.shape), before)


def test_co_circular_arcs_without_a_shared_occluder_are_not_merged():
    # The same four arcs, but the crossing region is background rather than a painted
    # occluder. They lie on a circle yet share no occluder (no T-junction evidence),
    # so the compound merge must leave them apart.
    seg = _interrupted_ring(cross=False)
    assert order.merge_fragments(seg, seg.rid < 0, Config()) is seg


def _merge_rings_to_stable(seg):
    # The ellipse ring arm runs in the dedicated post-loop pass, not merge_fragments.
    cfg = Config()
    while True:
        merged = order.merge_ring_ellipses(seg, seg.rid < 0, cfg)
        if merged is seg:
            return seg
        assert np.array_equal(merged.rid >= 0, seg.rid >= 0)
        seg = merged
        order.build(seg, seg.rid < 0, cfg)


def _ellipse_ring(cx, cy, rx, ry, angle, width, canvas):
    """A constant-width elliptical stroke ring = outer ellipse minus inner ellipse."""
    outer = raster_prim(Prim("ellipse", cx, cy, rx + width / 2, ry + width / 2, angle), canvas)
    inner = raster_prim(Prim("ellipse", cx, cy, rx - width / 2, ry - width / 2, angle), canvas)
    return outer & ~inner


def _seg_from_regions(regions, canvas):
    rid = np.full(canvas, -1, np.int32)
    shapes = []
    for region, color in regions:
        labels, n = ndi.label(region)
        for i in range(1, n + 1):
            mask = Mask.from_full(labels == i)
            if mask.area < 6:
                continue
            s = Shape(len(shapes), color, mask, mask)
            rid[labels == i] = s.id
            shapes.append(s)
    seg = Segmentation(rid, shapes, np.array([c for _, c in regions], np.uint8))
    order.build(seg, rid < 0, Config())
    return seg


def _interrupted_ellipse(cross=True, debris=False, cover_color=(233, 188, 89)):
    """An elongated elliptical ring broken by a crossing bar into same-colour arcs.

    The ring is far too elongated for the circle arm (axis ratio ~0.4), so only the
    ellipse fallback can reunite it. ``cross`` paints the bar so both arcs share it as
    an occluder; ``debris`` scatters same-colour blocks off the ring (the panel-cell /
    star contamination) that must not corrupt the fit or be swept into the merge.
    """
    canvas = (260, 320)
    cx, cy, rx, ry, angle, width = 160, 130, 110, 46, 30.0, 6
    ring = _ellipse_ring(cx, cy, rx, ry, angle, width, canvas)
    bar = np.zeros(canvas, bool)
    bar[:, 152:168] = True  # vertical bar splitting the ring into two arcs
    navy = ring & ~bar
    if debris:
        # Same-colour blocks placed well off the ring; if they were pooled into the
        # cluster they would wreck the ellipse fit.
        navy[20:34, 20:34] = True
        navy[226:240, 286:300] = True
    regions = [(navy, (24, 46, 76))]
    if cross:
        regions.append((bar, cover_color))
    occupied = np.logical_or.reduce([m for m, _ in regions])
    regions.append((~occupied, (255, 255, 255)))
    return _seg_from_regions(regions, canvas)


def test_compound_siblings_reunite_an_interrupted_ellipse_ring():
    # Two same-colour arcs of one elongated ellipse, each occluded by the crossing
    # bar. No circle fits (axis ratio ~0.4), so only the ellipse fallback can reunite
    # them -- into ONE joint carrying a native <ellipse> stroke.
    seg = _interrupted_ellipse(cross=True)
    navy_before = [s for s in seg.shapes if s.color == (24, 46, 76)]
    assert len(navy_before) >= 2
    # The circle arm must genuinely reject this hull (elongated, not circular).
    vis = np.logical_or.reduce([s.vis.to_full(seg.rid.shape) for s in navy_before])
    ys, xs = np.nonzero(vis)
    hull = cv2.convexHull(np.c_[xs, ys].astype(np.float32)).reshape(-1, 2).astype(np.float64)
    circ, rms, _ = fit_circle(hull)
    assert rms > 0.02 * circ.rx  # circle gate fails
    # merge_fragments (which never runs the ellipse arm) leaves the arcs split;
    # only the dedicated post-loop ring pass reunites them.
    assert order.merge_fragments(seg, seg.rid < 0, Config()) is seg
    stable = _merge_rings_to_stable(seg)
    navy_after = [s for s in stable.shapes if s.color == (24, 46, 76)]
    assert len(navy_after) == 1
    joint = navy_after[0]
    # every observed arc pixel preserved by the union
    before = np.logical_or.reduce([s.vis.to_full(seg.rid.shape) for s in navy_before])
    assert np.array_equal(joint.vis.to_full(stable.rid.shape), before)
    # emitted as a native ellipse stroke with a plausible constant width
    assert joint.closed_stroke is not None
    assert joint.closed_stroke.prim.kind == "ellipse"
    assert 4.0 <= joint.closed_stroke.width <= 9.0
    # elongated, not a near-circle (the circle arm's territory)
    pr = joint.closed_stroke.prim
    assert min(pr.rx, pr.ry) / max(pr.rx, pr.ry) < 0.8


def test_contaminated_same_colour_ellipse_hull_is_not_merged():
    # Same-colour debris scattered off the ring. The debris sits in its own
    # singleton cluster (no shared occluder) so it is never pooled with the arcs,
    # and the arc cluster still fits cleanly -- so the ring DOES reunite but the
    # debris blocks stay separate and never corrupt the fit.
    seg = _interrupted_ellipse(cross=True, debris=True)
    stable = _merge_rings_to_stable(seg)
    navy = [s for s in stable.shapes if s.color == (24, 46, 76)]
    # the two debris blocks remain their own shapes; only the two arcs merged
    assert len(navy) == 3
    joint = max(navy, key=lambda s: s.vis.area)
    assert joint.closed_stroke is not None and joint.closed_stroke.prim.kind == "ellipse"
    # a direct check that _fit_ring_ellipse rejects a contaminated / implausible hull:
    # the CLEAN arcs (no debris) are accepted; adding far same-colour debris into the
    # pooled hull wrecks the ellipse fit and the helper refuses it.
    clean_seg = _interrupted_ellipse(cross=True, debris=False)
    canvas = clean_seg.rid.shape
    arcs = np.logical_or.reduce([s.vis.to_full(canvas) for s in clean_seg.shapes
                                 if s.color == (24, 46, 76)])
    assert order._fit_ring_ellipse(arcs, *canvas) is not None  # clean arcs alone: accepted
    contaminated = arcs.copy()
    contaminated[5:25, 290:315] = True  # a far same-colour square wrecks the ellipse fit
    assert order._fit_ring_ellipse(contaminated, *canvas) is None


def test_two_distinct_same_colour_ellipse_arcs_without_shared_occluder_are_not_merged():
    # Two separate elongated same-colour elliptical arcs, each a single fragment, with
    # NO occluder between them (the regions that break each ring are background). They
    # are co-plausible and co-elongated, but neither shares an occluder, so
    # _cluster_by_shared_occluder keeps each in its own singleton cluster and the
    # ellipse arm never fits across the two -- no merge.
    canvas = (200, 480)
    width = 6
    left = _ellipse_ring(110, 100, 80, 34, 20.0, width, canvas)
    right = _ellipse_ring(370, 100, 80, 34, -20.0, width, canvas)
    gap = np.zeros(canvas, bool)
    gap[:, 100:120] = True   # background break in the left ring
    gap[:, 360:380] = True   # background break in the right ring
    navy = (left | right) & ~gap
    regions = [(navy, (24, 46, 76))]
    occupied = np.logical_or.reduce([m for m, _ in regions])
    regions.append((~occupied, (255, 255, 255)))
    seg = _seg_from_regions(regions, canvas)
    # four arcs total, but no two share a painted occluder (the gaps are background)
    assert len([s for s in seg.shapes if s.color == (24, 46, 76)]) >= 2
    # neither merge_fragments nor the dedicated ring pass may join across the two rings
    assert order.merge_fragments(seg, seg.rid < 0, Config()) is seg
    assert order.merge_ring_ellipses(seg, seg.rid < 0, Config()) is seg


def test_two_complete_circles_sharing_an_occluder_are_not_merged():
    # Two whole same-colour discs crossed by one bar: each disc snaps to a complete
    # circle on its own, so they are distinct finished objects, not fragments of one
    # ring -- the compound merge must refuse even though a bar occludes both and their
    # outer hulls could be read as co-circular.
    canvas = (160, 300)
    left = raster_prim(Prim("circle", 70, 80, 45, 45), canvas)
    right = raster_prim(Prim("circle", 230, 80, 45, 45), canvas)
    bar = np.zeros(canvas, bool)
    bar[70:90, :] = True
    regions = [(left & ~bar, (24, 46, 76)), (right & ~bar, (24, 46, 76)),
               (bar, (233, 188, 89))]
    occupied = np.logical_or.reduce([m for m, _ in regions])
    regions.append((~occupied, (255, 255, 255)))
    rid = np.full(canvas, -1, np.int32)
    shapes = []
    for region, color in regions:
        labels, n = ndi.label(region)
        for i in range(1, n + 1):
            mask = Mask.from_full(labels == i)
            if mask.area < 6:
                continue
            s = Shape(len(shapes), color, mask, mask)
            rid[labels == i] = s.id
            shapes.append(s)
    seg = Segmentation(rid, shapes, np.array([c for _, c in regions], np.uint8))
    order.build(seg, rid < 0, Config())
    assert order.merge_fragments(seg, seg.rid < 0, Config()) is seg
