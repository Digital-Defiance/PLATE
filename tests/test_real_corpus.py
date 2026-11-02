"""Existence + no-crash guard for the generated real-artwork corpus.

This is a DIAGNOSTIC corpus, not a gate: the only assertions here are that the
images exist as readable RGBA PNGs and that ``plate bench samples/real`` runs to
completion without raising. There are deliberately NO quality thresholds, SSIM
floors, or object-count checks on these images.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from plate import metrics, pipeline
from plate.cli import main
from plate.config import Config, load
from plate.imageio import noise_fraction, open_rgba
from plate.raster import have_renderer

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "samples" / "real"
CHALLENGES = ROOT / "samples" / "challenges"


def _work_planes(path: Path):
    """Reproduce load_image's resize (longest side <= work_size, LANCZOS) so the
    noise estimators are measured on exactly the pixels segmentation sees."""
    cfg = Config()
    im = open_rgba(path)
    w, h = im.size
    longest = max(w, h)
    if longest > cfg.work_size:
        scale = cfg.work_size / longest
        im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    arr = np.asarray(im)
    return arr[..., :3].copy(), arr[..., 3].copy()

EXPECTED = {
    "real_sunset_gradient",
    "real_radial_orb",
    "real_soft_shadow_card",
    "real_sensor_noise_badge",
    "real_jpeg_artifacts",
    "real_thin_strokes_type",
    "real_busy_palette",
    "real_near_duplicate_swatches",
    "real_panorama_banner",
    "real_tall_poster",
    "real_translucent_overlaps",
    "real_textured_bg",
    "real_glow_logo",
    "real_mixed_mess",
}


def test_real_corpus_images_exist():
    assert CORPUS.is_dir(), "samples/real/ is missing (run scripts/make_real_corpus.py)"
    present = {p.stem for p in CORPUS.glob("real_*.png")}
    assert EXPECTED <= present, f"missing generated images: {sorted(EXPECTED - present)}"
    for stem in EXPECTED:
        with Image.open(CORPUS / f"{stem}.png") as img:
            assert img.mode == "RGBA", f"{stem}.png is not RGBA"
            assert img.size[0] > 0 and img.size[1] > 0


def test_bench_runs_clean_on_real_corpus(tmp_path):
    rc = main(["bench", "samples/real", "-o", str(tmp_path)])
    assert rc == 0


# ---------------------------------------------------------------------------
# R5 (engine-completion Task 8) — heavy sensor-noise / JPEG-artifact collapse.
#
# TERMINAL STATE (b): DOCUMENTED LIMIT, measured. Do NOT lower the global
# noise_fraction gate (0.04) to "catch" these collapses — the pins below prove
# that any global trigger low enough to catch them also re-denoises clean
# shipped art, breaking the 24 shipped SVGs' byte-identity (GC-4). The
# `noise_fraction` overlap first measured in the JPEG investigation (clean
# shipped art scoring HIGHER than the noisy inputs) is the standing precedent.
#
# Measured 2026-11 at work_size=1536 (see .kiro/specs/engine-completion):
#   real_sensor_noise_badge  noise_fraction 0.8703  SSIM ~0.352  (gate ALREADY fires)
#   real_jpeg_artifacts      noise_fraction 0.0352  SSIM ~0.554, 269 objects
#   clean noisy_badge.png    noise_fraction 0.0781  (shipped sample)
#   logo_orbit_wordmark.png  noise_fraction 0.0399  (shipped SVG, in the overlap band)
# ---------------------------------------------------------------------------


def test_sensor_noise_badge_collapse_is_not_a_denoise_trigger_gap():
    """real_sensor_noise_badge measures noise_fraction ~0.87 — far above the 0.04 auto
    gate — so the global branch ALREADY fires at full strength (two bilateral passes).
    The collapse is therefore not a missed trigger: heavy uniform noise has destroyed the
    flat-colour structure the classical palette needs, and no stronger denoise recovers it.
    This pins that the trigger already fires, so the failure is information loss, state (b)."""
    rgb, alpha = _work_planes(CORPUS / "real_sensor_noise_badge.png")
    nf = noise_fraction(rgb, alpha)
    assert nf > 0.5, nf                                   # measured ~0.8703
    assert nf > 0.04, (nf, "the global auto-denoise gate already fires on this input")


@pytest.mark.skipif(not have_renderer(), reason="SSIM collapse needs the render extra")
def test_sensor_noise_badge_stays_collapsed_even_at_maximum_denoise():
    """Stronger denoise does not rescue the sensor-noise badge: auto (level 2) renders at
    SSIM ~0.352 and a heavy level-6 pass stays within a hair of it (measured 0.3519 vs
    0.3532, a swing of <0.01 that is not a structural recovery). Pins the measured collapse
    floor so this is never re-chased as a denoise-strength bug."""
    path = CORPUS / "real_sensor_noise_badge.png"
    rgba = np.asarray(open_rgba(path))
    auto = metrics.fidelity(pipeline.run(path, load(denoise=-1)).svg, rgba)["ssim"]
    heavy = metrics.fidelity(pipeline.run(path, load(denoise=6)).svg, rgba)["ssim"]
    assert auto < 0.40, auto                              # measured ~0.3519
    assert heavy < 0.40, heavy                            # measured ~0.3532
    assert abs(heavy - auto) < 0.03, (auto, heavy)        # no structural recovery from denoise


def test_jpeg_artifact_collapse_sits_below_the_gate_and_overlaps_shipped_art():
    """real_jpeg_artifacts measures noise_fraction ~0.0352, BELOW the 0.04 auto gate, so it
    is not auto-denoised. The documented limit: any global gate low enough to catch it
    (threshold <= its noise_fraction) also fires on clean shipped art. logo_orbit_wordmark
    (a shipped SVG) measures ~0.0399 — inside the (jpeg_nf, 0.04] band — so a lowered gate
    newly denoises it. This is the `noise_fraction` overlap precedent, pinned."""
    jpeg_rgb, jpeg_alpha = _work_planes(CORPUS / "real_jpeg_artifacts.png")
    jpeg_nf = noise_fraction(jpeg_rgb, jpeg_alpha)
    assert jpeg_nf < 0.04, jpeg_nf                        # below the gate: not auto-denoised

    orbit_rgb, orbit_alpha = _work_planes(CHALLENGES / "logo_orbit_wordmark.png")
    orbit_nf = noise_fraction(orbit_rgb, orbit_alpha)
    # A gate low enough to catch the JPEG collapse (<= jpeg_nf) also catches this shipped SVG.
    assert jpeg_nf < orbit_nf <= 0.04, (jpeg_nf, orbit_nf)

    badge_rgb, badge_alpha = _work_planes(ROOT / "samples" / "noisy_badge.png")
    assert noise_fraction(badge_rgb, badge_alpha) > jpeg_nf, "clean noisy_badge overlaps too"


def test_lowering_the_gate_to_catch_jpeg_artifacts_changes_a_shipped_svg():
    """The byte-identity proof behind the overlap pin: re-denoising logo_orbit_wordmark —
    which a gate lowered to catch real_jpeg_artifacts would newly do — produces a different
    SVG. So no global noise trigger can catch the JPEG collapse without breaking the 24
    shipped SVGs (GC-4). This is why state (b) is the terminal state, not (a)."""
    src = CHALLENGES / "logo_orbit_wordmark.png"
    shipped = pipeline.run(src, load(denoise=0)).svg       # current output: not denoised
    redenoised = pipeline.run(src, load(denoise=1)).svg    # what a lowered gate would produce
    assert shipped != redenoised, "re-denoising must perturb the shipped SVG (overlap proof)"
