"""A small exposed cap must be proved to belong to the same hidden curve."""
import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from scipy import ndimage as ndi

from plate import pipeline
from plate.config import Config
from plate.masks import Mask
from plate.raster import have_renderer
from plate.scene import Loaded
from challenges import assert_target, drawables, _mask


def test_orbit_all_seven_strokes_and_radial_core_match_unchanged_targets():
    if not have_renderer():
        pytest.skip('requires renderer')
    directory = Path(__file__).resolve().parents[1]/'samples/challenges'
    result = pipeline.run(directory/'logo_orbit_wordmark.png')
    actual = ET.fromstring(result.svg)
    target = ET.parse(directory/'logo_orbit_wordmark.target.svg').getroot()
    got = [e for e in actual.iter() if e.get('stroke') or
           (e.tag.endswith('circle') and e.get('fill', '').startswith('url('))]
    wanted = [e for e in target.iter() if e.get('stroke') or e.get('id') == 'gradient-core']
    assert len(got) == len(wanted) == 8
    # Both highlights are painted over the navy monogram. Tiny model/ownership
    # fringes must not promote that earlier artwork into a new occluder.
    leaves = drawables(actual)
    for label in ('upper-light-arc', 'lower-light-arc'):
        region = _mask(target, next(e for e in wanted if e.get('id') == label))
        cream = max([e for e in leaves if e.get('stroke') == '#f5edda'],
                    key=lambda e: np.count_nonzero(_mask(actual, e) & region))
        beneath = [e for e in leaves if e.get('fill') == '#182e4c'
                   and np.count_nonzero(_mask(actual, e) & region) > 16]
        assert beneath and all(leaves.index(e) < leaves.index(cream) for e in beneath)
    actual[:] = [e for e in actual if e.tag.endswith('defs')]+got
    target[:] = [e for e in target if e.tag.endswith('defs')]+wanted
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(target, encoding='unicode'))
    # Compound navy emblem fragments (the badge-ring arcs and four cutout tabs)
    # are reunited into one ring object, so ORBIT now emits 38, not 44. The seven
    # strokes and the radial core above are still matched against the unchanged
    # targets by assert_target.
    assert result.stats['shapes'] == 38
    assert result.shapes is result.seg.shapes
    assert [s.id for s in result.shapes] == list(range(len(result.shapes)))
    for s in result.shapes:
        assert np.all(result.seg.rid[s.vis.to_full(result.seg.rid.shape)] == s.id)


def _parts(butt=False):
    if not have_renderer():
        pytest.skip('requires renderer')
    from PIL import Image
    import cairosvg
    cap = 'butt' if butt else 'round'
    curve = ('<path d="M164 196Q189 166 226 176" fill="none" stroke="#f5edda" '
             f'stroke-width="8" stroke-linecap="{cap}" stroke-linejoin="round"/>')
    loop = ('<ellipse cx="215" cy="240" rx="190" ry="62" transform="rotate(25 215 240)" '
            'fill="none" stroke="#e9bc59" stroke-width="6"/>')
    def raster(body):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="440" height="440">'+body+'</svg>'
        png = cairosvg.svg2png(bytestring=svg.encode(), scale=4)
        with Image.open(io.BytesIO(png)) as im:
            return np.asarray(im.convert('RGBA').resize((440, 440), Image.Resampling.LANCZOS))
    ink, cover = raster(curve)[..., 3] >= 128, raster(loop)[..., 3] >= 128
    labels, count = ndi.label(ink & ~cover)
    masks = [Mask.from_full(labels == i) for i in range(1, count+1) if np.count_nonzero(labels == i) >= 6]
    assert len(masks) == 2
    masks.sort(key=lambda m: -m.area)
    source = raster('<rect width="440" height="440" fill="#182e4c"/>'+curve+loop)
    loaded = Loaded(source[..., :3].copy(), source[..., 3].copy(), (440, 440), 1.)
    return *masks, Mask.from_full(cover), loaded, ink


def test_small_cap_rejoins_a_full_round_curve_with_disjoint_observation():
    from plate.stages.curves import fit_fragmented_curve
    main, tail, cover, image, expected = _parts()
    fit = fit_fragmented_curve(main, tail, Config(), cover, image, (245, 237, 218))
    assert fit is not None and fit.completed
    assert abs(fit.width-8) < .5
    actual = fit.full.to_full(expected.shape)
    assert (actual & expected).sum()/(actual | expected).sum() >= .96
    assert np.all(ndi.binary_dilation(actual)[main.to_full(expected.shape) | tail.to_full(expected.shape)])


@pytest.mark.parametrize('problem', ['butt', 'dot', 'offset', 'uncovered'])
def test_unrelated_caps_and_uncovered_gaps_do_not_form_a_curve(problem):
    from plate.stages.curves import fit_fragmented_curve
    main, tail, cover, image, _ = _parts(butt=problem == 'butt')
    if problem == 'dot':
        y, x = np.mgrid[:440, :440]
        tail = Mask.from_full((x-229)**2+(y-169)**2 <= 9)
    if problem == 'offset':
        tail = Mask(tail.a, tail.y0+6, tail.x0)
    if problem == 'uncovered':
        cover = Mask.from_full(np.zeros((440, 440), bool))
    assert fit_fragmented_curve(main, tail, Config(), cover, image, (245, 237, 218)) is None


@pytest.mark.parametrize('gap', [1, 3, 6])
def test_even_narrow_exposed_gaps_stay_open(gap):
    from plate.stages.curves import fit_fragmented_curve
    main, tail, cover, image, _ = _parts()
    observed = main.to_full((440, 440))
    observed[:, 185:185+gap] = False
    assert fit_fragmented_curve(Mask.from_full(observed), tail, Config(), cover, image, (245, 237, 218)) is None


@pytest.mark.parametrize('switch', ['strokes', 'complete_hidden'])
def test_fragment_pooling_respects_disable_switches(switch):
    from plate.stages.curves import fit_fragmented_curve
    main, tail, cover, image, _ = _parts()
    assert fit_fragmented_curve(main, tail, Config(**{switch: False}), cover, image, (245, 237, 218)) is None


@pytest.mark.parametrize('gap', [1, 3, 6])
@pytest.mark.parametrize('transparent', [False, True])
def test_a_gap_beside_the_crossing_is_not_an_antialias_fringe(gap, transparent):
    from plate.stages.curves import fit_fragmented_curve
    main, tail, cover, image, _ = _parts()
    observed = main.to_full((440, 440))
    removed = observed & ndi.binary_dilation(cover.to_full((440, 440)), iterations=gap)
    image.rgb[removed] = (24, 46, 76)
    if transparent:
        image.alpha[removed] = 0
    assert fit_fragmented_curve(Mask.from_full(observed & ~removed), tail, Config(), cover, image, (245, 237, 218)) is None


@pytest.mark.parametrize('problem', [None, 'parent', 'colour', 'earlier', 'unproved'])
def test_recovery_requires_siblings_matching_colour_and_a_later_proven_loop(problem):
    from plate.scene import Shape, Segmentation
    from plate.stages.curves import recover
    main, tail, cover, image, _ = _parts()
    shapes = [Shape(i, (245, 237, 218) if i < 2 else (233, 188, 89), m, m, sil=m)
              for i, m in enumerate((main, tail, cover))]
    rid = np.full((440, 440), -1, np.int32)
    for s in shapes:
        rid[s.vis.to_full(rid.shape)] = s.id
    seg = Segmentation(rid, shapes, np.zeros((0, 3), np.uint8))
    known = {cover: object()}
    roots = [0, 1, 2]
    if problem == 'parent':
        shapes[1].parent = 2
    elif problem == 'colour':
        shapes[1].color = (250, 235, 220)
    elif problem == 'earlier':
        roots = [2, 0, 1]
    elif problem == 'unproved':
        known = {}
        shapes[2].full = cover.filled()
    recovered = recover(seg, roots, image, Config(), known)
    if problem is None:
        assert recovered is not None and recovered.ids == (0, 1)
    else:
        assert recovered is None
