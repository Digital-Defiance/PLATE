"""Editable constant-width curves, including occlusion and rejection controls."""
import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image, ImageDraw

from plate import pipeline
from plate.config import Config
from plate.masks import Mask
from plate.raster import have_renderer


def _curve_png(tmp_path, width=12):
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
           '<rect width="400" height="300" fill="#ffffff"/>'
           f'<path d="M60 240V100Q60 60 100 60H230Q270 60 270 100V200Q270 240 310 240H350" '
           f'fill="none" stroke="#182e4c" stroke-width="{width}" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / "curve.png"
        image.resize((400, 300), Image.Resampling.LANCZOS).save(path)
    return path


@pytest.mark.parametrize("width", [6, 12, 16])
def test_curved_line_emits_one_editable_open_stroke(tmp_path, width):
    result = pipeline.run(_curve_png(tmp_path, width), Config())
    strokes = [e for e in ET.fromstring(result.svg).iter() if e.get("stroke")]
    assert len(strokes) == 1
    stroke = strokes[0]
    assert stroke.get("fill") == "none"
    assert abs(float(stroke.get("stroke-width")) - width) <= 1
    assert stroke.get("stroke-linecap") == stroke.get("stroke-linejoin") == "round"
    assert "Z" not in stroke.get("d").upper()
    assert result.stats["strokes"] == 1
    assert result.stats["anchors"] <= 25


def test_occluded_route_matches_independent_target():
    from challenges import assert_target
    if not have_renderer():
        pytest.skip("requires renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "stroked_route.png", Config())
    assert_target(result.svg, (directory / "stroked_route.target.svg").read_text())


def test_detached_circle_does_not_attract_a_stroke_endpoint(tmp_path):
    from plate.geometry import Prim, raster_prim
    from plate.stages.strokes import fit_stroke
    result = pipeline.run(_curve_png(tmp_path, 12), Config(strokes=False))
    ink = next(s for s in result.shapes if np.linalg.norm(np.array(s.color)-(24, 46, 76)) < 3)
    # It is aligned and near enough to pass the geometric proximity gate, but
    # a real white gap separates the stroke from the circle.
    circle = Prim("circle", 59.5, 274.5, 20, 20)
    cover = Mask.from_full(raster_prim(circle, (300, 400)))
    stroke = fit_stroke(ink.full, Config(), [(cover, circle)])
    assert stroke is not None
    assert not stroke.completed, "a nearby circle must not invent a visible connection"


def test_stroke_width_scales_back_to_source_pixels(tmp_path):
    result = pipeline.run(_curve_png(tmp_path, 16), Config(work_size=200))
    strokes = [e for e in ET.fromstring(result.svg).iter() if e.get("stroke")]
    assert len(strokes) == 1
    assert abs(float(strokes[0].get("stroke-width")) - 16) <= 1


def test_stroke_detection_can_be_disabled(tmp_path):
    result = pipeline.run(_curve_png(tmp_path), Config(strokes=False))
    assert result.stats["strokes"] == 0
    assert not any(e.get("stroke") for e in ET.fromstring(result.svg).iter())


def test_thin_color_discovery_respects_explicit_palette(tmp_path):
    result = pipeline.run(_curve_png(tmp_path, 6), Config(palette=("#ffffff",)))
    assert result.seg.palette.tolist() == [[255, 255, 255]]
    assert result.stats["strokes"] == 0


def test_zero_decimal_stroke_coordinates_preserve_integer_zeroes(tmp_path):
    from plate import metrics
    path = _curve_png(tmp_path, 12)
    result = pipeline.run(path, Config(path_precision=0))
    with Image.open(path) as image:
        fidelity = metrics.fidelity(result.svg, np.asarray(image.convert("RGBA")))
    assert fidelity["ssim"] >= 0.985


@pytest.mark.parametrize("kind", ["taper", "branch", "ring"])
def test_nonuniform_branched_and_closed_shapes_are_not_open_strokes(kind):
    from plate.stages.strokes import fit_stroke
    image = Image.new("L", (200, 160))
    draw = ImageDraw.Draw(image)
    if kind == "taper":
        draw.polygon([(20, 70), (180, 40), (180, 120), (20, 90)], fill=255)
    elif kind == "branch":
        draw.line([(30, 30), (100, 80), (170, 30)], fill=255, width=10)
        draw.line([(100, 80), (100, 140)], fill=255, width=10)
    else:
        draw.ellipse((30, 20, 170, 150), outline=255, width=10)
    assert fit_stroke(Mask.from_full(np.asarray(image) > 0), Config()) is None


def test_wide_square_ended_letter_is_not_replaced_by_round_caps():
    from plate.stages.strokes import fit_stroke
    from challenges import _mask
    if not have_renderer():
        pytest.skip("requires target renderer")
    path = Path(__file__).resolve().parents[1] / "samples/challenges/edge_crossing_type.target.svg"
    root = ET.parse(path).getroot()
    letter = next(e for e in root if e.get("id") == "letter-C")
    assert fit_stroke(Mask.from_full(_mask(root, letter)), Config()) is None


def test_stroke_style_survives_svg_emission():
    from plate import metrics
    from plate.scene import Node
    from plate.stages.emit import write_svg
    node = Node("Ink", "path", (24, 46, 76), d="M2 2L20 20", stroke_width=3,
                stroke_linecap="butt", stroke_linejoin="bevel")
    svg = write_svg([node], (30, 30))
    path = next(e for e in ET.fromstring(svg).iter() if e.tag.endswith("}path"))
    assert path.get("stroke-width") == "3"
    assert path.get("stroke-linecap") == "butt"
    assert path.get("stroke-linejoin") == "bevel"
    assert path.get("fill") == "none"
    assert metrics.analyze_svg(svg)["strokes"] == 1
    assert metrics.analyze_svg(svg)["anchors"] == 2


def test_orbit_motion_curves_stay_strokes_and_square_ended_letter_stays_filled():
    from challenges import _mask, assert_target, drawables
    if not have_renderer():
        pytest.skip("requires target renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "logo_orbit_wordmark.png")
    actual = ET.fromstring(result.svg)
    target = ET.parse(directory / "logo_orbit_wordmark.target.svg").getroot()
    letter = next(e for e in target.iter() if e.get("id") == "descriptor-3-U")
    wanted_mask = _mask(target, letter)
    elements = drawables(actual)
    masks = [_mask(actual, e) for e in elements]
    ious = [np.count_nonzero(m & wanted_mask)/max(1, np.count_nonzero(m | wanted_mask)) for m in masks]
    got_letter = elements[int(np.argmax(ious))]
    assert got_letter.get("stroke") is None, "square-ended outlined U must keep its filled silhouette"
    wanted = [e for e in target.iter() if e.get("id", "").startswith("motion-line-")]
    got = [e for e, mask in zip(elements, masks) if e.get("stroke")
           and np.nonzero(mask)[1].mean() > 700]
    assert len(got) == len(wanted) == 3
    actual[:] = got
    target[:] = wanted
    assert_target(ET.tostring(actual, encoding="unicode"), ET.tostring(target, encoding="unicode"))
