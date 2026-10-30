"""Same-colour background islands may be redundant; foreground repainting is not."""
import io

import numpy as np
import pytest
from PIL import Image

from plate import pipeline
from plate.config import Config
from plate.geometry import Prim, raster_prim
from plate.masks import Mask
from plate.raster import have_renderer
from plate.scene import Segmentation, Shape
from plate.stages import order


def _run(tmp_path, body):
    if not have_renderer():
        pytest.skip("requires renderer")
    import cairosvg
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240">'+body+'</svg>'
    with Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), scale=4))) as image:
        path = tmp_path / "island.png"
        image.resize((320, 240), Image.Resampling.LANCZOS).save(path)
    return pipeline.run(path, Config())


def test_closed_frame_does_not_split_its_underlying_background(tmp_path):
    result = _run(tmp_path, '<rect width="320" height="240" fill="#182e4c"/>'
                  '<path d="M90 60H230V70H90Z M90 170H230V180H90Z" fill="#e88040"/>'
                  '<path d="M90 60H100V180H90Z M220 60H230V180H220Z" fill="#a9d1b5"/>')
    navy = [s for s in result.shapes if s.color == (24, 46, 76)]
    assert len(navy) == 1
    assert result.stats["shapes"] == 5


def test_same_colour_pupil_is_separate_from_background(tmp_path):
    result = _run(tmp_path, '<rect width="320" height="240" fill="#182e4c"/>'
                  '<circle cx="160" cy="120" r="60" fill="#e88040"/>'
                  '<circle cx="160" cy="120" r="15" fill="#182e4c"/>')
    assert result.stats["shapes"] == 3
    assert sum(s.color == (24, 46, 76) for s in result.shapes) == 2


def test_same_colour_island_inside_transparent_hole_stays_separate(tmp_path):
    result = _run(tmp_path, '<path d="M40 40H280V200H40Z M100 90H220V150H100Z" '
                  'fill="#182e4c" fill-rule="evenodd"/>'
                  '<circle cx="160" cy="120" r="10" fill="#182e4c"/>')
    assert result.stats["shapes"] == 2
    assert all(s.parent is None for s in result.shapes)


@pytest.mark.parametrize("model", ["mask", "primitive", "trace"])
def test_parent_merge_does_not_erase_foreground_repainting(model):
    canvas = (60, 80)
    island = np.zeros(canvas, bool); island[25:35, 35:45] = True
    red = np.zeros(canvas, bool); red[20:40, 15:35] = True
    background = ~(island | red)
    shapes = []
    rid = np.full(canvas, -1, np.int32)
    for i, (a, color) in enumerate([(background, (24, 46, 76)), (red, (232, 128, 64)),
                                   (island, (24, 46, 76))]):
        m = Mask.from_full(a)
        shapes.append(Shape(i, color, m, m, sil=m))
        rid[a] = i
    shapes[0].full = shapes[0].sil = Mask.from_full(np.ones(canvas, bool))
    shapes[0].children = [1, 2]
    shapes[1].parent = shapes[2].parent = 0
    # An earlier completed sibling extends behind the island. The island's
    # later paint is necessary even though its colour matches the parent.
    if model == "primitive":
        # A fitted primitive may paint beyond the stored mask's boundary.
        shapes[1].prim = Prim("rect", 30, 30, 15, 10)
    elif model == "mask":
        shapes[1].full = Mask.from_full(red | island)
    else:
        shapes[1].draw = shapes[1].full.dilated(1, canvas)
    seg = Segmentation(rid, shapes, np.array([s.color for s in shapes], np.uint8))
    cfg = Config(snap_primitives=False) if model == "trace" else Config()
    assert order.merge_fragments(seg, np.zeros(canvas, bool), cfg) is seg


def test_badge_repainting_strip_remains_visible(samples):
    if not have_renderer():
        pytest.skip("requires renderer")
    from plate.raster import render_svg
    result = pipeline.run(samples / "badge.png", Config())
    rendered = render_svg(result.svg, result.loaded.orig_size)
    assert np.linalg.norm(rendered[510, 300].astype(float)-(20, 40, 90)) < 10


def test_parent_model_must_paint_the_child_not_just_its_filled_silhouette():
    canvas = (70, 90)
    full = raster_prim(Prim("ellipse", 40, 35, 27, 25), canvas)
    island = np.zeros(canvas, bool)
    island[34:37, 66] = True
    vis = Mask.from_full(full & ~island)
    child = Mask.from_full(island)
    parent = Shape(0, (24, 46, 76), vis, Mask.from_full(full), sil=Mask.from_full(full),
                   prim=Prim("circle", 40, 35, 25, 25), children=[1])
    shapes = [parent, Shape(1, parent.color, child, child, sil=child, parent=0)]
    rid = np.full(canvas, -1, np.int32)
    rid[vis.to_full(canvas)] = 0
    rid[island] = 1
    seg = Segmentation(rid, shapes, np.array([parent.color], np.uint8))
    assert order.merge_fragments(seg, rid < 0, Config()) is seg
