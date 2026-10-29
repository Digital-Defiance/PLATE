# STATUS (update this at the end of every work session)

Last updated: 2026-10-29 (session 2) · Version 0.0.1 · Tests: 24 passing (`pytest -q`)

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
