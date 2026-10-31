"""Short exposed round-cap curves keep their authored stroke geometry."""
import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from challenges import _mask, assert_target, drawables
from PIL import Image

from plate import pipeline
from plate.config import Config
from plate.raster import have_renderer
from plate.stages.strokes import fit_stroke

pytestmark = pytest.mark.skipif(not have_renderer(), reason="requires renderer")


def _curve(tmp_path, mirror=False, transparent=False, cap="round"):
    import cairosvg
    transform = ' transform="translate(256 0) scale(-1 1)"' if mirror else ""
    background = '' if transparent else '<rect width="256" height="144" fill="#fff6df"/>'
    target = ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="144">'
              + background
              + '<path id="curve" d="M148 105Q189 102 212 88" fill="none" '
              f'stroke="#182e4c" stroke-width="4" stroke-linecap="{cap}" '
              f'stroke-linejoin="round"{transform}/></svg>')
    source = tmp_path/'curve.png'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=target.encode(), scale=4))) as image:
        image.resize((256, 144), Image.Resampling.LANCZOS).save(source)
    return source, target


@pytest.mark.parametrize("mirror", [False, True])
@pytest.mark.parametrize("transparent", [False, True])
def test_short_round_curve_matches_independent_target(tmp_path, mirror, transparent):
    source, target = _curve(tmp_path, mirror, transparent)
    result = pipeline.run(source)
    assert result.stats['strokes'] == 1
    actual, wanted = ET.fromstring(result.svg), ET.fromstring(target)
    actual[:] = [e for e in actual.iter() if e.get('stroke')]
    wanted[:] = [e for e in wanted if e.get('id') == 'curve']
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(wanted, encoding='unicode'))


@pytest.mark.parametrize("mirror", [False, True])
def test_short_square_cap_curve_stays_filled(tmp_path, mirror):
    source, _ = _curve(tmp_path, mirror, cap="square")
    result = pipeline.run(source)
    assert result.stats['strokes'] == 0


def test_rejected_centreline_needs_source_boundary_evidence(tmp_path):
    source, _ = _curve(tmp_path, mirror=True)
    result = pipeline.run(source, Config(strokes=False))
    ink, = [s for s in result.shapes if s.color[0] < 128]
    assert fit_stroke(ink.full, Config()) is None
    assert fit_stroke(ink.full, Config(), img=result.loaded, color=ink.color) is not None


def test_all_four_ember_whiskers_are_independently_editable():
    directory = Path(__file__).resolve().parents[1]/'samples/challenges'
    result = pipeline.run(directory/'logo_ember_crest.png')
    actual = ET.fromstring(result.svg)
    target = ET.parse(directory/'logo_ember_crest.target.svg').getroot()
    wanted = [e for e in target if 'whisker' in e.get('id', '')]
    elements = drawables(actual)
    masks = [_mask(actual, e) for e in elements]
    recovered = []
    for expected in wanted:
        mask = _mask(target, expected)
        ious = [np.count_nonzero(mask & got)/max(1, np.count_nonzero(mask | got)) for got in masks]
        got = elements[int(np.argmax(ious))]
        assert got.get('stroke') is not None, expected.get('id')
        recovered.append(got)
    assert len(wanted) == len({id(e) for e in recovered}) == 4
    actual[:] = recovered
    target[:] = wanted
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(target, encoding='unicode'))
