"""Independent per-object robustness contracts; stress misses are reported separately."""
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from plate import pipeline
from plate.config import Config
from plate.raster import have_renderer
from plate.robustness import SweepCase, cases, evaluate, make_input, run_case

pytestmark = pytest.mark.skipif(not have_renderer(), reason='robustness geometry requires renderer')


@pytest.mark.parametrize('scale', [.5, 1])
@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_isolated_marker_survives_without_a_flat_palette_seed(tmp_path, scale, angle):
    case = SweepCase(scale=scale, angle=angle)
    report = run_case(case, tmp_path/'marker')
    marker = next(o for o in report['objects'] if o['name'] == 'marker')
    assert marker['checks']['present'], report
    assert marker['checks']['topology'], marker
    assert report['checks']['object_count'], report
    # This regression guards source ownership. At half size the 12 source pixels
    # survive, but snapping them to a rectangle still misses the independent 90%
    # circle-coverage contract. That stress failure stays red in the sweep.
    image, _ = make_input(case)
    result = pipeline.run(tmp_path/'marker/input.png')
    rgba = np.asarray(image)
    gold = (rgba[..., 3] >= 128) & (rgba[..., 0] > 180) & (rgba[..., 1] > 120) & (rgba[..., 2] < 90)
    assert (result.seg.rid[gold] >= 0).all()
    if scale == 1:
        assert marker['checks']['detail_coverage'], marker


@pytest.mark.parametrize('case', [c for c in cases() if c.tier == 'core'], ids=lambda c: c.name)
def test_core_scale_and_rotation_contract(case, tmp_path):
    report = run_case(case, tmp_path/'case')
    assert report['passed'], report


def test_same_seed_reproduces_input_and_different_seed_changes_noise():
    from dataclasses import replace
    case = SweepCase(noise=4, seed=204, tier='stress')
    first, first_svg = make_input(case)
    again, again_svg = make_input(case)
    different, different_svg = make_input(replace(case, seed=205))
    assert first_svg == again_svg == different_svg
    assert np.array_equal(np.asarray(first), np.asarray(again))
    assert not np.array_equal(np.asarray(first), np.asarray(different))


def test_matcher_rejects_missing_small_detail_even_when_whole_image_ssim_passes():
    case = SweepCase()
    image, expected = make_input(case)
    root = ET.fromstring(expected)
    root.remove(next(e for e in root if e.get('id') == 'marker'))
    report = evaluate(case, ET.tostring(root, encoding='unicode'), expected, image)
    assert report['scores']['reference_white'] > .98
    assert report['scores']['reference_dark'] > .98
    assert not report['passed'] and not report['checks']['objects']
    assert not next(o for o in report['objects'] if o['name'] == 'marker')['checks']['present']


def test_matcher_rejects_hidden_ring_hole_even_if_count_and_colour_match():
    case = SweepCase()
    image, expected = make_input(case)
    root = ET.fromstring(expected)
    ring = next(e for e in root if e.get('id') == 'ring')
    ring.set('d', 'M166 44A24 24 0 1 0 214 44A24 24 0 1 0 166 44Z')
    report = evaluate(case, ET.tostring(root, encoding='unicode'), expected, image)
    assert report['checks']['object_count']
    assert not next(o for o in report['objects'] if o['name'] == 'ring')['checks']['topology']


def test_matcher_rejects_a_filled_route_in_place_of_an_editable_stroke():
    case = SweepCase()
    image, expected = make_input(case)
    root = ET.fromstring(expected)
    route = next(e for e in root if e.get('id') == 'route')
    route.set('fill', route.get('stroke'))
    route.attrib.pop('stroke')
    route.set('d', 'M20 104L104 104L104 108L20 108Z')
    report = evaluate(case, ET.tostring(root, encoding='unicode'), expected, image)
    assert report['checks']['object_count']
    assert not next(o for o in report['objects'] if o['name'] == 'route')['checks']['editable_stroke']


def test_native_reference_passes_its_own_independent_contract():
    case = SweepCase()
    image, expected = make_input(case)
    assert evaluate(case, expected, expected, image)['passed']


def test_empty_output_records_missing_objects_without_a_matcher_crash():
    case = SweepCase()
    image, expected = make_input(case)
    root = ET.fromstring(expected)
    root[:] = []
    report = evaluate(case, ET.tostring(root, encoding='unicode'), expected, image)
    assert not report['passed'] and len(report['objects']) == 5
    assert all(not o['checks']['present'] for o in report['objects'])


def test_unexpected_gradient_is_a_colour_contract_failure_not_a_parser_crash():
    case = SweepCase()
    image, expected = make_input(case)
    root = ET.fromstring(expected)
    ns = '{http://www.w3.org/2000/svg}'
    defs = ET.SubElement(root, ns+'defs')
    gradient = ET.SubElement(defs, ns+'linearGradient', {'id': 'ramp'})
    ET.SubElement(gradient, ns+'stop', {'stop-color': '#1e5fc3'})
    ET.SubElement(gradient, ns+'stop', {'offset': '1', 'stop-color': '#1e5fc3'})
    next(e for e in root if e.get('id') == 'disc').set('fill', 'url(#ramp)')
    report = evaluate(case, ET.tostring(root, encoding='unicode'), expected, image)
    assert report['checks']['object_count']
    assert not next(o for o in report['objects'] if o['name'] == 'disc')['checks']['color']


def test_stress_suite_is_explicit_and_names_are_unique():
    matrix = cases()
    assert len(matrix) == 78 and sum(c.tier == 'core' for c in matrix) == 36
    assert len({c.name for c in matrix}) == len(matrix)
    assert all(c.tier == 'stress' for c in matrix if c.noise or c.blur or c.contrast < 1)


def test_sweep_refuses_to_overwrite_existing_outputs(tmp_path):
    directory = tmp_path/'keep'
    directory.mkdir()
    marker = directory/'actual.svg'
    marker.write_text('existing artwork')
    with pytest.raises(FileExistsError):
        run_case(SweepCase(), directory)
    assert marker.read_text() == 'existing artwork'


def test_explicit_palette_remains_authoritative_for_an_isolated_new_colour(tmp_path):
    image, _ = make_input(SweepCase())
    path = tmp_path/'input.png'
    image.save(path)
    palette = ('#1e5fc3', '#d43740', '#199364', '#141e2d')
    result = pipeline.run(path, Config(palette=palette))
    assert result.seg.palette.tolist() == [list(bytes.fromhex(c[1:])) for c in palette]


@pytest.mark.parametrize('area_limit', [100, 200])
def test_isolated_palette_recovery_obeys_the_requested_speckle_threshold(tmp_path, area_limit):
    image, _ = make_input(SweepCase())
    path = tmp_path/'input.png'
    image.save(path)
    result = pipeline.run(path, Config(filter_speckle=area_limit))
    assert np.linalg.norm(result.seg.palette.astype(float)-[234, 172, 35], axis=1).min() > 20


@pytest.mark.parametrize('seed', [17, 204])
def test_mild_noise_panels_recovers_primitives_at_sigma_2(tmp_path, seed):
    """Mild Gaussian noise (sigma 2) used to sit below the auto-denoise trigger, corrupting
    boundaries so circles/rects failed to snap and were emitted as Beziers (primitives 2/1,
    anchors 35/49). The interior-noise estimator now trips denoise for exactly these cases."""
    case = SweepCase(family='panels', noise=2, seed=seed, tier='stress')
    report = run_case(case, tmp_path/'case')
    assert report['passed'], report
    by_name = {o['name']: o for o in report['objects']}
    for name in ('disc', 'panel', 'detail'):
        checks = by_name[name]['checks']
        assert checks['primitive'], (name, report)
        assert checks['anchors'], (name, report)
        assert checks['silhouette'], (name, report)
    assert by_name['disc']['checks']['detail_coverage'], report
    assert report['stats']['primitives'] == 4, report
    assert report['stats']['anchors'] <= 16, report


def test_interior_noise_estimator_separates_mild_noise_from_clean_edges():
    """The estimator must stay at ~0 on clean art (even edge-dense/rotated marks) and rise
    above the threshold on mild sigma-2 noise. This is the regression guard proving edge
    density alone does not trip the new trigger (which would risk smearing clean strokes)."""
    from plate.imageio import interior_noise_fraction

    def planes(case):
        arr = np.asarray(make_input(case)[0])
        return arr[..., :3].copy(), arr[..., 3].copy()

    for family in ('panels', 'marks'):
        rgb, alpha = planes(SweepCase(family=family))
        assert interior_noise_fraction(rgb, alpha) < 0.002, family
    rgb, alpha = planes(SweepCase(family='panels', noise=2, seed=17, tier='stress'))
    assert interior_noise_fraction(rgb, alpha) > 0.002
