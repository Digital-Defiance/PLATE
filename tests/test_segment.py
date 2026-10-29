"""Thin-detail and antialiasing regressions for classical segmentation."""
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image, ImageDraw

from plate import pipeline
from plate.config import Config
from plate.scene import Loaded
from plate.stages.segment import segment

NAVY = (24, 46, 76)
CREAM = (245, 237, 218)


def _loaded(rgb, alpha=None):
    h, w = rgb.shape[:2]
    if alpha is None:
        alpha = np.full((h, w), 255, np.uint8)
    return Loaded(rgb, alpha, (w, h), 1.0)


def _color_mask(seg, color):
    mask = np.zeros(seg.rid.shape, bool)
    for shape in seg.shapes:
        if np.linalg.norm(np.array(shape.color) - color) < 3:
            mask |= seg.rid == shape.id
    return mask


@pytest.mark.parametrize("width", [3, 5, 7])
@pytest.mark.parametrize("angle", [0, 45, 90])
def test_isolated_thin_marks_retain_palette_color(width, angle):
    ss = 4
    image = Image.new("RGB", (180 * ss, 140 * ss), NAVY)
    draw = ImageDraw.Draw(image)
    # Establish this colour in the palette away from the narrow mark.
    draw.rectangle((10*ss, 10*ss, 40*ss, 40*ss), fill=CREAM)
    mask = Image.new("L", image.size)
    md = ImageDraw.Draw(mask)
    a = math.radians(angle)
    dx, dy = 11 * math.cos(a), 11 * math.sin(a)
    line = ((100-dx)*ss, (90-dy)*ss, (100+dx)*ss, (90+dy)*ss)
    draw.line(line, fill=CREAM, width=width*ss)
    md.line(line, fill=255, width=width*ss)
    rgb = np.asarray(image.resize((180, 140), Image.Resampling.LANCZOS))
    expected = np.asarray(mask.resize((180, 140), Image.Resampling.LANCZOS)) >= 128
    result = segment(_loaded(rgb), Config())
    recovered = _color_mask(result, CREAM)
    recovered[:50] = False  # exclude the palette reference swatch
    iou = np.count_nonzero(recovered & expected) / max(
        1, np.count_nonzero(recovered | expected))
    assert iou >= 0.85, f"{width}px mark at {angle}deg: IoU {iou:.3f}"
    assert len(result.shapes) == 3, "background, reference swatch, and one connected mark"


def test_antialiased_edge_does_not_borrow_unrelated_palette_color():
    rgb = np.full((100, 220, 3), 255, np.uint8)
    rgb[:, 101:] = 0
    rgb[:, 100] = 127  # 50% black/white coverage, not a grey object
    rgb[10:35, 10:35] = 127  # real grey swatch establishes a third palette colour
    result = segment(_loaded(rgb), Config())
    grey = _color_mask(result, (127, 127, 127))
    assert not grey[:, 95:106].any(), "a blend must not become a false grey outline"
    assert grey[15:30, 15:30].all()


def test_seed_fallback_keeps_transparency_and_speckle_filtering():
    rgb = np.full((80, 160, 3), NAVY, np.uint8)
    rgb[10:30, 10:30] = CREAM
    rgb[50, 70] = CREAM  # isolated noise, smaller than filter_speckle
    rgb[45:60, 110:120] = CREAM  # RGB under transparency is irrelevant
    alpha = np.full((80, 160), 255, np.uint8)
    alpha[40:65, 105:125] = 0
    result = segment(_loaded(rgb, alpha), Config())
    cream = _color_mask(result, CREAM)
    assert not cream[48:53, 68:73].any()
    assert (result.rid[40:65, 105:125] == -1).all()
    assert cream[15:25, 15:25].all()


def test_all_panel_ticks_survive_segmentation():
    from challenges import _mask
    from plate.raster import have_renderer, render_svg

    if not have_renderer():
        pytest.skip("target stroke masks require the render extra")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "complex_instrument_panel.png", Config())
    root = ET.parse(directory / "complex_instrument_panel.target.svg").getroot()
    recovered = _color_mask(result.seg, CREAM)
    rendered = render_svg(result.svg, result.loaded.orig_size)
    emitted = np.linalg.norm(rendered.astype(float) - CREAM, axis=2) < 45
    ticks = [e for e in root if "-tick-" in e.get("id", "")]
    assert len(ticks) == 18
    for tick in ticks:
        expected = _mask(root, tick)
        coverage = np.count_nonzero(recovered & expected) / np.count_nonzero(expected)
        assert coverage >= 0.8, f"{tick.get('id')}: only {coverage:.0%} survives segmentation"
        painted = np.count_nonzero(emitted & expected) / np.count_nonzero(expected)
        assert painted >= 0.8, f"{tick.get('id')}: only {painted:.0%} survives SVG output"


@pytest.mark.parametrize("width", [3, 5, 7])
def test_thin_curve_stays_connected_to_seeded_head(width):
    ss = 4
    image = Image.new("RGB", (220*ss, 170*ss), NAVY)
    mask = Image.new("L", image.size)
    # A thick head supplies flat seeds; the narrow branch contains long straight
    # runs and a bend. It must not be excluded merely because its head is seeded.
    points = [(35, 75), (75, 75)]
    for t in np.linspace(0, 1, 40):
        points.append((75+40*t-20*t*t, 75+25*t*t))
    points += [(95, 130), (180, 130)]
    coords = [(x*ss, y*ss) for x, y in points]
    for draw, color in ((ImageDraw.Draw(image), CREAM), (ImageDraw.Draw(mask), 255)):
        draw.ellipse((21*ss, 61*ss, 49*ss, 89*ss), fill=color)
        draw.line(coords, fill=color, width=width*ss, joint="curve")
    rgb = np.asarray(image.resize((220, 170), Image.Resampling.LANCZOS))
    expected = np.asarray(mask.resize((220, 170), Image.Resampling.LANCZOS)) >= 128
    result = segment(_loaded(rgb), Config())
    owners = result.rid[expected]
    cream_ids = [s.id for s in result.shapes if np.linalg.norm(np.array(s.color)-CREAM) < 3]
    counts = [np.count_nonzero(owners == sid) for sid in cream_ids]
    assert max(counts, default=0) / expected.sum() >= 0.9, "curve must be one connected colour region"


@pytest.mark.parametrize("route", ["left-signal-route", "right-signal-route"])
def test_panel_signal_route_is_one_continuous_region(route):
    from challenges import _mask
    from plate.raster import have_renderer

    if not have_renderer():
        pytest.skip("target stroke masks require the render extra")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "complex_instrument_panel.png", Config())
    root = ET.parse(directory / "complex_instrument_panel.target.svg").getroot()
    target = next(e for e in root if e.get("id") == route)
    expected = _mask(root, target)
    color = tuple(bytes.fromhex(target.get("stroke")[1:]))
    owners = result.seg.rid[expected]
    counts = [np.count_nonzero(owners == s.id) for s in result.seg.shapes
              if np.linalg.norm(np.array(s.color)-color) < 3]
    assert max(counts, default=0) / expected.sum() >= 0.9, "signal route remains fragmented"
