"""Fine-detail ownership: supported taper tips belong to regions, isolated dots do not."""
import numpy as np
import pytest
from PIL import Image
from scipy import ndimage as ndi

from plate import pipeline
from plate.config import Config, load
from plate.masks import Mask
from plate.scene import Loaded, Segmentation, Shape
from plate.stages import rescue

CREAM = (245, 237, 218)
DARK = (12, 40, 44)


def _scene(rid, rgb, colors, alpha=None):
    h, w = rid.shape
    shapes = []
    for sid, color in enumerate(colors):
        mask = Mask.from_full(rid == sid)
        shapes.append(Shape(sid, color, mask, mask))
    img = Loaded(rgb, np.full((h, w), 255, np.uint8) if alpha is None else alpha, (w, h), 1.)
    return img, Segmentation(rid.copy(), shapes, np.array(colors, np.uint8))


def _wedge(rotation=0):
    y, x = np.indices((80, 120))
    expected = (x < 65) & (np.abs(y - 40) < (65 - x) * .24)
    owned = expected & (x < 52)  # simulate segmentation truncating a tapering gap
    dot = (x - 95)**2 + (y - 20)**2 <= 9
    rid = np.zeros(expected.shape, np.int32)
    rid[owned], rid[dot] = 1, 2
    rgb = np.where((expected | dot)[..., None], DARK, CREAM).astype(np.uint8)
    rid, rgb, expected, dot = [np.rot90(a, rotation).copy() for a in (rid, rgb, expected, dot)]
    return (*_scene(rid, rgb, [CREAM, DARK, DARK]), expected, dot)


def _assert_partition(seg):
    coverage = np.zeros(seg.rid.shape, np.int32)
    for shape in seg.shapes:
        mask = shape.vis.to_full(seg.rid.shape)
        assert np.array_equal(mask, seg.rid == shape.id)
        assert np.array_equal(shape.full.to_full(seg.rid.shape), mask)
        coverage += mask
    assert np.all(coverage == 1)


@pytest.mark.parametrize("rotation", range(4))
def test_supported_gap_tip_is_owned_by_one_region(rotation):
    img, seg, expected, dot = _wedge(rotation)
    previous = seg.rid.copy()
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert count == np.count_nonzero(expected & (previous != 1))
    assert np.all(new.rid[expected] == 1)
    assert np.all(new.rid[dot] == 2), "the isolated real dot must remain separate"
    assert np.array_equal(new.rid[~expected], previous[~expected])
    assert np.array_equal(seg.rid, previous), "the caller's old segmentation must remain valid"
    _assert_partition(new)


def test_reconnection_is_disabled_by_default():
    img, seg, *_ = _wedge()
    new, count = rescue.reconnect_tips(img, seg, Config())
    assert new is seg and count == 0


def test_tip_fragment_merges_without_leaving_stale_region_ids():
    img, seg, expected, dot = _wedge()
    rid = seg.rid.copy()
    rid[39:42, 62:63] = 3
    img, seg = _scene(rid, img.rgb, [CREAM, DARK, DARK, DARK])
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert count > 0 and len(new.shapes) == 3
    assert np.all(new.rid[expected] == 1)
    assert np.all(new.rid[dot] == 2)
    _assert_partition(new)


def test_isolated_unassigned_dot_is_not_given_to_a_distant_region():
    img, seg, expected, _ = _wedge()
    # Restore the whole wedge, but add a separate dot which the rescue must retain
    # as fine detail instead of merging into the large dark region.
    seg.rid[expected] = 1
    seg.shapes[0].vis = Mask.from_full(seg.rid == 0)
    seg.shapes[1].vis = Mask.from_full(seg.rid == 1)
    img.rgb[57:61, 91:95] = DARK
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


def test_raw_ink_between_two_regions_does_not_merge_them():
    rid = np.zeros((80, 120), np.int32)
    rid[36:44, 5:35], rid[36:44, 75:105] = 1, 2
    ink = rid > 0
    ink[39:42, 35:75] = True
    rgb = np.where(ink[..., None], DARK, CREAM).astype(np.uint8)
    img, seg = _scene(rid, rgb, [CREAM, DARK, DARK])
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


def test_reconnection_cannot_cut_a_donor_bridge():
    y, x = np.indices((80, 120))
    cream = ((x - 20)**2 + (y - 40)**2 <= 15**2) | ((x - 95)**2 + (y - 40)**2 <= 15**2)
    cream[36:45, 20:96] = True
    rid = np.where(cream, 0, 1).astype(np.int32)
    source = cream.copy()
    source[32:49, 58:61] = False
    rgb = np.where(source[..., None], CREAM, DARK).astype(np.uint8)
    img, seg = _scene(rid, rgb, [CREAM, DARK])
    assert ndi.label(cream)[1] == 1 and ndi.label(source)[1] == 2
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


@pytest.mark.parametrize("alpha", [0, 128, 230])
def test_transparent_or_translucent_pixels_keep_ownership(alpha):
    img, seg, expected, _ = _wedge()
    img.alpha[expected & (seg.rid != 1)] = alpha
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


@pytest.mark.parametrize("sid", [0, 1])
def test_gradient_donor_or_target_is_not_reassigned(sid):
    img, seg, *_ = _wedge()
    seg.shapes[sid].grad = object()  # only identity/exclusion matters for this stage
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


def test_pipeline_reconnects_before_tracing_and_keeps_dot_detail(tmp_path, monkeypatch):
    img, seg, expected, _ = _wedge()
    path = tmp_path / "wedge.png"
    Image.fromarray(img.rgb).save(path)
    monkeypatch.setattr(pipeline, "segment", lambda image, cfg: seg)
    cfg = load("smooth", denoise=0, gradients=False, complete_hidden=False, strokes=False)
    result = pipeline.run(path, cfg)
    assert result.stats["reconnected"] > 0
    assert len(np.unique(result.seg.rid[expected])) == 1
    found, _ = rescue.find(result.loaded, result.seg, cfg.rescue_min_area,
                            rescue.absorbable_ids(result.seg, img.alpha.shape, img.scale))
    dark = next(mask for color, mask in found if color == DARK)
    assert not dark[38:43, 56:65].any(), "no separate overlay at the gap tip"
    assert dark[18:23, 93:98].any(), "the real dot remains available for the fine-detail layer"
