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


def test_mission_patch_shaded_planet_has_no_free_gradient_boundary():
    """DOCUMENTED INFORMATION LIMIT, measured — do NOT weaken gradient._grow_radial_bands'
    free-boundary/arc gate to force complex_mission_patch's shaded-planet to reunite.

    The authored shaded-planet is one radial-gradient circle (cx=460 cy=400 r=182) painted
    entirely INSIDE the teal sky disc (#267d83). The PNG maps 1:1 to the 960x960 viewBox, so
    the planet's rim is adjacent only to the sky, never to background/empty canvas: walking
    the rim at r+4 lands on sky foreground at every sample. With zero free silhouette arc,
    the radial-band grower that would reunite the gradient fragments (split by overlaid
    solar arrays, orbits and the crossing ribbon) can never fit the circle. Reuniting it
    would mean inventing the fully-occluded boundary from the ramp alone -- exactly what the
    gate forbids. This pins the measured enclosure so a regression or silent gate-weakening
    is caught. complex_mission_patch stays xfail.
    """
    import numpy as np

    cx, cy, r = 460, 400, 182
    sky = np.array([0x26, 0x7d, 0x83])
    with Image.open(DIRECTORY / "complex_mission_patch.png") as image:
        rgba = np.asarray(image.convert("RGBA"))
    rgb, alpha = rgba[..., :3].astype(int), rgba[..., 3]

    free = 0
    on_sky = 0
    for deg in range(360):
        a = math.radians(deg)
        x = round(cx + (r + 4) * math.cos(a))
        y = round(cy + (r + 4) * math.sin(a))
        if not (0 <= x < rgba.shape[1] and 0 <= y < rgba.shape[0]):
            continue
        if alpha[y, x] < 128:
            free += 1                                   # free = background / empty canvas
        elif np.abs(rgb[y, x] - sky).max() <= 24:
            on_sky += 1                                 # rim adjacent to the enclosing sky
    # The whole rim is occluded by foreground (the enclosing sky plus overlaid solar
    # arrays, orbits, ribbon and other craters), never by empty canvas: zero free
    # boundary points means _grow_radial_bands cannot fit the silhouette. A substantial
    # share of the rim is the bare sky, confirming the planet is painted inside it.
    assert free == 0, f"planet rim has {free} free boundary points; enclosure broke"
    assert on_sky >= 150, f"planet rim is not substantially enclosed by sky ({on_sky}/360)"


def test_event_poster_gradient_disc_is_fragmented_by_opaque_overlays():
    """DOCUMENTED INFORMATION LIMIT, measured — do NOT relax gradient.detect's _single_object
    gate (pooling disconnected components) to force complex_event_poster's gradient disc.

    The authored gradient-disc-behind-title is one linear-gradient circle (cx=480 cy=468
    r=260). Opaque art painted on top (six crossing-lines, the diagonal ribbon, a dot grid
    and the headline letters) slices it, so in the raster the disc's own gradient colours
    survive as several mutually-disconnected regions rather than one. Pooling them into one
    gradient would require completing the fill across opaque occluders with no clean
    silhouette -- which the _single_object / free-boundary gates refuse. This pins that the
    disc's visible gradient area is broken into >= 2 disconnected components, the measured
    reason the single authored disc cannot be recovered. complex_event_poster stays xfail.
    """
    import numpy as np
    from scipy import ndimage as ndi

    cx, cy, r = 480, 468, 260
    with Image.open(DIRECTORY / "complex_event_poster.png") as image:
        rgba = np.asarray(image.convert("RGBA"))
    rgb, alpha = rgba[..., :3].astype(int), rgba[..., 3]

    yy, xx = np.ogrid[:rgba.shape[0], :rgba.shape[1]]
    inside_disc = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    # The disc's own warm ramp runs #edba68 -> #d17d79; its red channel dominates and its
    # blue channel stays low, unlike the overlaid navy/mint/cream art painted on top.
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    ramp = inside_disc & (alpha >= 128) & (red >= 190) & (blue <= 140) & (green >= 110) & (green <= 200)
    labels, _ = ndi.label(ramp, np.ones((3, 3)))
    sizes = np.bincount(labels.ravel())[1:]
    substantial = int((sizes >= 200).sum())
    assert substantial >= 2, (
        f"gradient disc ramp is one region ({substantial} substantial components); "
        "the overlay-fragmentation limit no longer holds")
