"""A hidden straight terminal needs contact, alignment and visible cap evidence."""
import copy
import io
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from plate import pipeline, metrics
from plate.config import Config
from plate.raster import have_renderer
from challenges import assert_target


def _needle(tmp_path, angle=0, scale=1, gap=None, offset=0, front=True, taper=False):
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    centre = np.array([160., 150.])
    axis = np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle))])
    start = centre if gap is None else centre+axis*(18+3.5+gap)
    end = centre+axis*80
    start, end = start*scale, end*scale
    line = (f'<path id="needle" d="M{start[0]} {start[1]}L{end[0]} {end[1]}" '
            f'fill="none" stroke="#e88040" stroke-width="{7*scale}" stroke-linecap="round"/>')
    if taper:
        line = '<path fill="#e88040" d="M160 146.5L240 138V162L160 153.5Z"/>'
    circle = f'<circle id="hub" cx="{160*scale}" cy="{(150+offset)*scale}" r="{18*scale}" fill="#f5edda"/>'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{360*scale}" height="{300*scale}">'
           f'<rect width="{360*scale}" height="{300*scale}" fill="#182e4c"/>'
           +(line+circle if front else circle+line)+'</svg>')
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / "needle.png"
        image.resize((360*scale, 300*scale), Image.Resampling.LANCZOS).save(path)
    return path, svg


@pytest.mark.parametrize("angle,scale", [(-135, 1), (-60, 1), (-20, 1), (-60, 2)])
def test_straight_needle_recovers_full_endpoint_under_hub(tmp_path, angle, scale):
    path, target = _needle(tmp_path, angle=angle, scale=scale)
    result = pipeline.run(path, Config(work_size=360))
    assert result.stats["strokes"] == 1
    needle, = [s for s in result.shapes if s.color == (232, 128, 64)]
    assert needle.completed
    assert_target(result.svg, target)
    with Image.open(path) as image:
        assert metrics.fidelity(result.svg, np.asarray(image.convert("RGBA")))["ssim"] >= .99


@pytest.mark.parametrize("gap", [1, 3, 6])
def test_gap_before_hub_does_not_become_a_hidden_connection(tmp_path, gap):
    path, _ = _needle(tmp_path, gap=gap)
    result = pipeline.run(path, Config())
    needle, = [s for s in result.shapes if s.color == (232, 128, 64)]
    assert not needle.completed
    assert needle.full.x0 >= 160+18+gap-2


@pytest.mark.parametrize("problem", ["offset", "taper"])
def test_hub_cannot_straighten_an_incompatible_silhouette(tmp_path, problem):
    path, _ = _needle(tmp_path, offset=14 if problem == "offset" else 0, taper=problem == "taper")
    result = pipeline.run(path, Config())
    assert result.stats["strokes"] == 0


def test_earlier_circle_does_not_complete_a_later_line(tmp_path):
    path, _ = _needle(tmp_path, front=False)
    result = pipeline.run(path, Config())
    needle, = [s for s in result.shapes if s.color == (232, 128, 64)]
    assert not needle.completed
    assert needle.full.x0 < 162  # retain the visible cap at the hub's centre


def test_all_panel_needles_match_independent_full_strokes():
    if not have_renderer():
        pytest.skip("requires target renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    target = ET.parse(directory / "complex_instrument_panel.target.svg").getroot()
    result = pipeline.run(directory / "complex_instrument_panel.png", Config())
    actual = ET.fromstring(result.svg)
    wanted = [e for e in target.iter() if "-needle" in e.get("id", "")]
    got = [e for e in actual.iter() if e.get("stroke") == "#e88040"]
    assert len(wanted) == len(got) == 3
    for root, elements in ((target, wanted), (actual, got)):
        root[:] = [copy.deepcopy(e) for e in elements]
    assert_target(ET.tostring(actual, encoding="unicode"), ET.tostring(target, encoding="unicode"))


@pytest.mark.parametrize("name", ["complex_instrument_panel", "stroked_route"])
def test_completion_switch_also_applies_to_stroke_endpoints(name):
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / f"{name}.png", Config(complete_hidden=False))
    assert not any(s.completed for s in result.shapes)
