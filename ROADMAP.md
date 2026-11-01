# ROADMAP / TODO

Updated: 2026-10-31. Final verification: **549 passed, 7 expected structural gaps**;
full robustness sweep **70/78**, core **36/36**. `STATUS.md` records measurements and
all seven remaining challenge failures; `docs/challenges.md` links each PNG to its
independent desired SVG.

Legend: [x] verified done · [ ] remaining · P0 validation · P1 next quality work · P2 product/AI · P3 research.

Owner steering: Jessica explicitly allows scope expansion as useful, provided
every addition and remaining item is recorded here and in HANDOFF. At the current
usage limit, finish a verified checkpoint before starting further expansion.

## Immediate handoff priority — conversion quality (2026-10-30)

Jessica asked for the gaps to be made actionable for the next agent, beyond the
Homebrew executable. Packaging is a separate delivery track; resolve any concrete
installation bug already underway, then work this queue. This latest direction
supersedes older statements deferring all engine work to the hosted service.

1. [x] Fixed the sigma-2 opaque-noise cases (seeds 17/204): the auto-denoise blind
   spot was a global `noise_fraction` estimator confounded by edge density. Added an
   `interior_noise_fraction` estimator (median residual among pixels ≥3px from any
   edge) OR'd into the denoise trigger, plus `Config.interior_noise=0.002`. Both
   cases pass; clean art and other noise levels protected by regression.
2. [x] Worked all 15 stress misses: **7 fixed** (sigma-2 noise ×2, half-size markers
   ×4, blur 0.7px ×1) and **8 remaining default-config limitations** (quarter-size
   route/marker ×4, blur 1.2px ×1, low contrast 1/16 ×1, hairline routes 1/2px ×2),
   each pinned by a test. Sweep **63/78 → 70/78**, core **36/36**, 24 shipped SVGs
   byte-identical in that campaign, no gate weakened. These are algorithm/default
   limits, not proven information-theoretic impossibilities; see the Oct-31 audit.
3. [~] Per-object challenge diagnostics DONE (`tests/challenge_diff.py` +
   `tests/challenge_report.py`; surfaces missing/extra/split/merged, silhouette IoU,
   topology, primitive/fill, paint order past the first count mismatch). STILL OPEN:
   incrementally close the seven complex targets using it — patch, storefront, poster,
   EMBER, ORBIT, ROOT and PLATE identity. ORBIT/EMBER are closest to their targets;
   the common blocker is same-colour organic separation and complex-scene gradient
   bands. PLATE identity's exact hidden geometry is ambiguous (document the limit,
   do not invent it). See HANDOFF's gap table and the detailed P1 backlog below.
   Partial progress Oct-31: EMBER **4/7 strokes**, all whiskers independently pass,
   **455→447 anchors**; complete target still xfail.
   - [ ] Fix false split/merge diagnostics on legitimate overlapping objects:
     identical overlapping back/front rectangles currently report two splits.
   - [ ] Broaden short curved butt-cap controls: an existing accepted fit emits
     round caps for the recorded butt-cap probe. Square-cap guards currently pass.
4. [~] Add the 10–20-image redistributable real corpus and broader independent
   alpha/gradient/occlusion/aspect-ratio/stroke/lettering contracts. Add per-case
   exception recording before fuzzing.
   DONE (generated portion): a redistributable, deliberately messy 14-image
   generated-realistic corpus now ships in `samples/real/` via
   `scripts/make_real_corpus.py`; run it as a diagnostic with
   `plate bench samples/real`, per-image numbers in `docs/REAL-CORPUS.md`. It is
   diagnostic only (no structural oracle, no gate). REMAINING: genuine CC0/PD
   drop-ins (slot + manifest ready in `samples/real/CREDITS.md`) and the broader
   independent structural contracts.
5. [ ] Close ICC/gamma colour-management, pre-decode resource limits and expanded
   native Illustrator editing/hidden-object/hole/4× seam/live-shape validation.

Each implementation must add bug regressions, pass full tests before/after, retain
independent targets/VTracer, and show before/after robustness and rendered bench
results. Current baseline: **36/36 core, 70/78 full sweep, 9/16 structural targets**;
the full suite (latest count in STATUS) does not hide the remaining sweep misses (all
pinned) or the 7 structural gaps. The separate hosted-service milestone below remains
unimplemented, not a reason to skip this authorized quality work. The next front is
item 3 (structural targets). Update this queue and HANDOFF as work lands.

## P1 — bake-off driven (do these first; re-run `plate bakeoff` after each and update `docs/BAKEOFF.md`)

An objective bake-off harness now scores PLATE against other tools on a synthetic corpus with
exact ground truth (`plate corpus` + `plate bakeoff`; method and results in `docs/BAKEOFF.md`).
PLATE ranks first under all five weightings, but the bake-off surfaced concrete weaknesses that
are the highest-value next fixes. Re-run `plate bakeoff bo/corpus/images --truth bo/corpus/truth`
after each change; do NOT tune the composite weights to flatter PLATE — fix the weakness.

- [ ] **JPEG robustness.** JPEG-damaged scenes recover **0/10** occluded objects (SSIM 0.967 vs
  VTracer 0.985 on damaged input); block/ringing noise breaks the T-junction occlusion test in
  `complete._junctions`/`_occludes`. Denoise or smooth contours harder before junction analysis.
  Target: JPEG-variant `hidden_completion` ≥ 0.6.
- [ ] **Same-colour touching objects merge** (colour-only segmentation can't split them): the
  recurring blocker also behind the EMBER/ROOT/storefront structural limits. Split regions at
  concavities / convexity defects, or via SAM (P2). Add corpus scenes that stress this.
- [ ] **Rect/polygon amodal completion** is weaker than circles (occluded rect 4/11, polygon 3/10,
  rrect 5/12 on the corpus). Extend the free edges of a partly-hidden rect/polygon by line
  intersection rather than only fitting on free points. Target overall `hidden_completion` ≥ 0.8.
- [ ] **Add external tools to the bake-off** (`--external DIR` with `IMAGE.TOOL.svg` exports):
  Illustrator Image Trace, Vectorizer.AI, Inkscape trace. Needs a Mac with those apps; record in
  `docs/BAKEOFF.md`.
- [ ] **Real-image bake-off** (20–30 images, no ground truth): run `plate bakeoff` to check the
  synthetic result is not flattering; structure metrics skip and the composite renormalises.
- [ ] **Extend the corpus generator** (`bakeoff/corpus.py`) with gradients, strokes, text-like
  shapes and shadows so these weaknesses stay visible under scoring.

All of these are tracked by `tests/test_bakeoff.py` (which also asserts the ground-truth SVG scores
perfect structure and a cutout-only tool loses completion credit — the method's own safeguards).

## Coverage boundary and quality gates

PLATE is not complete across every meaningful PNG. Its intended launch scope is
logos/icons/diagrams/graphic illustrations, not photographic or painterly image
reconstruction. A successful decode, high render SSIM and correct editable
structure are separate claims. **9/16 authored structural targets pass**; seven
remain strict expected gaps. **24/24 Illustrator workflows and 636 native checks
pass** for the SVGs currently produced; that is interchange validation, not proof
of complete PNG reconstruction. README's coverage table is the public scope.

- [x] Correct actual Illustrator layer import with Adobe namespace markers and
  explicit containers for standalone top-level shapes. Preserve original IDs,
  geometry, stacking, gradients, nested groups and existing-document state.
- [~] Add a representative, redistributable 10–20-image real-artwork corpus,
  tagged by artwork family and difficulty; report per-image failures, not just
  aggregate scores. Independent authored fixtures remain the structural oracle.
  DONE (generated portion): a 14-image generated-realistic corpus ships in
  `samples/real/` (`scripts/make_real_corpus.py`) with a committed per-image
  diagnostic table in `docs/REAL-CORPUS.md`; it is diagnostic only, so the
  independent authored fixtures in `samples/challenges/` remain the structural
  oracle. REMAINING: genuine CC0/PD drop-ins per `samples/real/CREDITS.md`.
- [x] Explicit static PNG decode matrix: all 15 legal colour/depth combinations,
  ordinary/Adam7 rows, tRNS/palette alpha, packing/filter/IDAT cases, exact 16-bit
  transparency, equivalent-encoding traces, hidden RGB, EXIF and selected malformed
  streams. Fix dropped 2/4/16-bit gray and 16-bit RGB keys; normalize all 16-bit
  channels consistently. See `docs/PNG-COVERAGE.md` (111 new cases).
- [x] Document and test current sample/metadata policy: nearest 8-bit reduction,
  EXIF once, ICC/gamma metadata without colour transformation, APNG default/first
  image only. This is not a colour-managed appearance guarantee.
- [ ] Broader PNG colour/robustness work: colour-managed sRGB normalization with
  wide-gamut/grayscale ICC and gamma fixtures; more malformed/chunk/fuzzing cases
  and explicit pre-decode resource limits. Animation reconstruction is outside
  the static-SVG scope. Distinguish decoding from intended display appearance.
- [x] Initial independent scale/rotation/noise/blur/contrast sweep: 78 cases across
  two authored scenes, 36 core + 42 stress, normalized per-object silhouettes,
  topology, detail recall, colour, primitives/anchors and editable strokes, plus
  both-background SSIM. Reproducible input seeds and JSON/HTML evidence. Fix small
  isolated novel-colour loss: core **24→36/36**, full **48→63/78**. See `docs/ROBUSTNESS.md`.
- [x] Worked the 15 measured stress misses: sweep 63/78 → 70/78. 7 fixed (sigma-2
  noise, half-size markers, blur 0.7px); 8 remain default-config failures (quarter-
  size route/marker, blur 1.2px, 1/16 contrast, 1/2px routes), each with measured
  evidence and a pin test, without a proof of impossibility. The .90 per-object coverage gate and all other gates were
  preserved; no shipped SVG changed. Mild-noise denoise detection was the sigma-2 fix.
- [ ] Expand sweeps to real artwork, aspect-ratio extremes, gradients/occlusion
  interactions and more independent geometry. Add per-case exception recording before
  fuzzing. The current two disjoint scenes are not a universal scale/noise guarantee.
- [ ] Broaden meaningful graphic-feature coverage: soft/varying alpha and shadows;
  clamped/nonlinear/elliptical gradients; branching/same-colour decomposition;
  other stroke caps/joins/dashes/widths; lettering and complex completion. Existing
  seven independent gap contracts remain active; inherently unobservable hidden
  geometry must be documented rather than promised as recoverable.
- [ ] Extend native checks to direct gradient-stop edits, isolated hidden shapes
  and compound holes, 4× seam checks and live-shape controls. Linear and radial
  gradient import are covered by the current 24-case suite; live widgets are not.
- [ ] Before broad beta quality claims, publish results by supported artwork
  family, explicit limitations and representative real inputs. Require the
  applicable structural/topology/detail gates and both-background fidelity floors
  to pass for each claimed family. No finite fixture set certifies every PNG.

These validation gates refine the intended product claims. The immediate quality
queue above reflects Jessica's latest direction; the earlier service-first plan
is retained below as a separate product milestone. Photos/textures, exact original
fonts/live text and arbitrary hidden authoring geometry are not launch guarantees.

## Separate product milestone — hosted service (unimplemented)

The product design is a classical hosted service; it is separate from the immediate
quality queue above. [docs/AUDIT.md](docs/AUDIT.md) records the earlier audit and
[docs/SERVICE.md](docs/SERVICE.md) records the product design. Service code is not built.

- [x] Fix low-valued 16-bit PNG normalization; cover zero/dark/full range, both byte orders and legacy Pillow integer-PNG decoding.
- [x] Return a nonzero batch exit status on any failure; retain valid outputs, summarize totals, and cover successful/mixed/all-failed/empty batches.
- [x] Review the existing output-error handler; its permission regression passes. It is included in concurrent release commit `dceaae2`.
- [ ] Build upload → queued, isolated worker → preview/download with explicit byte,
  dimension, time and memory limits; working-size resize is not a decode limit.
- [ ] Add accounts, race-safe daily quotas, anonymous abuse controls, ownership and expiry.
- [ ] Add verified/idempotent Stripe webhooks and supporter entitlement lifecycle.
- [ ] Choose deployment/auth, add container/CI/monitoring and measure worker capacity.
- [ ] Complete Illustrator validation and a representative real-image corpus before beta claims.

Audited baseline full suite: **541 passed/7 xfailed**, including the output-permission and
packaging regressions, 19 audit-bug cases, 26 headless Illustrator/layer cases and
111 PNG-matrix cases and the expanded robustness regressions. See STATUS for the
latest post-change count. Nine of 16 authored structural targets pass;
all 16 meet light/dark fidelity floors. Do not lower contracts to clear the hard tail.

## Done

- [x] Classical pipeline, primitives, containment/completion, named layers, CLI, metrics, bench/report and VTracer comparison.
- [x] Real LM Studio naming/grouping run, beyond mocks; earlier hardware run used `qwen/qwen3.8-27b`. Naming quality and latency remain open below.
- [x] Linear/radial gradient detection and live SVG gradient fills. `shaded`: 5 objects, 1 radial gradient, SSIM 0.9557. Complex occluded gradients remain open.
- [x] Fixture infrastructure: 15 current-behaviour controls and 16 PNG/desired-SVG challenges, including four compositions with 44–64 objects, three original complex logos with 34–56 objects, and the actual 11-object PLATE identity. Generators: `scripts/make_controls.py`, `scripts/make_challenges.py`, `scripts/make_complex_scenes.py`, `scripts/make_logo_challenges.py`, `scripts/make_plate_brand.py`.
- [x] Interior-text control (`t5_text_on_shape`) and edge-crossing lettering challenge (`edge_crossing_type`). Both pass; semantic text grouping/OCR remain open.
- [x] Geometry safety: score the full primitive footprint and validate completion containment before restoring observed pixels. Six regression cases in `tests/test_geometry_validation.py`; poster footer and storefront pavement stay rectangular. All eight original sample SVGs unchanged.
- [x] Thin details and continuous branches: all 18 gauge ticks survive, both panel signal routes are continuous, and 3/5/7px curves remain attached to seeded heads. Repeated stable colours can seed a narrow line even when edge dilation removed every flat pixel; gradient ramps and explicit palettes are protected.
- [x] First editable-stroke implementation: unbranched near-constant-width curves emit open paths with source-scaled width and round caps/joins. Endpoint continuation is restricted to supported later-painted circles. `stroked_route` now passes its independent target (15.5px fit within 16±1px, 4 objects, 25 total anchors). Disable with `--set strokes=false`.
- [x] Straight round-cap recovery from paths and primitive approximations, using antialias/alpha coverage and competing rectangle/ellipse fits. Panel: all 18 ticks and four screw slots pass independent stroke contracts, **24/27 strokes**, anchors **303→259**, SSIM **0.9854→0.9862**. Patch solar cells, storefront paving joints and ROOT name rules also recover as strokes. Square ends, taper and genuine ellipses remain protected.
- [x] Full instrument-panel target: **59 objects / 27 strokes / 249 anchors / SSIM 0.9864**. Recover the three hidden needle terminals using contact, relative T-junctions, free-cap fitting and visible-source validation. Apply paint constraints only for accepted fits; merge the redundant chassis island with safeguards for earlier overpainting. All other benchmark SVGs remain byte-identical to the preceding run.
- [x] Complete thin closed circles/ellipses become native editable strokes. ROOT outer seal independently matches its target: **2→3 strokes, 610→559 anchors, SSIM 0.9806→0.9830**. Full-disc silhouettes, cutouts and thick/nonuniform rings are protected; interrupted loops remain open work.
- [x] Preserve unresolved alpha-contour pixels: a 5px circle improves from four objects/26 anchors to one editable circle/four anchors, SSIM **.9929→.9996**. Restore ORBIT motion curves after polygon snapping; preserve square-ended U and opaque primitives. Seven new regressions; donut SSIM **.9864→.9939**, ORBIT **.9787→.9811**. ROOT now has 51 objects/522 anchors; same-colour decomposition remains unmet.
- [x] Preserve holes containing mostly opaque artwork when a clear transparent core remains. ORBIT's front path now has one hole instead of four false holes; isolated geometry IoU **.1503→.8630**, anchors **603→600**, white/dark SSIM **.9812/.9882**. Fully opaque covers and thin fringes stay protected. Editable ellipse fitting still needs cleaner gradient-crossing segmentation.
- [x] Pool supported interrupted ellipse fragments. ORBIT's mint back orbit now passes its independent target alongside the front orbit, including paint order: **60→57 objects, 4→5 strokes, 539→500 anchors**, SSIM **.9816/.9889**. Both-terminal T-junctions, source coverage and hidden-pixel checks protect narrow/background gaps; visible ownership stays disjoint and reindexed. Twelve new regressions.
- [x] Pool a long visible curve and its small exposed cap under a proven later closed stroke. ORBIT's upper highlight now passes alongside its other six strokes and radial core: **45→44 objects, 352→345 anchors, SSIM 0.9846/0.9925**. Source core/gap checks and explicit occluder paint constraints protect earlier artwork; 22 new cases. Two long fragments, arbitrary covers and unknown ordering remain open.
- [x] Recover a short stable-width curve clipped by a known later native closed stroke. Bounded free-boundary cubic fitting restores ORBIT's lower cream highlight: **5→6 strokes, 357→352 anchors, SSIM .9844/.9923**. Exposed caps, flat-cap source evidence and unsupported gaps are protected; eleven regression cases. Disconnected/two-hidden-cap curves and unknown ordering remain open.
- [x] Recover disconnected affine radial bands around an existing seed with a shared source-colour model, supported full circular geometry and hidden-pixel coverage. ORBIT: **57→45 objects, 500→357 anchors, SSIM .9843/.9922**. Preserve flat/noisy craters and gradient-backed foreground holes; nine new regression cases. Nonlinear/clamped/elliptical ramps remain open.
- [x] Shared gradients behind supported occluders when fragments independently complete to matching primitives. The badge passes its target: 5 objects, 1 full radial disc, 20 anchors, current SSIM 0.9924. Shared linear/radial fits, incompatible colours/geometries, unsupported gaps and source scaling have regressions.
- [x] Pool disconnected free-boundary arcs and occluder components without joining their tangents. Same-colour siblings merge only after a supported shared primitive fit. `edge_crossing_type` now passes unchanged: 7 → 5 objects, 55 → 36 anchors, SSIM 0.9914 → 0.9931. Original samples and all VTracer outputs remain byte-identical.

## P1 — quality work, in implementation order

Each change needs a focused regression, before/after tests, and rendered `plate bench`
results. Retain VTracer as the control and keep target SVGs independent of PLATE output.

1. [x] **Preserve isolated thin details during segmentation.** `stages/segment.py` now restores near-palette cores only in components without flat seeds, vetoing explained antialias blends. All 18 gauge ticks survive, with ≥80% coverage both in segmentation and emitted SVG. `tests/test_segment.py` protects several widths/orientations, speckles, transparency and false outlines. Existing circle-stack regression remains green.
2. [ ] **Complete stroke coverage.** Round-capped straight marks, open curves, aligned hidden straight terminals, closed loops across crossings and supported interrupted ellipses are implemented. Both ORBIT orbital ellipses pass independently: **7/7 strokes**, 44 objects/345 anchors. The panel passes **59 objects/27 strokes**; ROOT outer seal passes (**9/32** total strokes). Both ORBIT highlights now pass beneath the gold loop. Next: EMBER's missing strokes, ROOT's inner ring joined to same-colour leaves (requires decomposition), non-leaf/non-sibling fragments, opaque counters, branched networks and other caps/joins. Preserve full discs, cutouts and real openings; verify Illustrator stroke editability.
3. [ ] **Extend shared gradients to harder occlusions.** `gradient_badge` and ORBIT's affine radial-circle band recovery are fixed. Nonlinear/clamped and general elliptical ramps remain open. The patch's detector omits outer/clamped bands and already absorbs its third crater into a gradient region; joining only the two gradient fragments leaves internal band edges in the fit. Recover coherent bands while retaining hard-edged craters, then use pooled free boundaries for the planet and recover the hull's linear gradient. Keep `twin_gradients` separate and `discrete_palette` at zero gradients. Conic/mesh gradients and focal-point fitting remain later work.
4. [ ] **Extend completion to complex letters, bars and ribbons.** Disconnected contour pooling and flat-sibling merging are implemented; `edge_crossing_type` passes with a full disc and 5 objects. Patch/poster completion remains open, including candidate selection when unrelated objects share a palette colour. Preserve relative T-junctions and containment/hidden-area safeguards. Geometric completion can improve independently of OCR.
5. [x] **Reduce chained-completion drift.** `occlusion_chain` passes: the back disc recovers to (145.1,160.1) r94.6 vs target (145,160) r95 (drift 3.5px→0.1px). Fix: `complete.evaluate` relaxes the occluder-coverage floors only for a primitive fit with RMS ≤ 0.5·tol, so the correct circle is no longer beaten by a boundary-hugging Bézier bridge. `overlap` <1px and `stack3` retained. Commit `ca92bbd`.
6. [x] **Preserve compound-path topology.** `perforated_plate` passes: the blue path is one component with three holes and the gold island is separate. Fix in `order._silhouettes` — re-open a hole-filled region that is predominantly transparent (a real perforation) instead of keeping a floating island's footprint as the shape colour; mostly-opaque fills (shape behind another) are untouched. Commit `ccd6188`. Still open for this theme: overlapping rings and soft alpha edges.
7. [ ] **Improve primitive/curve decisions and corners.** Full-footprint validation is fixed; rounded corners, sharp stars, outlined letters and polygon cleanup remain. Evaluate candidate ranking/corner constraints; merge bevel vertices <3px apart and investigate optional angle/symmetry cleanup. Validate `complex_storefront` and `complex_event_poster`. Poster SSIM is now 0.9715, but object structure still fails its target.
8. [ ] **Expose partial structural progress.** Extend challenge diagnostics beyond the first count mismatch: report missing/extra/split objects, per-object silhouette error, holes, primitive/fill types and paint order. Keep integrity/fidelity checks active for expected gaps. Promote a strict expected failure only when its independent target is met; do not refresh targets from output or loosen contracts to conceal failures.

Complex logo targets are now available, with fidelity checks active on both backgrounds:
EMBER **51 target / 51 actual**, but shield full-silhouette IoU is only 0.8383
(4/7 strokes now recovered; all four whiskers pass independently);
ORBIT **34 / 44**, with compound-emblem/ambiguous-patch fragmentation despite the recovered radial core and all seven strokes; ROOT **56 / 51**, with
**9 of 32** intended editable strokes recovered. Use these alongside the existing
scenes for completion, compound paths, gradient separation and stroke work.

The instrument panel is the first passing large composition (**59 / 59**, 27 strokes).
Three complex scene targets remain unmet: patch **45 target / 72 actual**,
storefront **64 / 73**, poster **44 / 83**. Restoring details can
expose additional visible fragments; their completion/merging remains open. Better SSIM alone does
not complete these tasks. See the current-gap table in `STATUS.md`.

## P0 — hardware and real-artwork validation (alongside P1)

- [x] **Automated Illustrator import/edit/AI roundtrip.** Opt-in `python -m plate.illustrator --output NEW_DIRECTORY`; the full 24-image corpus passes 636 checks in Illustrator 30.8.2. Native names, layers/groups, geometry/order, strokes, linear/radial fills and independently checked edits survive. All render SSIMs ≥.9928. Details: `docs/illustrator-checklist.md`.
- [x] **Actual Illustrator layers.** `i:layer="yes"` in Adobe's 10.0 namespace imports real named layers directly. Standalone roots use layer containers; nested semantic groups remain groups. All 24 render identically before/after; layer names/order and object membership are checked explicitly. Raw imports and AI reopening pass without native postprocessing.
- [x] **Existing-document preservation.** A separate-call native probe verified that the normal runner preserves an already-open copied AI with unsaved changes, marker geometry/colour, active document and interaction setting. Only owned test documents close. Evidence: `/tmp/plate-illustrator-preservation/preservation.json`. An earlier nested wrapper timed out without a visible dialog; cause remains unidentified.
- [ ] **Remaining Illustrator validation.** Live-shape widgets, direct gradient edits, wider opacity/blend inputs, native hidden-shape/hole isolation and high-zoom seams. Inspect app state after any timeout before retrying. The full 24-case run and post-fix preservation test completed normally.
- [~] **Real-world corpus.** Gather 10–20 logos, clipart and scans in `samples/real/`; run `plate bench samples/real` and record failures. Current benchmark results are synthetic. DONE (generated portion): a redistributable, deliberately messy 14-image generated-realistic corpus now ships in `samples/real/` (`scripts/make_real_corpus.py`); run `plate bench samples/real`, per-image results in `docs/REAL-CORPUS.md`. Diagnostic only, no gate. REMAINING: genuine CC0/PD drop-ins (slot + manifest ready in `samples/real/CREDITS.md`).
- [ ] **Real VLM quality/performance.** Connection/naming/grouping work; improve left/right names, grouping accuracy and one-request-per-shape latency (earlier face run ≈6s/shape). Verify on real images.

## P1 — further robustness

- [ ] Extend thin-colour discovery to hairlines/fully antialiased features with no stable pre-dilation colour core; retain palette budgets and the gradient-band veto. Continuous panel routes and seeded-head branches are now covered by regressions.
- [ ] Ring/compound-path semantic naming (e.g. "Red ring"); validate `t3_ring` without changing its even-odd topology.
- [ ] Thin occluded rectangles: a narrow bar split by a perpendicular cover can fail hidden-area validation because rasterized perimeter pixels dominate the inferred extra area. Correct pixel-boundary evaluation before changing occlusion thresholds.
- [ ] Palette pressure: exercise >64 distinct flat colours and k-means in `stages/segment.py`; add a labelled mosaic.
- [ ] Extend the implemented flat-region opacity/faint-object support to nonuniform alpha/shadows; validate both backgrounds.
- [ ] Scale consistency: run the same authored logo at 1×/2×/4×; compare object recovery and source-coordinate geometry. Badge source scaling at a 400px working size passes; reducing work_size to 200 currently loses gradient detection before reconciliation (10 flat objects / 0 gradients).

## P2 — optional naming/grouping and text

Current architecture: classical CPU geometry, no GPU/heavy ML; VLM naming/grouping
is optional and off by default. Earlier SAM, VLM geometry-merge and VLM preset
ideas are parked, requiring Jessica's explicit change of direction before work.

- [ ] Improve optional VLM naming/grouping quality and latency without changing geometry.
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
