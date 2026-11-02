"""Bake-off `smoothness`: how much more the render's outlines wiggle than the reference's
(report-only metric). SSIM/edge-F1 cannot see wobble, so this gives it a number."""
import cv2
import numpy as np

from plate.bakeoff import score

BG, INK = (20, 40, 44), (240, 240, 230)


def _disc(wavy: float = 0.0, freq: int = 18) -> np.ndarray:
    im = np.zeros((200, 200, 3), np.uint8)
    im[:] = BG
    th = np.linspace(0, 2 * np.pi, 400)
    r = 70 + (wavy * np.sin(th * freq) if wavy else np.zeros_like(th))
    pts = np.stack([100 + r * np.cos(th), 100 + r * np.sin(th)], 1).astype(np.int32)
    cv2.fillPoly(im, [pts], INK)
    return im


def test_identical_is_perfectly_smooth():
    s = _disc()
    assert score.smoothness(s, s) == dict(smoothness=1.0, wobble=0.0)


def test_wavy_render_scores_lower_than_smooth_reference():
    smooth, wavy = _disc(0.0), _disc(2.5)
    r = score.smoothness(wavy, smooth)
    assert r["wobble"] > 0.0 and r["smoothness"] < 0.95


def test_smoother_render_is_not_penalised():
    """A clean render of a wavy source is not punished - wobble is one-sided excess."""
    smooth, wavy = _disc(0.0), _disc(2.5)
    assert score.smoothness(smooth, wavy) == dict(smoothness=1.0, wobble=0.0)


def test_more_waviness_scores_lower():
    smooth = _disc(0.0)
    mild = score.smoothness(_disc(1.2), smooth)["smoothness"]
    harsh = score.smoothness(_disc(3.0), smooth)["smoothness"]
    assert harsh < mild < 1.0


def test_antialias_blur_does_not_count():
    """A soft (blurred) reference and a crisp render of the same disc agree (blends excluded)."""
    crisp = _disc()
    soft = cv2.GaussianBlur(crisp, (0, 0), 1.0)
    assert score.smoothness(crisp, soft)["smoothness"] >= 0.97


def test_metric_is_report_only():
    assert "smoothness" not in score.DEFAULT_WEIGHTS
    assert "wobble" not in score.DEFAULT_WEIGHTS
