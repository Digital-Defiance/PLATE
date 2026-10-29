"""Rasterize independently authored SVG targets into deterministic challenge PNGs.

Requires the render extra and libcairo. Targets are source artwork, NEVER pipeline
output. Run from the repository root: python scripts/make_challenges.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main(outdir=None):
    import cairosvg

    out = Path(outdir) if outdir else ROOT / "samples" / "challenges"
    out.mkdir(parents=True, exist_ok=True)
    for target in sorted((ROOT / "samples" / "challenges").glob("*.target.svg")):
        # Supersample so inputs test antialiased raster reconstruction, rather than
        # Cairo's native-size edge coverage alone. Preserve transparency and holes.
        png = cairosvg.svg2png(bytestring=target.read_bytes(), scale=4)
        with Image.open(io.BytesIO(png)) as high:
            image = high.convert("RGBA").resize(
                (high.width // 4, high.height // 4), Image.Resampling.LANCZOS)
            dest = out / target.name.replace(".target.svg", ".png")
            image.save(dest)
            print(dest)


if __name__ == "__main__":
    main(*sys.argv[1:2])
