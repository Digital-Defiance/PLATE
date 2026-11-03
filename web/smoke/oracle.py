"""CLI oracle for the headless-browser smoke test (task 18).

The smoke test loads the real web page in headless Chromium, drops a fixed PNG
sample, drives a conversion through the DOM, and asserts the SVG the page
produced equals the CLI SVG. This script is the CPython side that produces that
source-of-truth CLI SVG the browser output is compared against.

It runs the UNCHANGED engine exactly as the CLI does — `pipeline.run(path,
Config())` on the default config, no overrides — and emits a tiny JSON manifest
the runner loads:

    {
      "sample": "badge.png",         # the fixed sample's filename
      "filename": "badge.png",       # what the page sees (its extension picks /input.<ext>)
      "imageBytesB64": "...",        # the exact bytes the page is handed
      "cliSvg": "...",               # the CLI SVG, the byte-identical oracle for a PNG
      "cliComposite": 0.8xxx         # bakeoff/score.py composite of the CLI SVG (fallback band)
    }

It is pure instrumentation: it imports PLATE but changes nothing in the engine,
writes only its chosen output file, and makes no network calls. Run it with the
project venv (system python3 lacks plate), prefixed with
DYLD_FALLBACK_LIBRARY_PATH so cairosvg's cairo can be found for the composite:

    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python \\
        web/smoke/oracle.py --sample badge.png -o /tmp/plate-smoke/manifest.json
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# The smoke test measures the UNCHANGED engine; import exactly what the CLI uses.
from plate.bakeoff import score as bakeoff_score
from plate.config import Config
from plate.pipeline import run as pipeline_run

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"


def build_manifest(sample: str) -> dict:
    """Run the CLI engine on the fixed sample and build the oracle manifest."""
    image_path = SAMPLES_DIR / sample
    if not image_path.exists():
        raise SystemExit(f"sample not found: {image_path}")

    data = image_path.read_bytes()

    # CLI source of truth: the unchanged engine on the default config, exactly as
    # the browser runs it with no overrides (Requirement 1.2 byte-identical).
    cli_svg = pipeline_run(image_path, Config()).svg

    # Composite of the CLI SVG against the source image, so the runner can report
    # the documented Bakeoff_Tolerance fallback band when (for a non-PNG) the SVG
    # is not byte-identical. For a PNG the byte-identical check is the real gate.
    ref_rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    cli_composite = bakeoff_score.score_svg(cli_svg, ref_rgb, None)["composite"]

    return {
        "sample": sample,
        "filename": image_path.name,
        "imageBytesB64": base64.b64encode(data).decode("ascii"),
        "cliSvg": cli_svg,
        "cliComposite": cli_composite,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        default="badge.png",
        help="fixed sample filename under samples/ (PNG so the result is byte-identical)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="path to write the JSON manifest the runner consumes",
    )
    args = parser.parse_args(argv)

    manifest = build_manifest(args.sample)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1))
    print(
        f"wrote {out} (sample={manifest['sample']}, "
        f"{len(base64.b64decode(manifest['imageBytesB64']))} bytes, "
        f"{len(manifest['cliSvg'])} svg chars, cli_composite={manifest['cliComposite']:.4f})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
