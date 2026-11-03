"""CLI-equivalence unit tests for ``plate.web.convert_bytes`` (task 1.6).

Example-based (not Hypothesis) checks that the browser glue is a thin shell around
the unchanged engine: for every ``samples/*.png`` the returned SVG is byte-identical
to what ``pipeline.run`` produces for the same input and default config, the result
dict has exactly ``{svg, stats, layers, warnings}`` with stats mirroring
``Result.stats`` and the layer summary matching the SVG's top-level layers in
bottom->top paint order, and the documented error / warning edges behave as
specified.

Requirements: 1.2 (in-browser == CLI SVG), 1.4 (exact {svg,stats,layers,warnings}).
"""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from plate import pipeline, web
from plate.config import Config
from plate.imageio import ImageLoadError

INKSCAPE_LABEL = "{http://www.inkscape.org/namespaces/inkscape}label"

# The flat-art PNGs scripts/make_samples.py generates (the `samples` fixture
# regenerates them if missing). Each is a CLI-equivalence fixture.
SAMPLE_NAMES = [
    "overlap",
    "stack3",
    "badge",
    "face",
    "donut_alpha",
    "ui_card",
    "noisy_badge",
    "shaded",
]


def _top_level_layer_labels(svg: str) -> list[str]:
    """The inkscape:label of each direct ``<g>`` child of ``<svg>``, in document
    order. emit.write_svg makes every top-level node a layer: a top-level group
    keeps its own name, a standalone top-level shape is wrapped in a ``<g>`` named
    ``"{name} layer"``. Document order is the engine's bottom->top paint order."""
    root = ET.fromstring(svg)
    return [
        child.get(INKSCAPE_LABEL)
        for child in root
        if child.tag.endswith("}g")
    ]


# --- CLI-equivalence: byte-identical SVG for every sample ------------------


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_convert_bytes_svg_byte_identical_to_cli(samples, name):
    """convert_bytes(bytes, name).svg == pipeline.run(path).svg (byte-identical).

    This is the thin-shell contract: the glue adds no conversion logic, so the same
    image and (default) config give exactly the SVG the CLI path emits."""
    path = samples / f"{name}.png"
    out = web.convert_bytes(path.read_bytes(), path.name)
    cli = pipeline.run(path, Config())
    assert out["svg"] == cli.svg


# --- Result shape: exactly {svg, stats, layers, warnings} ------------------


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_convert_bytes_dict_has_exactly_four_keys(samples, name):
    path = samples / f"{name}.png"
    out = web.convert_bytes(path.read_bytes(), path.name)
    assert set(out) == {"svg", "stats", "layers", "warnings"}
    assert isinstance(out["svg"], str) and out["svg"].lstrip().startswith("<?xml")
    assert isinstance(out["stats"], dict) and out["stats"]
    assert isinstance(out["layers"], list) and out["layers"]
    assert isinstance(out["warnings"], list)


# Wall-clock timings differ run to run; they are mirrored by presence/type, not value.
_TIMING_KEYS = ("t_segment", "t_order", "t_trace", "t_total")


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_convert_bytes_stats_mirror_result_stats(samples, name):
    """The returned stats mirror Result.stats: same keys, and every non-timing
    (count/structure) value is identical to the CLI's. Timing keys vary per run,
    so they are only required to be present and non-negative numbers."""
    path = samples / f"{name}.png"
    out = web.convert_bytes(path.read_bytes(), path.name)
    cli = pipeline.run(path, Config())

    assert set(out["stats"]) == set(cli.stats)
    for key, value in cli.stats.items():
        if key in _TIMING_KEYS:
            assert isinstance(out["stats"][key], (int, float))
            assert out["stats"][key] >= 0
        else:
            assert out["stats"][key] == value


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_layer_summary_matches_svg_top_level_layers_in_paint_order(samples, name):
    """The layer summary lists the SVG's top-level layers in bottom->top order.

    A group layer's SVG label is its name; a standalone shape promoted to a layer
    is wrapped in a ``<g>`` labelled ``"{name} layer"``. The summary order must
    equal the document order of those top-level groups."""
    path = samples / f"{name}.png"
    out = web.convert_bytes(path.read_bytes(), path.name)
    layers = out["layers"]

    # order field is a dense 0..n-1 index in paint order.
    assert [layer["order"] for layer in layers] == list(range(len(layers)))

    expected_labels = [
        layer["name"] if layer["kind"] == "group" else f"{layer['name']} layer"
        for layer in layers
    ]
    assert _top_level_layer_labels(out["svg"]) == expected_labels


# --- Error edges: empty bytes, bad extension, corrupt image ----------------


def test_empty_bytes_raise_convert_error():
    with pytest.raises(web.ConvertError):
        web.convert_bytes(b"", "logo.png")


@pytest.mark.parametrize("filename", ["logo.gif", "logo.bmp", "logo.txt", "logo"])
def test_unrecognised_extension_raises_convert_error(filename):
    with pytest.raises(web.ConvertError):
        web.convert_bytes(b"\x89PNG\r\n\x1a\n some bytes", filename)


def test_extension_matching_is_case_insensitive(samples):
    """A recognised extension in any case is accepted and runs the engine (so a
    corrupt payload with a valid extension reaches engine validation, not the
    extension guard)."""
    png = (samples / "badge.png").read_bytes()
    out = web.convert_bytes(png, "BADGE.PNG")
    assert set(out) == {"svg", "stats", "layers", "warnings"}


def test_corrupt_image_propagates_engine_image_load_error():
    """A recognised extension but undecodable bytes must surface the engine's own
    ImageLoadError (engine validation is never bypassed), not a glue error."""
    with pytest.raises(ImageLoadError):
        web.convert_bytes(b"not a real png, just junk bytes", "broken.png")


# --- Beta JPEG warning: present iff check_noise reports jpeg AND noisy ------


def _encode(arr: np.ndarray, fmt: str, **save) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, fmt, **save)
    return buf.getvalue()


def _two_tone(noise_sigma: float, seed: int) -> np.ndarray:
    """A flat two-colour image, optionally with additive Gaussian noise."""
    rng = np.random.default_rng(seed)
    a = np.full((200, 200, 3), 180, np.uint8)
    a[:, :100] = (40, 80, 200)
    if noise_sigma:
        a = np.clip(a.astype(np.float32) + rng.normal(0, noise_sigma, a.shape), 0, 255)
    return a.astype(np.uint8)


def test_beta_jpeg_warning_present_when_jpeg_and_noisy():
    data = _encode(_two_tone(noise_sigma=25.0, seed=0), "JPEG", quality=30)
    noise = web.check_noise(data, "noisy.jpg")
    assert noise["jpeg"] and noise["noisy"]  # precondition for the warning
    out = web.convert_bytes(data, "noisy.jpg")
    assert web.BETA_JPEG_WARNING in out["warnings"]


def test_no_warning_for_clean_jpeg():
    """JPEG source but not noisy -> no beta warning (iff, not just if)."""
    data = _encode(_two_tone(noise_sigma=0.0, seed=1), "JPEG", quality=98)
    noise = web.check_noise(data, "clean.jpg")
    assert noise["jpeg"] and not noise["noisy"]
    out = web.convert_bytes(data, "clean.jpg")
    assert web.BETA_JPEG_WARNING not in out["warnings"]


def test_no_warning_for_noisy_png():
    """Noisy but not a JPEG source -> no beta warning (iff, not just if)."""
    data = _encode(_two_tone(noise_sigma=30.0, seed=2), "PNG")
    noise = web.check_noise(data, "noisy.png")
    assert not noise["jpeg"] and noise["noisy"]
    out = web.convert_bytes(data, "noisy.png")
    assert web.BETA_JPEG_WARNING not in out["warnings"]


def test_clean_png_samples_have_no_warnings(samples):
    """The synthetic flat-art PNG samples are clean PNGs, so none warn."""
    for name in ("badge", "overlap", "shaded"):
        path = samples / f"{name}.png"
        out = web.convert_bytes(path.read_bytes(), path.name)
        assert out["warnings"] == []
