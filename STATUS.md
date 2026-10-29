# STATUS (update this at the end of every work session)

Last updated: 2026-10-29 (session 3) · Version 0.0.1 · Tests: 39 passing (`pytest -q`)

## Gradients (new this session — feat/gradients worktree)
Smooth colour ramps inside one region are now detected and emitted as real SVG
`<linearGradient>` / `<radialGradient>` fills instead of posterized flat bands. New stage
`src/plate/stages/gradient.py` runs BETWEEN `segment()` and `order.build()`: it groups
adjacent thin same-family bands (adjacency + Lab dE), gates them conservatively, fits a
linear or radial model, and merges a confident set into ONE `Shape` carrying a
`GradientFill`. A gradient fill and a snapped primitive are orthogonal — a shaded disc comes
out as a live `<circle>` that also carries `fill="url(#...)"`.

- **Measured on `samples/shaded.png` (observe-and-record, NOT a hard gate):** 5 shapes,
  1 radial gradient, SSIM **0.9557** (was ~0.918 when posterized into ~12 flat bands),
  100% primitives, completed 0. The design's ≤3-shapes / SSIM≥0.97 aspiration was left as
  observe-and-record because the real ramp is clipped/offset/R-saturated; the enforced test
  asserts only gradients≥1 and shapes<10.
- **No flat-art regression (verified via `plate bench samples`):** badge 10, donut_alpha 2,
  face 8, overlap 3, stack3 4, ui_card 5 — identical shape counts and SSIM to before. The
  vtracer baseline (`baseline.py`) is untouched. Flat control goldens are byte-identical
  (empty `<defs>` is never emitted; only the 3 new gradient controls got fresh goldens).
- **MUST-FIX #1 (stop count vs min bands) settled in code:** emitted stops are sampled from
  the fitted curve at a FIXED set of `GRAD_STOPS=7` bins over the axis parameter, so the stop
  list is well-defined for ANY admitted region regardless of source band count. The
  `grad_min_bands` admission gate counts *source* bands and is independent of the stop count.
  Covered by `test_stop_count_independent_of_band_count` (min-bands region and many-bands
  region both yield a valid ordered 2..7-stop list).
- **MUST-FIX #2 (radial fit objective) settled in code:** the radial centre search passes a
  per-pixel VECTOR residual to `scipy.optimize.least_squares` (observed centred luma minus a
  closed-form affine prediction from the normalized radius), not a scalar. Verified the radial
  fit converges on the `shaded` sphere (bench above) and on the `t3_radial_grad` control, and
  `test_radial_recovers_center_and_radius` asserts the fitted centre/radius land within ~1.5px
  of ground truth for a synthetic radial gradient.
- **New config levers (`config.py`):** `gradients` (bool, default True), `grad_max_residual`
  (0.06), `grad_min_bands` (6), `grad_min_frac` (0.00017), `grad_band_max_frac` (0.15),
  `grad_step_de` (14.0). Each is automatically a `--set` flag and TOML key.
  NOTE/DEVIATION: `grad_band_max_frac` is **0.15**, not the design's 0.0017. Verified by
  running — the actual `shaded` PNG (400×400, never upscaled) posterizes into ~12 chunky
  bands (2–23% of canvas), so a 0.0017 (≈0.17%) gate made detection a guaranteed no-op on the
  one sample it must fire on. A sweep showed 0.15 admits the ramp (shaded fires 1 radial
  gradient) while EVERY flat sample/control stays at zero gradients; the real flat-art guard
  is `grad_min_bands` (flat art never yields ≥6 dE-adjacent monotone bands), proven by the
  `test_detect_no_regression_on_flat_controls` test. Rationale documented inline in config.py.
- **New controls:** `t3_linear_grad` (linear rect → 1 linearGradient, SSIM 0.9922),
  `t3_radial_grad` (radial disc → 1 `<circle>` with radialGradient, SSIM 0.9893),
  `t4_grad_behind_circle` (gradient box behind a solid circle → ONE full gradient rect with
  NO hole, circle painted on top, SSIM 0.9918). The no-hole / paint-order guarantee is pinned
  by a bespoke assert branch in `test_controls.py`.
- **Limitations:** linear + radial only (no conic/mesh); focal point not fit in v1 (`None`);
  the background linear ramp on `shaded` (only 4 bands, < grad_min_bands) is NOT merged.
  Whether Illustrator imports a `userSpaceOnUse` gradient on a live `<circle>`/`<rect>` as an
  editable fill is UNVERIFIED (goes on the Illustrator checklist).

### Verification commands run this session (worktree, Python 3.11 venv)
- `PYTHONPATH=src DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q` → **39 passed**.
- `… plate bench samples -o /tmp/grad_bench` → shaded 5 shapes / SSIM 0.9557; flat samples unchanged (see above).
- `… plate trace samples/shaded.png -o /tmp/shaded.svg` → contains a `<radialGradient>`.
- `t4_grad_behind_circle` golden confirmed: one full `<rect ... fill="url(#...)">` (no evenodd,
  no hole) with the `<circle>` as a sibling painted after it.

## Works (verified in the sandbox with synthetic images)
- Full classical pipeline: segment → tree → occlusion → amodal completion → order → primitives → Bézier → named layered SVG.
- Ground-truth checks: hidden circle recovered to <1px (tests/test_pipeline.py); 3-circle stack ordering; ellipse orientation; annulus → 2 circles.
- Auto denoise (bilateral) for noisy/JPEG input.
- CLI: trace, batch, sweep, bench, doctor, `--set lever=value`, `--report`, sidecar `.plate.json`.
- **CONTROL regression suite (new this session)**: `scripts/make_controls.py` generates 11 synthetic PNGs in 5 complexity tiers (T1 trivial → T5 hard); `tests/controls.py` holds the ground-truth contract; `tests/test_controls.py` asserts the structured `Result` (object counts, primitive types, params within tolerance, layer names, paint order, nesting), enforces a per-tier SSIM floor when a renderer is present, and keeps a soft golden-SVG diff (`tests/golden/controls/`, `PLATE_UPDATE_GOLDEN=1` to refresh). All 11 clear their SSIM floor (worst 0.982).

## Verified on real hardware THIS SESSION (macOS M-series, Python 3.11 venv)
- **Real LM Studio VLM path works end to end** (was mock-only before). `plate doctor --vlm-url http://localhost:1234/v1` lists loaded models; `plate trace samples/face.png --vlm-url ... --vlm-model qwen/qwen3.8-27b` produced semantic names (Face, Mouth, Tongue, Left/Right Eye, Eye Highlight) AND semantic groups (eyes = eyeball+highlight) as nested Illustrator `<g>` layers. SSIM 0.993.
- `qwen/qwen3.8-27b` is vision-capable and works for both naming and grouping. `qwen2.5-coder-7b` is text-only (HTTP 400 on images). Embedding models are skipped by the new auto-selector.
- `cairosvg` rendering now works on this machine (so `bench`/`--report`/sweep report SSIM). Required `brew install cairo` (already present) PLUS the dyld fix below.

## Fixed this session
- **`plate doctor` crashed** when an optional dep is installed but unusable (cairosvg importing but failing to load libcairo raised `OSError`, not `ImportError`, so the old `except ImportError` missed it and doctor died before checking LM Studio). Now catches any exception and reports BROKEN/optional; probes cairosvg through the renderer helper.
- **cairosvg could not find libcairo on macOS/Homebrew.** cairocffi's dlopen doesn't search `/opt/homebrew/lib`, and SIP strips `DYLD_*` across protected binaries, so it must be set before process start. `cli.main` now re-execs itself once (guarded by `PLATE_DYLD_REEXEC`) with `DYLD_FALLBACK_LIBRARY_PATH` pointing at the Homebrew cairo dir (`raster.cairo_lib_dirs` / `ensure_dyld_cairo`). Added `src/plate/__main__.py` so `python -m plate` is a valid re-exec target. Renderer now "just works" via the CLI.
- **VLM grouping intermittently failed** with "no JSON in reply". Root cause: Qwen3 is a reasoning model and wraps/precedes JSON with `<think>…</think>` blocks and prose. Hardened `vlm._json` to strip think-blocks and code fences and extract the first *balanced* `{...}`/`[...]`. NOTE: `response_format: json_object` is NOT used — LM Studio returns HTTP 400 for it on this model.
- **VLM model auto-selection was blind** (`models[0]`). New `vlm.pick_model` skips obvious non-vision models (embedding/rerank/tts/etc.) and `describe` logs which model it used and warns when zero names come back. Explicit `--vlm-model` still wins.

## NOT verified / unknown (do these next on the Mac)
1. **Illustrator import**: do top-level `<g>` become layers with the right names? Are circles/rects editable live shapes? Follow `docs/illustrator-checklist.md` and record results here. (STILL the main open P0 — needs a human in Illustrator.)
2. **Real-world images** (logos, clipart, scans). Only synthetic samples tested. Collect 10–20 real ones into `samples/real/` and run `plate bench`.
3. VLM naming quality: the model names both eyes "Left Eye" (dedupe suffixes → "Left Eye 2") rather than distinguishing left/right; naming is ~6s/shape (one request per shape → 47–65s for the face). Prompt/throughput tuning is open.

## Known weaknesses
- Gradients/shading/photos get posterized into flat bands (by design for now; see ROADMAP "Gradients"). THIS IS THE NEXT PLANNED FEATURE.
- Occluder with a bar crossing a circle's edge (badge inner disc) → no completion, stays a Bézier path.
- Triangle apex can get 2 vertices (bevel from blur); polygon snap keeps them.
- Noisy input: ring edges slightly wobbly after denoise; SSIM 0.87.
- Naming a ring/annulus says "Red shape" (could be "Red ring"). Ring/annulus currently stays a single even-odd path, NOT two `<circle>`s (pinned as a known-behaviour control in `t3_ring`).
- SAM segmenter not implemented (config `segmenter` accepts only "classical").
- No disk cache for segmentation; large images (>3000px) are downscaled to `work_size` (1536) for analysis, output is rescaled.
- Uncommitted: nothing has been `git commit`ted yet.

## Env notes for the next session
- venv at `.venv` (Python 3.11 via `python3.11`); system python is 3.9 which is too old. `pip install -e ".[dev,render]"` done.
- `cairo` is installed via Homebrew; the CLI handles the dyld path itself. If you call the library directly (not via `plate`), prefix with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
- LM Studio reachable at `http://localhost:1234/v1`; use `--vlm-model qwen/qwen3.8-27b` (vision-capable). Load a vision model before expecting names.
