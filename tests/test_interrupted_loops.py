"""Disconnected loop fragments need a shared fit and observed occlusion evidence."""
import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from plate import pipeline
from plate.config import Config
from plate.raster import have_renderer
from challenges import assert_target


def _scene(tmp_path, angle=25, scale=1, gap=False, background=False, cover_color='#182e4c'):
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    bg = '<rect width="420" height="320" fill="#ffffff"/>' if background else ''
    ink = (f'<ellipse cx="210" cy="160" rx="165" ry="85" transform="rotate({angle} 210 160)" '
           'fill="none" stroke="#a9d1b5" stroke-width="8"/>')
    cover = f'<rect x="140" y="10" width="140" height="300" fill="{cover_color}"/>'
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="320">'+bg+ink+cover+'</svg>'
    path = tmp_path / 'loop.png'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4*scale))) as image:
        image = image.resize((420*scale, 320*scale), Image.Resampling.LANCZOS)
        if gap:
            alpha = np.asarray(image.getchannel('A')).copy()
            alpha[160*scale:(160+gap)*scale, :130*scale] = 0
            image.putalpha(Image.fromarray(alpha))
        image.save(path)
    if scale != 1:
        root = ET.fromstring(svg)
        for element in root.iter():
            for attr in ('x', 'y', 'cx', 'cy', 'rx', 'ry', 'width', 'height', 'stroke-width'):
                if attr in element.attrib:
                    element.set(attr, str(float(element.get(attr))*scale))
            if element.get('transform'):
                element.set('transform', f'rotate({angle} {210*scale} {160*scale})')
        svg = ET.tostring(root, encoding='unicode')
    return path, svg


@pytest.mark.parametrize('angle,scale,work', [(0, 1, 1536), (25, 1, 1536), (25, 2, 420)])
def test_hidden_loop_rejoins_as_one_complete_editable_ellipse(tmp_path, angle, scale, work):
    path, target = _scene(tmp_path, angle, scale)
    result = pipeline.run(path, Config(work_size=work))
    assert result.stats['shapes'] == 2
    assert result.stats['strokes'] == 1
    assert len(result.shapes) == len(result.seg.shapes) == result.stats['shapes']
    for shape in result.shapes:
        assert np.all(result.seg.rid[shape.vis.to_full(result.seg.rid.shape)] == shape.id)
    assert_target(result.svg, target)


@pytest.mark.parametrize('switch', ['strokes', 'complete_hidden'])
def test_fragment_recovery_respects_disable_switches(tmp_path, switch):
    path, _ = _scene(tmp_path)
    result = pipeline.run(path, Config(**{switch: False}))
    assert result.stats['shapes'] == 3
    assert not any(e.get('stroke') and e.tag.endswith('ellipse') for e in ET.fromstring(result.svg).iter())


@pytest.mark.parametrize('gap', [1, 3, 6])
def test_transparent_gap_is_not_hidden_under_the_cover(tmp_path, gap):
    path, _ = _scene(tmp_path, gap=gap)
    result = pipeline.run(path)
    assert not any(e.get('stroke') and e.tag.endswith('ellipse') for e in ET.fromstring(result.svg).iter())


def test_a_background_matching_gap_is_not_occlusion_evidence(tmp_path):
    path, _ = _scene(tmp_path, background=True, cover_color='#ffffff')
    result = pipeline.run(path)
    assert not any(e.get('stroke') and e.tag.endswith('ellipse') for e in ET.fromstring(result.svg).iter())


@pytest.mark.parametrize('different', ['width', 'centre'])
def test_incompatible_same_colour_arcs_are_not_joined(tmp_path, different):
    if not have_renderer():
        pytest.skip('requires renderer')
    import cairosvg
    left, right = (190, 230) if different == 'centre' else (210, 210)
    right_width = 12 if different == 'width' else 8
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="420" height="320">'
           '<defs><clipPath id="l"><rect width="210" height="320"/></clipPath>'
           '<clipPath id="r"><rect x="210" width="210" height="320"/></clipPath></defs>'
           f'<ellipse cx="{left}" cy="160" rx="165" ry="85" fill="none" stroke="#a9d1b5" '
           'stroke-width="8" clip-path="url(#l)"/>'
           f'<ellipse cx="{right}" cy="160" rx="165" ry="85" fill="none" stroke="#a9d1b5" '
           f'stroke-width="{right_width}" clip-path="url(#r)"/>'
           '<rect x="140" y="10" width="140" height="300" fill="#182e4c"/></svg>')
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / 'incompatible.png'
        image.resize((420, 320), Image.Resampling.LANCZOS).save(path)
    result = pipeline.run(path)
    assert not any(e.get('stroke') and e.tag.endswith('ellipse') for e in ET.fromstring(result.svg).iter())


def test_orbit_loops_match_independent_targets_and_paint_order():
    if not have_renderer():
        pytest.skip('requires renderer')
    directory = Path(__file__).resolve().parents[1] / 'samples/challenges'
    result = pipeline.run(directory / 'logo_orbit_wordmark.png')
    actual = ET.fromstring(result.svg)
    target = ET.parse(directory / 'logo_orbit_wordmark.target.svg').getroot()
    wanted = [e for e in target.iter() if e.get('id') in ('back-orbit', 'front-orbit')]
    got = [e for e in actual.iter() if e.tag.endswith('ellipse')
           and e.get('stroke') in ('#a9d1b5', '#e9bc59')]
    assert len(got) == len(wanted) == 2
    actual[:] = got
    target[:] = wanted
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(target, encoding='unicode'))
