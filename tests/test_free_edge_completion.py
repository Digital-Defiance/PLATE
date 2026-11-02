"""Rect/polygon amodal completion by free-edge line intersection (Task 4, R2 state (a)).

A partly-hidden rectilinear shape whose corner is behind an occluder cannot be recovered by
fitting the free contour points alone: `fit_rect`'s minAreaRect seed is biased by the cut, so
its RMS exceeds the completion tolerance. The free-edge path extends the straight free edges and
intersects adjacent non-parallel ones to reconstruct the hidden corner, then feeds the clean
polygon to the EXISTING `evaluate` with unchanged gates. These tests pin that behaviour at the
unit level (no renderer): the reconstructed geometry, and that the gates still reject a shape
that merely abuts a neighbour.

Validates: Requirements 2 (R2).
"""
import numpy as np
from scipy import ndimage as ndi

from plate.bezier import resample_closed
from plate.config import Config
from plate.geometry import contours_xy, fit_rect
from plate.masks import Mask
from plate.scene import Segmentation, Shape
from plate.stages import order
from plate.stages.complete import _free_edge_quad, _free_edge_runs


def _cls_for(vis_mask, occ_mask):
    """Classify a visible mask's contour points as free (0) / occluded (2) like try_complete."""
    cont = resample_closed(contours_xy(vis_mask)[0], 1.0)
    near = ndi.binary_dilation(occ_mask, iterations=2)
    h, w = vis_mask.shape
    xi = np.clip(np.round(cont[:, 0]).astype(int), 0, w - 1)
    yi = np.clip(np.round(cont[:, 1]).astype(int), 0, h - 1)
    cls = np.where(near[yi, xi], 2, 0)
    return cont, cls


def test_free_edge_reconstructs_hidden_corner_of_axis_aligned_rect():
    """The hidden bottom-right corner of a rect is reconstructed at the true vertex by extending
    and intersecting the two free edges that meet there."""
    h = w = 200
    rect = np.zeros((h, w), bool)
    rect[40:141, 40:161] = True              # corners at (40,40),(160,40),(160,140),(40,140)
    occ = np.zeros((h, w), bool)
    occ[110:, 120:] = True                   # hides the bottom-right corner (160,140)
    vis = rect & ~occ

    cont, cls = _cls_for(vis, occ)
    runs = _free_edge_runs(cont, cls)
    assert len(runs) >= 3, "the three fully/partly visible rect edges must be recovered"

    quad = _free_edge_quad(cont, cls)
    assert quad is not None and len(quad) == 4
    # the reconstructed quad must contain the true hidden corner (160, 140)
    corner = quad[np.argmin(np.linalg.norm(quad - np.array([160.0, 140.0]), axis=1))]
    assert np.linalg.norm(corner - np.array([160.0, 140.0])) < 3.0

    # re-fit to a clean axis-aligned rect: centre ~ (100, 90), half-extents ~ {60, 50}
    pr, rms = fit_rect(quad)
    assert rms < 1.0
    assert abs(pr.cx - 100.0) < 3 and abs(pr.cy - 90.0) < 3
    half = sorted((pr.rx, pr.ry))            # axis labelling depends on fit_rect's chosen angle
    assert abs(half[0] - 50.0) < 3 and abs(half[1] - 60.0) < 3


def test_free_point_fit_alone_cannot_place_the_hidden_corner():
    """Without edge extension, fitting the free points alone biases the rectangle (the whole
    point of the free-edge path): minAreaRect over the visible L-shaped points does not land the
    hidden corner at (160,140). This is the baseline the free-edge reconstruction improves on."""
    h = w = 200
    rect = np.zeros((h, w), bool)
    rect[40:141, 40:161] = True
    occ = np.zeros((h, w), bool)
    occ[110:, 120:] = True
    vis = rect & ~occ
    cont, cls = _cls_for(vis, occ)
    free = cont[cls == 0]
    pr, _ = fit_rect(free)
    # the free-point rect does not reach the true far corner; its max x stays short of 160
    far = pr.cx + pr.rx
    assert far < 157.0, "the free-point fit should fall short of the hidden corner"


def _occluded_rect_scene(cover=True):
    """A red rect with its right third hidden behind a blue bar (cover=True) or merely abutting
    a blue rect to its right that does NOT overlap it (cover=False)."""
    canvas = (180, 220)
    rect = np.zeros(canvas, bool)
    rect[40:140, 30:170] = True
    bar = np.zeros(canvas, bool)
    if cover:
        bar[20:160, 150:200] = True          # overlaps the rect's right edge
        red = rect & ~bar
    else:
        bar[40:140, 172:200] = True          # sits beside the rect, no overlap
        red = rect.copy()
    masks = [(red, (210, 40, 40)), (bar, (40, 70, 190))]
    occupied = np.logical_or.reduce([m for m, _ in masks])
    masks.append((~occupied, (255, 255, 255)))
    rid = np.full(canvas, -1, np.int32)
    shapes = []
    palette = []
    for region, color in masks:
        labels, count = ndi.label(region)
        for i in range(1, count + 1):
            mask = Mask.from_full(labels == i)
            s = Shape(len(shapes), color, mask, mask)
            rid[labels == i] = s.id
            shapes.append(s)
        palette.append(color)
    seg = Segmentation(rid, shapes, np.array(palette, np.uint8))
    order.build(seg, rid < 0, Config())
    return seg


def test_occluded_rect_completes_to_full_rectangle():
    """End to end through order.build: the covered red rect is completed to its full silhouette
    (its hidden right edge reconstructed) so its full mask spans the whole 30..170 width."""
    seg = _occluded_rect_scene(cover=True)
    red = next(s for s in seg.shapes if tuple(s.color) == (210, 40, 40))
    xs = np.nonzero(red.full.to_full((180, 220)).any(axis=0))[0]
    assert xs.max() >= 166, "the completed rect must reach its true right edge (~170)"
    assert red.completed


def test_abutting_rect_is_not_completed_into_its_neighbour():
    """A rect that merely sits beside a non-overlapping neighbour must NOT be 'completed' across
    the seam: the occluder-coverage gate (unchanged) rejects an invented extension."""
    seg = _occluded_rect_scene(cover=False)
    red = next(s for s in seg.shapes if tuple(s.color) == (210, 40, 40))
    xs = np.nonzero(red.full.to_full((180, 220)).any(axis=0))[0]
    # it keeps its own extent (~30..170) and does not grow into the neighbour past ~172
    assert xs.max() < 172


# --------------------------------------------------------------------------- R7b
# Thin occluded rectangles. For a narrow bar the reconstructed "extra" region is a thin band
# whose rasterised 1px PERIMETER is an area-independent constant that dominates the occluder-
# coverage fraction, so a perfectly-fit rect (RMS << tol) whose hidden interior is fully under
# the occluder is wrongly rejected as the bar narrows (measured: ~130 uncovered perimeter px,
# 0 interior, at every height; full-extra coverage 0.69 at 6px rising to 0.86 at 20px, crossing
# the 0.85 floor only when thick). The fix evaluates the coverage floor on the eroded INTERIOR
# of extra for RECT candidates only, and only when the band is thin (perimeter >= 25% of area)
# AND its interior is essentially fully (>= 0.98) under the occluders - so the seam no longer
# dominates, while the 0.85/0.65 shape floors, the occluder set and the 15deg _occludes
# threshold are all unchanged (GC-5). These pin the moved number and the preserved negative.


import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from plate import pipeline

_RED = (210, 40, 40)
_NAVY = (24, 46, 76)


def _thin_bar_png(tmp, barh, cover=True):
    """Render (anti-aliased) a thin red horizontal bar whose middle is crossed by a tall navy
    occluder (cover=True) or that merely sits beside a navy bar with no overlap (cover=False)."""
    ss = 4
    W, H = 200, 180
    im = Image.new("RGB", (W * ss, H * ss), (255, 255, 255))
    d = ImageDraw.Draw(im)
    y0 = 90
    d.rectangle([c * ss for c in (20, y0, 180, y0 + barh)], fill=_RED)
    if cover:
        d.rectangle([c * ss for c in (80, 40, 120, 140)], fill=_NAVY)   # tall occluder
    else:
        d.rectangle([c * ss for c in (80, y0 + barh + 6, 120, y0 + barh + 40)], fill=_NAVY)
    path = Path(tmp) / f"bar_{barh}_{cover}.png"
    im.resize((W, H), Image.LANCZOS).save(path)
    return path


def _red_shapes(result):
    return [s for s in result.seg.shapes
            if np.linalg.norm(np.array(s.color) - np.array(_RED)) < 45]


@pytest.mark.parametrize("barh", [8, 12])
def test_thin_occluded_bar_completes_into_one_rect(tmp_path, barh):
    """R7b state (a): a thin red bar (8-12px tall) whose middle is hidden behind a tall navy bar
    recovers as ONE completed rectangle. Before the pixel-boundary fix the reconstructed rect's
    rasterised perimeter seam dropped the occluder-coverage fraction below the 0.85 floor for
    thin bars (measured full-extra coverage 0.74 at 8px, 0.80 at 12px), so the bar stayed as two
    separate red fragments and emitted no rect; now the seam-corrected (eroded-interior) coverage
    admits the genuine completion. Measured: red fragments 2 -> 1, emitting a <rect>."""
    result = pipeline.run(_thin_bar_png(tmp_path, barh, cover=True), Config())
    reds = _red_shapes(result)
    assert len(reds) == 1, f"barh={barh}: expected one completed bar, got {len(reds)} fragments"
    assert any(getattr(s, "prim", None) and s.prim.kind == "rect" for s in reds), \
        f"barh={barh}: the completed bar must emit a rect primitive"


def test_thick_occluded_bar_was_already_completing(tmp_path):
    """Control: a thick (20px) occluded bar completed to a rect even before the fix (its
    perimeter seam was a small fraction of the extra), so the fix does not change it. Pins that
    the correction is additive for thin bars, not a behaviour change for normal ones."""
    result = pipeline.run(_thin_bar_png(tmp_path, 20, cover=True), Config())
    reds = _red_shapes(result)
    assert len(reds) == 1
    assert any(getattr(s, "prim", None) and s.prim.kind == "rect" for s in reds)


@pytest.mark.parametrize("barh", [8, 12])
def test_thin_bar_abutting_a_non_overlapping_neighbour_is_not_completed(tmp_path, barh):
    """Negative regression for the seam correction: a thin bar that merely sits next to a
    non-overlapping navy bar must NOT be 'completed' into it. Its interior is not under the
    neighbour, so the 0.98 interior-coverage guard rejects an invented extension - the bar stays
    one fragment with no spurious hidden growth (no rect completion is forced)."""
    result = pipeline.run(_thin_bar_png(tmp_path, barh, cover=False), Config())
    reds = _red_shapes(result)
    # the bar is one visible piece; it must not acquire a completed hidden region under the
    # non-overlapping neighbour (its full extent stays ~ its visible extent).
    for s in reds:
        full_w = s.full.a.shape[1]
        vis_w = s.vis.a.shape[1]
        assert full_w <= vis_w + 4, f"barh={barh}: completed width grew past the visible bar"
