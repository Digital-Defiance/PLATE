"""Rejoin visible fragments only when geometry and occluders support the union."""
import numpy as np
import pytest
from scipy import ndimage as ndi

from plate.config import Config
from plate.geometry import Prim, raster_prim
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
