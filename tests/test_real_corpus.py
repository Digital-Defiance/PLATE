"""Existence + no-crash guard for the generated real-artwork corpus.

This is a DIAGNOSTIC corpus, not a gate: the only assertions here are that the
images exist as readable RGBA PNGs and that ``plate bench samples/real`` runs to
completion without raising. There are deliberately NO quality thresholds, SSIM
floors, or object-count checks on these images.
"""
from pathlib import Path

from PIL import Image

from plate.cli import main

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "samples" / "real"

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
