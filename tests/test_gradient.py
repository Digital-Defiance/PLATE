"""Unit tests for gradient fit math (geometry.fit_*) and the detect() merge stage.

Pure tests (no renderer needed) except the shaded observe-and-record note, which
guards its SSIM leg behind have_renderer(). Run with:
    PYTHONPATH=src DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib pytest -q tests/test_gradient.py
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from plate.config import Config
from plate.geometry import GRAD_STOPS, fit_linear_gradient, fit_radial_gradient
from plate.masks import Mask
from plate.scene import Loaded, Segmentation, Shape
from plate.stages.gradient import detect


def test_complex_poster_keeps_gradient_when_recovering_thin_branches():
    from pathlib import Path
    from plate import pipeline
    path = Path(__file__).resolve().parents[1] / "samples/challenges/complex_event_poster.png"
    assert pipeline.run(path, Config()).stats["gradients"] >= 1


@pytest.mark.parametrize("source_scale,work_size", [(1, 1536), (2, 400)])
def test_occluded_gradient_badge_is_one_full_disc(tmp_path, source_scale, work_size):
    from pathlib import Path
    from plate import pipeline
    from plate.raster import have_renderer
    from challenges import assert_target
    from PIL import Image
    from xml.etree import ElementTree as ET
    directory = Path(__file__).resolve().parents[1] / "samples/challenges"
    path = directory / "gradient_badge.png"
    if source_scale != 1:
        with Image.open(path) as image:
            image = image.resize((400 * source_scale, 360 * source_scale), Image.Resampling.NEAREST)
            path = tmp_path / "scaled-badge.png"
            image.save(path)
    result = pipeline.run(path, Config(work_size=work_size))
    assert result.stats["shapes"] == 5
    assert result.stats["gradients"] == 1
    disc, = [s for s in result.shapes if s.grad is not None]
    assert disc.completed and disc.prim.kind == "circle"
    scale = result.loaded.scale
    assert abs((disc.prim.cx + .5) / scale - 200 * source_scale) < source_scale
    assert abs((disc.prim.cy + .5) / scale - 180 * source_scale) < source_scale
    assert abs(disc.prim.rx / scale - 135 * source_scale) < source_scale
    if have_renderer():
        target = ET.fromstring((directory / "gradient_badge.target.svg").read_text())
        target.set("width", str(400 * source_scale))
        target.set("height", str(360 * source_scale))
        assert_target(result.svg, ET.tostring(target, encoding="unicode"))


def _occluded_disc(kind="radial", incompatible=False, shifted=False, uncovered=False):
    """Independent analytic ramp samples on two arcs separated by a solid ribbon."""
    from plate.geometry import Prim, raster_prim
    from plate.stages import order
    H, W = 160, 180
    y, x = np.mgrid[:H, :W]
    disc = raster_prim(Prim("circle", 90, 80, 55, 55), (H, W))
    lower = raster_prim(Prim("circle", 102 if shifted else 90, 80, 55, 55), (H, W))
    cover = np.zeros((H, W), bool)
    cover[65:95, 20:160] = True
    parts = [disc & (y < 65), lower & (y >= 95)]
    if not uncovered:
        parts.append(cover)
    parts.append(~np.logical_or.reduce(parts))
    u = np.hypot(x - 90, y - 80) / 55 if kind == "radial" else x / W
    rgb = np.full((H, W, 3), 255, np.uint8)
    colors = np.stack([230 - 100*u, 200 - 80*u, 150 + 10*u], axis=2).clip(0, 255).astype(np.uint8)
    rgb[parts[0] | parts[1]] = colors[parts[0] | parts[1]]
    if incompatible:
        rgb[parts[1]] = 255 - rgb[parts[1]]
    if not uncovered:
        rgb[cover] = (30, 60, 120)
    rid = np.full((H, W), -1, np.int32)
    shapes = []
    for i, part in enumerate(parts):
        mask = Mask.from_full(part)
        shape = Shape(i, tuple(int(v) for v in rgb[part].mean(axis=0)), mask, mask)
        if i < 2:
            ys, xs = np.nonzero(part)
            fit = fit_radial_gradient if kind == "radial" else fit_linear_gradient
            shape.grad, _ = fit(np.c_[xs, ys], rgb[part].astype(float))
        shapes.append(shape)
        rid[part] = i
    seg = Segmentation(rid, shapes, np.zeros((1, 3), np.uint8))
    img = Loaded(rgb, np.full((H, W), 255, np.uint8), (W, H), 1.)
    order.build(seg, rid < 0, Config())
    return seg, img


@pytest.mark.parametrize("kind", ["linear", "radial"])
def test_shared_gradient_refits_pixels_and_rebuilds_ownership(kind):
    from plate.stages import gradient, order
    seg, img = _occluded_disc(kind=kind)
    old_owned = seg.rid >= 0
    out = gradient.merge_occluded(seg, img, Config())
    assert len(out.shapes) == len(seg.shapes) - 1
    assert out.palette is seg.palette
    assert np.array_equal(out.rid >= 0, old_owned)
    assert [s.id for s in out.shapes] == list(range(len(out.shapes)))
    for s in out.shapes:
        assert np.array_equal(out.rid == s.id, s.vis.to_full(out.rid.shape))
        assert s.parent is None and s.children == [] and s.prim is None
    order.build(out, out.rid < 0, Config())
    disc, = [s for s in out.shapes if s.grad is not None]
    assert disc.grad.kind == kind and disc.completed
    assert abs(disc.prim.rx - 55) < 1
    assert disc.full.area > disc.vis.area


@pytest.mark.parametrize("kind", ["linear", "radial"])
@pytest.mark.parametrize("problem", ["incompatible", "shifted", "uncovered"])
def test_shared_gradient_rejects_incompatible_fragments(kind, problem):
    from plate.geometry import Prim
    from plate.stages.gradient import merge_occluded
    seg, img = _occluded_disc(kind=kind, **{problem: True})
    if problem == "uncovered":
        # Even matching model hints must be checked against current occlusion.
        for s in seg.shapes[:2]:
            s.completed = True
            s.prim = Prim("circle", 90, 80, 55, 55)
    assert merge_occluded(seg, img, Config()) is seg


def test_shared_gradient_respects_completion_switch():
    from plate.stages.gradient import merge_occluded
    seg, img = _occluded_disc()
    assert merge_occluded(seg, img, Config(complete_hidden=False)) is seg


# --------------------------------------------------------------------------- helpers

def _grid(n=40):
    xs = np.tile(np.arange(n), n)
    ys = np.repeat(np.arange(n), n)
    return np.c_[xs, ys].astype(float)


def _angle_between(v, u):
    v = np.asarray(v, float); u = np.asarray(u, float)
    c = float(np.dot(v, u) / (np.linalg.norm(v) * np.linalg.norm(u) + 1e-12))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


# --------------------------------------------------------------------------- fit math

def test_linear_recovers_direction_and_endpoints():
    P = _grid(40)
    u = np.array([math.cos(math.radians(30)), math.sin(math.radians(30))])
    t = P @ u
    tn = (t - t.min()) / (t.max() - t.min())
    # affine ramp blue->red along u
    C = np.stack([40 + tn * 200, 30 + tn * 40, 220 - tn * 180], 1)
    g, res = fit_linear_gradient(P, C)
    assert g.kind == "linear"
    assert res < 0.02, f"affine ramp residual too high: {res}"
    axis = np.array(g.end) - np.array(g.start)
    ang = min(_angle_between(axis, u), _angle_between(axis, -u))
    assert ang < 2.0, f"recovered axis off by {ang:.2f} deg"
    # endpoint stops near the constructed endpoints. Stops are per-bin pixel MEANS, so the
    # extreme stops sit slightly inside the true endpoints (a bin averages a range of the
    # ramp) -- allow for that inward pull rather than asserting the exact endpoint colour.
    first, last = g.stops[0].rgb, g.stops[-1].rgb
    ends = sorted([first, last], key=lambda c: c[2])   # red end has low blue
    assert ends[0][0] > 200 and ends[1][0] < 80       # bright-R end high, dark-R end low
    assert ends[0][2] < 80 and ends[1][2] > 180       # and blue mirrors it


def test_linear_clipped_core_low_residual():
    """A channel that saturates at 255 over part of the axis must still fit well because
    the piecewise binned-means model represents the plateau (not a single affine line)."""
    P = _grid(40)
    u = np.array([1.0, 0.0])
    t = P @ u
    tn = (t - t.min()) / (t.max() - t.min())
    R = np.clip(tn * 2.0 * 255, 0, 255)        # clips at 255 for the upper half of the axis
    C = np.stack([R, 120 + 0 * tn, 60 + 0 * tn], 1)
    g, res = fit_linear_gradient(P, C)
    assert res < 0.03, f"clipped-core piecewise residual too high: {res}"
    # the piecewise model should plateau: last stops' R channel at/near 255
    assert g.stops[-1].rgb[0] >= 250


def test_radial_recovers_center_and_radius():
    P = _grid(60)
    cx0, cy0 = 20.0, 35.0
    rho = np.hypot(P[:, 0] - cx0, P[:, 1] - cy0)
    rn = rho / rho.max()
    C = np.stack([255 * (1 - rn), 120 * (1 - rn), 60 * (1 - rn)], 1).clip(0, 255)
    g, res = fit_radial_gradient(P, C)
    assert g.kind == "radial"
    assert res < 0.02, f"radial residual too high: {res}"
    assert abs(g.center[0] - cx0) < 1.5 and abs(g.center[1] - cy0) < 1.5, g.center
    assert abs(g.radius - rho.max()) < 1.5, g.radius


def test_rejects_random_colours():
    P = _grid(40)
    rng = np.random.default_rng(1)
    C = rng.integers(0, 256, size=(len(P), 3)).astype(float)
    _, rl = fit_linear_gradient(P, C)
    _, rr = fit_radial_gradient(P, C)
    assert min(rl, rr) > Config().grad_max_residual, (rl, rr)


def test_fit_is_deterministic():
    P = _grid(40)
    u = np.array([0.6, 0.8])
    t = P @ u; tn = (t - t.min()) / (t.max() - t.min())
    C = np.stack([tn * 255, tn * 128, 255 - tn * 255], 1)
    g1, r1 = fit_linear_gradient(P, C)
    g2, r2 = fit_linear_gradient(P, C)
    assert r1 == r2
    assert [(s.offset, s.rgb) for s in g1.stops] == [(s.offset, s.rgb) for s in g2.stops]


def test_stop_count_independent_of_band_count():
    """MUST-FIX #1: emitted stops are sampled from the fitted curve at a FIXED set of bins,
    so a region with exactly the minimum bands and one with many bands both yield a valid,
    correctly-ordered stop list of at most GRAD_STOPS entries."""
    P = _grid(60)
    u = np.array([1.0, 0.0]); t = P @ u; tn = (t - t.min()) / (t.max() - t.min())

    # "few bands" region: colour quantized into exactly 6 steps
    few = np.floor(tn * 6) / 5.0
    Cf = np.stack([few * 255, few * 128, 255 - few * 255], 1).clip(0, 255)
    gf, _ = fit_linear_gradient(P, Cf)
    # "many bands" region: a smooth ramp (hundreds of distinct colours)
    Cm = np.stack([tn * 255, tn * 128, 255 - tn * 255], 1)
    gm, _ = fit_linear_gradient(P, Cm)

    for g in (gf, gm):
        assert 2 <= len(g.stops) <= GRAD_STOPS
        offs = [s.offset for s in g.stops]
        assert offs == sorted(offs), "stops must be in ascending offset order"
        assert offs[0] == 0.0 and offs[-1] == 1.0, "stops must span the full axis"


# --------------------------------------------------------------------------- detect()

def _loaded_from_bands(bands, H, W):
    """bands: list of (mask_bool_HxW, rgb). Build a Loaded whose rgb paints each band."""
    rgb = np.full((H, W, 3), 255, np.uint8)
    alpha = np.zeros((H, W), np.uint8)
    for m, col in bands:
        rgb[m] = col
        alpha[m] = 255
    return Loaded(rgb=rgb, alpha=alpha, orig_size=(W, H), scale=1.0)


def _seg_from_bands(bands, H, W):
    rid = np.full((H, W), -1, np.int32)
    shapes = []
    for i, (m, _col) in enumerate(bands):
        mk = Mask.from_full(m)
        ys, xs = np.nonzero(m)
        rid[ys, xs] = i
        shapes.append(Shape(id=i, color=tuple(int(c) for c in _col), vis=mk, full=mk))
    return Segmentation(rid=rid, shapes=shapes, palette=np.array([[0, 0, 0]], np.uint8))


def _vertical_ramp_bands(H, W, nbands=10, x0=0, x1=None):
    """nbands vertical stripes spanning columns [x0,x1) forming a linear ramp in x.

    The per-band colour step is kept gentle (a shallow grey->light ramp) so adjacent-band
    Lab dE stays below the default join threshold grad_step_de=14, i.e. the bands look like
    one posterized smooth ramp rather than a set of unrelated flat regions."""
    x1 = W if x1 is None else x1
    bands = []
    edges = np.linspace(x0, x1, nbands + 1).astype(int)
    for k in range(nbands):
        m = np.zeros((H, W), bool)
        m[:, edges[k]:edges[k + 1]] = True
        f = k / (nbands - 1)
        v = int(round(120 + f * 110))          # 120 -> 230 grey ramp, ~12 step over 10 bands
        col = (v, v, v)
        bands.append((m, col))
    return bands


def test_detect_merges_ramp_to_one_shape():
    H = W = 80
    bands = _vertical_ramp_bands(H, W, nbands=8)
    img = _loaded_from_bands(bands, H, W)
    seg = _seg_from_bands(bands, H, W)
    cfg = Config()
    out = detect(seg, img, cfg)
    grads = [s for s in out.shapes if s.grad is not None]
    assert len(grads) == 1, f"expected one merged gradient shape, got {len(grads)}"
    assert grads[0].grad.kind == "linear"
    # palette passed through unchanged (identity)
    assert out.palette is seg.palette
    # ids contiguous 0..n-1
    assert [s.id for s in out.shapes] == list(range(len(out.shapes)))
    # rid references only valid ids or -1
    assert out.rid.max() < len(out.shapes)
    assert set(np.unique(out.rid)) <= set(range(len(out.shapes))) | {-1}


def test_detect_disjoint_rid_no_double_assign():
    """MUST pass without tripping the disjoint-write assertion in detect()."""
    H = W = 80
    bands = _vertical_ramp_bands(H, W, nbands=8)
    img = _loaded_from_bands(bands, H, W)
    seg = _seg_from_bands(bands, H, W)
    out = detect(seg, img, Config())
    # every opaque pixel maps to exactly one survivor id
    painted = (out.rid >= 0).sum()
    assert painted == (img.alpha > 0).sum()


def test_detect_no_regression_on_flat_controls(controls_dir):
    """The key flat-art guard: detect() must NOT merge anything on flat controls."""
    from plate.imageio import load_image
    from plate.stages.segment import segment
    cfg = Config()
    for name in ("t2_two_circles", "t3_nested", "t4_badge", "t5_hexagon", "t1_circle"):
        png = controls_dir / f"{name}.png"
        img = load_image(png, cfg)
        seg = segment(img, cfg)
        out = detect(seg, img, cfg)
        assert len(out.shapes) == len(seg.shapes), f"{name}: detect changed shape count"
        assert all(s.grad is None for s in out.shapes), f"{name}: detect fired on flat art"
        assert [s.id for s in out.shapes] == list(range(len(out.shapes)))


def test_detect_background_ramp_stays_background_size():
    """A banded linear background merges to one shape still spanning >=60% of the canvas."""
    H = W = 120
    bands = _vertical_ramp_bands(H, W, nbands=8)   # spans the whole canvas
    img = _loaded_from_bands(bands, H, W)
    seg = _seg_from_bands(bands, H, W)
    out = detect(seg, img, Config())
    grads = [s for s in out.shapes if s.grad is not None]
    assert len(grads) == 1
    assert grads[0].vis.area >= 0.6 * H * W, "merged background must still be >=60% of canvas"


def test_resolution_invariance_1536_vs_3072():
    """MUST fire at both work-size scales: the fractional gates track canvas area, so a ramp
    realized at the reference scale and at 2x resolution both merge to one gradient shape."""
    cfg = Config()
    for scale in (1, 2):
        H = W = 80 * scale
        bands = _vertical_ramp_bands(H, W, nbands=8)
        img = _loaded_from_bands(bands, H, W)
        seg = _seg_from_bands(bands, H, W)
        out = detect(seg, img, cfg)
        grads = [s for s in out.shapes if s.grad is not None]
        assert len(grads) == 1, f"scale {scale}x: gradient did not fire"


# --------------------------------------------------------------------------- shaded note

def test_shaded_observe_and_record(samples, capsys):
    """Non-gating: assert only the guaranteed direction of travel (gradients>=1, shapes<10).
    Actual shapes/SSIM are printed for STATUS.md (design: shaded is observe-and-record)."""
    from plate import pipeline
    r = pipeline.run(samples / "shaded.png", Config())
    ssim = None
    from plate.raster import have_renderer
    if have_renderer():
        import numpy as _np
        from PIL import Image
        from plate import metrics
        src = _np.asarray(Image.open(samples / "shaded.png").convert("RGBA"))
        ssim = metrics.fidelity(r.svg, src).get("ssim")
    print(f"\n[shaded] shapes={r.stats['shapes']} gradients={r.stats['gradients']} ssim={ssim}")
    assert r.stats["gradients"] >= 1
    assert r.stats["shapes"] < 10
