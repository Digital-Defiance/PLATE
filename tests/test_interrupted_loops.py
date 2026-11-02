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


# ---------------------------------------------------------------------------
# Task 5 / R6a: ROOT inner-seal interrupted CIRCULAR ring via the circle arm of
# order._merge_compound_siblings. The ring is a #a9d1b5 circular stroke broken
# into same-colour arc fragments by crossing navy branches/roots and leaves;
# several short arc slivers snap to a tiny rect/rrect on their own, which used to
# veto the whole cluster and leave the ring split into Beige_* extras matched only
# as an open arc (IoU 0.27). The circle arm now reunites exactly the on-ring arcs
# (shared 15deg occluder cluster + fit_circle rms<=0.02*r / arc>=160deg), excluding
# off-ring same-colour leaves, without relaxing any gate.
# ---------------------------------------------------------------------------


def test_root_inner_seal_arcs_reunite_into_one_ring_without_swallowing_leaves():
    """POSITIVE regression: the measured challenge_report number moved.

    Before (main @ cfe42e2): the inner-seal matched an open arc at IoU 0.2715 with
    6 extra Beige_* ring fragments and topology (1, 0). The circle arm now pools the
    on-ring arcs into ONE compound path: inner-seal IoU rises above 0.33 with
    topology (>=7, 0), the ring-arc extras are gone (<=1 extra remains, the separate
    Task 6 leaf-vein split), and the adjacent same-colour leaf-3/leaf-6 stay matched
    (not merged into the ring). logo_root_seal legitimately remains xfail -- its
    dominant gap is the Task 7 same-colour limit -- so this pins the per-object
    improvement, not promotion.
    """
    if not have_renderer():
        pytest.skip("requires renderer")
    from challenge_diff import diff_target

    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "logo_root_seal.png", Config())
    diff = diff_target(result.svg, (directory / "logo_root_seal.target.svg").read_text())

    inner = next(m for m in diff.matched if m.expected == "inner-seal-stroke")
    # Ring reunited: IoU rose from 0.2715, and the arcs are one topological body.
    assert inner.iou > 0.33, f"inner-seal IoU did not rise: {inner.iou:.4f}"
    assert inner.actual_topology[0] >= 7, f"arcs not reunited: {inner.actual_topology}"
    # The ring-arc Beige_* extras are gone; at most the Task 6 leaf-vein split remains.
    beige_ring_extras = [e for e in diff.extra if e.startswith("Beige") and "ellipse" not in e]
    assert beige_ring_extras == [], f"ring still split into extras: {beige_ring_extras}"
    # NEGATIVE guard within the asset: the off-ring same-colour leaves are NOT eaten.
    assert "leaf-3" not in diff.missing and "leaf-6" not in diff.missing, (
        "the ring merge wrongly swallowed an adjacent same-colour leaf")


def _ring_scene(tmp_path, *, disc=False):
    """A #a9d1b5 CIRCULAR stroke ring (r=110) crossed by a navy bar (the shared
    occluder), split into same-colour arcs.

    disc=True adds a LARGE same-colour solid disc (r=55) centred inside the ring --
    well OFF the ring band and ~0.7x the ring's mass -- that the same bar also crosses,
    so it joins the shared-occluder cluster. It is the adjacent same-colour object the
    merge must NOT swallow.
    """
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    ring = ('<circle cx="210" cy="160" r="110" fill="none" stroke="#a9d1b5" '
            'stroke-width="16"/>')
    blob = ('<circle cx="210" cy="160" r="55" fill="#a9d1b5"/>' if disc else '')
    bar = '<rect x="195" y="10" width="30" height="300" fill="#182e4c"/>'
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="420" height="320">'
           + ring + blob + bar + '</svg>')
    path = tmp_path / 'ring.png'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        image.resize((420, 320), Image.Resampling.LANCZOS).save(path)
    return path


def test_circular_ring_crossed_by_a_shared_occluder_reunites(tmp_path):
    """POSITIVE: an interrupted CIRCULAR ring whose arcs share one occluder and lie
    on one circle reunites into a single compound mint shape."""
    path = _ring_scene(tmp_path)
    result = pipeline.run(path)
    mint = [s for s in result.shapes if s.color == (169, 209, 181)]
    assert len(mint) == 1, f"ring arcs did not reunite into one shape: {len(mint)}"


def test_off_ring_same_colour_disc_is_not_merged_into_the_ring(tmp_path):
    """NEGATIVE (contaminated hull): a large same-colour disc that shares the occluder
    but lies OFF the ring band is NOT pooled into the ring. The ring may still reunite,
    but the disc keeps its own identity, so more than one mint shape survives (the
    circle arm never pools a fragment whose body sits off the common circle)."""
    path = _ring_scene(tmp_path, disc=True)
    result = pipeline.run(path)
    mint = [s for s in result.shapes if s.color == (169, 209, 181)]
    assert len(mint) >= 2, (
        f"off-ring same-colour disc was wrongly merged into the ring: {len(mint)} mint shapes")


def test_arcs_without_a_shared_occluder_are_not_reunited(tmp_path):
    """NEGATIVE (no shared occluder): two same-colour quarter arcs that lie on one
    circle but are separated by transparent background -- neither is occluded, so the
    shared-occluder clustering never links them and the circle arm cannot reunite them
    (no 15deg T-junction evidence). They must stay distinct, not be joined across the
    open gaps."""
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    # Two opposite quarter arcs of the same r=110 circle, each a stand-alone wedge, with
    # transparent gaps (no occluder) between them.
    def wedge(a0, a1):
        import numpy as _np
        x0, y0 = 210 + 110 * _np.cos(_np.deg2rad(a0)), 160 + 110 * _np.sin(_np.deg2rad(a0))
        x1, y1 = 210 + 110 * _np.cos(_np.deg2rad(a1)), 160 + 110 * _np.sin(_np.deg2rad(a1))
        return (f'<path d="M {x0:.1f} {y0:.1f} A 110 110 0 0 1 {x1:.1f} {y1:.1f}" '
                'fill="none" stroke="#a9d1b5" stroke-width="16"/>')
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="420" height="320">'
           + wedge(200, 250) + wedge(20, 70) + '</svg>')
    path = tmp_path / 'arcs.png'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        image.resize((420, 320), Image.Resampling.LANCZOS).save(path)
    result = pipeline.run(path)
    mint = [s for s in result.shapes if s.color == (169, 209, 181)]
    assert len(mint) >= 2, "arcs with no shared occluder were wrongly reunited"
