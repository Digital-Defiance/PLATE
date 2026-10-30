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
