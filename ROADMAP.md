# ROADMAP / TODO

Updated: 2026-10-29. Current verification: **81 passed, 9 expected structural gaps**.
`STATUS.md` records measurements and all nine remaining challenge failures;
`docs/challenges.md` links each PNG to its independent desired SVG.

Legend: [x] verified done · [ ] remaining · P0 validation · P1 next quality work · P2 product/AI · P3 research.

## Done

- [x] Classical pipeline, primitives, containment/completion, named layers, CLI, metrics, bench/report and VTracer comparison.
- [x] Real LM Studio naming/grouping run, beyond mocks; earlier hardware run used `qwen/qwen3.8-27b`. Naming quality and latency remain open below.
- [x] Linear/radial gradient detection and live SVG gradient fills. `shaded`: 5 objects, 1 radial gradient, SSIM 0.9557. Complex occluded gradients remain open.
- [x] Fixture infrastructure: 15 current-behaviour controls and 12 PNG/desired-SVG challenges, including four compositions with 44–64 target objects. Generators: `scripts/make_controls.py`, `scripts/make_challenges.py`, `scripts/make_complex_scenes.py`.
- [x] Interior-text control (`t5_text_on_shape`) and actual edge-crossing lettering challenge (`edge_crossing_type`). Fixture creation is done; text awareness/completion are not.
- [x] Geometry safety: score the full primitive footprint and validate completion containment before restoring observed pixels. Six regression cases in `tests/test_geometry_validation.py`; poster footer and storefront pavement stay rectangular. All eight original sample SVGs unchanged.

## P1 — quality work, in implementation order

Each change needs a focused regression, before/after tests, and rendered `plate bench`
results. Retain VTracer as the control and keep target SVGs independent of PLATE output.

1. [ ] **Preserve thin details during segmentation — next change.** In `stages/segment.py`, retain reliable colour seeds/components when edge detection consumes an entire narrow feature. All 18 gauge ticks currently disappear before tracing; denoising off does not help. Add isolated ticks/slots at several widths and orientations; verify all 18 survive in `complex_instrument_panel`. Protect speckle filtering and antialiased edges.
2. [ ] **Emit editable strokes.** After preserving pixels, fit centrelines and constant width; extend `scene.py`, `pipeline.py` and `stages/emit.py` for stroke width/caps/joins. Verify `stroked_route` becomes an open 16px stroked path with its endpoint circles; recover panel routes/needles/ticks and patch orbits/panel details. Filled outlines do not meet this target.
3. [ ] **Fit shared gradients across occlusion.** In `stages/gradient.py` and completion/order integration, fit compatible fragments separated by supported occluders as one model/full silhouette. `gradient_badge` needs one radial disc, not two; `complex_mission_patch` needs two gradients, currently zero. Keep `twin_gradients` separate and `discrete_palette` at zero gradients. Patch palette caps 16/32/64 gave identical results. Conic/mesh gradients and focal-point fitting remain later work.
4. [ ] **Complete behind multiple edge-crossing occluders.** In `stages/complete.py` / `order.py`, pool supported free-boundary fragments for letters, bars and ribbons. Verify `edge_crossing_type` recovers one full disc (5 total objects, currently 7), then the badge/poster/patch. Preserve the relative T-junction test and containment/occlusion safeguards. Geometric completion can improve independently of OCR.
5. [ ] **Reduce chained-completion drift.** `occlusion_chain` has the right count but its back circle drifts ≈3.5px (full-silhouette IoU ≈0.946). Recover all authored circles within the contract while retaining `overlap` centre/radius error <1px and `stack3` ordering/primitive tests.
6. [ ] **Preserve compound-path topology.** Remove the stray second component from the blue path in `perforated_plate`, retaining its three transparent holes and separate gold island. Check segmentation, silhouette filling, completion, bleed and tracing; do not erase intended small objects to hide the artifact. Extend to overlapping rings and soft alpha edges.
7. [ ] **Improve primitive/curve decisions and corners.** Full-footprint validation is fixed; rounded corners, sharp stars, outlined letters and polygon cleanup remain. Evaluate candidate ranking/corner constraints; merge bevel vertices <3px apart and investigate optional angle/symmetry cleanup. Validate `complex_storefront` and `complex_event_poster`. Poster SSIM is 0.9493; reach ≥0.95 while retaining useful editable structure.
8. [ ] **Expose partial structural progress.** Extend challenge diagnostics beyond the first count mismatch: report missing/extra/split objects, per-object silhouette error, holes, primitive/fill types and paint order. Keep integrity/fidelity checks active for expected gaps. Promote a strict expected failure only when its independent target is met; do not refresh targets from output or loosen contracts to conceal failures.

All four complex structural targets remain unmet: patch **45 target / 55 actual**,
storefront **64 / 68**, panel **59 / 37**, poster **44 / 57**. Better SSIM alone does
not complete these tasks. See the current-gap table in `STATUS.md`.

## P0 — hardware and real-artwork validation (alongside P1)

- [ ] **Illustrator import.** Follow `docs/illustrator-checklist.md`; verify names/layers, nested groups, live primitives, compound holes and `userSpaceOnUse` gradients. Record results and adjust `stages/emit.py` from evidence.
- [ ] **Real-world corpus.** Gather 10–20 logos, clipart and scans in `samples/real/`; run `plate bench samples/real` and record failures. Current benchmark results are synthetic.
- [ ] **Real VLM quality/performance.** Connection/naming/grouping work; improve left/right names, grouping accuracy and one-request-per-shape latency (earlier face run ≈6s/shape). Verify on real images.

## P1 — further robustness

- [ ] Ring/compound-path semantic naming (e.g. "Red ring"); validate `t3_ring` without changing its even-odd topology.
- [ ] Palette pressure: exercise >64 distinct flat colours and k-means in `stages/segment.py`; add a labelled mosaic.
- [ ] Soft alpha edges/shadows: check light/dark backgrounds and preserve opacity rather than baking in a background colour.
- [ ] Scale consistency: run the same authored logo at 1×/2×/4×; compare object recovery and source-coordinate geometry.

## P2 — AI / text

- [ ] Optional SAM-family segmenter for touching same-colour shapes and shaded masks (`stages/sam.py`, optional extra). Keep heavy ML dependencies out of core; verify against bench.
- [ ] VLM object-merge suggestions before tracing (current integration names/groups output; it does not drive geometric reconstruction).
- [ ] VLM preset selection (logo / illustration / lineart).
- [ ] Text detection/grouping: preserve outlined letters in a named text group, optionally OCR. Use the existing interior-text and edge-crossing fixtures; fixture creation is no longer a prerequisite.

## P2 — product

- [ ] `plate trace --open` for Illustrator on macOS; `plate watch DIR`.
- [ ] PDF/AI export via an appropriate exporter (`--format pdf`); verify imported editability.
- [ ] Segmentation disk cache `.plate-cache/` keyed by image hash and configuration.
- [ ] Package/release `plate-svg`; GitHub Actions running pytest on macOS/Linux with rendering checks.
- [ ] Pre-commit/ruff configuration and type checking.

## P3 — research / docs

- [ ] Compare with Illustrator Image Trace and Vectorizer.AI using `docs/METRICS.md`; publish a README table.
- [ ] Document prior art and measured results in a write-up.

## Commit policy

The Git repository already exists. Never commit or push unless Jessica asks.
Preserve existing staged and unstaged work; inspect `git status` before editing.
