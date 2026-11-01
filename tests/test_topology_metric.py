"""Bake-off `topology`: same solid pieces in render and reference (report-only metric)."""
import numpy as np

from plate.bakeoff import score

BG, INK = (20, 40, 44), (240, 240, 230)


def _scene(dots):
    im = np.zeros((120, 160, 3), np.uint8)
    im[:] = BG
    im[30:90, 20:70] = INK                     # a block
    for x, y in dots:
        im[y - 2:y + 3, x - 2:x + 3] = INK     # 5x5 dots
    return im


def test_identical_is_perfect():
    ref = _scene([(110, 40), (130, 80)])
    assert score.topology(ref, ref) == dict(topology=1.0, topo_extra=0, topo_missing=0)


def test_dropped_dot_is_missing():
    ref = _scene([(110, 40), (130, 80)])
    t = score.topology(_scene([(110, 40)]), ref)
    assert (t["topo_extra"], t["topo_missing"]) == (0, 1)
    (p,) = score.topology_pieces(_scene([(110, 40)]), ref)
    assert p["kind"] == "missing" and abs(p["at"][0] - 130) < 2 and abs(p["at"][1] - 80) < 2


def test_speck_and_split_are_extra():
    ref = _scene([(110, 40)])
    ren = _scene([(110, 40), (140, 100)])      # a stray speck
    ren[60:63, 20:70] = BG                     # and the block cut in two
    t = score.topology(ren, ref)
    assert t["topo_extra"] >= 2 and t["topo_missing"] == 0, t   # speck + split (+ the bg it splits into)


def test_antialias_blends_do_not_count():
    """A soft (blurred) reference and a crisp render of the same scene agree."""
    import cv2
    crisp = _scene([(110, 40), (130, 80)])
    soft = cv2.GaussianBlur(crisp, (0, 0), 1.0)
    assert score.topology(crisp, soft)["topology"] == 1.0


def test_metric_does_not_change_composite():
    assert "topology" not in score.DEFAULT_WEIGHTS
