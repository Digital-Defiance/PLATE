"""Property 4: Warning matches behaviour (browser-web-page spec, task 1.4).

The UI warning must never lie: ``plate.web.check_noise(data, filename)["noisy"]``
must agree with whether the *engine's* ``imageio.load_image`` auto-denoise would
actually fire for the same input. That is:

    check_noise(image).noisy  <=>  (noise_fraction(image) > 0.04
                                    OR interior_noise_fraction(image) > interior_noise)

where the fractions are measured on exactly the working array ``load_image``
derives (same decode, same work_size LANCZOS downscale, no upscale) under the
default ``Config``.

**Validates: Requirements 4.2**

The oracle here is recomputed straight from the engine's own decoder
(``open_rgba``), the engine's own resize branch (the ``longest > work_size``
LANCZOS downscale ``load_image`` uses when ``upscale == 1.0``), and the engine's
own estimators + trigger constant -- NOT a copy of ``check_noise``'s body -- so a
drift between the warning and the real engine behaviour would fail the property.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image

from plate import web
from plate.config import Config
from plate.imageio import (
    _is_jpeg,
    interior_noise_fraction,
    noise_fraction,
    open_rgba,
)

# The synthetic sample PNGs that ship with the suite (AGENTS.md / make_samples.py),
# spanning clean flat art, an explicitly noisy badge, a face, a shaded gradient and
# an overlap scene. These exercise both sides of the trigger on real engine inputs.
SAMPLE_NAMES = [
    "badge.png",
    "noisy_badge.png",
    "face.png",
    "shaded.png",
    "overlap.png",
    "stack3.png",
    "donut_alpha.png",
    "ui_card.png",
]


def _engine_working_rgba(path):
    """Reproduce the working ``rgb``/``alpha`` arrays ``imageio.load_image`` feeds to
    its auto-denoise test under the default Config (``upscale == 1.0``): open via the
    engine decoder, then apply the engine's own ``longest > work_size`` LANCZOS
    downscale (and no upscale, matching the default lever)."""
    cfg = Config()
    im = open_rgba(path)
    w, h = im.size
    longest = max(w, h)
    if longest > cfg.work_size:
        scale = cfg.work_size / longest
        im = im.resize(
            (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
        )
    arr = np.asarray(im)
    return arr[..., :3].copy(), arr[..., 3].copy()


def _engine_would_denoise(path) -> bool:
    """The exact auto-denoise condition from ``imageio.load_image`` (the ``level < 0``
    branch), evaluated on the engine's working array. This is the ground truth the
    UI warning must mirror."""
    cfg = Config()
    rgb, alpha = _engine_working_rgba(path)
    return bool(
        noise_fraction(rgb, alpha) > 0.04
        or interior_noise_fraction(rgb, alpha) > cfg.interior_noise
    )


# ---------------------------------------------------------------------------
# Example-based coverage of the real sample images (both sides of the trigger)
# ---------------------------------------------------------------------------
def test_noisy_sample_warns_and_matches_engine(samples):
    """The explicitly noisy sample must be flagged, and the flag must match the engine."""
    path = samples / "noisy_badge.png"
    data = path.read_bytes()
    report = web.check_noise(data, "noisy_badge.png")
    assert "error" not in report
    assert report["noisy"] is True
    assert report["noisy"] == _engine_would_denoise(path)


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_check_noise_matches_engine_on_samples(samples, name):
    """For every shipped sample, the warning agrees with the engine's auto-denoise
    decision -- the warning never lies (never warns on art the engine treats as
    clean, never stays silent on art the engine would denoise)."""
    path = samples / name
    data = path.read_bytes()
    report = web.check_noise(data, name)
    assert "error" not in report, report
    assert report["noisy"] == _engine_would_denoise(path)
    # jpeg flag likewise mirrors the engine's format probe, not the extension.
    assert report["jpeg"] == _is_jpeg(path)


# ---------------------------------------------------------------------------
# Property: warning <=> engine trigger, across generated inputs
# ---------------------------------------------------------------------------
def _encode(arr: np.ndarray, fmt: str) -> bytes:
    """Encode an (H, W, 3|4) uint8 array to PNG or JPEG bytes."""
    mode = "RGBA" if arr.shape[2] == 4 else "RGB"
    im = Image.fromarray(arr, mode)
    buf = io.BytesIO()
    if fmt == "jpeg":
        im.convert("RGB").save(buf, format="JPEG", quality=20)
    else:
        im.save(buf, format="PNG")
    return buf.getvalue()


@st.composite
def _images(draw):
    """Generate small images spanning clean flat regions through heavy noise, so the
    property exercises both branches of the trigger and the boundary between them."""
    h = draw(st.integers(min_value=16, max_value=48))
    w = draw(st.integers(min_value=16, max_value=48))
    # A flat base colour with a couple of flat blocks (clean art), then an optional
    # dose of per-pixel noise whose strength is swept across the trigger boundary.
    base = draw(st.integers(min_value=0, max_value=255))
    arr = np.full((h, w, 3), base, dtype=np.uint8)
    # a second flat block to introduce genuine (clean) edges
    bh, bw = h // 2, w // 2
    block = draw(st.integers(min_value=0, max_value=255))
    arr[:bh, :bw] = block
    noise_sigma = draw(st.integers(min_value=0, max_value=60))
    if noise_sigma > 0:
        seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
        rng = np.random.default_rng(seed)
        noise = rng.normal(0.0, float(noise_sigma), size=arr.shape)
        arr = np.clip(arr.astype(np.float64) + noise, 0, 255).astype(np.uint8)
    fmt = draw(st.sampled_from(["png", "jpeg"]))
    return _encode(arr, fmt), f"generated.{'jpg' if fmt == 'jpeg' else 'png'}"


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(image=_images())
def test_warning_matches_engine_trigger(image):
    """Property 4: ``check_noise(...).noisy`` is true iff the engine's auto-denoise
    would fire on the same decoded+resized working array.

    **Validates: Requirements 4.2**
    """
    data, filename = image
    report = web.check_noise(data, filename)
    # Decode/resize must succeed for these well-formed generated images.
    assert "error" not in report, report

    # Oracle: recompute the engine's own auto-denoise condition from the same bytes
    # via a throwaway file the engine decoder can open (open_rgba / load_image read a
    # path), mirroring load_image exactly rather than re-running check_noise's body.
    # delete=False (as plate.web.check_noise does) so the engine decoder can reopen
    # the path by name; the finally removes it so no image persists.
    suffix = Path(filename).suffix or ".png"
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 - reopened by path, closed in finally
        prefix="plate-oracle-", suffix=suffix, delete=False
    )
    try:
        tmp.write(data)
        tmp.close()
        expected = _engine_would_denoise(Path(tmp.name))
    finally:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)

    assert report["noisy"] == expected
