"""Property 1: Thin shell / source of truth (browser-web-page spec, task 1.7).

The browser shell adds no conversion logic: the SVG it returns must be exactly
the SVG the CLI/engine produces for the same image bytes and the same resolved
config. That is, for every supported image and every valid preset+lever config:

    convert_bytes(bytes(image), name, overrides)["svg"]
        == pipeline.run(path(image), build_config(overrides)).svg

**Validates: Requirements 1.1, 1.2, 1.3**

The oracle is the engine itself, used directly -- we write the same bytes to a
path and call the unchanged ``pipeline.run`` with the config ``build_config``
resolves, then compare byte-for-byte against ``convert_bytes(...)["svg"]``. We do
NOT re-implement ``convert_bytes``; the glue is exercised exactly as the worker
calls it. A drift between the shell and the CLI (any extra transform in the
glue) would break the equality and fail the property.

Inputs are both shipped ``samples/*.png`` (real engine inputs spanning flat art,
overlaps, alpha, gradients and a face) and small generated synthetic PNGs, paired
with configs drawn from valid preset + lever combinations. ``vlm_url`` is kept
empty throughout so the core path stays offline and deterministic (Property 1 is
about the no-network core conversion, not the optional naming call).
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

from plate import pipeline, web
from plate.config import PRESETS
from plate.web import LEVER_MAP, NUMERIC_RANGES, build_config, convert_bytes

# Shipped sample PNGs (AGENTS.md / make_samples.py): flat badge, an overlap scene,
# an alpha donut, a 3-way stack, a shaded gradient, a face and a UI card -- real
# engine inputs that exercise segmentation, occlusion, gradients and strokes.
SAMPLE_NAMES = [
    "badge.png",
    "overlap.png",
    "donut_alpha.png",
    "stack3.png",
    "shaded.png",
    "face.png",
    "ui_card.png",
]

# Config fields the generated override maps may touch. vlm_url / vlm_model are
# deliberately excluded so the core conversion path performs no network I/O.
_BOOL_FIELDS = ("snap_primitives", "strokes", "gradients", "remove_background")

# UI aliases grouped by the Config field they resolve to (either spelling is valid
# over the worker boundary), mirroring the glue's documented LEVER_MAP contract.
_FIELD_TO_ALIASES: dict[str, list[str]] = {}
for _alias, _field in LEVER_MAP.items():
    _FIELD_TO_ALIASES.setdefault(_field, []).append(_alias)


def _cli_svg(data: bytes, filename: str, overrides: dict | None) -> str:
    """Oracle: run the UNCHANGED engine exactly as the CLI would for these bytes and
    this resolved config. Write the bytes to a path (as the CLI reads a file) and call
    ``pipeline.run(path, build_config(overrides))`` -- the same config resolution the
    glue uses, but reached independently of ``convert_bytes``'s body."""
    ext = (Path(filename).suffix or ".png").lstrip(".").lower() or "png"
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 - reopened by path, closed in finally
        prefix="plate-cli-oracle-", suffix=f".{ext}", delete=False
    )
    try:
        tmp.write(data)
        tmp.close()
        return pipeline.run(Path(tmp.name), build_config(overrides)).svg
    finally:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)


def _assert_equivalent(data: bytes, filename: str, overrides: dict | None) -> None:
    """The Property-1 contract: the shell's SVG is byte-identical to the engine's."""
    out = convert_bytes(data, filename, overrides)
    assert set(out) == {"svg", "stats", "layers", "warnings"}
    assert out["svg"] == _cli_svg(data, filename, overrides)


# ---------------------------------------------------------------------------
# Generators: valid override maps + small synthetic PNGs
# ---------------------------------------------------------------------------
_presets = st.sampled_from(sorted(PRESETS) + [None])


@st.composite
def _valid_overrides(draw):
    """A valid UI override map: an optional preset plus a random subset of valid
    levers, each spelled with a randomly chosen (camelCase or snake_case) alias.
    Numeric levers are drawn WITHIN their engine-sane range so the resolved config
    is representative (clamping itself is covered by the Property-3 config test);
    vlm_url stays empty so the core path is offline."""
    overrides: dict[str, object] = {}

    preset = draw(_presets)
    if preset is not None:
        overrides["preset"] = preset

    for field, (lo, hi) in NUMERIC_RANGES.items():
        if draw(st.booleans()):
            alias = draw(st.sampled_from(_FIELD_TO_ALIASES[field]))
            if field in ("max_colors", "work_size"):
                overrides[alias] = draw(st.integers(min_value=int(lo), max_value=int(hi)))
            else:
                overrides[alias] = draw(
                    st.floats(min_value=lo, max_value=hi, allow_nan=False, allow_infinity=False)
                )

    for field in _BOOL_FIELDS:
        if draw(st.booleans()):
            alias = draw(st.sampled_from(_FIELD_TO_ALIASES[field]))
            overrides[alias] = draw(st.booleans())

    return overrides


def _encode_png(arr: np.ndarray) -> bytes:
    mode = "RGBA" if arr.shape[2] == 4 else "RGB"
    buf = io.BytesIO()
    Image.fromarray(arr, mode).save(buf, format="PNG")
    return buf.getvalue()


@st.composite
def _synthetic_png(draw):
    """A small flat-colour PNG with a couple of blocks and an optional alpha hole --
    enough structure to drive segmentation/occlusion while staying fast to convert."""
    h = draw(st.integers(min_value=24, max_value=56))
    w = draw(st.integers(min_value=24, max_value=56))
    channels = draw(st.sampled_from([3, 4]))
    bg = draw(st.integers(min_value=0, max_value=255))
    arr = np.full((h, w, channels), bg, dtype=np.uint8)
    if channels == 4:
        arr[..., 3] = 255
    # a foreground block in a different flat colour
    fg = draw(st.integers(min_value=0, max_value=255))
    y0, x0 = draw(st.integers(min_value=0, max_value=h // 2)), draw(st.integers(min_value=0, max_value=w // 2))
    y1, x1 = draw(st.integers(min_value=y0 + 4, max_value=h)), draw(st.integers(min_value=x0 + 4, max_value=w))
    arr[y0:y1, x0:x1, :3] = fg
    # optional transparent hole (only meaningful with an alpha channel)
    if channels == 4 and draw(st.booleans()):
        arr[y0 + 1 : max(y0 + 2, (y0 + y1) // 2), x0 + 1 : max(x0 + 2, (x0 + x1) // 2), 3] = 0
    return _encode_png(arr), "synthetic.png"


# ---------------------------------------------------------------------------
# Example-based anchors on the shipped samples (real engine inputs)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_default_config_matches_cli_on_samples(samples, name):
    """With no overrides, the shell's SVG equals the CLI's default-config SVG."""
    data = (samples / name).read_bytes()
    _assert_equivalent(data, name, None)


@pytest.mark.parametrize("name", SAMPLE_NAMES)
@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_each_preset_matches_cli_on_a_sample(samples, name, preset):
    """Every shipped preset resolves and converts identically through shell and CLI."""
    data = (samples / name).read_bytes()
    _assert_equivalent(data, name, {"preset": preset})


def test_lever_overrides_match_cli(samples):
    """A concrete preset + mixed-lever override map stays byte-identical to the CLI."""
    data = (samples / "overlap.png").read_bytes()
    overrides = {
        "preset": "logo",
        "maxColors": 6,
        "simplify": 1.2,
        "snapPrimitives": False,
        "removeBackground": True,
    }
    _assert_equivalent(data, "overlap.png", overrides)


# ---------------------------------------------------------------------------
# Property 1: equivalence across valid configs on the shipped samples
# ---------------------------------------------------------------------------
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(name=st.sampled_from(SAMPLE_NAMES), overrides=_valid_overrides())
def test_equivalence_on_samples_over_valid_configs(samples, name, overrides):
    """**Property 1** on real engine inputs: for a shipped sample and any valid
    preset+lever config, ``convert_bytes(...).svg == pipeline.run(path, build_config(overrides)).svg``.

    **Validates: Requirements 1.1, 1.2, 1.3**
    """
    data = (samples / name).read_bytes()
    _assert_equivalent(data, name, overrides)


# ---------------------------------------------------------------------------
# Property 1: equivalence across valid configs on generated synthetic images
# ---------------------------------------------------------------------------
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(image=_synthetic_png(), overrides=_valid_overrides())
def test_equivalence_on_synthetic_over_valid_configs(image, overrides):
    """**Property 1** on randomized synthetic inputs: the shell's SVG is byte-identical
    to the engine's for the same bytes and resolved config.

    **Validates: Requirements 1.1, 1.2, 1.3**
    """
    data, filename = image
    _assert_equivalent(data, filename, overrides)
