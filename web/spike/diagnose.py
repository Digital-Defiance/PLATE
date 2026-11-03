"""Attribute each outside-tolerance spike scene to library versions or to Pyodide.

The spike (``run.ts``) compares every browser SVG with the CLI SVG. When a scene
lands outside Bakeoff_Tolerance, two explanations compete: the browser runs
different library versions (Pyodide 314.0.7 ships numpy 2.4.6, scipy 1.18.0,
opencv-python 4.11.0.86, pillow 12.2.0, scikit-image 0.26.0 on Python 3.14.2,
while the CLI venv has its own versions), or something specific to Pyodide's
WebAssembly builds. This diagnostic separates them by rerunning those scenes
natively, in a CPython venv that has Pyodide's library versions, with the very
wheel the browser installed.

  convert  Run with the diagnostic venv's python. Reruns the scenes with the
           unchanged ``plate.web.convert_bytes`` (the browser's entry point) and
           records the environment, Pillow's JPEG codec, and a digest of the
           pixels the engine's decoder (``imageio.open_rgba``) produces.

  decode   Records only the environment, codec and decoded-pixel digests. The
           runner executes it inside Pyodide (Node, same WebAssembly builds as
           the browser) to see the decoder output the browser starts from.

  compare  Run with the CLI venv's python (``bakeoff/score.py`` needs cairosvg).
           Attributes each scene and prints a Markdown section for STATUS.md:
             library versions  rerun == browser SVG, or the rerun stays within
                               tolerance of the browser but not of the CLI
             Pyodide           rerun == CLI SVG != browser SVG, or the rerun stays
                               within tolerance of the CLI but the browser does not
             undetermined      anything else

  same-pixels         Task-5 gate proof. Run with the diagnostic venv's python.
           For every JPEG scene, feed the engine the EXACT RGBA pixels Pyodide
           decoded (loaded from ``diag/<decode-label>/<scene>.rgba.npy``) by
           patching ``plate.imageio.open_rgba`` in THIS script only -- the engine
           is never edited and the original JPEG stays on disk so ``_is_jpeg``
           still sees a JPEG. Then it calls ``plate.web.convert_bytes`` (the
           browser's entry point, so the noise pre-check sees the same pixels) and
           writes the resulting SVG to ``diag/same-pixels/<scene>.svg``.

  same-pixels-report  Run with the CLI venv's python (scoring needs cairosvg).
           Compares each ``same-pixels`` SVG with the browser SVG the spike
           captured: byte-identical, else within Bakeoff_Tolerance by the same
           ``bakeoff/score.py`` composite ``driver.py`` uses. Prints a Markdown
           section for STATUS.md and records ``diag/same-pixels/proof.json``.

Writes only under ``<dir>/diag/<label>/`` and makes no network calls. The engine
is never modified.

Usage (``run.ts --diag-python`` runs all three steps itself):

    /tmp/plate-pyodide-venv/bin/python web/spike/diagnose.py convert -o /tmp/plate-spike
    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/diagnose.py compare -o /tmp/plate-spike
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

MANIFEST_NAME = "manifest.json"
RESULTS_NAME = "classification.json"
BROWSER_DIR = "browser"
DIAG_DIR = "diag"
RERUN_LABEL = "pyodide-versions"  # native CPython with Pyodide's library versions
PYODIDE_LABEL = "pyodide"  # decoder output inside Pyodide itself
SAME_PIXELS_LABEL = "same-pixels"  # engine run on the exact pixels Pyodide decoded
PROOF_NAME = "proof.json"
RECORD_NAME = "record.json"

# Distributions whose versions identify an environment.
DISTRIBUTIONS = (
    "numpy",
    "scipy",
    "opencv-python-headless",
    "opencv-python",
    "pillow",
    "scikit-image",
    "plate-svg",
)


def outside_scenes(out: Path) -> list[str]:
    """Scene names the spike scored outside Bakeoff_Tolerance."""
    results = json.loads((out / RESULTS_NAME).read_text())
    return [s["name"] for s in results["scenes"] if s["classification"] == "outside-tolerance"]


def environment() -> dict:
    """Python, platform, library versions, Pillow's JPEG codec, and plate's location."""
    import importlib.metadata as md
    import platform

    from PIL import features

    import plate

    versions = {}
    for name in DISTRIBUTIONS:
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            continue
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "plate": str(Path(plate.__file__).parent),
        "versions": versions,
        "jpegCodec": {
            "libjpeg": features.version("jpg"),
            "libjpegTurbo": bool(features.check_feature("libjpeg_turbo")),
        },
    }


def decode_digest(path: Path) -> dict:
    """Digest of the RGBA pixels the engine's own decoder produces for ``path``."""
    import numpy as np

    from plate.imageio import open_rgba

    pixels = np.ascontiguousarray(np.asarray(open_rgba(path)))
    return {"shape": list(pixels.shape), "sha256": hashlib.sha256(pixels.tobytes()).hexdigest()}


def _scenes(out: Path, wanted: list[str] | None) -> list[dict]:
    manifest = json.loads((out / MANIFEST_NAME).read_text())
    names = wanted if wanted else outside_scenes(out)
    return [s for s in manifest["scenes"] if s["name"] in names]


def _record(out: Path, scenes: list[dict]) -> dict:
    return {
        "environment": environment(),
        "scenes": [s["name"] for s in scenes],
        "decode": {s["name"]: decode_digest(out / "corpus" / "images" / s["filename"]) for s in scenes},
    }


def convert(out: Path, label: str, wanted: list[str] | None) -> None:
    """Rerun the scenes in this interpreter and record its decoder output."""
    from plate import web

    scenes = _scenes(out, wanted)
    dest = out / DIAG_DIR / label
    dest.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        data = base64.b64decode(scene["imageBytesB64"])
        svg = web.convert_bytes(data, scene["filename"])["svg"]
        (dest / f"{scene['name']}.svg").write_text(svg, encoding="utf-8")
        print(f"{scene['name']:14} rerun ({len(svg)} svg chars)", file=sys.stderr)
    (dest / RECORD_NAME).write_text(json.dumps(_record(out, scenes), indent=1))
    print(f"wrote {dest}", file=sys.stderr)


def decode(out: Path, label: str, wanted: list[str] | None) -> None:
    """Record this interpreter's decoder output for the scenes (no conversion),
    keeping the decoded RGBA arrays so ``compare`` can measure the difference."""
    import numpy as np

    from plate.imageio import open_rgba

    scenes = _scenes(out, wanted)
    dest = out / DIAG_DIR / label
    dest.mkdir(parents=True, exist_ok=True)
    for scene in scenes:
        pixels = np.asarray(open_rgba(out / "corpus" / "images" / scene["filename"]))
        np.save(dest / f"{scene['name']}.rgba.npy", pixels)
    (dest / RECORD_NAME).write_text(json.dumps(_record(out, scenes), indent=1))
    print(f"wrote {dest / RECORD_NAME}", file=sys.stderr)


def _decode_delta(saved: Path, image: Path) -> str:
    """How the saved decoder output differs from this interpreter's decode."""
    import numpy as np

    from plate.imageio import open_rgba

    if not saved.exists():
        return "not measured"
    theirs = np.load(saved).astype(np.int16)
    ours = np.asarray(open_rgba(image)).astype(np.int16)
    if theirs.shape != ours.shape:
        return f"shape {list(theirs.shape)} vs {list(ours.shape)}"
    delta = np.abs(theirs - ours)
    if not delta.any():
        return "same"
    share = float((delta.max(axis=2) > 0).mean()) * 100
    return f"differ: {share:.1f}% of pixels, max abs diff {int(delta.max())}"


def attribute(rerun: str, browser: str, cli: str,
              rerun_c: float, browser_c: float, cli_c: float, tolerance: float) -> str:
    """Where the browser/CLI gap comes from, by SVG identity first, then composites."""
    if rerun == browser:
        return "library versions"
    if rerun == cli:
        return "Pyodide"
    if abs(rerun_c - cli_c) <= tolerance < abs(browser_c - cli_c):
        return "Pyodide"
    if abs(rerun_c - browser_c) <= tolerance < abs(rerun_c - cli_c):
        return "library versions"
    return "undetermined"


def _versions_text(env: dict) -> str:
    libs = ", ".join(f"{k} {v}" for k, v in env["versions"].items())
    return f"Python {env['python']} ({env['platform']}); {libs}"


def _codec_text(env: dict) -> str:
    codec = env["jpegCodec"]
    kind = "libjpeg-turbo" if codec["libjpegTurbo"] else "IJG libjpeg"
    return f"{kind} (Pillow reports jpg {codec['libjpeg']})"


def compare(out: Path) -> str:
    """Attribute each rerun scene and return the STATUS.md Markdown section."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import driver  # web/spike/driver.py: the same reference/scoring the spike used

    from plate.bakeoff import score as bakeoff_score

    manifest = {s["name"]: s for s in json.loads((out / MANIFEST_NAME).read_text())["scenes"]}
    results_doc = json.loads((out / RESULTS_NAME).read_text())
    tolerance = float(results_doc["bakeoffTolerance"])
    results = {s["name"]: s for s in results_doc["scenes"]}
    rerun_dir = out / DIAG_DIR / RERUN_LABEL
    rerun = json.loads((rerun_dir / RECORD_NAME).read_text())
    pyodide_path = out / DIAG_DIR / PYODIDE_LABEL / RECORD_NAME
    pyodide = json.loads(pyodide_path.read_text()) if pyodide_path.exists() else None
    here = environment()
    truth_dir = out / "corpus" / "truth"

    def same(a: dict | None, b: dict | None) -> str:
        if a is None or b is None:
            return "not measured"
        return "same" if a == b else "differ"

    rows: list[dict] = []
    for name in rerun["scenes"]:
        scene = manifest[name]
        image = out / "corpus" / "images" / scene["filename"]
        cli_svg = scene["cliSvg"]
        browser_svg = (out / BROWSER_DIR / f"{name}.svg").read_text(encoding="utf-8")
        rerun_svg = (rerun_dir / f"{name}.svg").read_text(encoding="utf-8")
        ref_rgb, truth = driver._reference_for(image, truth_dir)
        rerun_c = bakeoff_score.score_svg(rerun_svg, ref_rgb, truth)["composite"]
        cli_c = float(scene["cliComposite"])
        browser_c = float(results[name]["browserComposite"])
        cli_decode = decode_digest(image)
        pyodide_decode = "not measured"
        if pyodide:
            pyodide_decode = same(pyodide["decode"].get(name), cli_decode)
            if pyodide_decode == "differ":
                saved = out / DIAG_DIR / PYODIDE_LABEL / f"{name}.rgba.npy"
                pyodide_decode = _decode_delta(saved, image)
        rows.append({
            "name": name,
            "rerunIsBrowser": rerun_svg == browser_svg,
            "rerunIsCli": rerun_svg == cli_svg,
            "cliComposite": cli_c,
            "browserComposite": browser_c,
            "rerunComposite": rerun_c,
            "decodeRerunVsCli": same(rerun["decode"].get(name), cli_decode),
            "decodePyodideVsCli": pyodide_decode,
            "attribution": attribute(rerun_svg, browser_svg, cli_svg, rerun_c, browser_c, cli_c, tolerance),
        })
    (rerun_dir / "attribution.json").write_text(json.dumps(rows, indent=1))

    codecs = [f"CLI venv {_codec_text(here)}", f"rerun venv {_codec_text(rerun['environment'])}"]
    if pyodide:
        codecs.insert(0, f"Pyodide {_codec_text(pyodide['environment'])}")
    decoder_check = (
        f"run inside Pyodide (Python {pyodide['environment']['python']}) under Node, which uses "
        "the same WebAssembly package builds as the browser."
        if pyodide else "not run inside Pyodide."
    )
    lines = [
        "<!-- SPIKE:browser-web-page:diagnostic:begin -->",
        "",
        "### Diagnostic: outside-tolerance scenes rerun natively with Pyodide's library versions",
        "",
        (f"- Native rerun (`web/spike/diagnose.py convert`): {_versions_text(rerun['environment'])}; "
         f"plate from `{rerun['environment']['plate']}`, installed from the same wheel the browser ran."),
        f"- CLI reference: {_versions_text(here)}.",
        f"- Decoder check (`diagnose.py decode`): {decoder_check}",
        f"- JPEG codec behind Pillow: {'; '.join(codecs)}.",
        "",
        ("A gap comes from **library versions** when the native rerun reproduces the browser SVG, and "
         "from **Pyodide** when the rerun reproduces the CLI SVG instead. When the rerun matches neither "
         f"byte for byte, the composites decide: the side the rerun stays within {tolerance} of. "
         "`decoded pixels` compares the RGBA output of the engine's decoder (`imageio.open_rgba`) "
         "with the CLI venv's."),
        "",
        ("| scene | rerun == browser | rerun == CLI | CLI composite | browser composite | rerun composite "
         "| decoded pixels, rerun | decoded pixels, Pyodide | gap comes from |"),
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {'yes' if r['rerunIsBrowser'] else 'no'} | {'yes' if r['rerunIsCli'] else 'no'} "
            f"| {r['cliComposite']:.4f} | {r['browserComposite']:.4f} | {r['rerunComposite']:.4f} "
            f"| {r['decodeRerunVsCli']} | {r['decodePyodideVsCli']} | **{r['attribution']}** |"
        )
    tally: dict[str, int] = {}
    for r in rows:
        tally[r["attribution"]] = tally.get(r["attribution"], 0) + 1
    summary = ", ".join(f"{k} {v}" for k, v in sorted(tally.items())) or "no scenes"
    lines += ["", f"Attribution: {summary}."]
    if rows and all(r["decodeRerunVsCli"] == "same" and r["decodePyodideVsCli"].startswith("differ")
                    for r in rows):
        lines += [
            "",
            ("For every scene above, the native rerun decodes the input exactly as the CLI venv "
             "does, while the decoder output inside Pyodide differs, so the conversion already "
             "starts from different pixels in the browser. The JPEG codecs behind Pillow are "
             "listed above."),
        ]
    lines += ["", "<!-- SPIKE:browser-web-page:diagnostic:end -->"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# same-pixels: task-5 gate proof (decoder-only JPEG difference)
# ---------------------------------------------------------------------------

def jpeg_scenes(out: Path) -> list[dict]:
    """Every manifest scene whose decoded source is a JPEG (``*_jpg`` corpus key)."""
    manifest = json.loads((out / MANIFEST_NAME).read_text())
    return [s for s in manifest["scenes"] if s["name"].endswith("_jpg")]


def same_pixels(out: Path, decode_label: str, wanted: list[str] | None) -> None:
    """Run the UNCHANGED engine on the exact RGBA pixels Pyodide decoded.

    For each JPEG scene we load the Pyodide-decoded RGBA array
    (``diag/<decode_label>/<scene>.rgba.npy``) and patch ``plate.imageio.open_rgba``
    -- the single pixel-decode path for both ``check_noise`` and ``pipeline.run`` --
    to return that array as a PIL image, *in this diagnostic script only*. The
    engine source is never touched; the JPEG file still exists on disk so the
    engine's ``_is_jpeg`` format probe keeps seeing a JPEG. ``convert_bytes`` (the
    browser entry point) then runs exactly as in the browser, starting from the
    browser's own decoded pixels. The resulting SVG lands in
    ``diag/same-pixels/<scene>.svg`` for ``same-pixels-report`` to score.
    """
    import numpy as np
    from PIL import Image

    from plate import imageio as plate_imageio
    from plate import web

    scenes = [s for s in jpeg_scenes(out) if not wanted or s["name"] in wanted]
    dest = out / DIAG_DIR / SAME_PIXELS_LABEL
    dest.mkdir(parents=True, exist_ok=True)

    original_open_rgba = plate_imageio.open_rgba
    for scene in scenes:
        name = scene["name"]
        npy = out / DIAG_DIR / decode_label / f"{name}.rgba.npy"
        if not npy.exists():
            raise FileNotFoundError(
                f"missing Pyodide-decoded pixels for {name}: {npy}\n"
                f"generate it with diagnose.py decode --scenes {name} inside Pyodide first"
            )
        pixels = np.load(npy)
        if pixels.ndim != 3 or pixels.shape[2] != 4 or pixels.dtype != np.uint8:
            raise ValueError(f"unexpected decoded array for {name}: shape {pixels.shape} dtype {pixels.dtype}")
        rgba_image = Image.fromarray(np.ascontiguousarray(pixels), "RGBA")

        # Feed the engine the browser's pixels regardless of the path it opens.
        # web.convert_bytes / check_noise both decode solely through open_rgba;
        # _is_jpeg re-reads the real JPEG file for format only, so it is untouched.
        plate_imageio.open_rgba = lambda _path, _img=rgba_image: _img.copy()
        # web.py imported open_rgba by name; patch that binding too.
        web.open_rgba = plate_imageio.open_rgba
        try:
            data = base64.b64decode(scene["imageBytesB64"])
            svg = web.convert_bytes(data, scene["filename"])["svg"]
        finally:
            plate_imageio.open_rgba = original_open_rgba
            web.open_rgba = original_open_rgba
        (dest / f"{name}.svg").write_text(svg, encoding="utf-8")
        print(f"{name:14} same-pixels rerun ({len(svg)} svg chars) from {npy.name}", file=sys.stderr)

    (dest / RECORD_NAME).write_text(json.dumps({
        "decodeLabel": decode_label,
        "environment": environment(),
        "scenes": [s["name"] for s in scenes],
    }, indent=1))
    print(f"wrote {dest}", file=sys.stderr)


def same_pixels_report(out: Path) -> str:
    """Score each same-pixels SVG against the browser SVG and return STATUS.md
    Markdown. The proof passes for a scene when the same-pixels SVG is
    byte-identical to the browser SVG, or within Bakeoff_Tolerance of it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import driver  # web/spike/driver.py: the same reference/scoring the spike used

    from plate.bakeoff import score as bakeoff_score

    manifest = {s["name"]: s for s in json.loads((out / MANIFEST_NAME).read_text())["scenes"]}
    results_doc = json.loads((out / RESULTS_NAME).read_text())
    tolerance = float(results_doc["bakeoffTolerance"])
    results = {s["name"]: s for s in results_doc["scenes"]}
    same_dir = out / DIAG_DIR / SAME_PIXELS_LABEL
    record = json.loads((same_dir / RECORD_NAME).read_text())
    truth_dir = out / "corpus" / "truth"

    rows: list[dict] = []
    for name in record["scenes"]:
        scene = manifest[name]
        image = out / "corpus" / "images" / scene["filename"]
        browser_svg = (out / BROWSER_DIR / f"{name}.svg").read_text(encoding="utf-8")
        same_svg = (same_dir / f"{name}.svg").read_text(encoding="utf-8")
        spike_class = results[name]["classification"]
        if same_svg == browser_svg:
            rows.append({
                "name": name, "match": "byte-identical", "diff": 0.0,
                "pass": True, "spikeClassification": spike_class,
                "browserComposite": float(results[name].get("browserComposite", scene["cliComposite"])),
                "samePixelsComposite": float(results[name].get("browserComposite", scene["cliComposite"])),
            })
            print(f"{name:14} PASS byte-identical to browser", file=sys.stderr)
            continue
        ref_rgb, truth = driver._reference_for(image, truth_dir)
        same_c = bakeoff_score.score_svg(same_svg, ref_rgb, truth)["composite"]
        browser_c = bakeoff_score.score_svg(browser_svg, ref_rgb, truth)["composite"]
        diff = abs(same_c - browser_c)
        passed = diff <= tolerance
        rows.append({
            "name": name,
            "match": "within-tolerance" if passed else "outside-tolerance",
            "diff": diff, "pass": passed, "spikeClassification": spike_class,
            "browserComposite": browser_c, "samePixelsComposite": same_c,
        })
        verdict = "PASS" if passed else "FAIL"
        print(f"{name:14} {verdict} vs browser (diff={diff:.4f}, tol={tolerance})", file=sys.stderr)

    all_pass = bool(rows) and all(r["pass"] for r in rows)
    (same_dir / PROOF_NAME).write_text(json.dumps({
        "bakeoffTolerance": tolerance,
        "decodeLabel": record["decodeLabel"],
        "allPass": all_pass,
        "scenes": rows,
    }, indent=1))

    lines = [
        "<!-- SPIKE:browser-web-page:same-pixels:begin -->",
        "",
        "### Proof: the engine on Pyodide's decoded pixels reproduces the browser SVG (task 5)",
        "",
        ("For every JPEG scene, the unchanged engine was rerun natively on the EXACT RGBA pixels "
         "Pyodide decoded (loaded from `diag/" + record["decodeLabel"] + "/<scene>.rgba.npy`), by "
         "patching `plate.imageio.open_rgba` in `web/spike/diagnose.py` only -- the engine is never "
         "edited, and the original JPEG stays on disk so the engine's `_is_jpeg` format probe still "
         "sees a JPEG. The call goes through `plate.web.convert_bytes`, the browser's entry point, so "
         "the noise pre-check sees the same pixels too. A scene passes when this same-pixels SVG "
         f"matches the browser SVG in `browser/<scene>.svg`: byte-identical, or within {tolerance} "
         "composite scored the way `driver.py` scores."),
        "",
        "| scene | spike classification vs CLI | same-pixels vs browser | composite diff | proof |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['spikeClassification']} | {r['match']} | {r['diff']:.4f} "
            f"| {'PASS' if r['pass'] else 'FAIL'} |"
        )
    passed_n = sum(1 for r in rows if r["pass"])
    lines += [
        "",
        (f"Proof result: {passed_n}/{len(rows)} JPEG scene(s) reproduced the browser SVG from the "
         "same decoded pixels. "
         + ("Every JPEG difference is therefore decoder-only: the engine, given the browser's pixels, "
            "produces the browser's SVG."
            if all_pass else
            "At least one JPEG scene did NOT reproduce the browser SVG from the same pixels, so the "
            "difference is not purely decoder-driven.")),
        "",
        "<!-- SPIKE:browser-web-page:same-pixels:end -->",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for cmd, help_text, label in (
        ("convert", "rerun scenes in this interpreter", RERUN_LABEL),
        ("decode", "record decoder output in this interpreter", PYODIDE_LABEL),
    ):
        p = sub.add_parser(cmd, help=help_text)
        p.add_argument("-o", "--output", required=True, help="the spike working directory")
        p.add_argument("--label", default=label)
        p.add_argument("--scenes", nargs="*", help="scene names (default: outside-tolerance)")
    p_compare = sub.add_parser("compare", help="attribute each rerun scene; print Markdown")
    p_compare.add_argument("-o", "--output", required=True, help="the spike working directory")

    p_same = sub.add_parser("same-pixels", help="rerun JPEG scenes on Pyodide's decoded pixels")
    p_same.add_argument("-o", "--output", required=True, help="the spike working directory")
    p_same.add_argument("--decode-label", default=PYODIDE_LABEL,
                        help="diag label holding the Pyodide-decoded .rgba.npy arrays")
    p_same.add_argument("--scenes", nargs="*", help="scene names (default: all JPEG scenes)")

    p_same_report = sub.add_parser("same-pixels-report",
                                   help="score same-pixels SVGs vs browser; print Markdown")
    p_same_report.add_argument("-o", "--output", required=True, help="the spike working directory")

    args = parser.parse_args(argv)

    out = Path(args.output)
    if args.cmd == "convert":
        convert(out, args.label, args.scenes)
    elif args.cmd == "decode":
        decode(out, args.label, args.scenes)
    elif args.cmd == "same-pixels":
        same_pixels(out, args.decode_label, args.scenes)
    elif args.cmd == "same-pixels-report":
        print(same_pixels_report(out))
    else:
        print(compare(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
