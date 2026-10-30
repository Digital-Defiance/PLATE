"""Independent desired SVG targets, including strict expected feature gaps."""
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from plate import metrics, pipeline
from plate.config import Config
from plate.raster import have_renderer

from challenges import CHALLENGES, TargetMismatch, assert_target, local

DIRECTORY = Path(__file__).resolve().parents[1] / "samples" / "challenges"


@pytest.fixture(scope="module", params=list(CHALLENGES))
def challenge(request):
    name = request.param
    image = DIRECTORY / f"{name}.png"
    assert image.exists(), "Run scripts/make_challenges.py to regenerate inputs"
    target = (DIRECTORY / f"{name}.target.svg").read_text()
    return name, image, target, pipeline.run(image, Config())


def test_challenge_svg_integrity(challenge):
    """Always active, including challenges whose desired structure is not supported."""
    _, _, _, result = challenge
    root = ET.fromstring(result.svg)
    assert not any(local(e) == "image" for e in root.iter()), "SVG must contain vectors"
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids)), "SVG IDs must be unique"
    for element in root.iter():
        fill = element.get("fill", "")
        if fill.startswith("url(#"):
            assert fill[5:-1] in ids, "dangling gradient reference"


def test_challenge_fidelity(challenge):
    """Check both backgrounds: white alone can hide lost transparent cutouts."""
    if not have_renderer():
        pytest.skip("challenge fidelity requires the render extra and libcairo")
    name, image, _, result = challenge
    with Image.open(image) as source:
        rgba = np.asarray(source.convert("RGBA"))
    for background in ((255, 255, 255), (24, 24, 24)):
        fidelity = metrics.fidelity(result.svg, rgba, bg=background)
        if "ssim" not in fidelity:
            pytest.skip("SSIM requires scikit-image")
        assert fidelity["ssim"] >= CHALLENGES[name].ssim_floor, (name, background, fidelity)


def test_challenge_editable_structure(challenge, request):
    if not have_renderer():
        pytest.skip("silhouette matching requires the render extra and libcairo")
    name, _, target, result = challenge
    if CHALLENGES[name].gap:
        request.node.add_marker(pytest.mark.xfail(
            strict=True, raises=TargetMismatch, reason=CHALLENGES[name].gap))
    assert_target(result.svg, target)


def test_target_matcher_rejects_hidden_geometry_and_order():
    """A pixel-perfect image can still have the wrong editable hidden objects."""
    if not have_renderer():
        pytest.skip("requires renderer")
    target = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
              '<circle id="disc" cx="50" cy="50" r="30" fill="red"/>'
              '<rect id="cover" x="50" y="10" width="40" height="80" fill="blue"/>'
              '</svg>')
    assert_target(target, target)
    # The changed half is entirely under the covering rect; rendered image agrees.
    bitten = target.replace('<circle id="disc" cx="50" cy="50" r="30" fill="red"/>',
                            '<path d="M50 20A30 30 0 0 0 50 80Z" fill="red"/>')
    with pytest.raises(TargetMismatch, match="silhouette"):
        assert_target(bitten, target)
    root = ET.fromstring(target)
    root[:] = list(reversed(root))
    with pytest.raises(TargetMismatch, match="paint order"):
        assert_target(ET.tostring(root, encoding="unicode"), target)


def test_target_matcher_rejects_filled_stroke_outline():
    if not have_renderer():
        pytest.skip("requires renderer")
    target = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
              '<path id="line" d="M20 50H80" fill="none" stroke="red" stroke-width="10"/>'
              '</svg>')
    outline = target.replace('d="M20 50H80" fill="none" stroke="red" stroke-width="10"',
                             'd="M20 45H80V55H20Z" fill="red"')
    with pytest.raises(TargetMismatch, match="editable stroke"):
        assert_target(outline, target)


def test_target_matcher_rejects_stray_component_inside_hole():
    if not have_renderer():
        pytest.skip("requires renderer")
    target = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
              '<path id="plate" d="M10 10H90V90H10Z M30 30H70V70H30Z" '
              'fill="blue" fill-rule="evenodd"/></svg>')
    # Tiny island barely affects IoU, but is still a spurious editable component.
    actual = target.replace('M30 30H70V70H30Z', 'M30 30H70V70H30Z M40 40H42V42H40Z')
    with pytest.raises(TargetMismatch, match="components/holes"):
        assert_target(actual, target)
