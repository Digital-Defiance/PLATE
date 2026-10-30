"""Short round-cap curves can lose a cap beneath a proven closed stroke."""
import io
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from plate import pipeline
from plate.config import Config
from plate.raster import have_renderer
from plate.stages.strokes import fit_crossed_curve
from challenges import assert_target, _mask


def _crossed(tmp_path, problem=None, scale=1):
    if not have_renderer():
        pytest.skip('requires renderer')
    import cairosvg
    path = 'M247 280Q225 306 192 293'
    cap = 'butt' if problem == 'butt' else 'round'
    curve = (f'<path id="curve" d="{path}" fill="none" stroke="#f5edda" '
             f'stroke-width="8" stroke-linecap="{cap}" stroke-linejoin="round"/>')
    if problem == 'taper':
        curve = '<path id="curve" d="M244 277Q223 300 192 291L192 295Q229 314 250 283Z" fill="#f5edda"/>'
    shift = 25 if problem == 'gap' else 0
    loop = (f'<ellipse id="cover" cx="215" cy="{240+shift}" rx="190" ry="62" '
            f'transform="rotate(25 215 {240+shift})" fill="none" stroke="#e9bc59" stroke-width="6"/>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="440" height="440">'
           '<circle cx="215" cy="240" r="117" fill="#182e4c"/>'+curve+loop+'</svg>')
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4*scale))) as im:
        output = tmp_path/'crossed.png'
        im.resize((440*scale, 440*scale), Image.Resampling.LANCZOS).save(output)
    if scale != 1:
        svg = svg.replace('width="440" height="440">', f'width="{440*scale}" height="{440*scale}" viewBox="0 0 440 440">')
    return output, svg


def test_orbit_lower_highlight_is_an_editable_full_stroke():
    if not have_renderer():
        pytest.skip('requires renderer')
    directory = Path(__file__).resolve().parents[1]/'samples/challenges'
    result = pipeline.run(directory/'logo_orbit_wordmark.png')
    actual = ET.fromstring(result.svg)
    target = ET.parse(directory/'logo_orbit_wordmark.target.svg').getroot()
    wanted = [e for e in target.iter() if e.get('id') in ('lower-light-arc', 'front-orbit')]
    lower = _mask(target, next(e for e in wanted if e.get('id') == 'lower-light-arc'))
    got = [e for e in actual.iter() if (e.get('stroke') == '#e9bc59' and e.tag.endswith('ellipse'))
           or (e.get('stroke') == '#f5edda' and (_mask(actual, e) & lower).sum() > 100)]
    assert len(got) == len(wanted) == 2
    actual[:] = got
    target[:] = wanted
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(target, encoding='unicode'))



def _parts(path):
    result = pipeline.run(path, Config(work_size=440, strokes=False))
    ink, = [s for s in result.shapes if s.color == (245, 237, 218)]
    loop, = [s for s in result.shapes if s.color[0] > 230 and s.color[1] < 210]
    return result, ink, loop


@pytest.mark.parametrize('scale', [1, 2])
def test_crossed_short_curve_preserves_full_shape_and_source_scaled_width(tmp_path, scale):
    path, target = _crossed(tmp_path, scale=scale)
    result, ink, loop = _parts(path)
    fitted = fit_crossed_curve(ink.vis, Config(), [loop.vis], result.loaded, ink.color)
    assert fitted is not None and fitted.completed
    assert abs(fitted.width-8) < .6
    # Check the full fitted curve independently of its partly hidden source mask.
    actual = ET.Element('svg', width=str(440*scale), height=str(440*scale))
    curve = (fitted.curves[0]+.5)*scale
    ET.SubElement(actual, 'path', d='M'+','.join(map(str, curve[0]))+'C'+' '.join(map(str, curve[1:].ravel())),
                  fill='none', stroke='#f5edda', **{'stroke-width': str(fitted.width*scale), 'stroke-linecap': 'round', 'stroke-linejoin': 'round'})
    wanted = ET.fromstring(target)
    wanted[:] = [e for e in wanted if e.get('id') == 'curve']
    if scale != 1:
        wanted.attrib.pop('viewBox', None)
        wanted[0].set('d', re.sub(r'\d+', lambda m: str(int(m[0])*scale), wanted[0].get('d')))
        wanted[0].set('stroke-width', str(8*scale))
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(wanted, encoding='unicode'))


@pytest.mark.parametrize('problem', ['butt', 'taper'])
def test_crossed_curve_rejects_flat_caps_and_taper(tmp_path, problem):
    path, _ = _crossed(tmp_path, problem)
    result, ink, loop = _parts(path)
    assert fit_crossed_curve(ink.vis, Config(), [loop.vis], result.loaded, ink.color) is None


@pytest.mark.parametrize('setting', ['strokes', 'complete_hidden'])
def test_crossed_curve_respects_disable_switches(tmp_path, setting):
    path, _ = _crossed(tmp_path)
    result, ink, loop = _parts(path)
    assert fit_crossed_curve(ink.vis, Config(**{setting: False}), [loop.vis], result.loaded, ink.color) is None


def test_detached_closed_stroke_does_not_complete_a_curve(tmp_path):
    path, _ = _crossed(tmp_path, 'gap')
    result, ink, loop = _parts(path)
    assert fit_crossed_curve(ink.vis, Config(), [loop.vis], result.loaded, ink.color) is None


@pytest.mark.parametrize('gap', [1, 3, 6])
def test_exposed_gap_before_closed_loop_is_not_hidden_completion(tmp_path, gap):
    from scipy import ndimage as ndi
    from plate.masks import Mask
    path, _ = _crossed(tmp_path)
    result, ink, loop = _parts(path)
    canvas = result.loaded.alpha.shape
    cut = ink.vis.to_full(canvas) & ~ndi.binary_dilation(loop.vis.to_full(canvas), iterations=gap)
    assert fit_crossed_curve(Mask.from_full(cut), Config(), [loop.vis], result.loaded, ink.color) is None
