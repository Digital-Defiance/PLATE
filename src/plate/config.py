"""Every quality lever lives here and maps 1:1 to a CLI flag and a TOML key.

Load order (later wins): built-in defaults -> --preset -> --config file -> CLI flags.
Coordinates / pixel units below are in *output* (original image) pixels unless noted.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


@dataclass(frozen=True)
class Config:
    # --- working resolution ---
    work_size: int = 1536           # longest side used internally; larger = finer, slower
    denoise: int = -1                # -1 auto (by measured noise), 0 off, N = N bilateral passes
    interior_noise: float = 0.002    # auto-denoise also fires when interior (edge-free) noise exceeds this
    # --- color / segmentation ---
    max_colors: int = 16            # palette cap (flat art usually auto-detects fewer)
    color_merge: float = 8.0        # merge palette colors closer than this (Lab dE)
    palette: tuple[str, ...] = ()   # fixed hex palette; empty = auto
    filter_speckle: int = 6         # drop regions smaller than N working px
    edge_threshold: float = 10.0    # gradient level that marks anti-aliased edges
    # --- structure ---
    group_depth: int = 3            # nesting depth of groups (0 = flat list of shapes)
    complete_hidden: bool = True    # reconstruct hidden parts of occluded shapes
    bleed: float = 1.0              # px that lower shapes extend under neighbours (no seams)
    remove_background: bool = False # drop the full-canvas background shape
    # --- curves ---
    simplify: float = 0.8           # max fitting error (px); higher = fewer anchors
    smooth: float = 0.8             # contour smoothing sigma (px) before fitting
    corner_threshold: float = 55.0  # degrees; turns sharper than this stay corners
    path_precision: int = 2         # decimals in path coordinates
    strokes: bool = True            # round-capped lines, open curves, thin closed loops
    # --- primitives ---
    snap_primitives: bool = True    # circles/ellipses/rects/polygons -> real elements
    snap_tolerance: float = 0.012   # mean edge deviation as a fraction of shape size
    # --- naming / AI ---
    name_layers: bool = True        # classical color+shape names; VLM refines if enabled
    vlm_url: str = ""               # OpenAI-compatible endpoint, e.g. http://localhost:1234/v1
    vlm_model: str = ""             # model id in LM Studio ("" = first loaded model)
    vlm_groups: bool = True         # let the VLM propose semantic groups
    segmenter: str = "classical"    # classical | sam (optional, needs [ai] extra)
    # --- gradients ---
    gradients: bool = True           # detect smooth ramps -> single linear/radial gradient fill
    grad_max_residual: float = 0.06  # max normalized colour-fit RMS (0..1) to accept a gradient
    grad_min_bands: int = 6          # a ramp must posterize into at least this many flat bands
    grad_min_frac: float = 0.00017   # min visible area (fraction of canvas H*W) for a ramp region
    grad_band_max_frac: float = 0.15  # a ramp band must be <= this fraction of H*W (see note)
    grad_step_de: float = 14.0       # max Lab dE between adjacent bands to join one ramp
    # NOTE on grad_band_max_frac: the design calibrated this at 0.0017 (~4000 px at a
    # hypothetical work_size=1536) assuming a smooth ramp posterizes into many thin slivers.
    # Verified by running: the actual `shaded` sample (400x400, never upscaled) posterizes
    # into only ~12 chunky bands, each 2-23% of the canvas, so a 0.0017 gate made gradient
    # detection a guaranteed no-op on the one sample it must fire on. Measured sweep: at 0.15
    # the sphere ramp is admitted (shaded -> 1 radial gradient, 5 shapes, SSIM ~0.956) while
    # EVERY flat sample/control stays at zero gradients. The real flat-art guard is
    # grad_min_bands (flat art never yields >=6 dE-adjacent monotone bands), confirmed by the
    # no-regression test; this gate only has to exclude a lone oversized flat region, which
    # grad_min_bands already rejects as a singleton. So 0.15 fires on ramps without regressing
    # flat art. Fractions still track work_size automatically (resolution-invariance test).
    # --- output ---
    illustrator_layers: bool = True # ids/labels so nested groups show in Illustrator Layers

    def merged(self, **overrides) -> "Config":
        valid = {f.name for f in fields(self)}
        bad = set(overrides) - valid
        if bad:
            raise KeyError(f"unknown config keys: {sorted(bad)}")
        return replace(self, **overrides)


PRESETS: dict[str, dict] = {
    "logo": dict(group_depth=3, max_colors=8, simplify=0.6, snap_tolerance=0.015),
    "illustration": dict(group_depth=3, max_colors=24, simplify=0.9, snap_tolerance=0.01),
    "lineart": dict(group_depth=1, max_colors=2, simplify=0.5, snap_primitives=False),
    "max": dict(work_size=3072, simplify=0.35, smooth=0.7, max_colors=32),
    "compact": dict(simplify=1.6, smooth=1.0, max_colors=12, filter_speckle=12),
}


def load(preset: str | None = None, config_path: Path | None = None, **cli) -> Config:
    cfg = Config()
    if preset:
        cfg = cfg.merged(**PRESETS[preset])
    if config_path:
        data = tomllib.loads(Path(config_path).read_text())
        if "palette" in data:
            data["palette"] = tuple(data["palette"])
        cfg = cfg.merged(**data)
    cli = {k: v for k, v in cli.items() if v is not None}
    if "palette" in cli and isinstance(cli["palette"], str):
        cli["palette"] = tuple(c.strip() for c in cli["palette"].split(",") if c.strip())
    return cfg.merged(**cli)
