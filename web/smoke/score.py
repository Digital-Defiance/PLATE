"""Composite scorer for the smoke test's non-byte-identical fallback (task 18).

For a PNG sample the smoke test asserts the page SVG is byte-identical to the
CLI SVG. Only when it is NOT identical does the runner fall back to the
documented Bakeoff_Tolerance band (Requirement 1.3): it writes the browser SVG
and calls this script to compute its `bakeoff/score.py` composite against the
same source image the oracle used, and the absolute difference from the CLI
composite. The runner compares that diff to the 0.01 tolerance.

This runs the UNCHANGED engine's scorer only; it changes nothing and makes no
network calls. Prefix with DYLD_FALLBACK_LIBRARY_PATH so cairosvg's cairo loads.

    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python \\
        web/smoke/score.py --sample badge.png --svg /tmp/plate-smoke/browser.svg \\
        --cli-composite 0.85
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from plate.bakeoff import score as bakeoff_score

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "samples"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", required=True, help="fixed sample filename under samples/")
    parser.add_argument("--svg", required=True, help="path to the browser SVG to score")
    parser.add_argument(
        "--cli-composite",
        type=float,
        required=True,
        help="the CLI SVG composite from the oracle manifest",
    )
    args = parser.parse_args(argv)

    image_path = SAMPLES_DIR / args.sample
    data = image_path.read_bytes()
    ref_rgb = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))

    browser_svg = Path(args.svg).read_text(encoding="utf-8")
    browser_composite = bakeoff_score.score_svg(browser_svg, ref_rgb, None)["composite"]
    diff = abs(browser_composite - args.cli_composite)

    print(json.dumps({"browserComposite": browser_composite, "diff": diff}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
