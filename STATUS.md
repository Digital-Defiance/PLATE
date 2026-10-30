# STATUS (update this at the end of every work session)

Last updated: 2026-10-29 (session 13, chained drift + compound-path topology fixed) · Version 0.0.1 · Tests: 150 passing, 7 expected feature gaps (`pytest -q`)

## Compound-path topology (session 13)

- Fixed `perforated_plate`: `order._silhouettes` hole-filled a shape and removed
  only transparent pixels, so a genuine perforation containing a floating opaque
  island (the middle hole holds a gold disc) kept the island's footprint as the
  plate colour — a stray 749px component inside the hole. Now each hole-filled
  region is checked before transparency removal: a predominantly-transparent
  region (>50%) is a real perforation and is re-opened in full (dropping the few
  island pixels); mostly-opaque regions (a shape genuinely sitting behind another,
  e.g. a background under on-top shapes) stay filled, so paint-order coverage is
  unchanged. A naive "drop all foreign newly-filled pixels" rule regressed every
  background and was rejected.
- Blue plate: 2 components → 1, three holes preserved, gold island separate.
  Promoted from strict xfail. overlap/stack3/donut(evenodd ring)/badge/ui_card
  byte-identical. Suite **150 passed, 7 xfailed**. Committed `ccd6188`.


## Chained-completion drift (session 13)

- Fixed `occlusion_chain`: the back disc completed via a Bézier bridge (drifted to
  (141.5,160.5) r93.1 vs target (145,160) r95) because its correct circle fit —
  RMS 0.25, 226° arc — was rejected by `complete.try_complete`'s occluder-coverage
  gate at 89.6% vs the 90% floor. A disc hidden by a same-size neighbour legitimately
  recovers a ~10% sliver past the occluder. `evaluate()` now relaxes the coverage
  floors (Cm 0.90→0.85, Cv 0.70→0.65) ONLY for a primitive with RMS ≤ 0.5·tol; the
  bridge and weak fits keep the strict floors, so a shape still cannot complete into
  a mere neighbour. Back disc now (145.1,160.1) r94.6 — drift 3.5px→0.1px.
- Promoted `occlusion_chain` from strict xfail to passing. `overlap` circle stays
  within 1px, `stack3` ordering/anchors unchanged; original samples unaffected.
  Suite **149 passed, 8 xfailed** (was 148/9). Committed `ca92bbd`.


## Current remaining work — start here

Geometry safety, thin-detail recovery and initial open-stroke support are complete.
All 18 ticks survive; both panel routes are continuous editable strokes. The
independent `stroked_route`, `gradient_badge` and `edge_crossing_type` targets pass.
The badge has one full radial disc behind its ribbon, and the lettering has one
full disc behind its three letters. Three original complex logo fixtures are now
generated and checked in the working tree (34–56 target objects). The nine strict expected failures below
remain open; they are desired structural targets, not pipeline crashes.
Appearance/integrity checks remain active. Current scene SSIM: mission patch
**0.9815**, storefront **0.9738**, instrument panel **0.9854**, poster **0.9715**.
All four clear 0.95 on white and dark backgrounds. Current regression floors:
patch/panel 0.97, storefront/poster 0.96. Structural targets remain unmet; historical
sections below retain their earlier measurements.

Implementation order (details and acceptance checks in `ROADMAP.md`):

1. Extend stroke coverage beyond open curves: straight primitives/ticks, closed loops, branched networks and automatic cap/join inference. The panel currently has 2 of its 27 desired strokes.
2. Recover hairlines/fully antialiased colours without stable cores; repeated stable new colours and seeded-head curves are already supported.
3. Extend shared gradients to fragments without independently completed primitives; the mission patch remains split. Retain separate ramps/flat swatches.
4. Extend the implemented contour pooling/flat-fragment merging to complex letters/ribbons and reduce chained-circle drift.
5. Preserve holes/components, then refine corners, primitive selection and complex object recovery.
6. Improve per-object failure diagnostics so partial progress is visible despite count mismatches.

| Remaining challenge | Current failure / required target |
| --- | --- |
| `complex_mission_patch` | 72 objects / 2 radial fragments; target 45 with one radial planet + one linear hull, correct occlusion/strokes/cutouts |
| `complex_storefront` | 73 objects; target 64, retaining repeated windows, awning panels, lettering, curves and small details |
| `complex_instrument_panel` | 60 objects; ticks visible and both routes are editable strokes, but target 59 requires 27 strokes overall |
| `complex_event_poster` | 83 objects; fidelity 0.9715 and one gradient, but target 44 still needs full underlying shapes, holes, strokes and lettering |
| `logo_ember_crest` | 51 objects matches count, but shield silhouette IoU 0.8385; 2 of 7 editable strokes recovered |
| `logo_orbit_wordmark` | 60 objects vs target 34; gradient/orbital emblem and outlined lettering fragment; 3 of 7 strokes |
| `logo_root_seal` | 52 objects vs target 56; touching organic shapes merge and 0 of 32 strokes recovered |

Still unverified: Illustrator layer/live-shape/gradient import and a 10–20-image
real-world corpus. Real LM Studio naming/grouping **is verified**; naming accuracy
and request latency remain work. Other deferred items (palette pressure, soft
alpha/shadows, scale consistency, optional SAM/text, product/export/release) remain
tracked in `ROADMAP.md`.

Session 7 (historical) changed documentation only: reconciled completed work, added the full
remaining queue, corrected stale gradient/VLM/text-fixture/Git notes, and retained
earlier measurements as history. Full suite before/after: **81 passed, 9 xfailed**.

## Complex logos and handover (session 12)

- Finished three original, deterministic logo designs, each with independently
  authored `.target.svg` and a transparent RGBA PNG rendered at 4× then downsampled.
  Files are in `samples/challenges/`; `scripts/make_logo_challenges.py` regenerates
  them without fonts, external assets, models or PLATE output. The images are done;
  the next agent does not need image-generation capability.
- **EMBER:** 800×960 fox crest, faceted face, 12 laurel leaves, four true shield
  cutouts, layered ribbon and outlined lettering; **51 objects / 7 strokes**.
- **ORBIT:** 1200×480 wordmark, off-centre radial gradient, compound monogram,
  crossing orbital ellipses, satellites, motion lines and small details;
  **34 objects / 1 gradient / 7 strokes**.
- **ROOT:** 900×900 tree seal, 15 organic leaves and veins, branches/roots,
  counter-cut trunk, closed circular strokes and outlined name;
  **56 objects / 32 strokes**, zero gradients.
- Pipeline baseline, white/dark SSIM: EMBER **0.9662 / 0.9678** (51 objects,
  472 anchors); ORBIT **0.9787 / 0.9846** (60 / 617); ROOT **0.9784 / 0.9836**
  (52 / 902). All structural targets remain unmet as specified in the current
  table. New fidelity floors: EMBER 0.96, ORBIT/ROOT 0.97, active on both backgrounds.
- Added the three strict structural gaps and nine artwork checks for exact target
  inventory, portable vector assets, dimensions, transparent negative spaces and
  pixel-identical target/PNG pairing. Full suite at that point **148 passed, 9 xfailed**
  (baseline **133/6**). Existing targets and pipeline code were not changed this session.
- Ran `plate bench samples/challenges -o /tmp/plate-logo-bench` with VTracer intact.
  Inputs were visually reviewed together in `plate-complex-logos.png` in this
  chat's visualization folder. Baseline JSON: `/tmp/plate-logos/baseline.json`.
- Prepared `HANDOFF.md` with exact state, reproduction commands, pending changes
  and priorities. No new commit or push. Previous completion work and all new logo
  assets remain uncommitted; current HEAD is `4da8ab0`.

## Disconnected boundaries and flat fragments (session 11)

- Committed the verified shared-gradient work as `4da8ab0`
  (`fix: merge compatible gradient fragments behind occluders`), as requested.
  No push. This session's new completion work remains uncommitted.
- `complete.try_complete` previously kept only the largest outline of each shape
  and occluder. It now pools free points from all external contours, preserving
  per-component tangent/junction calculations and the relative 15° test. Hole
  contours are excluded by winding. Bézier bridging stays restricted to one
  contour; separate contours are never joined by an invented tangent segment.
- `order.merge_fragments` proposes same-colour flat siblings as one object only
  when the union passes primitive fitting, visible containment and hidden-area
  support. `Segmentation.rebuilt` centralizes ID/ownership rebuilding and clears
  stale tree/completion fields. Pipeline recomputes order after each accepted merge.
- **`edge_crossing_type` now passes its unchanged independent target:** 7 → **5
  objects**, 55 → **36 anchors**, 2 → **3 live primitives**, one complete cyan disc
  behind all three letters. SSIM **0.9914 → 0.9931** on white and dark backgrounds.
  The badge also improves **0.9922 → 0.9924** by fitting both visible arcs.
- Six new regression cases cover a disc visible in four arcs, disconnected
  occluder pieces, full paint order after merging, unsupported gaps, a visible
  outlier and the completion switch. Full suite **133 passed, 6 xfailed**
  (baseline **126/7**). No target SVGs or goldens changed.
- Ran both original/challenge benchmarks. Rendered the lettering output and its
  isolated underlying geometry, plus all eight original samples. Only the
  lettering and gradient-badge PLATE SVGs change; every other output, including
  VTracer, is byte-identical. Review sheets: `plate-fragment-completion.png` and
  `plate-fragment-original-samples.png` in this chat's visualization folder.
  SVGs: `/tmp/plate-fragments-{samples,challenges}`.
- Mission-patch diagnosis: several omitted outer bands are actual gradient pixels
  despite sharing palette colours with craters. The third crater at (515,470) is
  already absorbed into a detected gradient. Simple colour-based growth would
  lose object boundaries; band recovery must preserve flat crater silhouettes.
  Pooling only the two detected gradient fragments still fails safely. Patch
  remains **72 objects / 2 radial fragments / SSIM 0.9815**; full target is open.
- Additional conservative limitation: a thin flat bar split by a perpendicular
  cover can be rejected because primitive rasterization adds perimeter pixels
  outside the cover. Track pixel-boundary evaluation in `ROADMAP.md`; hidden-area
  and containment thresholds were not relaxed to force a merge.

## Shared gradients across supported occlusion (session 10)

- Committed the previously verified thin-detail/curve/stroke work as `03a133f`
  (`feat: recover thin curves and editable SVG strokes`), as requested. No push.
- Added a post-order reconciliation pass in `stages/gradient.py`. Gradient fragments
  must independently complete to matching primitives (≥0.97 full-model IoU), then
  their union must pass fresh relative T-junction, containment and hidden-area
  checks. A pooled fit uses original RGB pixels; each fragment must retain its
  colour fit within the configured residual and 0.01 of its independent fit.
  Rebuild IDs, ownership and all order/completion fields after each accepted merge.
- **`gradient_badge` now passes its independent target**, unchanged: 6 → **5 objects**,
  2 → **1 radial gradient**, 24 → **20 anchors**. Recovered circle in source SVG
  coordinates: centre ≈(200.23, 180.09), radius ≈134.73 versus (200, 180), 135.
  White/dark SSIM **0.9922** (previous duplicate-disc output 0.9936); the structural
  improvement has a small fidelity tradeoff. The full-silhouette/paint-order
  contract passes at native size and with a 2× source reduced to 400 working pixels.
- Eleven new regressions cover the target/source scaling, shared linear/radial
  ramps, incompatible colours/geometries, unsupported gaps and completion disabled.
  Promoted the badge from strict xfail; suite **126 passed, 7 xfailed** (baseline
  **114/8**). No target SVGs or goldens changed.
- Ran `plate bench samples` and `plate bench samples/challenges`; rendered and
  inspected the badge and all original sample SVGs. Every other benchmark SVG,
  including VTracer controls, is byte-identical to the previous verified run.
  Review: `plate-shared-gradient.png` and `plate-gradient-original-samples.png`
  in this chat's visualization folder; SVGs in `/tmp/plate-gradient-{samples,challenges}`.
- Remaining: mission-patch planet fragments have no individually completed
  primitives, so this merge correctly leaves them unchanged (72 objects, 2 radial
  fragments). Joint free-boundary completion and the hull's linear gradient remain
  open. A 200px badge working-size probe produces 10 flat objects / 0 gradients
  before reconciliation; track this under resolution consistency rather than claim
  gradient recovery at every scale. These were the seven structural gaps at that session.

## Continuous curves and editable strokes (session 9)

- Extended `segment.py` recovery to distant branches of partially seeded regions.
  Require a repeated solid core so smooth gradient bands keep coherent assignments.
  Palette discovery also examines stable pre-dilation cores, admitting repeated
  new colours within the existing budget while respecting explicit palettes.
  Both curved panel signal routes now form single continuous colour regions;
  3/5/7px branches stay attached to their seeded heads.
- Added `stages/strokes.py`: numpy thinning, unbranched-chain checks, subpixel
  cross-section centring, width validation, open Schneider fitting and full-mask
  reconstruction checks. Reject holes, meaningful junctions, taper and poor fits.
  Round-cap/join detection currently runs on nonprimitive, nongradient path
  candidates; existing live primitives remain primitives.
- `Node` and the emitter now carry width/cap/join styles. Pipeline converts widths
  and centreline coordinates back to source pixels and continues aligned terminals
  only beneath touching, later-painted circles. A detached-circle regression
  prevents invented visible connections; terminal contact is checked through the
  antialias halo. Stats/metrics include `strokes`.
  `Config.strokes=True` is default; `--set strokes=false` disables recovery.
- Promoted **`stroked_route` from strict xfail to passing**, without changing its
  independent target: one open 15.5px stroke within the 16±1px contract, full
  hidden endpoints, 4 objects and **25 anchors vs 36 before**. SSIM **0.9913**
  (previous filled outline 0.9917); editability/full target now pass.
- Current complex results: panel **60 objects / 2 strokes / SSIM 0.9854**
  (was 61 / 0 / 0.9788), patch **72 / 1 stroke / 2 radial fragments / 0.9815**,
  storefront **73 / 0.9738**, poster **83 / 1 gradient / 0.9715**. Dark SSIM:
  panel 0.9854, patch 0.9830, storefront 0.9752, poster 0.9715.
- Regression coverage: five continuity cases, fourteen stroke cases (6/12/16px
  curves, scaling, disable switch, explicit palette, integer coordinates, occluded
  target, nonstroke rejection and styles/metrics), plus a poster-gradient guard.
  A broad initial branch fallback lost that gradient; solid-colour confidence
  checks fixed it. Square-ended wide lettering is not approximated by round caps.
- Full suite **114 passed, 8 xfailed**, baseline 93/9. `plate bench samples` and
  `plate bench samples/challenges` run with the unchanged VTracer control. Original
  flat structural tests remain green; badge SSIM 0.9441→0.9492, face 0.9929→0.9919,
  noisy badge 0.8675→0.8674 (small fidelity changes recorded, not hidden).
- Visually inspected all originals, complex outputs, panel/routes and two changed
  control goldens. Refreshed only `t2_two_circles` (≈0.1px fit changes) and
  `t5_text_on_shape` (C/E fragments reconnect into letters). No OCR/text grouping
  was added; all desired target SVGs remain unchanged. Nothing committed/pushed.
- Remaining: full stroke coverage, shared gradient reconstruction, lettering/chain
  completion, holes/components and complex object recovery, plus Illustrator import
  and real artwork validation. Automatic detection still assumes round caps/joins;
  the emitter supports explicit alternative styles for future models.

## Isolated thin-detail recovery (session 8)

- `stages/segment.py` now restores near-unmixed existing palette colours when an
  entire isolated component lacks flat seeds. A wider local two-colour explanation
  vetoes antialias blends. Components already containing flat seeds retain their
  original assignments; this restriction preserves the three-circle stack that
  an earlier, broader prototype regressed. Re-estimate coverage around restored
  cores through the resampling halo; normal transparency/speckle cleanup remains.
- Restored the corrected implementation and `tests/test_segment.py` after the
  unfinished files were removed and later reappeared during the session. Verified
  the corrected variant in a temporary copy before applying it to the workspace.
- Twelve regression cases: 3/5/7px marks at 0/45/90°, false grey-outline veto,
  transparency/speckle safeguards, and all **18 panel ticks**. The real-panel test
  requires ≥80% coverage per tick in both segmentation and rendered SVG; measured
  emitted coverage is **82.6–84.5%**, versus zero before. Stroke output is not yet
  implemented; preserving a filled tick does not satisfy the full panel contract.
- Bench before → after SSIM: panel **0.9666 → 0.9788** (37 → 61 objects), patch
  **0.9628 → 0.9809** (55 → 78), storefront **0.9623 → 0.9699** (68 → 76), poster
  **0.9493 → 0.9685** (57 → 85). More restored regions can expose additional
  fragments; desired object counts/target SVGs remain unchanged. Patch now emits
  **2 radial planet fragments**, not the target radial-planet/linear-hull pair.
- Dark-background SSIM: patch **0.9825**, storefront **0.9708**, panel **0.9788**,
  poster **0.9685**. Tightened regression floors to 0.97 patch/panel and 0.96
  storefront/poster. The nine expected structural failures remain open.
- `plate bench samples`: seven original sample SVGs remain byte-identical; badge
  improves **0.9435 → 0.9441**, anchors **86 → 71**. Hidden-circle/stack tests stay
  green; VTracer untouched. Visually reviewed panel before/after, all original
  samples and the sole changed control golden (`t4_badge`: plaque width 161 → 160,
  dot radii closer to authored 15px). Refreshed only that reviewed soft golden.
- Full suite: **93 passed, 9 xfailed**, versus baseline 81/9. No commits/pushes.
  Remaining narrow curved/attached branches and missing-palette-colour discovery
  are explicitly tracked before editable stroke recovery.

## Geometry validation fixes (session 6)

- Fixed **cropped primitive scoring** in `stages/primitives.py`: candidate error
  now includes the full primitive footprint, rather than clipping it into the
  source mask crop. Rotated ellipse bounds are analytic; polygon/rect bounds
  follow their raster vertices. Reject non-finite fits and comparisons exceeding
  twice the source dimensions before allocating an expanded raster.
- Fixed **ineffective completion containment check** in `stages/complete.py`:
  reject models that exclude >3% of the observation BEFORE unioning in observed
  pixels. Existing relative T-junction logic and acceptance thresholds retained.
- Added 6 regression cases in `tests/test_geometry_validation.py`. Before fixing:
  4 failed / 2 passed, reproducing oversized ellipses on long rects, an accepted
  completion model discarding visible pixels, and the complex poster footer.
  After fixing: all pass; valid completion remains accepted.
- `plate bench samples/challenges`: poster **SSIM 0.9283 → 0.9493**, footer now a
  live rect (rx=420, ry=50) instead of an ellipse (rx≈663). Storefront **0.9515 →
  0.9623**, pavement stays rectangular, anchors **576 → 567**. Panel **0.9665 →
  0.9666**; mission patch unchanged **0.9628**. Object counts remain unchanged;
  full challenge contracts still have nine expected gaps. Raised regression SSIM
  floors to **0.95 storefront / 0.94 poster** to protect the measured gains.
- `plate bench samples -o /tmp/plate-geometry-after-samples`: all eight original
  PLATE SVGs are **byte-identical** to the previous session. VTracer baseline
  untouched. Visually inspected before/after renders and all original outputs.
- Full suite before: **75 passed, 9 xfailed**. After: **81 passed, 9 xfailed**,
  renderer enabled and localhost allowed for the mock VLM server. `git diff
  --check` clean. No commit/push; existing staged and unstaged work preserved.
- Next focused fix: preserve the 18 missing gauge ticks in segmentation, then
  recover stroke centreline/width. Gradient and edge-crossing completion work
  remains as described in `docs/challenges.md`.

## Complex PNG compositions (session 5)

- Created **four large compositions with independently authored target SVGs** in
  `samples/challenges/`: mission patch (960×960, 45 target objects), storefront
  (960×800, 64), instrument panel (960×800, 59), event poster (960×960, 44).
  `scripts/make_complex_scenes.py` reproducibly authors and rasterizes them at 4×
  with Lanczos downsampling. Lettering is custom outlined geometry; no font/assets
  are required. All target objects have visible pixels (audited by isolated masks).
- Added contracts to `tests/challenges.py` and source artwork protections in
  `tests/test_complex_scene_assets.py` (object/gradient/stroke counts, image sizes,
  portable vector content, and nine genuine transparent mission-patch cutouts).
  All four desired structures remain strict expected gaps; appearance and SVG
  integrity checks remain active. Regression SSIM floors: patch/panel 0.95,
  storefront 0.94, poster 0.92. Desired fidelity remains ≥0.95; lower floors pin
  measured behaviour on new difficult fixtures, not success against the goal.
- `plate bench samples/challenges -o /tmp/plate-complex-bench`: mission patch
  **55 objects / 0 gradients / SSIM 0.9628** (target 45 / 2); storefront **68 /
  0.9515** (target 64); panel **37 / 0.9665** (target 59); poster **57 / 0.9283**
  (target 44). Dark-background SSIM: 0.9644 / 0.9485 / 0.9665 / 0.9283.
  VTracer controls retained. Original `plate bench samples` values unchanged.
- Visually inspected all four PNGs and source-vs-rendered-PLATE comparisons.
  Confirmed all 18 gauge ticks are absent immediately after segmentation.
  Patch palette-limit sweeps 16/32/64 made no difference; panel denoise=0 made
  no difference; disabling primitive snaps leaves 37 objects (SSIM 0.9660).
- Code inspection found an ineffective completion containment check (model is
  unioned with observations before containment is tested) and cropped primitive
  comparisons that cannot penalize model area outside the mask crop. Poster
  footer incorrectly emits an ellipse with rx≈663 versus the source rect's
  half-width 420. These are diagnosed/proposed fixes, **not fixed this session**.
  Suggested sequence and supporting evidence recorded in `docs/challenges.md`.
- Full renderer-enabled suite: **75 passed, 9 xfailed** (existing mock VLM server
  requires localhost permission). Pipeline, emitter and baseline were not edited;
  existing user changes preserved. Nothing committed or pushed.

## Independent desired-output challenges (session 4)

- Added **8 authored SVG targets paired with supersampled PNG inputs** in
  `samples/challenges/`; regenerate with `scripts/make_challenges.py`. These are
  independent desired artwork, not copies of PLATE's current SVG output. Existing
  uncommitted text-control/README work was preserved; pipeline and VTracer untouched.
- `tests/challenges.py` / `tests/test_challenges.py` compare full per-object silhouettes
  (including occluded geometry), primitive types, hole/component topology, gradient
  kinds, open strokes, and overlapping paint order. IDs/formatting/disjoint ordering
  are allowed to vary. All eight have always-active SVG integrity and dual-background
  fidelity checks (SSIM ≥0.95), even when their desired structure is a known gap.
- **3 structural targets pass:** nested dial (8 objects / SSIM 0.9916), independent
  twin gradients (5 / 0.9882), discrete palette (9 rects, zero gradients / 0.9963).
- **5 strict expected gaps:** perforated plate has a stray connected component;
  occlusion-chain back circle drifts ≈3.5px (full silhouette IoU ≈0.946);
  gradient badge duplicates its shaded disc (6 objects / 2 gradients vs target 5 / 1);
  edge-crossing lettering fragments its disc (7 vs 5 objects); route remains a filled
  outline rather than an open 16px stroke. Targets remain unchanged until features
  meet them. Expected failures catch only structural `TargetMismatch`; crashes and
  fidelity regressions are not suppressed. Full target success is a strict XPASS.
- Verified `plate bench samples` and `plate bench samples/challenges` against the
  plain-VTracer baseline. Original sample numbers match the prior session. Rendered
  and visually inspected input / authored target / PLATE comparisons for all 8.
- Full suite requires localhost permission for the existing mock VLM HTTP server;
  the initial sandbox-only run failed there (39 passed). Baseline with that access:
  **40 passed**. Final suite with renderer: **62 passed, 5 xfailed**.
- Reproduction commands, exact targets, measured metrics, and future scene ideas:
  `docs/challenges.md`. Illustrator import remains unverified.

## Gradients (implemented in session 3)
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
- **CONTROL regression suite**: `scripts/make_controls.py` generates 15 synthetic PNGs in 5 complexity tiers (T1 trivial → T5 hard); `tests/controls.py` holds current-behaviour contracts; `tests/test_controls.py` asserts object counts, primitive parameters, names, paint order and nesting, with fidelity floors and soft golden-SVG diffs (`tests/golden/controls/`). A separate set of 12 independent desired-SVG challenges includes 9 still-unmet structural targets.

## Earlier real-hardware verification (macOS M-series, Python 3.11 venv)
- **Real LM Studio VLM path works end to end** (was mock-only before). `plate doctor --vlm-url http://localhost:1234/v1` lists loaded models; `plate trace samples/face.png --vlm-url ... --vlm-model qwen/qwen3.8-27b` produced semantic names (Face, Mouth, Tongue, Left/Right Eye, Eye Highlight) AND semantic groups (eyes = eyeball+highlight) as nested Illustrator `<g>` layers. SSIM 0.993.
- `qwen/qwen3.8-27b` is vision-capable and works for both naming and grouping. `qwen2.5-coder-7b` is text-only (HTTP 400 on images). Embedding models are skipped by the new auto-selector.
- `cairosvg` rendering now works on this machine (so `bench`/`--report`/sweep report SSIM). Required `brew install cairo` (already present) PLUS the dyld fix below.

## Earlier environment/VLM fixes
- **`plate doctor` crashed** when an optional dep is installed but unusable (cairosvg importing but failing to load libcairo raised `OSError`, not `ImportError`, so the old `except ImportError` missed it and doctor died before checking LM Studio). Now catches any exception and reports BROKEN/optional; probes cairosvg through the renderer helper.
- **cairosvg could not find libcairo on macOS/Homebrew.** cairocffi's dlopen doesn't search `/opt/homebrew/lib`, and SIP strips `DYLD_*` across protected binaries, so it must be set before process start. `cli.main` now re-execs itself once (guarded by `PLATE_DYLD_REEXEC`) with `DYLD_FALLBACK_LIBRARY_PATH` pointing at the Homebrew cairo dir (`raster.cairo_lib_dirs` / `ensure_dyld_cairo`). Added `src/plate/__main__.py` so `python -m plate` is a valid re-exec target. Renderer now "just works" via the CLI.
- **VLM grouping intermittently failed** with "no JSON in reply". Root cause: Qwen3 is a reasoning model and wraps/precedes JSON with `<think>…</think>` blocks and prose. Hardened `vlm._json` to strip think-blocks and code fences and extract the first *balanced* `{...}`/`[...]`. NOTE: `response_format: json_object` is NOT used — LM Studio returns HTTP 400 for it on this model.
- **VLM model auto-selection was blind** (`models[0]`). New `vlm.pick_model` skips obvious non-vision models (embedding/rerank/tts/etc.) and `describe` logs which model it used and warns when zero names come back. Explicit `--vlm-model` still wins.

## Remaining external validation
1. **Illustrator import**: do top-level `<g>` become layers with the right names? Are circles/rects editable live shapes? Follow `docs/illustrator-checklist.md` and record results here. (STILL the main open P0 — needs a human in Illustrator.)
2. **Real-world images** (logos, clipart, scans). Only synthetic samples tested. Collect 10–20 real ones into `samples/real/` and run `plate bench`.
3. VLM naming quality: the model names both eyes "Left Eye" (dedupe suffixes → "Left Eye 2") rather than distinguishing left/right; naming is ~6s/shape (one request per shape → 47–65s for the face). Prompt/throughput tuning is open.

## Known weaknesses
- Basic linear/radial gradients work. Disconnected/occluded ramps and decorated shaded objects can still split or posterize; photos and conic/mesh gradients remain unsupported.
- Occluder with a bar crossing a circle's edge (badge inner disc) → no completion, stays a Bézier path.
- Triangle apex can get 2 vertices (bevel from blur); polygon snap keeps them.
- Noisy input: ring edges slightly wobbly after denoise; SSIM 0.87.
- Naming a ring/annulus says "Red shape" (could be "Red ring"). Ring/annulus currently stays a single even-odd path, NOT two `<circle>`s (pinned as a known-behaviour control in `t3_ring`).
- SAM segmenter not implemented (config `segmenter` accepts only "classical").
- No disk cache for segmentation; large images (>3000px) are downscaled to `work_size` (1536) for analysis, output is rescaled.
- Source control: the repository exists. Inspect staged/unstaged changes and preserve them; commit/push only when Jessica asks.

## Env notes for the next session
- venv at `.venv` (Python 3.11 via `python3.11`); system python is 3.9 which is too old. `pip install -e ".[dev,render]"` done.
- `cairo` is installed via Homebrew; the CLI handles the dyld path itself. If you call the library directly (not via `plate`), prefix with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`.
- LM Studio reachable at `http://localhost:1234/v1`; use `--vlm-model qwen/qwen3.8-27b` (vision-capable). Load a vision model before expecting names.
