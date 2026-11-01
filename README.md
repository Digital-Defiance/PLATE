# PLATE — Primitive-aware Layered Amodal Tracing Engine

PLATE is a local, open-source command-line tool that converts a raster image (PNG/JPG/WebP/BMP/TIFF)
into an **Illustrator-friendly, layered SVG**. Instead of the flat soup of thousands of path points a
typical auto-tracer produces, PLATE reconstructs the *editable structure* of the artwork:

- **Real objects, not pixel outlines** — a circle becomes one `<circle>` with 4 anchors, not a 90-point path.
- **Named layers and nested groups** — top-level artwork imports as actual Illustrator layers; standalone shapes get their own layer containers. Semantic groups remain nested inside them. Verified on Illustrator 30.8.2.
- **Correct stacking order** — shapes are painted bottom-to-top in the order they actually overlap.
- **Hidden parts completed** — when one shape is partly hidden behind another, PLATE reconstructs the
  occluded shape's *full* silhouette (amodal completion) and paints the occluder on top. The shape
  underneath is whole, with no hole cut out of it.
- **True primitives** — circles, ellipses, rectangles, rounded rectangles, polygons, and rings
  (two circles, even-odd) are emitted as live SVG shapes you can keep editing; everything else is a
  minimal-anchor Bézier path.
- **Optional AI naming** — a local vision-language model (via LM Studio) can replace classical names
  ("Navy circle") with semantic ones ("Left Eye") and group related shapes, entirely offline.
- **Editable strokes** — suitable constant-width curves become open SVG paths with a stroke
  width and round caps/joins; thin circular/elliptical loops become native stroked primitives.

By Digital Defiance (501(c)(3)). MIT licensed.

The [PLATE logo](assets/brand/README.md) doubles as a tracing challenge: its layered
P, transparent counters and registration strokes test the structure PLATE recovers.

> **Status (v0.1.0):** working classical engine; the real-LM-Studio VLM path is validated (naming +
> semantic grouping against a live vision model). Linear/radial gradients and conservative
> strokes are implemented. All 24 benchmark images pass 636 automated Illustrator 30.8.2
> checks for actual layers, names, grouping, order, geometry, strokes, gradients, edits and `.ai` round trips;
> see `docs/illustrator-checklist.md` for measured results and remaining checks.
> Full state and known limitations are in `STATUS.md`; plans in `ROADMAP.md`. Continuing the project
> with a coding agent? Start with **`AGENTS.md`**.

## What PLATE covers

PLATE is intended for logos, icons, diagrams and graphic illustrations with
recoverable shapes. It is **not a universal PNG reconstruction tool**. Opening a
PNG successfully, matching its rendered pixels and recovering its intended
editable objects are three different levels of success.

| Artwork / feature | Current coverage and limits |
| --- | --- |
| Flat geometric artwork | Strong synthetic coverage for circles, ellipses, rectangles, polygons, containment and supported occlusion. Complex compositions can still split or merge objects. |
| Thin lines and outlines | Straight round-capped marks, selected open curves and circular/elliptical loops become strokes. Branched networks, touching same-colour details, other caps/joins and variable-width/dashed strokes lack comprehensive coverage. |
| Gradients | Linear/radial fills and some supported occlusions work. Clamped/nonlinear ramps, general elliptical/focal gradients and complex decorated shading remain incomplete; mesh/conic gradients are outside current coverage. |
| Transparency | Hard cutouts and tested flat-opacity regions work. Soft shadows, feathering, spatially varying alpha and blend effects are not broadly validated. |
| Lettering | Traced outlines can remain editable paths. Original fonts, live text, reading order and semantic letter grouping are not recovered reliably. |
| Tiny, noisy or low-contrast art | A controlled [78-case sweep](docs/ROBUSTNESS.md) measures per-object detail/topology: 70/78 pass, including all 36 core cases; 8 stress cases still fail. Tiny markers/hairlines, stronger blur and low contrast remain limits of current defaults. |
| PNG decoding / colour | All 15 legal static colour/depth combinations are tested with Adam7, tRNS and palette alpha. Channels normalize to 8-bit RGBA. ICC/gamma colour transforms remain unimplemented; APNG uses only the default/first image. See [PNG coverage and policy](docs/PNG-COVERAGE.md). |
| Photos, textures and painterly artwork | Outside the current editable-object quality claim; these are not the intended launch use case. |

The **16 independent desired-SVG challenges have 9 structural passes and 7 known
gaps**, despite all 16 meeting their light/dark appearance floors. The seven gaps
are mission patch, storefront, event poster, EMBER, ORBIT, ROOT and the PLATE logo;
matching object counts alone does not make these pass. Some hidden authoring
geometry is inherently ambiguous from a raster. See [the measured gaps](docs/AUDIT.md).

The **24/24 Illustrator workflows validate SVG interchange**, including real
layers and native edits; they do not turn those seven reconstruction gaps into
passes. A representative real-artwork corpus, broader colour management, scale/noise
sweeps and further native editing checks are still needed. The remaining work and
acceptance gates are tracked in [ROADMAP.md](ROADMAP.md).

## Requirements

- **macOS or Linux**, **Python ≥ 3.10** (developed and tested on Python 3.11).
- Core dependencies (installed automatically): `numpy`, `scipy`, `opencv-python-headless`, `pillow`, `vtracer`, `scikit-image`.
- **Optional, for metrics / reports / `plate bench`** (`render` extra): `cairosvg`.
  `cairosvg` needs the native **cairo** library:
  - macOS: `brew install cairo`
  - Debian/Ubuntu: `sudo apt-get install libcairo2`
- **Optional, for AI naming**: [LM Studio](https://lmstudio.ai/) running its local server with a
  **vision-capable** model loaded (e.g. Qwen2.5-VL, Qwen3-VL, Gemma 3, Pixtral). No extra Python deps —
  PLATE talks to the OpenAI-compatible endpoint with the standard library.

> **Note for macOS + Homebrew:** `cairosvg` does not find Homebrew's libcairo on its own (SIP strips
> `DYLD_*` from inherited environments). The `plate` CLI handles this automatically by re-pointing the
> dynamic loader at the Homebrew cairo directory on startup, so rendering "just works". If you call the
> rendering code **directly** (your own script, or running `pytest`), prefix the command with
> `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.

## Install

```bash
cd /Volumes/Code/PLATE
python3.11 -m venv .venv && source .venv/bin/activate   # use a 3.10+ interpreter; macOS system python3 may be 3.9
pip install -e ".[dev,render]"      # dev = pytest + ruff; render = cairosvg
plate doctor                        # check deps and whether LM Studio is reachable
pytest -q                           # latest verification counts are recorded in STATUS.md
```

`plate doctor` reports each dependency (including whether the cairo renderer is usable) and lists any
models currently loaded in LM Studio:

```bash
plate doctor --vlm-url http://localhost:1234/v1
```

## Use

```bash
# one image -> one layered SVG (+ an HTML report comparing source vs SVG, the layer tree, and metrics)
plate trace logo.png -o logo.svg --report

# presets tuned for different artwork
plate trace art.jpg --preset illustration        # logo | illustration | lineart | max | compact

# set ANY config lever ad hoc
plate trace art.png --set simplify=1.2 --set max_colors=12

# retain filled outlines instead of automatically recovering editable curved strokes
plate trace art.png --set strokes=false

# semantic names + groups from a local vision model (LM Studio must be running with a vision model).
# --vlm-model is optional; omit it to auto-pick a loaded model, or pass the id shown by `plate doctor`.
plate trace art.png --vlm-url http://localhost:1234/v1 --vlm-model <your-vision-model-id>

# convert a whole folder, preserving structure
plate batch ./pngs -o ./svgs

# explore one lever: trace at several values and tabulate anchors vs fidelity
plate sweep art.png simplify 0.4 0.8 1.6

# compare PLATE against the plain-VTracer control on a folder (editability + fidelity)
plate bench samples

# plain VTracer output only (the control used by `bench`)
plate trace art.png --baseline

# objective bake-off: generate a synthetic corpus with exact ground truth, then score
# PLATE against other tools (VTracer, Potrace) on fidelity, structure and editability
plate corpus -o bo/corpus -n 24 --seed 1
plate bakeoff bo/corpus/images --truth bo/corpus/truth -o bo/out   # open bo/out/report.html
```

`plate batch` continues after individual failures and prints totals. Its exit code is
0 when every conversion succeeds, 1 when any conversion fails, or 2 when no images are found.

**Per-image overrides:** drop a sidecar JSON next to the image — `art.plate.json` beside `art.png`,
e.g. `{"simplify": 2.0, "max_colors": 8}` — and those levers apply just to that image.

## How it works (pipeline)

1. **Segment** — build an exact flat-colour palette (merged in Lab space); assign anti-aliased edge
   pixels to a colour by coverage; auto bilateral denoise for noisy/JPEG input.
2. **Contain** — build a nesting tree (a shape's parent is the smallest silhouette that contains it)
   → nested Illustrator groups.
3. **Occlusion + amodal completion** — a relative T-junction test decides which neighbour hides which
   shape; the hidden outline is reconstructed (circle/ellipse/rect fit, otherwise a tangent-continuous
   Bézier bridge). Primitive fits pool free arcs from separate components. Same-colour fragments
   can reunite when their union passes geometric and occlusion checks; matching completed gradient
   fragments can share one refitted ramp and full silhouette.
4. **Paint order** — topological sort bottom-to-top, with a small restricted bleed under later shapes
   to avoid hairline seams.
5. **Primitive snapping** — circle, ellipse, rect, rounded rect, polygon (≤14 vertices), ring
   (two circles, even-odd) emitted as live SVG elements; everything else falls through to…
6. **Bézier tracing / strokes** — sub-pixel contours, corner detection and Schneider fitting.
   Suitable unbranched constant-width curves instead get a fitted centreline and editable stroke;
   straight round-capped marks can also replace ellipse/rectangle approximations. Their cap fits
   use PNG antialias coverage and compete with rectangle/ellipse models. Complete thin loops can
   become stroked circles/ellipses; matching interrupted arcs can reunite when both terminals
   have occlusion evidence and hidden sections are covered. A short curve clipped by a known later
   loop can retain its full round cap through a constrained free-boundary fit. A long arc and small
   exposed cap can reunite when a shared curve and observed crossing explain their gap. Gradient fills, junctions and uncertain
   stroke fits retain their existing form; filled discs and genuine cutouts are protected.
7. **Names** — classical ("Navy circle") or, if a VLM is configured, semantic names and groups from a
   local vision model. Output carries `id`, `data-name`, and `inkscape:label` so names survive import
   into both Illustrator and Inkscape.

## Measured (`plate bench samples`, synthetic set)

Measured default configuration on 2026-10-29 (lower anchors/shape is better; SSIM P = PLATE,
V = plain VTracer). Regenerate any time with `plate bench samples`.

| image | PLATE anchors (/shape) | VTracer anchors (/shape) | PLATE prim% | SSIM P / V |
|---|---|---|---|---|
| overlap | 12 (4.0) | 27 (9.0) | 100 | .994 / .990 |
| stack3 | 16 (4.0) | 56 (14) | 100 | .997 / .986 |
| face | 43 (5.38) | 82 (10) | 100 | .992 / .991 |
| badge | 64 (6.4) | 389 (32) | 70 | .949 / .961 |
| ui_card | 14 (2.8) | 198 (33) | 40 | .979 / .991 |
| noisy_badge | 115 (11.5) | 2707 (13) | 70 | .867 / .891 |
| shaded (gradient) | 39 (7.8) | 31 | 100 | .956 / .934 |

Honest read: big editability wins on flat art; pixel fidelity is comparable to VTracer, slightly lower
on a few. Basic smooth gradients are editable fills; complex occluded gradients can still split
or posterize. Independent desired-SVG challenges and remaining failures are in `docs/challenges.md`.
The UI card now has three editable straight strokes in place of filled pill approximations;
its lower primitive percentage reflects that representation change.

For a tougher read, `plate bench samples/real` runs PLATE on a deliberately messy,
generated-realistic corpus (gradients, soft shadows, noise, JPEG-like artifacts, busy and
near-duplicate palettes, extreme aspect ratios, translucent overlaps). This is a diagnostic,
not a gate: per-image numbers are in `docs/REAL-CORPUS.md`, and provenance plus the CC0
drop-in instructions are in `samples/real/CREDITS.md`.

## Bake-off against other tools

Objective scoring on 24 synthetic scenes with **exact ground truth** (`plate corpus` +
`plate bakeoff`). Every metric is normalised to 0–1 (higher is better); the composite weights
and full method are in [`docs/BAKEOFF.md`](docs/BAKEOFF.md).

| tool | composite | geometry-only\* | anchors / shape | hidden parts recovered | SSIM (clean) |
|---|---|---|---|---|---|
| **PLATE** | **0.79** | **0.79** | **10** | 46% | 0.988 |
| VTracer (stacked) | 0.50 | 0.64 | 23 | 8% | 0.990 |
| VTracer (cutout) | 0.49 | 0.63 | 34 | 9% | — |
| Potrace (8-colour stack) | 0.43 | 0.56 | 100 | 8% | — |

\*geometry-only removes credit for layer names and true primitives, which only PLATE produces.
PLATE ranks first under all five weightings (balanced, geometry-only, fidelity-first,
editability-first, structure-first).

**Read it honestly:**
- PLATE's win is editability and structure — fewer anchors, real primitives, named layers, hidden
  parts completed. On pixel fidelity it is a near-tie with VTracer on clean images (SSIM 0.988 vs
  0.990, with lower mean pixel error) and **worse on JPEG-damaged input** (SSIM 0.967 vs 0.985).
- Weak spots the bake-off surfaced: only ~46% of hidden objects are recovered (occluded
  rectangles/polygons are worst), **0 of 10** on JPEG-damaged scenes, and touching same-colour
  objects merge. These are the top [ROADMAP](ROADMAP.md) items.
- The corpus is flat vector art, so it says nothing yet about photos/gradients, and Illustrator
  Image Trace / Vectorizer.AI are not in the table yet (they need manual exports; see
  [`docs/BAKEOFF.md`](docs/BAKEOFF.md)).

## Testing

```bash
pytest -q                                   # full suite
# if you invoke rendering directly on macOS/Homebrew, make libcairo findable:
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib pytest -q
```

The suite includes a **control regression suite** (`tests/test_controls.py`, fixtures generated by
`scripts/make_controls.py`): synthetic images of increasing complexity (T1 trivial → T5 hard), each
with a machine-checkable ground-truth contract (`tests/controls.py`) asserting object counts,
primitive types, parameters within tolerance, layer names, paint order, and nesting — plus a per-tier
SSIM floor when the renderer is available, and a soft golden-SVG diff (`tests/golden/controls/`,
refresh with `PLATE_UPDATE_GOLDEN=1`).

Independent PNG/desired-SVG challenges check hidden geometry, holes, gradients, stroke width and
paint order. The `stroked_route` target now passes as one open stroke behind its endpoint circles.
`gradient_badge` also passes with one full radial disc beneath its ribbon.
`edge_crossing_type` passes with one full disc behind all three letters.
Three complex logo fixtures add an EMBER fox crest, ORBIT wordmark and ROOT tree seal,
with independently authored SVG targets and transparent PNGs. Regenerate with
`python scripts/make_logo_challenges.py`; see `docs/challenges.md` for current failures.
Six desired structural targets remain expected failures; ordinary fidelity/integrity checks stay
active. Stroke detection uses only existing numpy/scipy dependencies; `--set strokes=false` disables
it. Automatic recovery targets round-capped straight marks and open curves, including a straight
terminal hidden under an aligned circular hub. The full instrument-panel target now passes:
**59 objects, all 27 strokes, 249 anchors**. ROOT's outer seal is an editable circle stroke;
its total is now **526 anchors** (9/32 strokes), after adaptive curve refitting and hole compaction.
Thin 5px circles stay connected, and ORBIT now has both orbital ellipses plus three editable
motion curves, plus one complete editable radial-gradient circle: **44 objects, 345 anchors,
7/7 strokes**, including both cream highlights. Compound navy shapes and ambiguous gradient
patches keep its overall structural target unmet.
More general interrupted/branched strokes,
opaque counters, more general occluders and other cap/join styles remain work.
`--set complete_hidden=false` also disables stroke completion.
Metrics and per-image stats include
`strokes` alongside object/anchor/gradient counts.

## Levers & presets

Every quality lever lives in `src/plate/config.py` (documented inline) and maps 1:1 to a CLI flag,
a TOML key, and `--set <lever>=<value>`. Presets: `logo`, `illustration`, `lineart`, `max`, `compact`.

## Project layout

```
src/plate/          core engine (stages/ holds the pipeline stages)
scripts/            synthetic sample + control generators
tests/              pytest suite, incl. the control regression suite
docs/               SPEC, METRICS protocol, Illustrator import checklist
samples/            generated synthetic test images
samples/real/       messy real-style evaluation corpus (diagnostic; see docs/REAL-CORPUS.md)
```

## Docs

Opt-in desktop validation (macOS + Illustrator; use a fresh output directory):

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib python -m plate.illustrator --output /tmp/plate-illustrator-NEW
```

This runs eight import/edit/save/reopen workflows and writes JSON evidence, PNGs
and `.ai` copies. All eight currently pass. To run the full 24-image corpus, append
`samples/*.png samples/challenges/*.png` before or after the options.
Full usage and remaining checks: `docs/illustrator-checklist.md`.

`AGENTS.md` (agent handoff) · `ROADMAP.md` · `STATUS.md` · `docs/BAKEOFF.md` · `docs/SPEC.md` ·
`docs/METRICS.md` · `docs/illustrator-checklist.md`
