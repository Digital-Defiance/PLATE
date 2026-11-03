"""Python-side driver for the Phase 1 spike measurement harness (task 3.2).

The spike proves the UNCHANGED PLATE engine runs in Pyodide and produces the same
SVG in the browser as on the CLI, across the 24-scene bake-off corpus, within
acceptable per-scene time. The TypeScript harness (`web/spike/measure.ts`) owns
driving the Web Worker / Pyodide runtime and recording timings + the
`opencv-python` load result; this driver owns the two things that must run in real
CPython with the engine's own tools:

  prepare  Generate the seed-1, 24-scene bake-off corpus (exactly what
           ``plate corpus`` builds) and, for every scene, compute the *CLI* SVG by
           calling the unchanged ``pipeline.run`` — the source of truth the browser
           output is compared against. Emit a single JSON manifest the harness
           loads: per-scene image bytes (base64), filename, the CLI SVG, and the
           CLI ``bakeoff/score.py`` composite. The engine is never modified.

  score    Given the browser SVGs the harness collected (one per scene, keyed by
           scene name), classify each against the CLI SVG as ``byte-identical``,
           ``within-tolerance``, or ``outside-tolerance`` using ``bakeoff/score.py``
           — the only place the composite can be computed, since the scoring deps
           (cairosvg / scikit-image) are deliberately NOT loaded in the browser.

Why the split: `bakeoff/score.py`'s composite needs `cairosvg` + `scikit-image`,
which the design excludes from the browser runtime. The harness therefore records
raw browser SVGs + timings; this driver scores them in CPython. Classification is
written back as JSON so the harness can fold it into the single ``STATUS.md`` block
(task 3.2's "write all outcomes into STATUS.md").

This driver is spike instrumentation: it imports PLATE but changes nothing in the
engine, writes only under its chosen output directory, and makes no network calls.

Usage (run with the project venv — system python3 lacks plate):

    # 1. Build the corpus + CLI reference manifest the TS harness consumes:
    .venv/bin/python web/spike/driver.py prepare -o /tmp/spike

    # 2. (the harness runs each scene in Pyodide and writes browser SVGs +
    #     timings + opencv result to /tmp/spike/browser/)

    # 3. Classify the browser SVGs against the CLI SVGs:
    .venv/bin/python web/spike/driver.py score -o /tmp/spike
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

# The spike measures the UNCHANGED engine; import exactly what the CLI uses.
from plate.bakeoff import score as bakeoff_score
from plate.bakeoff.corpus import load_truth, make_corpus, scene_svg
from plate.config import Config
from plate.pipeline import run as pipeline_run

# ---------------------------------------------------------------------------
# Spike constants
# ---------------------------------------------------------------------------

# The design pins the spike to the 24-scene, seed-1 bake-off corpus (see
# docs/BAKEOFF.md and the engine-completion status entries, which are all stated
# against "24-scene corpus, seed 1").
CORPUS_N = 24
CORPUS_SEED = 1

# Bakeoff_Tolerance (requirements glossary): the composite-score tolerance defined
# by bakeoff/score.py, used as the documented fallback when the browser SVG is not
# byte-identical to the CLI SVG. score.py does not export a named constant, so the
# spike fixes the fallback band here: the browser output is "within tolerance" when
# its composite is within BAKEOFF_TOLERANCE of the CLI composite. 0.01 is a tight
# band (the corpus composites sit near 0.85; platform float drift that leaves the
# SVG non-identical should still score within a hundredth of the CLI). Task 5's
# GATE reads this classification; adjust here if the spike measurements justify it.
BAKEOFF_TOLERANCE = 0.01

MANIFEST_NAME = "manifest.json"
RESULTS_NAME = "classification.json"
BROWSER_DIR = "browser"  # harness writes <scene>.svg here, one per corpus scene


# ---------------------------------------------------------------------------
# prepare: corpus + CLI reference the browser output is measured against
# ---------------------------------------------------------------------------

def _scene_name(image_path: Path) -> str:
    """The corpus scene key (``scene00`` / ``scene03_jpg``), used to match a
    browser SVG back to its CLI reference. `make_corpus` names JPEG-damaged
    variants ``*_jpg``; the stem is the stable key the harness echoes back."""
    return image_path.stem


def prepare(out: Path) -> dict:
    """Generate the seed-1 24-scene corpus and the CLI reference manifest.

    For every scene: read the raw image bytes exactly as a browser upload would,
    run the UNCHANGED ``pipeline.run`` to get the CLI SVG (the source of truth),
    and score that CLI SVG with ``bakeoff/score.py`` so the ``score`` step can
    report a composite *difference*, not just the browser composite in isolation.

    Writes ``<out>/manifest.json`` (consumed by ``measure.ts``) and leaves the
    corpus images/truth under ``<out>/corpus`` for reference. Returns the manifest
    dict as well.
    """
    out.mkdir(parents=True, exist_ok=True)
    corpus_dir = out / "corpus"
    # make_corpus is exactly what `plate corpus -n 24 --seed 1` runs; same scenes.
    image_paths = make_corpus(corpus_dir, n=CORPUS_N, seed=CORPUS_SEED)
    truth_dir = corpus_dir / "truth"

    scenes: list[dict] = []
    for image_path in sorted(image_paths):
        name = _scene_name(image_path)
        data = image_path.read_bytes()

        # CLI source of truth: the unchanged engine on the default config, exactly
        # as the browser runs it with no overrides (Property 1 equivalence check).
        cli_svg = pipeline_run(image_path, Config()).svg

        # Score the CLI SVG against the CLEAN reference the bake-off uses (truth
        # render when ground truth exists, so JPEG-damaged inputs are scored
        # against clean truth exactly like `plate bakeoff`).
        ref_rgb, truth = _reference_for(image_path, truth_dir)
        cli_composite = bakeoff_score.score_svg(cli_svg, ref_rgb, truth)["composite"]

        scenes.append({
            "name": name,
            "filename": image_path.name,
            "imageBytesB64": base64.b64encode(data).decode("ascii"),
            "cliSvg": cli_svg,
            "cliComposite": cli_composite,
        })
        print(f"prepared {name:14} cli_composite={cli_composite:.4f} "
              f"({len(data)} bytes, {len(cli_svg)} svg chars)", file=sys.stderr)

    manifest = {
        "corpusN": CORPUS_N,
        "corpusSeed": CORPUS_SEED,
        "bakeoffTolerance": BAKEOFF_TOLERANCE,
        "scenes": scenes,
    }
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=1))
    print(f"\nwrote {out / MANIFEST_NAME} ({len(scenes)} scenes); "
          f"browser SVGs expected in {out / BROWSER_DIR}/<scene>.svg", file=sys.stderr)
    return manifest


def _reference_for(image_path: Path, truth_dir: Path):
    """Return ``(ref_rgb, truth_or_None)`` for scoring, mirroring the bake-off
    runner: when ground truth exists, score against the CLEAN truth render (so a
    JPEG-damaged input is compared fairly), and supply the loaded truth for
    structure metrics; otherwise score against the source image itself."""
    import io

    import numpy as np
    from PIL import Image

    ref = np.asarray(Image.open(image_path).convert("RGB"))
    truth_json = truth_dir / f"{image_path.stem}.json"
    if not truth_json.exists():
        return ref, None

    truth = load_truth(truth_json)
    import cairosvg
    png = cairosvg.svg2png(
        bytestring=scene_svg(truth["objects"]).encode(),
        output_width=ref.shape[1],
        output_height=ref.shape[0],
    )
    ref_clean = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    return ref_clean, truth


# ---------------------------------------------------------------------------
# score: classify the browser SVGs the harness collected
# ---------------------------------------------------------------------------

def classify(out: Path) -> dict:
    """Classify each browser SVG against its CLI SVG.

    Reads ``<out>/manifest.json`` (CLI references) and ``<out>/browser/<scene>.svg``
    (what the harness captured from Pyodide), and for every scene records one of:

      byte-identical    exact text match with the CLI SVG (the spike's target)
      within-tolerance  not identical, but composite within BAKEOFF_TOLERANCE of CLI
      outside-tolerance not identical and composite differs by more than the band
                        (a failure, per Requirement 2.3 / 3.3)
      missing-browser-svg  the harness did not produce an SVG for this scene

    Writes ``<out>/classification.json`` the harness folds into the STATUS.md block.
    Returns the results dict.
    """
    manifest = json.loads((out / MANIFEST_NAME).read_text())
    tolerance = float(manifest.get("bakeoffTolerance", BAKEOFF_TOLERANCE))
    browser_dir = out / BROWSER_DIR
    corpus_dir = out / "corpus"
    truth_dir = corpus_dir / "truth"

    results: list[dict] = []
    for scene in manifest["scenes"]:
        name = scene["name"]
        cli_svg = scene["cliSvg"]
        cli_composite = float(scene["cliComposite"])
        browser_path = browser_dir / f"{name}.svg"

        if not browser_path.exists():
            results.append({
                "name": name,
                "classification": "missing-browser-svg",
                "cliComposite": cli_composite,
            })
            print(f"{name:14} MISSING browser svg ({browser_path})", file=sys.stderr)
            continue

        browser_svg = browser_path.read_text(encoding="utf-8")
        if browser_svg == cli_svg:
            results.append({
                "name": name,
                "classification": "byte-identical",
                "cliComposite": cli_composite,
                "browserComposite": cli_composite,
                "compositeDiff": 0.0,
            })
            print(f"{name:14} byte-identical", file=sys.stderr)
            continue

        # Not byte-identical: fall back to the composite comparison (Req 2.3).
        image_path = _corpus_image(corpus_dir, scene["filename"])
        ref_rgb, truth = _reference_for(image_path, truth_dir)
        browser_composite = bakeoff_score.score_svg(browser_svg, ref_rgb, truth)["composite"]
        diff = abs(browser_composite - cli_composite)
        classification = "within-tolerance" if diff <= tolerance else "outside-tolerance"
        results.append({
            "name": name,
            "classification": classification,
            "cliComposite": cli_composite,
            "browserComposite": browser_composite,
            "compositeDiff": diff,
        })
        print(f"{name:14} {classification} (diff={diff:.4f}, tol={tolerance})", file=sys.stderr)

    out_results = {"bakeoffTolerance": tolerance, "scenes": results}
    (out / RESULTS_NAME).write_text(json.dumps(out_results, indent=1))
    print(f"\nwrote {out / RESULTS_NAME}", file=sys.stderr)
    return out_results


def _corpus_image(corpus_dir: Path, filename: str) -> Path:
    """Resolve a scene's source image under the prepared corpus images dir."""
    return corpus_dir / "images" / filename


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prepare = sub.add_parser("prepare", help="build the corpus + CLI reference manifest")
    p_prepare.add_argument("-o", "--output", required=True,
                           help="spike working directory (manifest + corpus land here)")

    p_score = sub.add_parser("score", help="classify browser SVGs against the CLI SVGs")
    p_score.add_argument("-o", "--output", required=True,
                         help="the same spike working directory used for `prepare`")

    args = parser.parse_args(argv)
    out = Path(args.output)
    if args.cmd == "prepare":
        prepare(out)
    elif args.cmd == "score":
        classify(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
