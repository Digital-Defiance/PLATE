"""Protect the independent artwork's complexity and portable PNG/SVG pairing."""
import math
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

from challenges import drawables, local

DIRECTORY = Path(__file__).resolve().parents[1] / "samples" / "challenges"


@pytest.mark.parametrize("name,size,objects,gradients,strokes", [
    ("mission_patch", (960, 960), 45, 2, 10),
    ("storefront", (960, 800), 64, 0, 4),
    ("instrument_panel", (960, 800), 59, 0, 27),
    ("event_poster", (960, 960), 44, 1, 6),
])
def test_complex_scene_artwork(name, size, objects, gradients, strokes):
    """The targets must stay complex, self-contained vector artwork."""
    path = DIRECTORY / f"complex_{name}"
    root = ET.fromstring(path.with_suffix(".target.svg").read_text())
    assert len(drawables(root)) == objects
    assert sum(local(e) in {"linearGradient", "radialGradient"} for e in root.iter()) == gradients
    assert sum(bool(e.get("stroke")) for e in drawables(root)) == strokes
    assert not any(local(e) in {"image", "text", "use"} for e in root.iter())
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids))
    for e in root.iter():
        for key, value in e.attrib.items():
            if key.rsplit("}", 1)[-1] == "href":
                assert value.startswith("#"), "artwork must not load external resources"
    with Image.open(path.with_suffix(".png")) as image:
        assert image.size == size
        assert image.mode == "RGBA"


def test_mission_patch_cutouts_are_transparent():
    with Image.open(DIRECTORY / "complex_mission_patch.png") as image:
        assert image.getpixel((0, 0))[3] == 0
        for angle in (-145, -115, -85, -55, -25, 55, 85, 115, 155):
            a = math.radians(angle)
            point = (round(480 + 390 * math.cos(a)), round(460 + 390 * math.sin(a)))
            assert image.getpixel(point)[3] < 10, f"rim cutout {angle} is obscured or filled"
