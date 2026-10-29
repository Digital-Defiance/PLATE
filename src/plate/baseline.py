"""Phase-0 baseline: plain VTracer, no AI. This is the control every later
stage must beat on the editability metrics (see docs/METRICS.md)."""
from __future__ import annotations

from pathlib import Path

from .config import Config


def trace_baseline(src: Path, dst: Path, cfg: Config) -> None:
    import vtracer  # imported lazily so `plate --help` stays instant

    vtracer.convert_image_to_svg_py(
        str(src),
        str(dst),
        colormode="color",
        hierarchical="stacked",
        mode="spline",
        filter_speckle=cfg.filter_speckle,
        color_precision=6,
        corner_threshold=int(cfg.corner_threshold),
        path_precision=cfg.path_precision,
    )
