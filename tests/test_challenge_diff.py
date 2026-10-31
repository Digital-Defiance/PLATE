"""Deterministic tests for the per-object challenge diagnostic.

Synthetic expected-vs-actual SVG pairs exercise each classification category.
Assertions are on categories, booleans and rounded values only (no fragile raw
float comparisons).
"""
import pytest

from plate.raster import have_renderer

from challenge_diff import diff_target
from challenges import TargetMismatch, assert_target

pytestmark = pytest.mark.skipif(
    not have_renderer(), reason="diagnostic masks require the render extra and libcairo")


def _svg(body, width=100, height=100):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}">{body}</svg>')


# A two-object scene: a disc with a covering rect to its right.
DISC = '<circle id="disc" cx="40" cy="50" r="25" fill="red"/>'
COVER = '<rect id="cover" x="60" y="10" width="30" height="80" fill="blue"/>'
TARGET = _svg(DISC + COVER)


def _categories(diff):
    return {k: diff.to_dict()[k] for k in
            ("missing", "extra", "split", "merged")}


def test_self_identical_is_all_matched():
    diff = diff_target(TARGET, TARGET)
    d = diff.to_dict()
    assert d["expected_count"] == 2
    assert d["actual_count"] == 2
    assert len(d["matched"]) == 2
    assert d["missing"] == []
    assert d["extra"] == []
    assert d["split"] == []
    assert d["merged"] == []
    assert all(m["silhouette_ok"] and m["topology_ok"]
               and m["primitive_ok"] and m["fill_ok"] and m["stroke_ok"]
               for m in d["matched"])
    assert all(p["ok"] for p in d["paint_order"])


def test_missing_object():
    actual = _svg(COVER)  # drops the disc
    d = diff_target(actual, TARGET).to_dict()
    assert "disc" in d["missing"]
    assert d["actual_count"] == 1
    assert d["expected_count"] == 2


def test_extra_object():
    extra = '<rect id="spare" x="5" y="5" width="8" height="8" fill="green"/>'
    actual = _svg(DISC + COVER + extra)
    d = diff_target(actual, TARGET).to_dict()
    assert "spare" in d["extra"]
    assert d["actual_count"] == 3


def test_split_object():
    # One expected disc rendered as two overlapping actual half-discs.
    halves = ('<path id="left" d="M40 25A25 25 0 0 0 40 75Z" fill="red"/>'
              '<path id="right" d="M40 25A25 25 0 0 1 40 75Z" fill="red"/>')
    actual = _svg(halves + COVER)
    d = diff_target(actual, TARGET).to_dict()
    split_expected = {s["expected"] for s in d["split"]}
    assert "disc" in split_expected
    disc_split = next(s for s in d["split"] if s["expected"] == "disc")
    assert len(disc_split["actual"]) >= 2


# A back rectangle spanning the canvas with a distinct smaller front
# rectangle sitting on top of it. The two overlap spatially (IoU ~0.25) but are
# genuinely distinct objects -- a self-diff must match both 1:1 with no
# split/merge noise.
BACK = '<rect id="back" x="0" y="0" width="100" height="100" fill="blue"/>'
FRONT = '<rect id="front" x="20" y="20" width="50" height="50" fill="red"/>'
OVERLAP = _svg(BACK + FRONT)


def test_overlapping_objects_self_diff_has_no_split_or_merge():
    # Regression: a distinct front object overlapping a back object must not be
    # miscounted as a split of (or merge with) the back object.
    d = diff_target(OVERLAP, OVERLAP).to_dict()
    assert len(d["matched"]) == 2
    assert d["split"] == []
    assert d["merged"] == []
    assert d["missing"] == []
    assert d["extra"] == []


def test_genuine_merge_still_detected():
    # Two distinct, disjoint target squares collapsed into one wide actual rect:
    # the actual subsumes both expected objects -> a genuine merge.
    target = _svg('<rect id="a" x="20" y="40" width="28" height="20" fill="red"/>'
                  '<rect id="b" x="52" y="40" width="28" height="20" fill="red"/>')
    actual = _svg('<rect id="wide" x="20" y="40" width="60" height="20" fill="red"/>')
    d = diff_target(actual, target).to_dict()
    assert len(d["merged"]) == 1
    merged = d["merged"][0]
    assert set(merged["expected"]) == {"a", "b"}
    assert merged["actual"] == "wide"
    assert d["split"] == []


def test_topology_difference():
    # evenodd plate with a hole; actual adds a stray island inside the hole.
    plate = ('<path id="plate" d="M10 10H90V90H10Z M30 30H70V70H30Z" '
             'fill="blue" fill-rule="evenodd"/>')
    target = _svg(plate)
    actual = _svg(plate.replace('M30 30H70V70H30Z',
                                'M30 30H70V70H30Z M40 40H42V42H40Z'))
    d = diff_target(actual, target).to_dict()
    matched = {m["expected"]: m for m in d["matched"]}
    assert "plate" in matched
    assert matched["plate"]["topology_ok"] is False
    assert matched["plate"]["expected_topology"] != matched["plate"]["actual_topology"]


def test_primitive_and_fill_mismatch():
    # disc emitted as a path instead of a circle.
    actual = _svg('<path id="disc" d="M40 25A25 25 0 1 0 40 75A25 25 0 1 0 40 25Z" '
                  'fill="red"/>' + COVER)
    d = diff_target(actual, TARGET).to_dict()
    matched = {m["expected"]: m for m in d["matched"]}
    assert matched["disc"]["primitive_ok"] is False
    assert matched["disc"]["expected_primitive"] == "circle"
    assert matched["disc"]["actual_primitive"] == "path"


def test_stroke_vs_fill():
    # An outlined stroke that was emitted as a filled rectangle.
    target = _svg('<path id="line" d="M20 50H80" fill="none" '
                  'stroke="red" stroke-width="10"/>')
    actual = _svg('<path id="line" d="M20 45H80V55H20Z" fill="red"/>')
    d = diff_target(actual, target).to_dict()
    matched = {m["expected"]: m for m in d["matched"]}
    assert matched["line"]["stroke_ok"] is False
    assert "stroke" in matched["line"]["stroke_detail"]


def test_reversed_paint_order():
    reversed_svg = _svg(COVER + DISC)  # cover painted first now
    d = diff_target(reversed_svg, TARGET).to_dict()
    reversed_pairs = [p for p in d["paint_order"] if not p["ok"]]
    assert reversed_pairs, "expected a reversed paint-order finding"
    assert any(p["note"] == "reversed" for p in reversed_pairs)


def test_assert_target_enriches_mismatch():
    actual = _svg(COVER)  # missing the disc -> count mismatch
    with pytest.raises(TargetMismatch) as excinfo:
        assert_target(actual, TARGET)
    message = str(excinfo.value)
    # Original first-line substring preserved for match= tests / xfail wiring.
    assert "object count" in message
    # Enriched diff summary is appended.
    assert "missing" in message
    from challenge_diff import TargetDiff
    assert isinstance(excinfo.value.diff, TargetDiff)
    assert "disc" in excinfo.value.diff_dict["missing"]
