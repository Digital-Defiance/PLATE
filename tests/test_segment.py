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


@pytest.mark.parametrize("kind,width", [("circle", 3), ("circle", 5), ("ellipse", 3), ("ellipse", 5)])
def test_transparent_loop_does_not_lose_opaque_pixels_to_nearby_transparency(tmp_path, kind, width):
    import io
    from plate.imageio import load_image
    from plate.raster import have_renderer
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg

    radii = 'r="115"' if kind == "circle" else 'rx="165" ry="85" transform="rotate(25 210 160)"'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="320">'
           f'<{kind} cx="210" cy="160" {radii} fill="none" stroke="#182e4c" '
           f'stroke-width="{width}"/></svg>')
    path = tmp_path / "loop.png"
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        image.resize((420, 320), Image.Resampling.LANCZOS).save(path)
    img = load_image(path, Config())
    expected = img.alpha >= 128
    result = segment(img, Config())
    assert len(result.shapes) == 1, "one closed loop must stay one connected colour region"
    assert np.array_equal(result.rid >= 0, expected), "foreground alpha must not become transparency"


# --------------------------------------------------------------------------- R7c
# Palette pressure > 64 colours: a labelled flat MOSAIC fixture (scripts/make_mosaic.py)
# exercises the two palette paths in _build_palette. Up to FLAT_PALETTE_CEILING (96)
# exactly-repeated flat colours are honoured verbatim; beyond the ceiling the input falls
# to the k-means fallback, which is bounded by max_colors (default 16, a photo cap). These
# tests pin the measured recovery of each path so the behaviour cannot drift.

def _mosaic(ncolors):
    """Build the mosaic fixture array + its ground-truth colours via the scripts generator."""
    import importlib.util
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("make_mosaic", root / "scripts/make_mosaic.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    img, meta = module.make_mosaic(ncolors)
    return img, np.array(meta["colors"], float)


def _recovered(palette, colors, tol=8.0):
    pal = palette.astype(float)
    if not len(pal):
        return 0
    return int(sum(np.linalg.norm(pal - c, axis=1).min() <= tol for c in colors))


def test_flat_mosaic_up_to_the_ceiling_is_recovered_verbatim_at_default_budget():
    """A 90-colour flat mosaic (<= FLAT_PALETTE_CEILING) is honoured exactly at the DEFAULT
    max_colors=16: the flat-palette branch keeps genuinely-distinct repeated flat colours
    because they explain ~100% of flat pixels, rather than collapsing them with k-means.
    Measured: palette 85, 84/90 colours recovered within 8 RGB (the few merges are pairs
    within the color_merge Lab floor by construction of the random generator)."""
    img, colors = _mosaic(90)
    h, w = img.shape[:2]
    seg = segment(_loaded(img), Config())
    assert len(seg.palette) >= 80, len(seg.palette)
    assert _recovered(seg.palette, colors) >= 82, _recovered(seg.palette, colors)


def test_high_cardinality_mosaic_collapses_to_max_colors_at_the_default_budget():
    """DOCUMENTED DEFAULT CEILING, measured. A 130-colour flat mosaic exceeds the
    FLAT_PALETTE_CEILING (96), so _build_palette takes the k-means fallback, which is bounded
    by max_colors. At the DEFAULT max_colors=16 (a deliberate cap for photographic input, to
    bound the O(K^2) per-pair edge assignment) the 130 distinct swatches collapse into 16
    averaged clusters: 0/130 recovered within 8 RGB. This is the measured default behaviour,
    not a bug - raising max_colors recovers the mosaic (next test)."""
    img, colors = _mosaic(130)
    seg = segment(_loaded(img), Config())
    assert len(seg.palette) == 16, len(seg.palette)
    assert _recovered(seg.palette, colors) == 0, _recovered(seg.palette, colors)


@pytest.mark.parametrize("max_colors,floor", [(96, 60), (130, 108)])
def test_kmeans_path_recovers_a_high_cardinality_mosaic_when_the_budget_is_raised(max_colors, floor):
    """R7c state (a): the k-means path in _build_palette DOES recover a >96-colour flat mosaic
    once max_colors is raised to admit it - proving recovery is a budget choice, not a path
    failure. Measured on the 130-colour fixture: max_colors=96 -> 73/130 recovered within 8
    RGB, max_colors=130 -> 113/130 (vs 0/130 at the default). The remainder are k-means
    centroids landing between near neighbours, inherent to a bounded clustering of exact
    swatches. Floors are set below the measured numbers to pin the recovery without being
    brittle to minor centroid drift."""
    img, colors = _mosaic(130)
    seg = segment(_loaded(img), Config(max_colors=max_colors))
    recovered = _recovered(seg.palette, colors)
    assert recovered >= floor, f"max_colors={max_colors}: only {recovered}/130 recovered"


# --------------------------------------------------------------------------- R7a
# Thin-colour / hairline discovery for FULLY ANTI-ALIASED features. The isolated-alpha-component
# admission in segment.py needs a stable, nearly-opaque (alpha >= 245) erodable INTERIOR core to
# admit a new flat colour from a narrow mark that carries no flat seed. A fully anti-aliased
# feature narrower than ~3 working px is almost all fringe: its eroded interior is empty or its
# core never reaches alpha >= 245, so its colour cannot be admitted. These tests PIN the measured
# sub-pixel floor (R7a state (b)): width >= 3 is admitted, width 2 is below the floor. Do NOT
# lower the admission gate to force the 2px case - the documented route pins in
# tests/test_robustness.py (test_hairline_route_1px/2px) prove any admitting rule regresses the
# currently-green marks-s0p5 line4 route and the panels blur halos.

def _isolated_aa_mark(width):
    """An isolated fully-anti-aliased cream diagonal dash on navy, with NO thick same-colour
    head/seed anywhere, so only the isolated-alpha-component path could admit its colour."""
    ss = 4
    w, h = 160, 120
    image = Image.new("RGB", (w * ss, h * ss), NAVY)
    ImageDraw.Draw(image).line([60 * ss, 40 * ss, 100 * ss, 80 * ss], fill=CREAM, width=width * ss)
    return np.asarray(image.resize((w, h), Image.Resampling.LANCZOS))


@pytest.mark.parametrize("width", [3, 4, 5])
def test_fully_antialiased_mark_at_or_above_the_floor_is_admitted(width):
    """R7a floor (upper side): a fully anti-aliased mark >= 3 working px has a stable opaque core
    and IS admitted to the palette as its own cream colour via the isolated-alpha path."""
    seg = segment(_loaded(_isolated_aa_mark(width)), Config())
    assert np.linalg.norm(seg.palette.astype(float) - np.array(CREAM), axis=1).min() < 20, \
        f"width={width}: cream must be admitted"


def test_fully_antialiased_2px_mark_is_below_the_isolated_alpha_admission_floor():
    """R7a state (b) DOCUMENTED SUB-PIXEL FLOOR, measured. A fully anti-aliased 2 working-px mark
    is almost all anti-alias fringe: it has no flat seed and no stable alpha>=245 erodable core,
    so the isolated-alpha-component admission cannot admit its true cream colour (measured: cream
    is NOT within 20 RGB of any palette entry, whereas the 3px mark above IS). Admitting it would
    require lowering the admission gate, which the route pins prove regresses shipped/green cases.
    This pins the floor so a regression or a silent gate-weakening is caught."""
    seg = segment(_loaded(_isolated_aa_mark(2)), Config())
    assert np.linalg.norm(seg.palette.astype(float) - np.array(CREAM), axis=1).min() >= 20, \
        "the 2px fully-antialiased mark must stay below the admission floor"
