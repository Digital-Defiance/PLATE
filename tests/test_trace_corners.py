"""Sharp contour endpoints must survive smoothing without inventing remote corners."""
import numpy as np
import pytest

from plate.bezier import contour_to_beziers
from plate.geometry import poly_area
from plate.masks import Mask
from plate.raster import have_renderer, render_svg
from plate.stages.trace import mask_contours

pytestmark = pytest.mark.skipif(not have_renderer(), reason="requires the render extra")


def _contours(kind, width, scale, rotation=0):
    a, b = 120 - width / 2, 120 + width / 2
    if kind == "triangle":
        path = f"M{a} 40L{b} 40L120 200Z"
    elif kind == "notch":
        path = f"M10 40H{a}L120 200L{b} 40H230V230H10Z"
    else:
        path = "M120 20A100 100 0 1 0 120 220A100 100 0 1 0 120 20Z"
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">'
           f'<path d="{path}" fill="white"/></svg>')
    rgb = render_svg(svg, (int(240 * scale), int(240 * scale)), (0, 0, 0))
    rgb = np.rot90(rgb, rotation).copy()
    mask = Mask.from_full(rgb[..., 0] >= 128)
    canvas = rgb.shape[:2]
    sigma = max(.8 * scale, .45)
    contour = max(mask_contours(mask, canvas, sigma), key=lambda p: abs(poly_area(p)))
    reference = max(mask_contours(mask, canvas, 0.), key=lambda p: abs(poly_area(p)))
    target = np.array([120., 200.])
    for _ in range(rotation):
        target = np.array([target[1], 240 - target[0]])
    return contour, reference, target, sigma


def _fit(contour, scale, reference=None, limit=2.5):
    return contour_to_beziers(contour, .8 * scale, 28, smooth_px=3 * scale,
                              straighten=True, corner_k=max(4, round(3 * scale)),
                              corner_reference=reference, reference_limit=limit)


def _tip_error(result, scale, target):
    _, curves = result
    points = (np.array([curve[3] for curve in curves]) + .5) / scale
    return float(np.linalg.norm(points - target, axis=1).min())


@pytest.mark.parametrize("kind", ["triangle", "notch"])
@pytest.mark.parametrize("width", [100, 140])
@pytest.mark.parametrize("scale", [2., 4.])
def test_observed_sharp_tips_retain_authored_endpoints(kind, width, scale):
    contour, reference, target, sigma = _contours(kind, width, scale)
    old = _tip_error(_fit(contour, scale), scale, target)
    new = _tip_error(_fit(contour, scale, reference, max(2.5, 3 * sigma)), scale, target)
    assert old > 1., "control must reproduce the smoothing shortfall"
    assert new < .2, (old, new)


@pytest.mark.parametrize("rotation", [1, 2, 3])
def test_tip_recovery_is_independent_of_orientation(rotation):
    contour, reference, target, sigma = _contours("notch", 100, 2., rotation)
    new = _tip_error(_fit(contour, 2., reference, 3 * sigma), 2., target)
    assert new < .2, new


def test_reversed_reference_winding_preserves_the_same_corner():
    contour, reference, target, sigma = _contours("notch", 100, 2.)
    new = _tip_error(_fit(contour, 2., reference[::-1], 3 * sigma), 2., target)
    assert new < .2, new


def test_round_boundary_is_not_sharpened():
    contour, reference, _, sigma = _contours("circle", 0, 2.)
    old = _fit(contour, 2.)
    new = _fit(contour, 2., reference, 3 * sigma)
    assert np.array_equal(old[0], new[0])
    assert np.array_equal(old[1], new[1])


def test_distant_reference_cannot_move_a_corner():
    contour, reference, _, sigma = _contours("triangle", 100, 2.)
    old = _fit(contour, 2.)
    new = _fit(contour, 2., reference + [50, 50], 3 * sigma)
    assert np.array_equal(old[0], new[0])
    assert np.array_equal(old[1], new[1])


def test_tip_recovery_respects_the_displacement_bound():
    contour, reference, target, sigma = _contours("triangle", 40, 2.)
    old = _tip_error(_fit(contour, 2.), 2., target)
    new = _tip_error(_fit(contour, 2., reference, 3 * sigma), 2., target)
    assert new == pytest.approx(old), "do not extend a tip beyond the bounded reference match"
