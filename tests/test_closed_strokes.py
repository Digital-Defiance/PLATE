"""Closed strokes preserve primitive geometry, width and genuine cutouts."""
import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from plate import metrics, pipeline
from plate.config import Config
from plate.raster import have_renderer
from challenges import assert_target


def _png(tmp_path, shape):
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="320">'+shape+'</svg>'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / "loop.png"
        image.resize((420, 320), Image.Resampling.LANCZOS).save(path)
    return path, svg


@pytest.mark.parametrize("kind,width,angle,work_size", [
    ("circle", 5, 0, 1536), ("circle", 6, 0, 1536), ("circle", 12, 0, 1536),
    ("ellipse", 5, 25, 1536),
    ("ellipse", 6, 25, 1536), ("ellipse", 8, 115, 1536),
    ("ellipse", 12, 0, 210),
])
def test_closed_primitive_stroke_matches_independent_target(tmp_path, kind, width, angle, work_size):
    radii = 'r="115"' if kind == "circle" else 'rx="165" ry="85"'
    shape = (f'<{kind} cx="210" cy="160" {radii} transform="rotate({angle} 210 160)" '
             f'fill="none" stroke="#182e4c" stroke-width="{width}"/>')
    path, target = _png(tmp_path, shape)
    result = pipeline.run(path, Config(work_size=work_size))
    assert result.stats["strokes"] == 1
    assert_target(result.svg, target)
    stats = metrics.analyze_svg(result.svg)
    assert stats["strokes"] == 1
    assert stats["anchors"] == 4
    with Image.open(path) as image:
        assert metrics.fidelity(result.svg, np.asarray(image.convert("RGBA")))["ssim"] >= .99
    assert pipeline.run(path, Config(work_size=work_size, strokes=False)).stats["strokes"] == 0


@pytest.mark.parametrize("shape", [
    '<circle cx="210" cy="160" r="110" fill="#182e4c"/>',
    '<circle cx="210" cy="160" r="90" fill="none" stroke="#182e4c" stroke-width="50"/>',
    '<path d="M90 160a120 120 0 1 0 240 0a120 120 0 1 0-240 0Z '
    'M110 160a106 106 0 1 0 212 0a106 106 0 1 0-212 0Z" fill="#182e4c" fill-rule="evenodd"/>',
    '<path d="M90 160a120 120 0 1 0 240 0a120 120 0 1 0-240 0Z '
    'M100 160a110 110 0 1 0 220 0a110 110 0 1 0-220 0Z '
    'M206 41h8v9h-8Z" fill="#182e4c" fill-rule="evenodd"/>',
    '<rect x="60" y="60" width="300" height="200" rx="30" fill="none" '
    'stroke="#182e4c" stroke-width="8"/>',
])
def test_discs_thick_rings_uneven_rings_and_cutouts_do_not_become_closed_strokes(tmp_path, shape):
    path, _ = _png(tmp_path, shape)
    from plate.masks import Mask
    from plate.stages.strokes import fit_closed
    with Image.open(path) as image:
        mask = Mask.from_full(np.asarray(image)[..., 3] >= 128)
    assert fit_closed(mask, Config()) is None
    result = pipeline.run(path, Config())
    assert not any(e.get("stroke") and e.tag.rsplit("}", 1)[-1] in ("circle", "ellipse")
                   for e in ET.fromstring(result.svg).iter())


def test_root_outer_seal_is_an_editable_circle_without_changing_its_target():
    if not have_renderer():
        pytest.skip("requires renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "logo_root_seal.png")
    actual, target = ET.fromstring(result.svg), ET.parse(directory / "logo_root_seal.target.svg").getroot()
    wanted = next(e for e in target.iter() if e.get("id") == "outer-seal-stroke")
    got, = [e for e in actual.iter() if e.get("stroke") == "#267d83"]
    actual[:] = [got]
    target[:] = [wanted]
    assert_target(ET.tostring(actual, encoding="unicode"), ET.tostring(target, encoding="unicode"))


def test_ring_bite_requires_visible_cover_and_completion_switch(tmp_path):
    shape = ('<circle cx="210" cy="160" r="115" fill="none" stroke="#182e4c" stroke-width="12"/>'
             '<circle cx="210" cy="39" r="9" fill="#e9bc59"/>')
    path, target = _png(tmp_path, shape)
    result = pipeline.run(path)
    assert result.stats["strokes"] == 1
    assert_target(result.svg, target)
    assert pipeline.run(path, Config(complete_hidden=False)).stats["strokes"] == 0


def test_filled_disc_under_concentric_disc_keeps_complete_silhouette(tmp_path):
    # Its visible band alone resembles a thin stroke. The independent target
    # requires the entire gold disc, including the part hidden by the navy disc.
    shape = ('<circle cx="210" cy="160" r="115" fill="#e9bc59"/>'
             '<circle cx="210" cy="160" r="105" fill="#182e4c"/>')
    path, target = _png(tmp_path, shape)
    result = pipeline.run(path)
    assert result.stats["strokes"] == 0
    assert_target(result.svg, target)


def test_orbit_front_orbit_recovers_as_an_editable_stroked_ellipse():
    """ORBIT's gold front orbit is a thin stroked ellipse threaded through the badge
    ring, gradient core, satellites and wordmark: ~2% of its boundary smears at
    crossings and ~37% sits near later-painted covers. It must still recover as ONE
    editable stroked ellipse (width ~6). The full ORBIT structural target stays a
    strict xfail; this pins the front-orbit sub-result only."""
    if not have_renderer():
        pytest.skip("requires renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "logo_orbit_wordmark.png")
    stroked = [e for e in ET.fromstring(result.svg).iter()
               if e.tag.rsplit("}", 1)[-1] == "ellipse" and e.get("stroke")
               and e.get("stroke").lower() == "#e9bc59"]
    assert len(stroked) == 1, "front orbit must be one editable stroked ellipse"
    assert abs(float(stroked[0].get("stroke-width")) - 6) <= 1.5


def test_notched_ring_is_not_accepted_as_a_clean_stroke(tmp_path):
    """The crossing-tolerance must NOT accept a ring with a genuine bite: a real
    defect is a long contiguous boundary deviation (and fails the footprint gate),
    unlike the sparse, scattered outliers a crossing produces."""
    # a stroked circle with a wedge cut out of its ring (a contiguous defect)
    ring = ('<path d="M95 160a115 115 0 1 0 230 0a115 115 0 1 0 -230 0Z '
            'M107 160a103 103 0 1 0 206 0a103 103 0 1 0 -206 0Z" '
            'fill="#182e4c" fill-rule="evenodd"/>'
            # carve a notch: an opaque wedge removing part of the ring body
            '<path d="M210 160L340 90L340 230Z" fill="#ffffff"/>')
    path, _ = _png(tmp_path, ring)
    from plate.masks import Mask
    from plate.stages.strokes import fit_closed
    with Image.open(path) as image:
        mask = Mask.from_full(np.asarray(image)[..., 3] >= 128)
    # the ring body is interrupted by the notch -> must not be a clean closed stroke
    assert fit_closed(mask, Config()) is None


def test_boundary_ok_distinguishes_scattered_outliers_from_a_clustered_defect():
    from plate.stages.strokes import _boundary_ok
    rng = np.random.default_rng(0)
    n = 1000
    res = rng.uniform(-.3, .3, n)                     # clean loop within tolerance
    assert _boundary_ok(res, .85)
    scattered = res.copy()
    scattered[rng.choice(n, 20, replace=False)] = 2.5  # 2% sparse crossings -> ok
    assert _boundary_ok(scattered, .85)
    clustered = res.copy()
    clustered[400:440] = 2.5                           # a contiguous 40-sample notch -> reject
    assert not _boundary_ok(clustered, .85)
    many = res.copy()
    many[rng.choice(n, 80, replace=False)] = 2.5       # 8% outliers -> reject
    assert not _boundary_ok(many, .85)


def test_circular_transparent_holes_are_emitted_as_arcs(tmp_path):
    """A round TRANSPARENT perforation forces an even-odd compound path; its round
    hole should trace as compact SVG arcs (round, editable), not a long Bézier chain.
    A non-circular transparent hole in the same path must stay Béziers."""
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    # transparent holes (no white rect behind) => one even-odd compound path
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
           '<path fill="#286ec8" fill-rule="evenodd" d="M40 40H360V160H40Z '
           'M90 100a38 38 0 1 0 76 0a38 38 0 1 0 -76 0Z '              # round hole
           'M250 62H326V138H250Z"/>'                                    # square hole
           '</svg>')
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / "plate.png"
        image.resize((400, 200), Image.Resampling.LANCZOS).save(path)
    result = pipeline.run(path, Config())
    plate = next(e for e in ET.fromstring(result.svg).iter()
                 if e.tag.rsplit("}", 1)[-1] == "path" and e.get("fill-rule") == "evenodd")
    d = plate.get("d")
    assert d.count("A") >= 2, "round transparent hole should be emitted as arcs"
    # the square hole must NOT be arced — it stays straight segments (no extra arcs)
    assert d.count("A") <= 4, "a non-circular hole must stay Béziers/lines, not arcs"
    with Image.open(path) as image:
        assert metrics.fidelity(result.svg, np.asarray(image.convert("RGBA")),
                                bg=(255, 255, 255))["ssim"] >= 0.97


def test_perforated_plate_holes_are_arcs_and_compact():
    """The perforated_plate challenge: its three round holes should emit as arcs,
    keeping the plate well under its old anchor count, still matching the target."""
    if not have_renderer():
        pytest.skip("requires renderer")
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    result = pipeline.run(directory / "perforated_plate.png")
    stats = metrics.analyze_svg(result.svg)
    assert stats["anchors"] <= 28, f"round holes should keep anchors low, got {stats['anchors']}"
    assert_target(result.svg, (directory / "perforated_plate.target.svg").read_text())
