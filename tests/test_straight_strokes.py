"""Short round strokes must retain cap geometry instead of becoming ellipses."""
import copy
import io
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from plate import pipeline
from plate.config import Config
from plate.raster import have_renderer
from challenges import assert_target


def _image(tmp_path, width, length, angle, cap="round", transparent=False, kind="line"):
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    x, y = 120 + length*math.cos(math.radians(angle)), 120 + length*math.sin(math.radians(angle))
    background = "" if transparent else '<rect width="320" height="240" fill="#ffffff"/>'
    if kind == "ellipse":
        shape = '<ellipse cx="160" cy="120" rx="40" ry="4" fill="#182e4c"/>'
    elif kind == "taper":
        shape = '<path d="M100 116L220 112V128L100 124Z" fill="#182e4c"/>'
    else:
        shape = (f'<path d="M120 120L{x} {y}" stroke="#182e4c" stroke-width="{width}" '
                 f'stroke-linecap="{cap}" fill="none"/>')
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">'+background+shape+'</svg>'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / "straight.png"
        image.resize((320, 240), Image.Resampling.LANCZOS).save(path)
    return path, svg


@pytest.mark.parametrize("width,length,angle,transparent", [
    (3, 12, 0, True), (5, 10, 25, False), (5, 10, 145, False),
    (7, 30, 45, False), (5, 30, 90, True), (12, 80, 20, True),
])
def test_straight_round_line_matches_authored_target(tmp_path, width, length, angle, transparent):
    path, target = _image(tmp_path, width, length, angle, transparent=transparent)
    # Isolate stroke fitting from discovery of an otherwise unseeded 3px colour.
    result = pipeline.run(path, Config(palette=("#ffffff", "#182e4c")))
    assert result.stats["strokes"] == 1
    stroke, = [e for e in ET.fromstring(result.svg).iter() if e.get("stroke")]
    assert stroke.get("stroke-linecap") == "round"
    assert "C" not in stroke.get("d") and "Z" not in stroke.get("d").upper()
    assert_target(result.svg, target)


@pytest.mark.parametrize("cap,angle,kind", [
    ("butt", 0, "line"), ("butt", 45, "line"), ("square", 25, "line"),
    ("round", 0, "ellipse"), ("round", 0, "taper"),
])
def test_other_shapes_do_not_acquire_round_caps(tmp_path, cap, angle, kind):
    path, _ = _image(tmp_path, 5, 100, angle, cap=cap, kind=kind)
    result = pipeline.run(path, Config(palette=("#ffffff", "#182e4c")))
    assert result.stats["shapes"] == 2
    assert result.stats["strokes"] == 0


@pytest.mark.parametrize("part,color,count", [("tick", "#f5edda", 18), ("slot", "#182e4c", 4)])
def test_panel_recovers_authored_straight_marks(part, color, count):
    if not have_renderer():
        pytest.skip("requires target renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    target = ET.parse(directory / "complex_instrument_panel.target.svg").getroot()
    result = pipeline.run(directory / "complex_instrument_panel.png", Config())
    actual = ET.fromstring(result.svg)
    wanted = [e for e in target.iter() if ("-tick-" in e.get("id", "") if part == "tick"
                                          else e.get("id", "").startswith("mount-slot-"))]
    got = [e for e in actual.iter() if e.get("stroke") == color]
    assert len(wanted) == len(got) == count
    for root, elements in ((target, wanted), (actual, got)):
        root[:] = [copy.deepcopy(e) for e in elements]
    assert_target(ET.tostring(actual, encoding="unicode"), ET.tostring(target, encoding="unicode"))


def test_straight_width_scales_to_source_coordinates_and_can_be_disabled(tmp_path):
    path, target = _image(tmp_path, 12, 80, 20, transparent=True)
    result = pipeline.run(path, Config(work_size=160))
    assert result.stats["strokes"] == 1
    assert_target(result.svg, target)
    assert pipeline.run(path, Config(work_size=160, strokes=False)).stats["strokes"] == 0
