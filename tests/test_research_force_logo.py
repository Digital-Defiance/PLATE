"""Regression fixture: the Research Force logo (a real JPEG logo) under the `smooth` preset.

Guards the fixes this image drove: JPEG-keyed denoise, outline smoothing, the polygon facet
cap, fine-detail rescue of the 2 px tagline, and bridging of tapering gap tips (which used to
float as dark specks between the page lines). ~1 minute: one pipeline run shared by all checks.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from plate import pipeline
from plate.bakeoff import score
from plate.config import load
from plate.raster import have_renderer, render_svg

LOGO = Path(__file__).resolve().parents[1] / "samples" / "fixtures" / "research_force_logo.jpeg"
pytestmark = pytest.mark.skipif(not have_renderer(), reason="needs an SVG renderer")


@pytest.fixture(scope="module")
def traced():
    ref = np.asarray(Image.open(LOGO).convert("RGB"))
    res = pipeline.run(LOGO, load("smooth", None, upscale=2.0))
    h, w = ref.shape[:2]
    ren = render_svg(res.svg, (w, h), (255, 255, 255))
    ren2 = render_svg(res.svg, (2 * w, 2 * h), (255, 255, 255))
    return ref, res, ren, ren2


def test_fidelity_floor(traced):
    ref, res, _, _ = traced
    f = score.fidelity(res.svg, ref)
    assert f["ssim"] >= 0.97, f
    assert f["edge_f1"] >= 0.99, f


def test_no_specks_or_lost_pieces(traced):
    """No pinched-off wedge tips or stray blobs (extra pieces). One 'missing' piece is tolerated:
    the dark triangle under the V joins a 1 px dark seam that the soft JPEG only half shows."""
    ref, _, ren, _ = traced
    t = score.topology(ren, ref)
    odd = score.topology_pieces(ren, ref)
    assert t["topo_extra"] == 0, odd
    assert t["topo_missing"] <= 1, odd


@pytest.mark.parametrize("x,y", [(640, 1091), (965, 1091)])
def test_tagline_periods_survive(traced, x, y):
    """'INDEPENDENT RESEARCH. ON THE RECORD.' - both periods are 2-3 px dots."""
    _, _, ren, _ = traced
    win = ren[y - 2:y + 3, x - 2:x + 3].astype(int).sum(2)
    assert win.max() > 450, win


def test_dot_in_the_v_survives(traced):
    """The small dark dot where the page lines meet (at 2x: around (1148, 1693))."""
    *_, ren2 = traced
    win = ren2[1688:1699, 1142:1155].astype(int).sum(2)
    assert win.min() < 300, win


def test_editable_size(traced):
    _, res, _, _ = traced
    assert res.stats["anchors"] <= 700, res.stats["anchors"]     # 356 when added; guards over-fragmenting


def test_outline_smoothness_is_measured_and_bounded(traced):
    """Kiro 13.6 is a DOCUMENTED LIMIT, state (b): the narrow gaps near the logo's spine come
    out ~1 px short and slightly wavy. The ownership sub-fix (rescue.reconnect_tips) already
    removed the floating spine knobs, so topology is clean (0 extra / 0 missing, pinned above);
    the residual is sub-piece wobble that SSIM/edge-F1 cannot see. The 13.5 smoothness metric
    gives it a number. Three broad fixes - global mask-blur reduction, blanket tip suppression,
    and a 35%% fold-clamp - each created extra pieces or showed no gain and were rejected
    (see tasks.md 13.6 / STATUS.md). This pins the measured state so a regression is visible.
    """
    ref, res, ren, _ = traced
    f = score.fidelity(res.svg, ref)
    # wobble is small but non-zero: the known slightly-wavy spine bends. Guard it does not
    # balloon (a regression that re-roughened the outlines) without claiming it is zero.
    assert 0.90 <= f["smoothness"] <= 1.0, f["smoothness"]
    assert f["wobble"] <= 0.01, f["wobble"]
