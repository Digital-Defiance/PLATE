# ROADMAP / TODO

Updated: 2026-10-29. Current verification: **148 passed, 9 expected structural gaps**.
`STATUS.md` records measurements and all nine remaining challenge failures;
`docs/challenges.md` links each PNG to its independent desired SVG.

Legend: [x] verified done · [ ] remaining · P0 validation · P1 next quality work · P2 product/AI · P3 research.

## Done

- [x] Classical pipeline, primitives, containment/completion, named layers, CLI, metrics, bench/report and VTracer comparison.
- [x] Real LM Studio naming/grouping run, beyond mocks; earlier hardware run used `qwen/qwen3.8-27b`. Naming quality and latency remain open below.
- [x] Linear/radial gradient detection and live SVG gradient fills. `shaded`: 5 objects, 1 radial gradient, SSIM 0.9557. Complex occluded gradients remain open.
- [x] Fixture infrastructure: 15 current-behaviour controls and 15 PNG/desired-SVG challenges, including four compositions with 44–64 objects and three original complex logos with 34–56 objects. Generators: `scripts/make_controls.py`, `scripts/make_challenges.py`, `scripts/make_complex_scenes.py`, `scripts/make_logo_challenges.py`.
- [x] Interior-text control (`t5_text_on_shape`) and edge-crossing lettering challenge (`edge_crossing_type`). Both pass; semantic text grouping/OCR remain open.
- [x] Geometry safety: score the full primitive footprint and validate completion containment before restoring observed pixels. Six regression cases in `tests/test_geometry_validation.py`; poster footer and storefront pavement stay rectangular. All eight original sample SVGs unchanged.
- [x] Thin details and continuous branches: all 18 gauge ticks survive, both panel signal routes are continuous, and 3/5/7px curves remain attached to seeded heads. Repeated stable colours can seed a narrow line even when edge dilation removed every flat pixel; gradient ramps and explicit palettes are protected.
- [x] First editable-stroke implementation: unbranched near-constant-width curves emit open paths with source-scaled width and round caps/joins. Endpoint continuation is restricted to supported later-painted circles. `stroked_route` now passes its independent target (15.5px fit within 16±1px, 4 objects, 25 total anchors). Disable with `--set strokes=false`.
- [x] Shared gradients behind supported occluders when fragments independently complete to matching primitives. The badge passes its target: 5 objects, 1 full radial disc, 20 anchors, current SSIM 0.9924. Shared linear/radial fits, incompatible colours/geometries, unsupported gaps and source scaling have regressions.
- [x] Pool disconnected free-boundary arcs and occluder components without joining their tangents. Same-colour siblings merge only after a supported shared primitive fit. `edge_crossing_type` now passes unchanged: 7 → 5 objects, 55 → 36 anchors, SSIM 0.9914 → 0.9931. Original samples and all VTracer outputs remain byte-identical.

## P1 — quality work, in implementation order

Each change needs a focused regression, before/after tests, and rendered `plate bench`
results. Retain VTracer as the control and keep target SVGs independent of PLATE output.

1. [x] **Preserve isolated thin details during segmentation.** `stages/segment.py` now restores near-palette cores only in components without flat seeds, vetoing explained antialias blends. All 18 gauge ticks survive, with ≥80% coverage both in segmentation and emitted SVG. `tests/test_segment.py` protects several widths/orientations, speckles, transparency and false outlines. Existing circle-stack regression remains green.
2. [ ] **Complete stroke coverage.** Open curved paths and continuous panel routes are implemented. Remaining: straight marks currently retained as live rects/polygons, closed strokes/rings, branched networks, and automatic inference of butt/square caps or other joins. The panel has 2 editable route strokes; its full target requires 27. Keep round-fit rejection for square-ended lettering and variable-width shapes, and verify Illustrator stroke editability.
3. [ ] **Extend shared gradients to harder occlusions.** `gradient_badge` is fixed. The patch's detector omits outer/clamped bands and already absorbs its third crater into a gradient region; joining only the two gradient fragments leaves internal band edges in the fit. Recover coherent bands while retaining hard-edged craters, then use pooled free boundaries for the planet and recover the hull's linear gradient. Keep `twin_gradients` separate and `discrete_palette` at zero gradients. Conic/mesh gradients and focal-point fitting remain later work.
4. [ ] **Extend completion to complex letters, bars and ribbons.** Disconnected contour pooling and flat-sibling merging are implemented; `edge_crossing_type` passes with a full disc and 5 objects. Patch/poster completion remains open, including candidate selection when unrelated objects share a palette colour. Preserve relative T-junctions and containment/hidden-area safeguards. Geometric completion can improve independently of OCR.
5. [ ] **Reduce chained-completion drift.** `occlusion_chain` has the right count but its back circle drifts ≈3.5px (full-silhouette IoU ≈0.946). Recover all authored circles within the contract while retaining `overlap` centre/radius error <1px and `stack3` ordering/primitive tests.
6. [ ] **Preserve compound-path topology.** Remove the stray second component from the blue path in `perforated_plate`, retaining its three transparent holes and separate gold island. Check segmentation, silhouette filling, completion, bleed and tracing; do not erase intended small objects to hide the artifact. Extend to overlapping rings and soft alpha edges.
7. [ ] **Improve primitive/curve decisions and corners.** Full-footprint validation is fixed; rounded corners, sharp stars, outlined letters and polygon cleanup remain. Evaluate candidate ranking/corner constraints; merge bevel vertices <3px apart and investigate optional angle/symmetry cleanup. Validate `complex_storefront` and `complex_event_poster`. Poster SSIM is now 0.9715, but object structure still fails its target.
8. [ ] **Expose partial structural progress.** Extend challenge diagnostics beyond the first count mismatch: report missing/extra/split objects, per-object silhouette error, holes, primitive/fill types and paint order. Keep integrity/fidelity checks active for expected gaps. Promote a strict expected failure only when its independent target is met; do not refresh targets from output or loosen contracts to conceal failures.

Complex logo targets are now available, with fidelity checks active on both backgrounds:
EMBER **51 target / 51 actual**, but shield full-silhouette IoU is only 0.8385;
ORBIT **34 / 60**, with orbital/wordmark fragmentation; ROOT **56 / 52**, with
**0 of 32** intended editable strokes recovered. Use these alongside the existing
scenes for completion, compound paths, gradient separation and stroke work.

All four complex structural targets remain unmet: patch **45 target / 72 actual**,
storefront **64 / 73**, panel **59 / 60**, poster **44 / 83**. Restoring details can
expose additional visible fragments; their completion/merging remains open. Better SSIM alone does
not complete these tasks. See the current-gap table in `STATUS.md`.

## P0 — hardware and real-artwork validation (alongside P1)

- [ ] **Illustrator import.** Follow `docs/illustrator-checklist.md`; verify names/layers, nested groups, live primitives, compound holes and `userSpaceOnUse` gradients. Record results and adjust `stages/emit.py` from evidence.
- [ ] **Real-world corpus.** Gather 10–20 logos, clipart and scans in `samples/real/`; run `plate bench samples/real` and record failures. Current benchmark results are synthetic.
- [ ] **Real VLM quality/performance.** Connection/naming/grouping work; improve left/right names, grouping accuracy and one-request-per-shape latency (earlier face run ≈6s/shape). Verify on real images.

## P1 — further robustness

- [ ] Extend thin-colour discovery to hairlines/fully antialiased features with no stable pre-dilation colour core; retain palette budgets and the gradient-band veto. Continuous panel routes and seeded-head branches are now covered by regressions.
- [ ] Ring/compound-path semantic naming (e.g. "Red ring"); validate `t3_ring` without changing its even-odd topology.
- [ ] Thin occluded rectangles: a narrow bar split by a perpendicular cover can fail hidden-area validation because rasterized perimeter pixels dominate the inferred extra area. Correct pixel-boundary evaluation before changing occlusion thresholds.
- [ ] Palette pressure: exercise >64 distinct flat colours and k-means in `stages/segment.py`; add a labelled mosaic.
- [ ] Soft alpha edges/shadows: check light/dark backgrounds and preserve opacity rather than baking in a background colour.
- [ ] Scale consistency: run the same authored logo at 1×/2×/4×; compare object recovery and source-coordinate geometry. Badge source scaling at a 400px working size passes; reducing work_size to 200 currently loses gradient detection before reconciliation (10 flat objects / 0 gradients).

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
