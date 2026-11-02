"""Generate a labelled flat-colour MOSAIC fixture for the palette-pressure case (R7c).

    python scripts/make_mosaic.py [outdir] [ncolors]      # default: samples/fixtures, 130

A mosaic is a grid of solid, exactly-repeated flat colours with no anti-aliasing
inside each tile (crisp tile borders only). It is the archetypal high-cardinality
flat-art input: a swatch chart / pixel-art / tile map whose colours are genuinely
distinct, not photo noise or a smooth ramp. It stresses the palette path in
`stages/segment._build_palette`:

  * up to FLAT_PALETTE_CEILING (96) exactly-repeated flat colours are honoured
    verbatim (the flat-palette branch), because they explain ~100% of flat pixels;
  * BEYOND that ceiling the input falls to the k-means fallback, which is bounded by
    `max_colors` (default 16, a photo cap). A >96-colour mosaic therefore collapses
    to `max_colors` averaged clusters UNLESS the caller raises `max_colors` - which
    is exactly what this fixture lets tests measure (see tests/test_segment.py).

Writes:
  <out>/mosaic_<ncolors>.png            the fixture image (crisp flat tiles)
  <out>/mosaic_<ncolors>.json           {tile, cols, rows, colors:[[r,g,b],...]}  (ground truth)

The colours are seeded and well separated (>= ~24 per channel bucket) so recovery
can be scored by exact/near-exact RGB match. Determinate: same ncolors -> same file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

TILE = 12       # px per tile side; no supersampling => crisp (non-antialiased) tile interiors
COLS = 12       # tiles per row


def mosaic_colors(ncolors: int) -> list[tuple[int, int, int]]:
    """Deterministic, well-separated distinct RGB colours (one per tile)."""
    rng = np.random.default_rng(7)
    colors: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    while len(colors) < ncolors:
        c = tuple(int(x) for x in rng.integers(0, 256, 3))
        bucket = (c[0] // 24, c[1] // 24, c[2] // 24)   # keep them perceptibly distinct
        if bucket in seen:
            continue
        seen.add(bucket)
        colors.append(c)
    return colors


def make_mosaic(ncolors: int = 130, tile: int = TILE, cols: int = COLS):
    """Return (image_array HxWx3 uint8, metadata dict). Crisp flat tiles, no AA."""
    colors = mosaic_colors(ncolors)
    rows = (ncolors + cols - 1) // cols
    img = np.zeros((rows * tile, cols * tile, 3), np.uint8)
    for i, c in enumerate(colors):
        r, cc = divmod(i, cols)
        img[r * tile:(r + 1) * tile, cc * tile:(cc + 1) * tile] = c
    meta = dict(tile=tile, cols=cols, rows=rows, ncolors=ncolors,
                colors=[list(c) for c in colors])
    return img, meta


def write(out: Path, ncolors: int = 130) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    img, meta = make_mosaic(ncolors)
    png = out / f"mosaic_{ncolors}.png"
    Image.fromarray(img).save(png)
    (out / f"mosaic_{ncolors}.json").write_text(json.dumps(meta))
    return png


if __name__ == "__main__":
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "samples/fixtures"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 130
    path = write(outdir, n)
    print(f"wrote {path} ({n} colours)")
