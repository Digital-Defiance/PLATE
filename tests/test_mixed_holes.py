"""Visible alpha voids remain holes even when opaque artwork fills most of them."""
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from scipy import ndimage as ndi

from plate import pipeline
from plate.masks import Mask
from plate.raster import have_renderer
from plate.scene import Shape
from plate.stages import order


def _frame_with_island(void):
    canvas = (140, 180)
    outer = np.zeros(canvas, bool)
    outer[10:130, 10:170] = True
    hole = np.zeros(canvas, bool)
    hole[25:115, 25:155] = True
    frame, island = outer & ~hole, hole & ~void
    shapes = []
    for sid, a in enumerate((frame, island)):
        mask = Mask.from_full(a)
        shapes.append(Shape(sid, (24, 46, 76) if sid == 0 else (233, 188, 89), mask, mask))
    return shapes, ~(frame | island), outer, frame


@pytest.mark.parametrize("side", [5, 10, 20])
def test_small_clear_void_protects_hole_occupied_mostly_by_an_island(side):
    void = np.zeros((140, 180), bool)
    void[55:55+side, 75:75+side] = True
    shapes, transparent, _, frame = _frame_with_island(void)
    order._silhouettes(shapes, transparent)
    # Opaque foreign artwork must not become the frame's hidden silhouette.
    assert np.array_equal(shapes[0].full.to_full(frame.shape), frame)
    assert np.array_equal(shapes[1].full.to_full(frame.shape), shapes[1].vis.to_full(frame.shape))


@pytest.mark.parametrize("fringe", [0, 1, 2])
def test_fully_opaque_cover_or_thin_alpha_fringe_does_not_reopen_whole_interior(fringe):
    void = np.zeros((140, 180), bool)
    if fringe:
        void[25:25+fringe, 25:155] = True
    shapes, transparent, outer, _ = _frame_with_island(void)
    order._silhouettes(shapes, transparent)
    assert np.array_equal(shapes[0].full.to_full(outer.shape), outer & ~void)


def test_orbit_front_loop_keeps_one_hole_and_no_opaque_core_in_its_full_silhouette():
    from challenges import _mask, _topology
    if not have_renderer():
        pytest.skip("requires independent target renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "logo_orbit_wordmark.png")
    root = ET.parse(directory / "logo_orbit_wordmark.target.svg").getroot()
    target = next(e for e in root if e.get("id") == "front-orbit")
    expected = _mask(root, target)
    shape = max(result.shapes, key=lambda s: np.count_nonzero(s.vis.to_full(expected.shape) & expected))
    full = shape.full.to_full(expected.shape)
    assert _topology(full) == (1, 1)
    assert not full[240, 215], "the orbital stroke must not acquire the opaque core's pixels"
    boundary = expected & ~ndi.binary_erosion(expected)
    assert np.count_nonzero(full ^ expected)/boundary.sum() <= .75
