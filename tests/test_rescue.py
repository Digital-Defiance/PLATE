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


def _small_gap(rotation=0):
    y, x = np.indices((80, 120))
    owned = (x >= 15) & (x < 21) & (y >= 35) & (y < 41)
    tail = (x >= 21) & (x < 30) & (np.abs(y - 37.5) < (30 - x) * .17)
    expected = owned | tail
    rid = owned.astype(np.int32)
    rgb = np.where(expected[..., None], DARK, CREAM).astype(np.uint8)
    rid, rgb, expected = [np.rot90(a, rotation).copy() for a in (rid, rgb, expected)]
    return (*_scene(rid, rgb, [CREAM, DARK]), expected)


@pytest.mark.parametrize("rotation", [0, 1])
def test_solid_core_anchors_a_small_gap_without_later_absorption(rotation):
    img, seg, expected = _small_gap(rotation)
    assert 6 < seg.shapes[1].vis.area < 60
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert count > 0
    assert np.all(new.rid[expected] == 1)
    assert new.shapes[1].detail_owner
    assert 1 not in rescue.absorbable_ids(new, img.alpha.shape, img.scale)
    _assert_partition(new)


def test_two_small_solid_cores_are_still_ambiguous():
    rid = np.zeros((80, 120), np.int32)
    rid[35:41, 15:21], rid[35:41, 43:49] = 1, 2
    ink = rid > 0
    ink[37:39, 21:43] = True
    rgb = np.where(ink[..., None], DARK, CREAM).astype(np.uint8)
    img, seg = _scene(rid, rgb, [CREAM, DARK, DARK])
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


def test_small_fragment_without_a_solid_core_is_not_promoted():
    rid = np.zeros((80, 120), np.int32)
    rid[39:41, 15:35] = 1
    ink = rid > 0
    ink[39:41, 35:45] = True
    rgb = np.where(ink[..., None], DARK, CREAM).astype(np.uint8)
    img, seg = _scene(rid, rgb, [CREAM, DARK])
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


def test_safe_part_of_a_tip_preserves_a_tiny_donor_lobe(monkeypatch):
    rid = np.ones((60, 100), np.int32)
    rid[10:35, 10:40] = 0
    rid[20:23, 40:46] = 0
    rid[19:24, 46:49] = 0  # 15px lobe connected through the 3px-high neck
    proposed = np.zeros(rid.shape, bool)
    proposed[18:25, 45] = True
    source = rid.copy()
    source[proposed] = 1
    rgb = np.where((source == 0)[..., None], CREAM, DARK).astype(np.uint8)
    img, seg = _scene(rid, rgb, [CREAM, DARK])
    img.scale, img.orig_size = 2., (50, 30)
    monkeypatch.setattr(rescue, "find", lambda *args, **kwargs: ([(DARK, proposed)], set()))
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert 0 < count < np.count_nonzero(proposed & (rid == 0))
    assert ndi.label(new.rid == 0)[1] == 1, "retain the original donor connection"
    assert np.all(new.rid[19:24, 46:49] == 0), "never discard the tiny donor lobe"
    assert ndi.label(new.rid == 1)[1] == 1
    _assert_partition(new)


def test_whole_foreign_object_is_not_erased_even_if_tiny(monkeypatch):
    rid = np.ones((60, 100), np.int32)
    rid[28:31, 48:51] = 0
    proposed = np.zeros(rid.shape, bool)
    proposed[27:32, 47:52] = True
    rgb = np.full((*rid.shape, 3), DARK, np.uint8)
    img, seg = _scene(rid, rgb, [CREAM, DARK])
    monkeypatch.setattr(rescue, "find", lambda *args, **kwargs: ([(DARK, proposed)], set()))
    new, count = rescue.reconnect_tips(img, seg, load("smooth"))
    assert new is seg and count == 0


def test_promoted_small_gap_is_traced_as_its_own_region(tmp_path, monkeypatch):
    img, seg, expected = _small_gap()
    path = tmp_path / "small-gap.png"
    Image.fromarray(img.rgb).save(path)
    monkeypatch.setattr(pipeline, "segment", lambda image, cfg: seg)
    cfg = load("smooth", denoise=0, gradients=False, complete_hidden=False, strokes=False)
    result = pipeline.run(path, cfg)
    owner = int(result.seg.rid[expected][0])
    assert result.seg.shapes[owner].detail_owner
    assert result.stats["rescued"] == 0 and result.stats["absorbed"] == 0
    assert np.all(result.seg.rid[expected] == owner)
