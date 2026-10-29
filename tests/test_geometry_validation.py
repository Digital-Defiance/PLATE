"""Regressions for primitive fits that invalidate the observed geometry."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from plate import pipeline
from plate.config import Config
from plate.geometry import Prim, raster_prim
from plate.masks import Mask
from plate.scene import Shape
from plate.stages import complete
from plate.stages.primitives import snap


@pytest.mark.parametrize("width,height", [(840, 100), (700, 50), (160, 40)])
def test_long_rectangle_cannot_snap_to_clipped_ellipse(width, height):
    mask = Mask(np.ones((height, width), dtype=bool), 810, 60)
    primitive = snap(mask, Config())
    assert primitive is not None and primitive.kind == "rect"
    assert abs(primitive.cx - (60 + (width - 1) / 2)) < 0.5
    assert abs(primitive.cy - (810 + (height - 1) / 2)) < 0.5
    assert abs(primitive.rx - width / 2) < 0.5
    assert abs(primitive.ry - height / 2) < 0.5


@pytest.mark.parametrize("shift,accepted", [(0, True), (10, False)])
def test_completion_rejects_model_that_discards_visible_pixels(monkeypatch, shift, accepted):
    """Even a fitter's nominally confident result must preserve the visible crescent."""
    canvas = (160, 180)
    circle = raster_prim(Prim("circle", 70, 80, 45, 45), canvas)
    cover = np.zeros(canvas, dtype=bool)
    cover[15:145, 70:150] = True
    visible = Mask.from_full(circle & ~cover)
    occluder = Mask.from_full(cover)
    behind = Shape(0, (210, 40, 40), visible, visible, sil=visible)
    front = Shape(1, (40, 70, 190), occluder, occluder, sil=occluder)

    fit = complete.fit_circle

    def candidate(points):
        primitive, residual, coverage = fit(points)
        return replace(primitive, cx=primitive.cx + shift), residual, coverage

    monkeypatch.setattr(complete, "fit_circle", candidate)
    # Exercise validation of this one candidate independently of fallback models.
    monkeypatch.setattr(complete, "fit_ellipse", lambda points: None)
    monkeypatch.setattr(complete, "fit_rect", lambda points: None)
    monkeypatch.setattr(complete, "_bridge", lambda points, classes: None)
    result = complete.try_complete(behind, [front], *canvas, Config())
    assert (result is not None) == accepted


def test_poster_footer_remains_an_editable_rectangle():
    path = Path(__file__).resolve().parents[1] / "samples/challenges/complex_event_poster.png"
    result = pipeline.run(path, Config())

    def leaves(nodes):
        for node in nodes:
            if node.kind == "group":
                yield from leaves(node.children)
            else:
                yield node

    footer = [node for node in leaves(result.nodes)
              if abs(node.params.get("cy", 0) - 860) < 2
              and node.params.get("rx", 0) > 300]
    assert len(footer) == 1
    assert footer[0].kind == "rect"
    assert abs(footer[0].params["rx"] - 420) < 1
    assert abs(footer[0].params["ry"] - 50) < 1
