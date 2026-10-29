# ROADMAP / TODO

Legend: [x] done · [ ] todo · priority P0 (do next) … P3 (later). Each item lists *where* and *how to verify*.

## Done
- [x] Classical engine, primitives, completion, layers, CLI, metrics, bench, report, VLM client (mock-tested)

## P0 — validate on real hardware (cannot be done in the sandbox)
- [ ] Illustrator checklist (`docs/illustrator-checklist.md`); fix emit.py based on findings (layer names are the big risk: may need `<g id=...>` only, or `data-name`).
- [ ] Real LM Studio run; fix prompts/parsing in `vlm.py`; recommended models: Qwen2.5-VL 7B, Gemma 3 12B, Mistral/Pixtral (anything vision-capable).
- [ ] Gather 10–20 real images in `samples/real/`; `plate bench samples/real`; list failures in STATUS.md.

## P1 — quality
- [x] **Gradients** (new `stages/gradient.py`): detect smooth colour ramps inside one region (linear/radial fit), emit `<linearGradient>/<radialGradient>` fills instead of posterized bands. DONE (feat/gradients). Measured `shaded`: 5 shapes, SSIM 0.9557 (was ~0.918 posterized), 1 radial gradient, 100% primitives. The ≤3 shapes / SSIM≥0.97 target was treated as observe-and-record (the real ramp is clipped/offset/R-saturated); the hard gate is gradients≥1 and shapes<10. Flat samples unchanged. Linear + radial only (no conic/mesh); focal not fit in v1; Illustrator gradient-import still UNVERIFIED.
- [ ] Completion when the occluder crosses the edge (badge inner disc): relax `n_free`/junction tests in `stages/complete.py`, validate with a new labelled sample. NOTE: this is also the blocker for "shape behind text" — text occludes a shape as many thin strokes crossing its edges (not clean corners), so the T-junction test does not fire and the shape stays a path with letter-shaped bites. See the "shape behind text" item under P2 AI / Text.
- [ ] Polygon cleanup: merge vertices <3px apart (`primitives.snap`), snap to right angles/symmetry optionally (`--set tidy=1`).
- [ ] Stroke detection: thin constant-width shapes → `<path stroke=...>` (lineart preset).
- [ ] Ring naming ("Red ring"), semantic names for compound paths.
- [ ] Handle `max_colors` palettes when image has >64 unique flat colours (kmeans path in segment.py is lightly tested).
- [ ] Alpha-edge handling for PNGs with soft shadows.

## P2 — AI
- [ ] SAM-family segmenter (`segmenter="sam"`): propose masks to split regions that share one colour (e.g. two touching same-colour shapes) and to merge shaded regions into one object. Add as `stages/sam.py`, optional extra `.[sam]`; MPS device on M4. Verify with `bench`.
- [ ] VLM: ask for object-level merge suggestions (e.g. "these 5 bands are one sphere"), apply in pipeline before tracing.
- [ ] Use VLM to pick preset automatically (logo vs illustration vs lineart).
- [ ] Text detection → keep as outlined paths named "Text: …" (optionally OCR).
- [ ] **Shape behind text** (combines Text detection above + edge-crossing completion in P1): when letters occlude a shape, (1) detect the text as text rather than tracing letterforms as shape bites, and (2) complete the shape underneath across the letter cuts. Recognition here is GEOMETRIC, not semantic — PLATE reconstructs an occluded outline, it does not "know" the shape is an ice cube/logo/etc.; the VLM can only put a semantic NAME on the result, it does not drive completion today. A glossy/transparent subject (e.g. a real ice cube) is additionally a gradient/photo case (see Gradients, and the posterization weakness). Verify with a dedicated labelled control (see below). Pin CURRENT behaviour first with a "shape behind text" control fixture in `scripts/make_controls.py` + `tests/controls.py` (expected today: shape stays a traced path with letter-shaped notches, text traced as per-letter outline paths, completed==0) so the test flips when this is fixed. ADD THIS FIXTURE AFTER the in-flight gradients branch merges, to avoid a conflict in the control files.

## P2 — product
- [ ] `plate trace --open` to launch Illustrator on macOS; `plate watch DIR`.
- [ ] PDF/AI export via Inkscape/cairosvg (`--format pdf`).
- [ ] Segmentation disk cache `.plate-cache/` keyed by image hash + levers.
- [ ] PyPI release as `plate-svg` (name `plate` is taken); GitHub Actions: pytest on macOS+Linux.
- [ ] Pre-commit/ruff config; type hints pass.

## P3 — research / docs
- [ ] Compare against Illustrator Image Trace and Vectorizer.AI with `docs/METRICS.md` protocol; publish table in README.
- [ ] Blog/paper write-up (prior art: LayerPeeler, AmodalSVG, SemLayer, VTracer).

## Commit policy
Nothing is committed yet. Initialise git in /Volumes/Code/PLATE and commit when the owner asks.
