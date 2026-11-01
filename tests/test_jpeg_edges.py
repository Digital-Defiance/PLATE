"""JPEG chroma boundaries checked against independently authored coverage masks."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from plate.config import Config, load
from plate.imageio import load_image
from plate.stages.segment import _edge_labels, segment

DARK = (12, 40, 44)
PINK = (241, 127, 176)
BLUE = (69, 195, 223)


def _art(kind, color):
    mask = Image.new("L", (256 * 4, 192 * 4))
    draw = ImageDraw.Draw(mask)
    if kind == "diagonal":
        draw.polygon([(29*4, 33*4), (225*4, 123*4), (225*4, 137*4), (29*4, 47*4)], fill=255)
    else:
        draw.arc((-120*4, 30*4, 280*4, 480*4), 210, 320, fill=255, width=14*4)
    mask = mask.resize((256, 192), Image.Resampling.LANCZOS)
    coverage = np.asarray(mask) / 255.0
    rgb = np.rint(np.array(DARK) + (np.array(color) - DARK) * coverage[..., None]).astype(np.uint8)
    return rgb, mask


def _mask(seg, color):
    found = np.zeros(seg.rid.shape, bool)
    for shape in seg.shapes:
        if shape.color == color:
            found |= seg.rid == shape.id
    return found


@pytest.mark.parametrize("kind", ["diagonal", "arc"])
@pytest.mark.parametrize("color", [PINK, BLUE])
@pytest.mark.parametrize("upscale", [1., 2.])
def test_jpeg_coloured_boundaries_follow_authored_geometry(tmp_path, kind, color, upscale):
    rgb, mask = _art(kind, color)
    path = tmp_path / "art.jpg"
    Image.fromarray(rgb).save(path, quality=85, subsampling=2)
    cfg = Config(palette=("#0c282c", "#{:02x}{:02x}{:02x}".format(*color)),
                 filter_speckle=1, upscale=upscale)
    img = load_image(path, cfg)
    expected = np.asarray(mask.resize((img.rgb.shape[1], img.rgb.shape[0]),
                                      Image.Resampling.LANCZOS)) >= 128
    errors = []
    for enabled in (False, True):
        actual = _mask(segment(img, cfg.merged(jpeg_edges=enabled)), color)
        errors.append(np.count_nonzero(actual ^ expected))
    assert errors[1] <= 0.4 * errors[0], errors


def test_luma_places_boundary_despite_opposite_chroma_shift():
    pal = np.array([DARK, (231, 142, 180)], np.float32)
    delta = pal[1] - pal[0]
    # These errors have zero BT.601 luma but push RGB coverage across 50%.
    error = np.array([-25., 25 * .299 / .587, 0.], np.float32)
    pix = np.array([pal[0] + .46 * delta - error, pal[0] + .54 * delta + error])
    nearby = np.ones((2, 2), bool)
    old, _ = _edge_labels(pix, pal, nearby)
    new, _ = _edge_labels(pix, pal, nearby, jpeg_nearby=nearby)
    assert old.tolist() == [1, 0], "control must reproduce the displaced colour edge"
    assert new.tolist() == [0, 1]


@pytest.mark.parametrize("pal", [
    [[20, 20, 20], [220, 220, 220]],  # brightness edge: retain its existing seed neighbourhood
    [[200, 30, 20], [20, 122, 20]],  # near-equal luma: no stable luminance coverage
    [[12, 40, 44], [246, 243, 236]],  # the logo's already-clean cream/dark boundary
])
def test_ineligible_pairs_keep_rgb_and_original_neighbourhood(pal):
    pal = np.array(pal, np.float32)
    pix = pal[0] + np.array([.4, .6], np.float32)[:, None] * (pal[1] - pal[0])
    nearby = np.array([[True, False], [True, True]])
    expected = _edge_labels(pix, pal, nearby)
    actual = _edge_labels(pix, pal, nearby, jpeg_nearby=np.ones_like(nearby))
    for a, b in zip(actual, expected):
        assert np.array_equal(a, b)


def test_rgb_still_selects_colour_pair_at_multicolour_junction():
    pal = np.array([DARK, PINK, BLUE], np.float32)
    pix = np.array([PINK, BLUE, DARK], np.float32)
    nearby = np.ones((3, 3), bool)
    labels, residual = _edge_labels(pix, pal, nearby, jpeg_nearby=nearby)
    assert labels.tolist() == [1, 2, 0]
    assert np.array_equal(residual, np.zeros(3))


def test_png_segmentation_does_not_change_when_jpeg_edges_enabled(tmp_path):
    rgb, _ = _art("diagonal", PINK)
    path = tmp_path / "art.png"
    Image.fromarray(rgb).save(path)
    cfg = Config()
    img = load_image(path, cfg)
    a, b = segment(img, cfg), segment(img, cfg.merged(jpeg_edges=True))
    assert np.array_equal(a.rid, b.rid)
    assert np.array_equal(a.palette, b.palette)


@pytest.mark.parametrize("format,filename,is_jpeg", [("JPEG", "renamed.png", True),
                                                    ("PNG", "renamed.jpeg", False)])
def test_source_format_controls_jpeg_edges(tmp_path, format, filename, is_jpeg):
    path = tmp_path / filename
    Image.new("RGB", (20, 20), DARK).save(path, format=format)
    assert load_image(path, Config()).is_jpeg is is_jpeg


def test_jpeg_edges_are_opt_in_and_overridable():
    assert not Config().jpeg_edges
    assert load("smooth").jpeg_edges
    assert not load("smooth", jpeg_edges=False).jpeg_edges
