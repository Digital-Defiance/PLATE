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
    # This regression guards source ownership: every gold source pixel must be owned
    # by a segment at both scales. Half-size markers now also recover as circles
    # (asserted below), so the 90% circle-coverage contract holds at .5 and 1.
    image, _ = make_input(case)
    result = pipeline.run(tmp_path/'marker/input.png')
    rgba = np.asarray(image)
    gold = (rgba[..., 3] >= 128) & (rgba[..., 0] > 180) & (rgba[..., 1] > 120) & (rgba[..., 2] < 90)
    assert (result.seg.rid[gold] >= 0).all()
    # Half-size markers now recover as genuine circles (snap fits a circle before the
    # tiny-mask rect fallback), so detail_coverage holds at both scales, not just 1.
    assert marker['checks']['detail_coverage'], marker


@pytest.mark.parametrize('angle', [0, 90, 180, 270])
def test_half_size_marker_recovers_as_a_circle_with_full_coverage(tmp_path, angle):
    case = SweepCase(scale=.5, angle=angle, tier='stress')
    report = run_case(case, tmp_path/'m')
    marker = next(o for o in report['objects'] if o['name'] == 'marker')
    assert marker['checks']['present'], report
    # Per-object recovery (NOT global SSIM): the emitted element must be a circle and
    # cover >= 90% of the authored silhouette.
    actual = ET.fromstring((tmp_path/'m'/'actual.svg').read_text())
    element = next(e for e in actual.iter() if e.get('id') == marker['actual_name'])
    assert element.tag.rsplit('}', 1)[-1] == 'circle', ET.tostring(element, encoding='unicode')
    assert marker['checks']['detail_coverage'], marker
    assert marker['coverage'] >= .9, marker


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


def test_blur_0p7_marker_recovers_as_a_full_coverage_circle(tmp_path):
    """A 5px gold marker blurred at sigma 0.7 has no flat palette seed (edge dilation
    consumes it), so it depends on the isolated-alpha-component fallback in segment.py.
    Its stable gold core has an interior p90 colour spread of ~4.12, which the old `> 3`
    gate rejected as a "variable ramp/noisy island", dropping the marker (4 shapes, want 5).
    The gate now tolerates a stable core up to 6, admitting the marker at coverage 1.0.
    FAILS on the `> 3` gate (marker absent); PASSES with the `> 6` gate."""
    case = SweepCase(family='marks', blur=.7, tier='stress')
    report = run_case(case, tmp_path/'m')
    assert report['checks']['object_count'], report
    marker = next(o for o in report['objects'] if o['name'] == 'marker')
    assert marker['checks']['present'], report
    assert marker['checks']['detail_coverage'], marker
    assert marker['coverage'] >= .9, marker
    # Per-object recovery, not global SSIM: the emitted element must be a circle.
    element = next(e for e in ET.fromstring((tmp_path/'m'/'actual.svg').read_text()).iter()
                   if e.get('id') == marker['actual_name'])
    assert element.tag.rsplit('}', 1)[-1] == 'circle', ET.tostring(element, encoding='unicode')


def test_isolated_island_with_a_variable_ramp_interior_stays_out_of_the_palette(tmp_path):
    """Over-loosening guard for the `> 6` interior-spread gate in segment.py. A genuinely
    variable island (a smooth colour ramp, no flat seed) must NOT be admitted as a new flat
    colour: its interior p90 spread far exceeds 6. A solid flat island supplies the only
    palette entry; nothing lands near the ramp's mid colour."""
    import numpy as np
    from PIL import Image

    from plate import pipeline
    from plate.config import Config

    rgba = np.zeros((48, 48, 4), np.uint8)
    rgba[4:44, 4:20] = [30, 95, 195, 255]          # solid flat island -> one palette entry
    for y in range(30, 40):                        # isolated ramp island, interior spread >> 6
        v = 40 + (y - 30) * 20
        rgba[y, 30:40] = [v, 50, 200 - v // 2, 255]
    source = tmp_path/'ramp.png'
    Image.fromarray(rgba).save(source)
    palette = pipeline.run(source, Config()).seg.palette.astype(float)
    assert palette.shape[0] == 1 and np.allclose(palette[0], [30, 95, 195])
    ramp_mid = np.array([130., 50., 135.])
    assert np.linalg.norm(palette - ramp_mid, axis=1).min() > 60


def test_blur_1p2_marker_is_below_the_alpha128_silhouette_floor(tmp_path):
    """DOCUMENTED FLOOR, measured — do NOT weaken the opaque gate to force this.
    At sigma 1.2 the 5px marker keeps flat seeds (gold enters the palette normally, so it is
    present and object_count is satisfied), but the blur erodes its alpha>=128 opaque
    silhouette to 44 px vs the target's 52 px. 44/52 = 0.846 < the 0.90 detail_coverage gate,
    so the case cannot pass. Measured alpha-threshold sweep on the marker core:
      alpha>=128 -> 44 px (coverage 0.846); alpha>=110 -> 52 px (1.0); alpha>=96 -> 52 px.
    Reaching 0.90 requires growing the silhouette below the alpha>=128 contract the evaluator
    and segmentation share; that single global threshold would grow every antialiased rim and
    break the 24 shipped SVGs' byte-identity. This test pins the floor so a regression (or a
    silent gate-weakening) is caught."""
    case = SweepCase(family='marks', blur=1.2, tier='stress')
    report = run_case(case, tmp_path/'m')
    assert report['checks']['object_count'], report           # 5 shapes: marker IS present
    marker = next(o for o in report['objects'] if o['name'] == 'marker')
    assert marker['checks']['present'], report
    assert not marker['checks']['detail_coverage'], marker     # below the alpha>=128 floor
    assert 0.80 <= marker['coverage'] <= 0.88, marker          # measured 0.846
    assert not report['passed'], report


def test_contrast_1_over_16_foreground_is_below_the_colour_merge_floor(tmp_path):
    """DOCUMENTED FUNDAMENTAL LIMIT, measured — do NOT lower color_merge to force this.
    At contrast 1/16 every foreground collapses to within ~5 Lab dE of the background
    (#878788): disc #7a7e84 dE 4.98, panel #857b7c dE 5.81, detail #7a817e dE 4.84 — all
    below the color_merge = 8.0 floor, so _build_palette merges them into the single
    background entry (1 shape, only Background present). Reference SSIM still passes, so this
    is purely object separation. The only separating lever, color_merge <= 4.5, is a GLOBAL
    change that alters shipped samples/shaded.png (2533 -> 2100 bytes), breaking byte-identity
    and splitting genuinely near-identical colours in real art. A foreground within ~5 dE of
    its background is below the floor that protects real artwork; this is a limit, not a bug.
    This test pins the merged state and the measured dE evidence."""
    import cv2
    import numpy as np

    from plate.robustness import target_svg

    case = SweepCase(family='panels', contrast=.0625, tier='stress')
    report = run_case(case, tmp_path/'p')
    assert report['stats']['shapes'] == 1, report              # all foregrounds merge into bg
    assert report['checks']['reference_white'] and report['checks']['reference_dark'], report
    assert next(o for o in report['objects'] if o['name'] == 'background')['checks']['present']
    for name in ('disc', 'panel', 'detail'):
        assert not next(o for o in report['objects'] if o['name'] == name)['checks']['present'], report

    def lab(value):
        rgb = np.array(list(bytes.fromhex(value[1:])), np.float32).reshape(1, 1, 3)/255
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[0, 0]

    colors = {e.get('id'): (e.get('fill') or e.get('stroke')) for e in ET.fromstring(target_svg(case))}
    background = lab(colors['background'])
    deltas = {name: float(np.linalg.norm(lab(colors[name]) - background)) for name in ('disc', 'panel', 'detail')}
    assert all(d < 8.0 for d in deltas.values()), deltas       # all below color_merge floor
    assert deltas['disc'] < 6 and deltas['panel'] < 7 and deltas['detail'] < 6, deltas


def test_hairline_route_1px_is_below_the_round_cap_half_width_floor(tmp_path):
    """DOCUMENTED FLOOR, measured — do NOT lower fit_straight's 0.75 half-width floor nor
    weaken the silhouette gate to force this. The authored 1px round-capped route renders
    to a 2-working-px band whose alpha is only ~147 everywhere (no pixel reaches alpha>=200),
    so it carries no flat seed and no erodable interior and the route colour #141e2d (RGB
    dist ~129 to the nearest palette entry) is never admitted: on the DEFAULT pipeline the
    route is absent (4 shapes, 0 strokes, object_count false), while reference SSIM still
    passes (the hairline is visually negligible).
    Even if the colour is force-admitted the case cannot pass: the thinnest round-capped
    stroke PLATE can emit is 1.5px (two rows) from fit_straight's 0.75 half-width lower
    bound, versus the authored 1px (one row) target in evaluate's authored-base-pixel space,
    giving silhouette IoU 0.5 / boundary deviation 1.0 (threshold IoU>=.96 or deviation<=.75).
    This is a geometric floor, matching prior art (the quarter-size 1-working-px route).
    This test pins the floor so a regression or a silent gate-weakening is caught."""
    case = SweepCase(route_width=1, tier='stress')
    report = run_case(case, tmp_path/'r')
    assert report['stats']['shapes'] == 4, report              # route colour not admitted
    assert report['stats']['strokes'] == 0, report
    assert not report['checks']['object_count'], report
    route = next(o for o in report['objects'] if o['name'] == 'route')
    assert route['checks'] == {'present': False}, route        # absent on the default pipeline
    assert report['checks']['reference_white'] and report['checks']['reference_dark'], report
    assert not report['passed'], report

    # Force-admit the authored palette: the route then emits as an editable stroke with the
    # right colour and width, but silhouette still fails (1.5px two-row stroke vs 1px target).
    image, target = make_input(case)
    source = tmp_path/'forced.png'
    image.save(source)
    palette = ('#1e5fc3', '#d43740', '#199364', '#141e2d', '#eaac23', '#ffffff')
    result = pipeline.run(source, Config(work_size=1536, palette=palette))
    forced = evaluate(case, result.svg, target, image)
    forced_route = next(o for o in forced['objects'] if o['name'] == 'route')
    assert forced_route['checks']['present'], forced
    assert forced_route['checks']['editable_stroke'] and forced_route['checks']['stroke_width'], forced_route
    assert not forced_route['checks']['silhouette'], forced_route   # geometric floor: IoU 0.5
    assert forced_route['iou'] <= 0.6, forced_route                 # measured 0.5


def test_hairline_route_2px_is_below_the_palette_admission_floor(tmp_path):
    """DOCUMENTED FLOOR, measured — do NOT add a palette-admission heuristic to force this;
    it regresses the currently-green marks-s0p5 line4 route and/or the panels blur cases.
    The authored 2px round-capped route renders to a 2-working-px band at alpha ~243, a
    genuinely distinct colour #141e2d (RGB dist ~129 to the nearest palette entry) with no
    flat seed and no erodable interior, so no automatic palette-seeding path admits it: on
    the DEFAULT pipeline the route is absent (4 shapes, 0 strokes, object_count false) while
    reference SSIM still passes.
    Unlike the 1px case this is NOT a geometric floor: force-admitting the authored palette
    recovers the route as a correct editable stroke that passes EVERY route check
    (editable_stroke, stroke_width ~2.01, silhouette IoU 1.0), proving the failure is palette
    admission, not stroke fitting. It stays a floor because no gate-preserving automatic rule
    can admit it: the geometrically-identical, currently-green marks-s0p5-r0 line4 route has
    an IDENTICAL measured signature (2-px band, max distance-transform 1.0, alpha min/med/max
    193/243/243) yet enters the palette through scene-dependent flat-core seeding; any rule
    keying on the route's own pixels fires on both, so admitting line2 regresses s0p5 line4
    (and broader variants hit the green panels blur halos). This test pins that discriminator."""
    case = SweepCase(route_width=2, tier='stress')
    report = run_case(case, tmp_path/'r')
    assert report['stats']['shapes'] == 4, report              # route colour not admitted
    assert report['stats']['strokes'] == 0, report
    assert not report['checks']['object_count'], report
    route = next(o for o in report['objects'] if o['name'] == 'route')
    assert route['checks'] == {'present': False}, route
    assert report['checks']['reference_white'] and report['checks']['reference_dark'], report
    assert not report['passed'], report

    # The discriminator: force the authored palette and the route passes all its checks,
    # so the only failure is palette admission, not stroke fitting.
    image, target = make_input(case)
    source = tmp_path/'forced.png'
    image.save(source)
    palette = ('#1e5fc3', '#d43740', '#199364', '#141e2d', '#eaac23', '#ffffff')
    result = pipeline.run(source, Config(work_size=1536, palette=palette))
    forced = evaluate(case, result.svg, target, image)
    forced_route = next(o for o in forced['objects'] if o['name'] == 'route')
    assert all(forced_route['checks'].values()), forced_route       # every route check passes
    assert forced_route['checks']['editable_stroke'], forced_route
    assert forced_route['checks']['silhouette'] and forced_route['iou'] >= 0.95, forced_route

    # The currently-green marks-s0p5-r0 line4 route is geometrically identical yet recovers,
    # because at that scale the route colour reaches the palette via flat-core seeding. Any
    # rule that admits line2 fires here too, so this green case guards against forcing line2.
    green = SweepCase(scale=.5, angle=0, tier='stress')
    green_report = run_case(green, tmp_path/'g')
    green_route = next(o for o in green_report['objects'] if o['name'] == 'route')
    assert green_route['checks']['present'], green_report
    assert green_report['stats']['strokes'] == 1, green_report
