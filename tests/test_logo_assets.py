"""Keep the original logo inputs paired with their independent targets."""
import io
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from challenges import _mask, _topology, drawables, local
from PIL import Image

from plate.raster import have_renderer

DIRECTORY = Path(__file__).resolve().parents[1] / "samples/challenges"
LOGOS = [
    ("ember_crest", (800, 960), 51, 0, 7),
    ("orbit_wordmark", (1200, 480), 34, 1, 7),
    ("root_seal", (900, 900), 56, 0, 32),
    ("plate", (1200, 400), 11, 0, 3),
]


@pytest.mark.parametrize("name,size,objects,gradients,strokes", LOGOS)
def test_logo_artwork_contract(name, size, objects, gradients, strokes):
    root = ET.fromstring((DIRECTORY / f"logo_{name}.target.svg").read_text())
    leaves = drawables(root)
    assert len(leaves) == objects
    assert sum(local(e) in {"linearGradient", "radialGradient"} for e in root.iter()) == gradients
    assert sum(bool(e.get("stroke")) for e in leaves) == strokes
    assert not any(local(e) in {"image", "text", "use"} for e in root.iter())
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids))
    for e in root.iter():
        assert all(value.startswith("#") for key, value in e.attrib.items()
                   if key.rsplit("}", 1)[-1] == "href")
    with Image.open(DIRECTORY / f"logo_{name}.png") as image:
        assert image.mode == "RGBA" and image.size == size
        assert image.getpixel((0, 0))[3] == 0


@pytest.mark.parametrize("name,points", [
    ("ember_crest", [(400, 59), (122, 150), (678, 150), (400, 739)]),
    ("orbit_wordmark", [(215, 84), (371, 240), (215, 396), (59, 240)]),
    ("root_seal", [(450, 455), (450, 460), (450, 475)]),
    ("plate", [(206, 148), (465, 192), (763, 203)]),
])
def test_logo_negative_spaces_are_transparent(name, points):
    with Image.open(DIRECTORY / f"logo_{name}.png") as image:
        for point in points:
            assert image.getpixel(point)[3] < 10


@pytest.mark.parametrize("name", [row[0] for row in LOGOS])
def test_logo_png_matches_authored_svg(name):
    if not have_renderer():
        pytest.skip("requires render extra and libcairo")
    import cairosvg
    target = DIRECTORY / f"logo_{name}.target.svg"
    png = cairosvg.svg2png(bytestring=target.read_bytes(), scale=4)
    with Image.open(DIRECTORY / f"logo_{name}.png") as image, Image.open(io.BytesIO(png)) as high:
        expected = high.convert("RGBA").resize(image.size, Image.Resampling.LANCZOS)
        assert np.array_equal(np.asarray(image), np.asarray(expected))


def test_plate_brand_is_the_challenge():
    """Exercise the actual public identity, rather than a simplified substitute."""
    brand = DIRECTORY.parents[1] / "assets/brand"
    assert (brand / "plate-logo.svg").read_bytes() == (DIRECTORY / "logo_plate.target.svg").read_bytes()
    assert (brand / "plate-logo.png").read_bytes() == (DIRECTORY / "logo_plate.png").read_bytes()


def test_plate_targets_are_complete_plates_with_real_holes():
    if not have_renderer():
        pytest.skip("requires renderer")
    root = ET.fromstring((DIRECTORY / "logo_plate.target.svg").read_text())
    by_id = {e.get("id"): e for e in drawables(root)}
    for name in ("back-plate-P", "middle-plate-P", "front-plate-P"):
        mask = _mask(root, by_id[name])
        assert _topology(mask) == (1, 1)
        assert not mask[148, 206]
        # Fully authored stem and bowl, including portions hidden in the logo.
        assert mask.sum() > 23000
    labels = [e.get("{http://www.inkscape.org/namespaces/inkscape}label")
              for e in root if local(e) == "g"]
    assert labels == ["Back Plate", "Middle Plate", "Front Plate", "Registration", "Wordmark"]
