"""Property tests for ``plate.web.build_config`` config fidelity.

**Property 3: Config fidelity**
**Validates: Requirements 6.3, 6.6**

For arbitrary valid override maps, ``build_config(overrides)`` must equal the
``Config`` the CLI would build for the equivalent ``--preset`` / ``--set`` flags,
i.e. ``load(preset).merged(**clamped_levers)``. Out-of-range numeric levers clamp
to the nearest bound; unknown preset / unknown lever keys raise a descriptive
error; LM Studio naming stays disabled unless ``vlmUrl`` is a non-empty,
non-whitespace string.

The test mirrors the real contract (it re-derives the expected ``Config`` from
``config.load`` / ``Config.merged`` and the glue's documented ranges) rather than
re-implementing ``build_config``'s internals.
"""
from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from plate.config import PRESETS, Config, load
from plate.web import (
    LEVER_MAP,
    NUMERIC_RANGES,
    ConfigError,
    build_config,
)

# ---- shared knowledge mirrored from the glue contract (not its implementation) ----

# Numeric levers that Config stores as int (so expected values must round + int()).
_INT_LEVERS = frozenset({"max_colors", "work_size"})

# Boolean toggle levers exposed by the UI.
_BOOL_FIELDS = ("snap_primitives", "strokes", "gradients", "remove_background")

# UI aliases grouped by the Config field they resolve to, so the generator can pick
# either the camelCase or snake_case spelling for the same lever.
_FIELD_TO_ALIASES: dict[str, list[str]] = {}
for _alias, _field in LEVER_MAP.items():
    _FIELD_TO_ALIASES.setdefault(_field, []).append(_alias)


def _expected_clamp(field: str, value: float) -> float | int:
    """Independent re-derivation of the glue's documented clamp rule."""
    lo, hi = NUMERIC_RANGES[field]
    clamped = min(max(float(value), lo), hi)
    return int(round(clamped)) if field in _INT_LEVERS else clamped


def _expected_config(preset, levers: dict) -> Config:
    """What the CLI would build for the equivalent --preset / --set flags."""
    return load(preset).merged(**levers)


# ---- generators -------------------------------------------------------------------

_presets = st.sampled_from(sorted(PRESETS) + [None])

# Finite floats (no NaN/inf) spanning well below and well above every range so the
# clamp-to-nearest-bound behaviour is exercised in both directions.
_numeric_value = st.floats(
    min_value=-1000.0, max_value=100000.0, allow_nan=False, allow_infinity=False
)


@st.composite
def _valid_overrides(draw):
    """A valid override map: optional preset + a random subset of valid levers, each
    spelled with a randomly chosen (camelCase or snake_case) alias, with numeric
    values that may fall outside the engine-sane range."""
    overrides: dict[str, object] = {}
    expected_levers: dict[str, object] = {}

    preset = draw(_presets)
    if preset is not None:
        overrides["preset"] = preset

    # numeric levers
    for field in NUMERIC_RANGES:
        if draw(st.booleans()):
            alias = draw(st.sampled_from(_FIELD_TO_ALIASES[field]))
            value = draw(_numeric_value)
            overrides[alias] = value
            expected_levers[field] = _expected_clamp(field, value)

    # boolean toggles
    for field in _BOOL_FIELDS:
        if draw(st.booleans()):
            alias = draw(st.sampled_from(_FIELD_TO_ALIASES[field]))
            value = draw(st.booleans())
            overrides[alias] = value
            expected_levers[field] = value

    # vlm model is a plain passthrough string
    if draw(st.booleans()):
        alias = draw(st.sampled_from(_FIELD_TO_ALIASES["vlm_model"]))
        value = draw(st.text(min_size=0, max_size=20))
        overrides[alias] = value
        expected_levers["vlm_model"] = value

    return preset, overrides, expected_levers


# ---- Property 3: for valid overrides, build_config == load(preset).merged(**levers) ----


@settings(max_examples=250)
@given(_valid_overrides())
def test_build_config_matches_cli_resolution(case):
    preset, overrides, expected_levers = case
    expected = _expected_config(preset, expected_levers)
    assert build_config(overrides) == expected


@settings(max_examples=150)
@given(
    preset=_presets,
    field=st.sampled_from(sorted(NUMERIC_RANGES)),
    value=_numeric_value,
)
def test_numeric_levers_clamp_to_nearest_bound(preset, field, value):
    lo, hi = NUMERIC_RANGES[field]
    alias = _FIELD_TO_ALIASES[field][0]
    overrides = {alias: value}
    if preset is not None:
        overrides["preset"] = preset

    cfg = build_config(overrides)
    got = getattr(cfg, field)

    expected = _expected_clamp(field, value)
    assert got == expected
    # And it genuinely lies within [lo, hi] (nearest-bound clamp, never rejected).
    assert lo <= got <= hi
    if value < lo:
        assert math.isclose(got, int(round(lo)) if field in _INT_LEVERS else lo)
    elif value > hi:
        assert math.isclose(got, int(round(hi)) if field in _INT_LEVERS else hi)


# ---- Property 3: for invalid keys, build_config raises ------------------------------


@given(
    bad_key=st.text(min_size=1, max_size=15).filter(
        lambda s: s not in LEVER_MAP and s != "preset"
    ),
    value=st.integers() | st.text(max_size=8) | st.booleans(),
)
def test_unknown_lever_key_raises(bad_key, value):
    with pytest.raises(ConfigError):
        build_config({bad_key: value})


@given(
    bad_preset=st.text(min_size=1, max_size=15).filter(lambda s: s not in PRESETS),
)
def test_unknown_preset_raises(bad_preset):
    with pytest.raises(ConfigError):
        build_config({"preset": bad_preset})


# ---- LM Studio naming stays disabled unless vlmUrl is non-empty non-whitespace ------

# Strings that are empty or whitespace-only -> naming stays off (engine default "").
_blank_urls = st.one_of(
    st.none(),
    st.just(""),
    st.text(alphabet=" \t\n\r", min_size=1, max_size=6),
)
# Non-empty non-whitespace strings -> naming enabled against that endpoint.
_real_urls = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")


@given(url=_blank_urls, alias=st.sampled_from(_FIELD_TO_ALIASES["vlm_url"]))
def test_blank_vlm_url_keeps_naming_disabled(url, alias):
    cfg = build_config({alias: url})
    # A blank/whitespace/None url leaves the engine's default empty endpoint.
    assert cfg.vlm_url == Config().vlm_url == ""


@given(url=_real_urls, alias=st.sampled_from(_FIELD_TO_ALIASES["vlm_url"]))
def test_nonempty_vlm_url_enables_naming(url, alias):
    cfg = build_config({alias: url})
    assert cfg.vlm_url == url
    assert cfg.vlm_url.strip() != ""


# ---- a couple of concrete examples anchoring the property -----------------------------


def test_example_preset_plus_clamped_lever():
    # work_size below the 64 floor clamps up; preset levers still apply.
    cfg = build_config({"preset": "logo", "workSize": 10, "maxColors": 5})
    assert cfg == load("logo").merged(work_size=64, max_colors=5)


def test_example_no_overrides_equals_defaults():
    assert build_config(None) == Config()
    assert build_config({}) == Config()


@pytest.mark.parametrize("value,expected", [(0, 1), (1, 1), (1.5, 1.5), (2, 2), (8, 2)])
def test_browser_detail_scale_is_bounded(value, expected):
    assert build_config({"upscale": value}).upscale == expected


def test_browser_research_force_recipe_matches_the_validated_cli_config():
    assert build_config({"preset": "smooth", "upscale": 2}) == load("smooth", upscale=2)
