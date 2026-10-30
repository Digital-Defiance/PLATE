"""Disconnected bands may share a ramp; constant foreground details may not."""
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from scipy import ndimage as ndi

from plate import pipeline
from plate.config import Config
from plate.geometry import GradientFill, GradientStop, Prim, fit_radial_gradient, raster_prim
from plate.masks import Mask
from plate.raster import have_renderer
from plate.scene import Loaded, Segmentation, Shape
from plate.stages import gradient, order


def _bands(incompatible=False, uncovered=False, noisy_crater=False):
    h, w = 240, 280
    y, x = np.mgrid[:h, :w]
    disc = raster_prim(Prim('circle', 140, 120, 90, 90), (h, w))
    rho = np.hypot(x-125, y-105)
    colors = np.clip(np.stack([240-.5*rho, 210-.7*rho, 130+.04*rho], axis=2), 0, 255).round().astype(np.uint8)
    bars = ((abs(x-140) < 5) & (y > 10) & (y < 230)) | ((abs(y-120) < 4) & (x > 20) & (x < 260))
    ring = (np.hypot(x-140, y-120) < 55) & (np.hypot(x-140, y-120) > 36)
    cover = bars | ring
    crater = (x-195)**2+(y-160)**2 <= 6**2
    visible = disc & ~cover & ~crater
    rgb = colors.copy()
    if incompatible:
        rgb[(y > 124) & visible] = 255-rgb[(y > 124) & visible]
    rgb[cover] = (24, 46, 76)
    rgb[crater] = colors[160, 195]  # Same ramp colour, but a genuinely flat object.
    if noisy_crater:
        noise = np.random.default_rng(0).integers(-2, 3, size=(int(crater.sum()), 3))
        rgb[crater] = np.clip(rgb[crater].astype(int)+noise, 0, 255)
    seed = visible & (x < 135) & (y < 116)
    parts = [seed]
    for band in np.unique((rho//9)[visible & ~seed]):
        labels, count = ndi.label(visible & ~seed & (rho//9 == band))
        parts.extend(labels == k for k in range(1, count+1))
    if not uncovered:
        parts.append(cover)
    parts.append(crater)
    rid = np.full((h, w), -1, np.int32)
    shapes = []
    for sid, a in enumerate(parts):
        m = Mask.from_full(a)
        shapes.append(Shape(sid, tuple(rgb[a].mean(axis=0).astype(int)), m, m))
        rid[a] = sid
    yy, xx = np.nonzero(seed)
    shapes[0].grad, _ = fit_radial_gradient(np.c_[xx, yy], rgb[yy, xx].astype(float))
    seg = Segmentation(rid, shapes, np.zeros((1, 3), np.uint8))
    img = Loaded(rgb, np.where(rid >= 0, 255, 0).astype(np.uint8), (w, h), 1.)
    order.build(seg, rid < 0, Config())
    return seg, img, disc, crater


@pytest.mark.parametrize('noisy_crater', [False, True])
def test_radial_bands_rejoin_without_absorbing_matching_flat_crater(noisy_crater):
    seg, img, disc, crater = _bands(noisy_crater=noisy_crater)
    before = seg.rid >= 0
    joined = gradient.merge_occluded(seg, img, Config())
    assert len(joined.shapes) < len(seg.shapes)-5
    assert np.array_equal(joined.rid >= 0, before)
    order.build(joined, joined.rid < 0, Config())
    ramp, = [s for s in joined.shapes if s.grad is not None]
    assert ramp.prim is not None and ramp.prim.kind == 'circle'
    model = ramp.full.to_full(disc.shape)
    assert (model & disc).sum()/(model | disc).sum() >= .97
    assert not np.any(ramp.vis.to_full(disc.shape) & crater)
    assert len(np.unique(joined.rid[crater])) == 1


@pytest.mark.parametrize('case', ['incompatible', 'uncovered', 'disabled', 'gradients_disabled'])
def test_band_recovery_requires_a_shared_ramp_and_hidden_geometry(case):
    seg, img, _, _ = _bands(incompatible=case == 'incompatible', uncovered=case == 'uncovered')
    cfg = Config(complete_hidden=False) if case == 'disabled' else Config(gradients=case != 'gradients_disabled')
    assert gradient.merge_occluded(seg, img, cfg) is seg


def test_orbit_gradient_core_and_orbits_keep_full_geometry_and_paint_order():
    from challenges import assert_target
    if not have_renderer():
        pytest.skip('requires renderer')
    directory = Path(__file__).resolve().parents[1] / 'samples/challenges'
    result = pipeline.run(directory / 'logo_orbit_wordmark.png')
    actual = ET.fromstring(result.svg)
    target = ET.parse(directory / 'logo_orbit_wordmark.target.svg').getroot()
    wanted = [e for e in target.iter() if e.get('id') in ('back-orbit', 'gradient-core', 'front-orbit')]
    circles = [e for e in actual.iter() if e.tag.endswith('circle') and e.get('fill', '').startswith('url(')]
    assert len(circles) == 1
    got = [e for e in actual.iter() if e in circles or
           (e.tag.endswith('ellipse') and e.get('stroke') in ('#a9d1b5', '#e9bc59'))]
    assert len(got) == len(wanted) == 3
    actual[:] = [e for e in actual if e.tag.endswith('defs')] + got
    target[:] = [e for e in target if e.tag.endswith('defs')] + wanted
    assert_target(ET.tostring(actual, encoding='unicode'), ET.tostring(target, encoding='unicode'))


@pytest.mark.parametrize('same_owner', [True, False])
def test_gradient_showing_through_a_ring_is_not_a_child_repaint(same_owner):
    canvas = (100, 120)
    outer = raster_prim(Prim('circle', 60, 50, 35, 35), canvas)
    inner = raster_prim(Prim('circle', 60, 50, 18, 18), canvas)
    ring = outer & ~inner
    background = ~ring if same_owner else ~outer
    parts = [background, ring] if same_owner else [background, ring, inner]
    shapes = []
    rid = np.full(canvas, -1, np.int32)
    for sid, part in enumerate(parts):
        m = Mask.from_full(part)
        shapes.append(Shape(sid, (200, 140, 80) if sid != 1 else (24, 46, 76), m, m))
        rid[part] = sid
    shapes[0].grad = GradientFill('linear', [GradientStop(0, (240, 200, 130)),
                                           GradientStop(1, (180, 120, 140))], start=(0, 0), end=(120, 0))
    # A previous ordering pass can have left a filled-circle completion behind.
    shapes[1].prim, shapes[1].completed = Prim('circle', 60, 50, 35, 35), True
    seg = Segmentation(rid, shapes, np.zeros((1, 3), np.uint8))
    order.build(seg, rid < 0, Config(complete_hidden=False))
    assert bool(shapes[1].full.to_full(canvas)[50, 60]) is (not same_owner)
    if same_owner:
        assert shapes[1].prim is None
