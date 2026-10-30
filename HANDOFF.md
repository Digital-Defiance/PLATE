# PLATE handover — 2026-10-30 (session 24, identity and tracing fixture)

Read `AGENTS.md`, then `STATUS.md`, then `ROADMAP.md`, then this file. This records
the immediate state at handover. Be skeptical of prose; verify with `pytest` and by
rendering.

## State at handover

- Session 24 identity, fixture, tests and handover are committed together at
  Jessica's request. Use `git log -1 --oneline` for the branding commit.
- Session 23 recovery is committed as **`2aa79bc`** (base `7300232`).
- Sessions 20–21 are committed as **`71f6740`**. Session 22's crossed-curve source
  and tests are committed as **`3c0a8e1`**; session-22 docs are `7300232`.
- Recent lineage: `a2579f0` (session-19 docs) ← `c5762b2` (session-19 tests) ←
  `7f0210c` (session-19 feat: stroked loops across crossings) ← `ea4330e` (docs) ←
  `632bb1c` (session 18, mixed-content holes) ← `ebf8762` (session 17) ←
  `a56c13e` (sessions 14–16) ← `0a0fddc`.
- No push. Commit/push only when Jessica asks.
- **Tests: 277 passed, 7 xfailed** (strict expected structural gaps). Run with the
  renderer on:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q`

## PLATE registration-P identity (session 24)

- Jessica requested a logo that also tests PLATE, then requested handover and
  commit with 4% usage remaining. Stop design iteration here; no pipeline changes.
- `assets/brand/plate-preview.png` shows the current design: three offset
  teal/vermilion/ink P plates, a shared transparent circular counter, a fine
  registration mark and original outlined lettering. SVG/PNG assets include
  primary/reversed lockups, square mark and simplified monochrome versions.
  `assets/brand/README.md` records usage, regeneration and measurements.
- `scripts/make_plate_brand.py` authors the vectors and 4× supersampled PNGs.
  Brand master and `samples/challenges/logo_plate.{png,target.svg}` are exact
  byte-identical pairs. All 13 regenerated SVG/PNG artifacts match byte-for-byte.
- Desired **11 objects / 3 strokes**. PLATE currently emits **11 / 125 anchors /
  1 stroke**, SSIM **0.9906 white / 0.9956 dark**. Back P silhouette IoU is only
  **0.1387**: it remains visible strips. Registration strokes merge and some
  square corners round. Arbitrary hidden compound geometry is not uniquely
  identifiable from the raster; keep this an aspirational authoring target.
- The new structural contract is a strict expected failure. Integrity and
  SSIM ≥0.98 on both backgrounds stay active; asset tests protect inventory,
  transparent counters, complete plate topology, named layers and master/fixture
  identity. Existing targets/goldens and all pipeline code remain unchanged.
- Both benches ran: `/tmp/plate-brand-{samples,challenges}`. Source/trace render
  inspected at `/tmp/plate-brand/comparison.png`; HTML report is
  `/tmp/plate-brand/logo_plate.report.html`. VTracer control remains intact:
  **333 objects / 824 anchors / white SSIM 0.9337**.
- Baseline **270 passed / 6 xfailed**, final **277 / 7**; changed Python files
  pass Ruff. The mock VLM requires expanded localhost access for full pytest.
  Illustrator import is still unverified. No push requested or performed.

## Fragmented cream-highlight recovery (session 23)

- **All seven ORBIT strokes plus the radial core pass together** against the
  unchanged independent targets, including silhouette/topology/width/paint order.
  The upper cream arc's long fragment and tiny exposed cap become one editable
  full cubic. **45→44 objects, 6→7 strokes, 352→345 anchors**. White/dark SSIM
  **.9844/.9923→0.9846/0.9925**, SVG **17,218→16,860 bytes**. Full ORBIT remains
  a strict xfail (target 34 objects); compound navy geometry still fragments.
- `stages/curves.py` pools only same-colour sibling leaves beneath a proven later
  native closed stroke. Exclude clipped sections from width estimates; fit both
  free boundaries to a bounded cubic. Require a nearby small cap, tight residuals,
  ≥95% exposed IoU, source-backed exposed cores and ≤30% hidden model area (also
  bounded by 3×width²). Reject holes/branches, unsupported gaps, unrelated dots,
  mismatched parents/colours, flat caps and earlier/unproved loops.
- `pipeline.py` rebuilds disjoint observed ownership, restores accepted fits and
  shares `_stroke_node` with ordinary open curves. A render check caught a real
  ordering regression: inferred edge pixels touched earlier navy shapes. The new
  curve now adds constraints only for its validated gold-loop occluder, via
  `Stroke.occluders`; both highlights are explicitly tested above the monogram.
- **270 passed, 6 xfailed** (baseline 248/6), with 22 new cases. Original eight and
  fourteen other challenge PLATE SVGs remain byte-identical. No target/golden/
  VTracer changes. Both benches rendered/inspected in
  `/tmp/plate-fragment-{samples,challenges}`; baseline
  `/tmp/plate-fragment-before-{samples,challenges}`; metrics `/tmp/plate-fragment-metrics.json`;
  tests `/tmp/plate-session23-final2-tests.txt`. Review sheets in this chat's visual
  folder: `plate-fragment-highlight.png`, `plate-fragment-original-samples.png`.
- Scope: one long visible arc plus a small exposed cap under a known later loop.
  Two long fragments, arbitrary covers, unknown ordering and networks remain open.
  Next: navy badge/monogram and ambiguous gradient patches; ROOT decomposition and
  mission-patch gradients remain open. Recovery committed at Jessica's request; no push.

## Crossed cream-highlight recovery (session 22)

- ORBIT's **lower cream highlight** is now an editable full cubic stroke beneath
  the gold orbit. Both unchanged targets pass together, including paint order.
  **5→6 strokes, 357→352 anchors**, still 45 vs target 34 objects. White/dark
  SSIM **.9843/.9922→.9844/.9923**; SVG **17,388→17,218 bytes**.
- `pipeline.py` precomputes native closed-loop fits before open-curve conversion.
  `strokes.fit_crossed_curve` runs only after ordinary fits fail, using independently
  accepted later-painted circle/ellipse stroke masks. Exactly one cap must remain
  exposed; stable-width topology, ≥65% free contour, bounded cubic/width fit,
  free-edge residuals, ≥95% visible IoU and local hidden-area checks constrain it.
  No paint reordering or broad T-junction relaxation. It cannot infer both hidden
  ends, pool fragments, or repair unknown paint order.
- A flat-cap regression initially fooled the binary fit. Source antialias contours
  preserve those corners and now veto it. Existing `_flat_terminal` defaults are
  unchanged; the fallback uses separate binary/source tolerances. Eleven cases
  cover the actual logo, full silhouette/width at 1×/2×, flat caps, taper, switches,
  detached covers and 1/3/6px exposed gaps. **248 passed, 6 xfailed** (baseline 237/6).
- All eight original and fourteen other challenge PLATE SVGs remain byte-identical.
  Targets/goldens/VTracer code unchanged. Rendered/inspected both benches in
  `/tmp/plate-crossed-{samples,challenges}`; comparison baseline
  `/tmp/plate-crossed-before-{samples,challenges}`; metrics `/tmp/plate-crossed-metrics.json`;
  tests `/tmp/plate-session22-final-tests.txt`. Review sheets in this chat's visual
  folder: `plate-crossed-highlight.png`, `plate-crossed-original-samples.png`.
- Next: compound navy badge/monogram and split upper cream arc. The upper arc has
  a large visible fragment plus a small one near a crossing; it needs supported
  open-curve pooling before the new one-component fallback can help. Opaque ring
  counters can still block native-loop discovery or order a cover too early; do
  not infer a new ordering from colour/proximity alone. ROOT decomposition and
  mission-patch gradients remain open.

## Radial-gradient band recovery (session 21; committed in session 22)

- ORBIT's disconnected bands now share **one complete native radial circle**.
  **57→45 objects, 500→357 anchors**, retaining **5 strokes / 1 gradient**.
  White/dark SSIM **.9816/.9889→.9843/.9922**; SVG **24,755→17,388 bytes**.
  The unchanged gradient-core/back-orbit/front-orbit sub-contract passes together,
  including topology and paint order. Full ORBIT remains a strict xfail (34/7).
- `gradient._grow_radial_bands` extends an existing seed using eroded source RGB
  samples and a shared affine RGB/radius field. Each candidate must beat a flat
  colour model (residual ≤0.8×colour variation); exact or noisy matching craters
  remain separate. Require ≥3 regions, a common circle with free RMS ≤0.5px and
  ≥270° angular coverage, observed local T-junction occlusion, ≥95% foreign-paint
  coverage of added area, and no uncovered inferred interior. Rebuild visible
  ownership without adding/removing observed pixels.
- `Shape.verified_prim` survives `Segmentation.rebuilt`; `order` restores this
  validated circle and its occluder constraints instead of refitting cut edges.
  Reopen a foreground ring's hole when its clear interior belongs to the same
  gradient ancestor; preserve full discs with a distinct child repaint. Clear stale
  primitive completions when reopening. See `tests/test_gradient_bands.py`.
- Nine cases added; **237 passed, 6 xfailed** (baseline 228/6). Eight original and
  fourteen other challenge PLATE SVGs are byte-identical. No target/golden/VTracer
  changes. Final benches `/tmp/plate-core-{samples,challenges}`, baseline
  `/tmp/plate-core-before-{samples,challenges}`, metrics `/tmp/plate-core-metrics.json`,
  tests `/tmp/plate-core-final-tests.txt`. Render review sheets in this chat's
  visualization folder: `plate-gradient-core.png`, `plate-core-original-samples.png`.
- Limits: affine radial RGB model and circular geometry only; tiny/ambiguous bands
  stay separate. General nonlinear/clamped/elliptical gradients and the mission
  patch remain open. No commit or push made.

## Interrupted ellipse recovery (session 20; committed in session 22)

- ORBIT's mint **back orbit** now matches its unchanged independent ellipse target.
  Two large arcs establish the geometry; two small matching fragments rejoin it.
  **60→57 objects, 4→5 editable strokes, 539→500 anchors**. White/dark SSIM
  **.9812/.9882→.9816/.9889**. Both back/front ellipse contracts pass, including
  their relative paint order. Full ORBIT remains a strict xfail (target 34/7).
- New `stages/loops.py` accepts same-colour, same-parent, leaf arcs only. Width and
  curvature must agree; both terminals of each seed need local relative T-junction
  evidence. Pool separate free contours and refine a shared ellipse using source
  antialias coverage. Every inferred hidden section needs observed non-background
  artwork, and source coverage/alpha checks protect even 1px visible openings.
  Small fragments join only after the large arcs establish the complete model.
- The pipeline rebuilds/reindexes visible ownership through `Segmentation.rebuilt`,
  recomputes order, restores the accepted full loop and adds stable sibling paint
  constraints. `_closed_node` shares native stroke emission with ordinary closed
  fits. Original `fit_closed` thresholds and session-19 changes are untouched.
- Twelve regressions cover rotation, 2× source/downsampling, ownership invariants,
  both disable switches, 1/3/6px alpha gaps, background-matching gaps, incompatible
  widths/centres, and both real ORBIT ellipses. **228 passed, 6 xfailed**, baseline
  **216/6**. All eight original PLATE sample SVGs and fourteen other challenge
  PLATE SVGs are byte-identical. No desired targets, goldens or VTracer code changed.
- Latest benches `/tmp/plate-pooled-final-{samples,challenges}`; baseline outputs
  `/tmp/plate-pooled-before-{samples,challenges}` (same pipeline with new recovery
  disabled); metrics `/tmp/plate-pooled-final-metrics.json`; test log
  `/tmp/plate-pooled-final-tests.txt`. Rendered/inspected both isolated back orbit
  and full composition plus all original samples. Review sheets in this chat's
  visualization folder: `plate-pooled-orbit.png`, `plate-pooled-original-samples.png`.
- Limits: this merge cannot split ROOT's ring from touching leaves, and does not
  accept arbitrary non-leaf/non-sibling fragments or an ellipse extending beyond
  the canvas. It deliberately refuses missing strokes with no opaque occluder
  evidence. No commit or push was requested/made in session 20.

## Stroked loops crossing other artwork (session 19)

- Closed the previous handover's primary ORBIT continuation item: the gold **front
  orbit** now recovers as one editable **stroked ellipse** (width 6.06 vs target 6,
  rx/ry 190/62). `fit_closed` in `src/plate/stages/strokes.py` required every
  boundary sample < 0.85px, every predicted/observed pixel within 1px, and ≥90% of
  the boundary free of later shapes. A thin stroke threaded through the badge ring,
  gradient core, satellites and wordmark violates all three (~2% of its boundary
  smears up to 2.8px at crossings; ~37% sits near later-painted covers) even though
  its visible arcs over-determine the ellipse (free-only fit RMS 0.26, footprint
  XOR 0.017).
- Three GUARDED relaxations, each still backed by a strong independent gate — a real
  notch/defect is still rejected:
  - `_boundary_ok` (new helper): tolerate boundary samples past tolerance only when
    SCATTERED (≤5% of points AND longest contiguous run ≤12). A notch is a long
    contiguous run → still fails.
  - stray-pixel footprint check: allow stray area within 3px of the shape up to 1%
    of the loop (was: any pixel >1px away rejects). The XOR ≤ 0.06 gate still caps
    gross mismatch.
  - free-boundary gate 0.9 → 0.5: a loop at least half-visible is over-determined;
    the residual/footprint gates on the free region remain the guarantees.
- Commits `7f0210c` (feat) + `c5762b2` (3 regressions: real-ORBIT front-orbit
  recovery, a notched ring still rejected, and the `_boundary_ok` scattered-vs-
  clustered unit test). ORBIT now emits **2 ellipses / 4 strokes** (was 1 / 3).
- **ORBIT's overall structural gap stays OPEN** (strict xfail): still **60 objects
  vs target 34**. The mint **back orbit** fragments into disconnected arcs, and the
  wordmark/emblem still fragment. Suite **216 passed, 6 xfailed**; panel stays
  59/27, ROOT 51/3, all eight original samples and the other challenges unchanged.
  No target/golden edits.

## IMPORTANT correction: why git commits hang (and the real fix)

Earlier handovers blamed the commit template / gpg. **That was wrong.** The real
blocker is a GLOBAL `pre-commit` hook: `core.hooksPath` points at
`~/.git-templates/hooks`, whose `pre-commit` opens an AppleScript "Select Identity"
GUI (`osascript choose from list`) that blocks forever in a non-interactive shell.
The hook honours its own bypass, `hooks.skipidentityprompt=true`. GPG signing works
fine once the hook is skipped. Commit with (all per-invocation `-c`, config untouched,
commits stay signed):
`GIT_EDITOR=true git -c hooks.skipidentityprompt=true -c commit.template= -c gpg.program=/tmp/gpg-batch.sh commit -F <msgfile>`
where `/tmp/gpg-batch.sh` is `#!/bin/sh` + `exec /opt/homebrew/bin/gpg --batch --no-tty "$@"`.
(Also: write commit messages to a file and use `-F`; multiline `-m` and streaming
`pytest` output both get truncated by the shell tooling here, so redirect pytest to a
log and read the tail.)

## Immediate continuation

1. Sessions 20–23 recovery work is committed. ORBIT
   now has **44 vs target 34 objects**, all seven intended strokes. Its full radial
   circle and seven strokes pass together; keep all six full gaps active.
2. Recover ORBIT's compound navy badge and monogram. The source-visible ownership
   probe still finds **eight badge-ring regions** and **three monogram regions**
   (≥3% of each target object's visible pixels). The wordmark itself does not show
   substantial splitting. Small ambiguous gradient patches also remain separate.
3. Both ORBIT highlights now pass. ROOT remains 51 vs 56 objects and 3/32 strokes; its inner mint ring shares colour with leaves and
   requires decomposition, beyond sibling-leaf pooling.
4. Extend shared gradients to the mission patch's clamped bands/craters and linear
   hull without absorbing foreground details. The new affine radial-circle method
   intentionally cannot handle every ramp or geometry.

The current probe is `/tmp/plate_core_review.py`. Source-visible masks and emitted
full silhouettes answer different questions; retain independent silhouette,
topology and paint-order checks rather than promoting a target on appearance alone.

## Mixed-content hole fix (session 18, committed `632bb1c`)

- `order._silhouettes` previously reopened an entire hole only when >50% of its
  pixels were transparent. ORBIT's front ellipse encloses a mostly opaque gradient
  core, so it incorrectly borrowed that artwork as its own fill and had four holes.
  Also reopen when the hole contains clear transparency surviving two erosion
  iterations. Fully opaque covers and thin 1–2px fringes keep old behaviour.
- ORBIT's front loop is now one hollow compound path: emitted isolated geometry
  IoU **.1503→.8630**, topology **(1 component, 4 holes)→(1,1)**. It is **not yet
  an editable ellipse**. Total **60 objects / 600 anchors / 3 strokes / 1 gradient**;
  white/dark SSIM **.9812/.9882** (was 60/603/3, .9811/.9870).
- Seven new tests cover mostly opaque holes with clear 5/10/20px voids, opaque and
  1/2px fringe negatives, and ORBIT full-loop geometry/topology. **213 passed,
  6 xfailed**, no warnings. All eight original PLATE SVGs and fourteen other
  challenge PLATE SVGs are byte-identical to `ebf8762`. Targets/goldens unchanged.
- Bench outputs `/tmp/plate-void-final-{samples,challenges}`; metrics
  `/tmp/plate-void-final-metrics.json`. Rendered/inspected full ORBIT, its isolated
  front loop, and all original samples. Durable review sheets in this chat's
  visualization folder: `plate-orbit-hole.png`, `plate-void-original-samples.png`.
- No unverified fitter experiments were left in source. Experiments/probes live
  only in `/tmp`; the implementation change is the small hole-classification fix.

## Alpha-contour repair (session 17)

- Fixed the 5px transparent circle: 295 unresolved opaque pixels previously
  borrowed transparency for 219 pixels, splitting one loop into four objects.
  Reuse existing wider colour explanations, and let unsupported near-palette
  alpha-edge cores seed the existing fallback even inside its resampling halo.
  Already-supported edge labels, palette budgets and blend competition remain.
  **Scope to source transparency**: an initial broad variant broke gradients.
- Circle (210,160), r115, width5 on 420×320: **4 objects/26 anchors → one native
  circle stroke/4 anchors**, SSIM **.9929→.9996**. Tested 3/5px circles and ellipses
  preserve all foreground alpha pixels. Do not generalize this fix to opaque
  boundaries without a separate gradient/antialias analysis.
- Cleaner masks snapped two ORBIT motion lines to polygons, bypassing the old
  path-only curved fitter. Consider polygons **bordering source transparency** as
  curve candidates too. Opaque filled primitives retain their prior eligibility:
  a broader fallback broke panel title/footer rectangle contracts.
- A source cap whose extreme front is confidently flat across ≥75% of the width
  rejects round-cap emission. This protects ORBIT's square-ended descriptor U.
  An independent regression requires the filled U and all three full editable
  motion curves, including widths, geometry and order. Seven new cases total.
- All seven opaque original PLATE sample SVGs and eleven challenge SVGs are
  byte-identical to `a56c13e`. Panel remains **59 objects/27 strokes/249 anchors,
  SSIM .9864**, fully passing. Current changed outputs:

  | Image | Objects / anchors / strokes | White / dark SSIM |
  | --- | --- | --- |
  | donut_alpha | 2 / 11 / 0 | .9939 / .9954 |
  | perforated_plate | 2 / 44 / 0 | .9943 / .9957 |
  | EMBER | 51 / 446 / 2 | .9663 / .9683 |
  | ORBIT (session 17; see newer result above) | 60 / 603 / 3 | .9811 / .9870 |
  | ROOT | 51 / 522 / 3 | .9830 / .9867 |

  ROOT's two mint fragments (previous IDs 20 and 23) now join through restored
  observed pixels. **51 vs target 56 remains a failure**, not object recovery.
  Same-colour ring/leaf separation is still needed. EMBER white MAE changes
  slightly, 2.123→2.135; no full logo structural target is met.
- Only the soft `tests/golden/controls/t3_ring.svg` snapshot was refreshed:
  unchanged one-object/even-odd topology, eight anchors, no stroke; source SSIM
  **.9884→.9983** independently verified. No `.target.svg` files changed.
- Verification: **206 passed, 6 xfailed**, both benches rendered/inspected.
  `/tmp/plate-alpha-final-{samples,challenges}`;
  `/tmp/plate-alpha-final-metrics.json`, `/tmp/plate-alpha-thin-loop-metrics.json`.
  Review sheets `plate-alpha-final-bench.png`, `plate-alpha-thin-loops.png` in
  this chat's visualization folder. VTracer implementation remains unchanged.

## Immediate continuation

> SUPERSEDED (session-18 note): item 1 below (front-orbit `fit_closed` rejection) was
> RESOLVED in session 19 — see "Stroked loops crossing other artwork" above; the front
> orbit now recovers as a stroked ellipse. Items 2–3 (back-orbit arc reconciliation,
> ROOT inner ring) remain open and are folded into the current "Immediate continuation —
> next ORBIT blocker" section near the top. Kept here for history.

1. ORBIT's front silhouette is now hollow, but `fit_closed` rejects gradient-crossing
   segmentation errors: approximately 45 boundary points exceed .85px deviation,
   max ≈2.82px; overall RMS ≈.329px. Several wrongly assigned boundary samples are
   actually solid gold RGB (233,188,89). Inspect local colour/coverage assignment;
   preserve strict width/notch tests rather than broadly permitting outliers.
2. Reconcile ORBIT's mint back-orbit arcs with geometric/occlusion evidence. Its
   full target still needs 34 objects; current count is 60. Foreground hierarchy
   has changed after correcting the front ring, so re-check parents/paint order.
3. ROOT's mint inner ring still shares colour with leaves; 51 vs 56 objects and
   3/32 strokes. Branched networks, same-colour separation and opaque counters
   remain later work. Preserve genuine cutouts and full discs under nested shapes.

All six full structural gaps remain open. Do not loosen targets to promote them.

## Thin closed strokes (session 16, included in checkpoint)

- ROOT outer seal now matches its unchanged independent target as a native 18px
  circle stroke. **52 objects / 3 of 32 strokes / 559 anchors** (was 52/2/610).
  White/dark SSIM **0.9830/0.9863** (was **0.9806/0.9846**). Full ROOT target
  remains a strict xfail; its inner ring is merged/split among mint leaves.
- `fit_closed` requires one hole, one component, thin constant width (≤15% of the
  minimum radius), low boundary residual and full-footprint agreement. PNG coverage
  refines boundaries; ellipses use true Euclidean normal offsets. Small bites can
  complete beneath observed later shapes only with ≥90% free boundary and the
  completion switch on. Native circle/ellipse SVG emission and metrics support
  strokes. Thick rings/cutouts and off-centre/uneven holes are protected.
- Fit `Shape.full`, **not** the visible rim: a prototype using `vis` broke the
  instrument panel by converting full discs beneath smaller discs to annuli.
  Its independent contract caught this; final panel is byte-identical. A new
  nested-disc test guards hidden filled silhouettes. Opaque-background annuli
  remain ambiguous/full-disc + counter objects; do not casually reinterpret them.
- Thirteen new regressions; **199 passed, 6 xfailed** vs **186/6**. Original eight
  PLATE sample SVGs and every other challenge PLATE SVG are byte-identical. VTracer
  code is unchanged, but the ORBIT control varied across repeated identical runs
  (1473/3559 vs 1470/3745 objects/anchors); byte stability is not claimed for it.
- Latest benches: `/tmp/plate-closed-final-{samples,challenges}`; metrics
  `/tmp/plate-closed-final-metrics.json`. Rendered/inspected ROOT and all original
  samples; review sheets `plate-closed-ring.png`, `plate-closed-original-samples.png`
  in this chat's visualization folder. No target/golden edits.
- At the session-16 checkpoint, next was interrupted loops and fragment reconciliation.
  ORBIT's back orbit is split
  into arcs; its front orbit's full silhouette is overfilled. ROOT inner ring
  shares colour with leaves and is fragmented/merged. Also a 5px transparent circle
  split into four regions during segmentation before fitting; that alpha-assignment
  issue is now fixed in session 17 above. Complete transparent circles/ellipses work
  at tested widths including 5px and downscaling.

## Full instrument panel passes (session 15, included in checkpoint)

- **59 objects / all 27 strokes / 249 anchors / SSIM 0.9864** white and dark. The
  complete independent target passes unchanged: hidden silhouettes, styles, object
  types, topology and paint order. This is the first passing large composition.
- Straight fitting now accepts one hidden terminal under an aligned circular hub.
  Require real contact, relative T-junction evidence (15°), a fitted free cap, low
  free-boundary residual and source-colour support for the entire exposed core.
  Small gaps, taper and off-centre hubs are rejected; source scaling is tested.
- For a larger hub initially sorted before its needle, pipeline considers the
  earlier sibling circle only with T-junction support. Add stable paint edges
  **only after the stroke fit succeeds**. Do not reintroduce a broad order-stage
  fallback: it changed noisy_badge/shaded ordering despite rejected stroke fits.
- The extra object was an 861px navy chassis island. Merge a same-colour leaf
  into its immediate parent only when the parent's painted interior covers it and
  no earlier mask, fitted primitive or traced fringe needs its later repaint.
  A validated open stroke ignores filled-path bleed; otherwise use conservative
  trace bounds. Preserve pupils, transparent-hole islands and primitive residuals.
- Benchmarking caught unsafe early merge/order variants; all were corrected.
  **Only the panel SVG changes from session 14.** All eight original samples,
  every other challenge and every VTracer output are byte-identical. Targets and
  goldens are unchanged. `complete_hidden=false` now applies to curve endpoints too.
- Twenty-one new cases plus panel promotion: **186 passed, 6 xfailed** vs **164/7**.
  Latest bench folders: `/tmp/plate-hubs-final-{samples,challenges}`, metrics
  `/tmp/plate-hubs-final-metrics.json`. Reviewed images: `plate-completed-panel.png`
  and `plate-hubs-original-samples.png` in the chat visualization folder.

## Earlier straight-stroke work (session 14, included in checkpoint)

- `fit_straight` fits round-capped lines with PCA and bounded least squares.
  It uses source RGB antialias coverage or alpha, preserving Lanczos overshoot.
  Cap-local rectangle competition protects square-ended lettering; ellipse
  competition preserves genuine ellipses. The full proposed footprint is checked.
  Subpixel source boundaries are not distorted to match quantized region labels.
- Pipeline considers primitive approximations too, then retains the old open-curve
  fallback. Gradients/circles/holes/backgrounds are excluded. Straight endpoints
  touching later-painted circles are left alone until hidden-end fitting is added.
- Panel **24/27 strokes**, all 18 ticks and four screw slots independently matched.
  Anchors **303→259**, SSIM **0.9854→0.9862**. Remaining: three needles hidden by
  hubs, plus a separate **60-vs-59** object mismatch.
- Patch **1→7 strokes**, storefront **0→2**, ROOT **0→2** (anchors **902→610**,
  SSIM **0.9784→0.9806**). UI card has three recovered pill strokes, anchors
  **24→14**, SSIM **0.9714→0.9788**. Seven other original sample SVGs and all
  VTracer SVGs are byte-identical. Targets/goldens are unchanged.
- Fourteen regressions cover small/rotated/transparent strokes, independent ticks
  and slots, cap/ellipse/taper rejection, source scaling and disabling detection.
  Tiny opaque 3px marks without stable palette seeds can still vanish upstream;
  that separate thin-colour discovery gap is not fixed by stroke fitting.
- Benchmarks: `/tmp/plate-straight-final-{samples,challenges}`, baseline
  `/tmp/plate-straight-before-{samples,challenges}`, metrics
  `/tmp/plate-straight-final-metrics.json`. Reviewed images in the chat visualization
  folder: `plate-straight-strokes.png`, `plate-straight-original-samples.png`.

## Previous session 13 work (all committed)

First, the previous handover's verified-but-uncommitted work was committed as-is:
- `572983c` pool disconnected contours + merge flat fragments in completion (`edge_crossing_type` 7→5 objects).
- `f8a901c` three original logo challenge fixtures (EMBER/ORBIT/ROOT) + asset tests.
- `db027fe` docs for the above + `HANDOFF.md`.

Then two structural gaps were closed (each a root-cause fix, verified no-regression):

1. **`occlusion_chain` — chained-completion drift** (`ca92bbd`).
   The back disc completed via a Bézier bridge and drifted to (141.5,160.5) r93.1
   vs target (145,160) r95, because `complete.try_complete`'s occluder-coverage gate
   rejected the correct circle fit (RMS 0.25, 226° arc) at 89.6% vs the 90% floor —
   a disc hidden by a same-size neighbour legitimately recovers a ~10% sliver past
   the occluder. `evaluate()` now takes the fit residual and relaxes the coverage
   floors (Cm 0.90→0.85, Cv 0.70→0.65) ONLY for a primitive with RMS ≤ 0.5·tol; the
   bridge and weak fits keep strict floors, so shapes still cannot complete into mere
   neighbours. Back disc now (145.1,160.1) r94.6, drift 3.5px→0.1px.

2. **`perforated_plate` — compound-path topology** (`ccd6188`).
   `order._silhouettes` hole-filled a shape and removed only transparent pixels, so a
   genuine perforation containing a floating OPAQUE island (the middle hole holds a
   gold disc) kept the island's footprint as the plate colour — a stray 749px
   component. Now each hole-filled region is checked before transparency removal:
   a predominantly-transparent region (>50%) is a real perforation and is re-opened
   in full (island pixels dropped with it); mostly-opaque regions (a shape genuinely
   sitting behind another, e.g. a background under on-top shapes) stay filled so
   paint-order coverage is unchanged. Blue plate: 2 components → 1, three holes kept.

Both promoted from strict xfail. `overlap` stays <1px, `stack3` ordering/anchors
unchanged, donut evenodd ring intact, all eight original sample SVGs byte-identical.

## Remaining 6 gaps (all strict xfail; promote only when the independent target is met)

Current numbers in `STATUS.md`'s top table. In rough ROADMAP P1 order:

| Challenge | Gap |
| --- | --- |
| `complex_mission_patch` | 72 objects / 2 radial fragments / 7 strokes; target 45 with one radial planet + one linear hull, craters preserved |
| `complex_event_poster` | 83 objects; crossing lettering/ribbon/lines fragment underlying shapes |
| `complex_storefront` | 73 objects / 2 strokes; target 64, repeated windows/awning/lettering merge or fragment |
| `logo_ember_crest` | 51 objects (count matches) but shield full-silhouette IoU 0.8383; 2/7 strokes |
| `logo_orbit_wordmark` | 44 objects vs 34; full radial core and all 7/7 strokes recovered; compound emblem and ambiguous patches remain |
| `logo_root_seal` | 51 vs 56 objects; touching same-colour organics merge; 3/32 strokes, outer circle passes independently |

The next stroke work includes ROOT's touching ring/leaves and EMBER's missing
strokes; logos need 7/7/32 strokes and recover 2/7/3. The panel's 27 strokes are complete.
Then address branched networks, other cap/join styles and non-circular/multiple
occluders. `stages/strokes.py` contains straight/open-curve and complete closed-loop recovery.

## Architectural decisions made with Jessica this session (IMPORTANT — honour these)

- **PLATE stays a CLASSICAL engine. It must run fully, correctly and deterministically
  with NO LM Studio, NO GPU, and NO heavy ML deps.** This is a hard invariant.
- **AI (LM Studio VLM) stays optional and cosmetic**: semantic names + grouping only,
  off by default (`vlm_url=""`), graceful fallback. It never touches geometry. Keep it
  that way. The ONE place a model could ever earn a geometric role is the provable
  "no signal" cases (splitting two touching same-colour shapes; merging posterized
  fragments that are semantically one object) — and only if a classical approach
  stalls. Do not force AI into segmentation/completion.
- **CPU only for now.** Jessica is interested in "use whatever hardware is available
  (CUDA/Metal/CPU)" for a future hosted converter, but explicitly chose to stick to
  CPU for now. Do NOT add GPU code. If revisited: build a device-capability layer with
  a guaranteed CPU fallback and within-tolerance CPU-parity tests, and PROFILE first —
  most of the hot path (contours, occlusion logic, Schneider fitting, VTracer) is
  branchy CPU code that does not move to GPU profitably; only palette assignment and
  bulk fits are GPU-shaped.

## Gotchas you will hit

- **System `python3` is 3.9 — too old.** Always use `.venv/bin/python` / `.venv/bin/pytest`
  (Python 3.11). `pip install -e ".[dev,render]"` is already done.
- **Rendering needs libcairo via a dyld shim on macOS.** The `plate` CLI self-handles it
  (re-exec with `DYLD_FALLBACK_LIBRARY_PATH`). But when you call the library directly in
  a script or run `pytest`, PREFIX with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`,
  or `have_renderer()` is False and all SSIM/silhouette checks silently skip.
- **git commits hang because of a global identity-prompt hook (CORRECTED — this is the
  real cause, not the commit template).** `core.hooksPath` points at `~/.git-templates/hooks`;
  its `pre-commit` hook opens an AppleScript "Select Identity" GUI (`osascript choose from
  list`) that blocks forever in a non-interactive shell. The hook itself honours a bypass:
  `hooks.skipidentityprompt=true`. Commit with:
  `GIT_EDITOR=true git -c hooks.skipidentityprompt=true -c commit.template= -c gpg.program=/tmp/gpg-batch.sh commit -F <msgfile>`
  where `/tmp/gpg-batch.sh` is `#!/bin/sh` + `exec /opt/homebrew/bin/gpg --batch --no-tty "$@"`.
  GPG signing IS enabled and DOES work once the hook is bypassed (standalone gpg was never the
  blocker; earlier sessions misattributed the hang to the template/gpg). All `-c` flags are
  per-invocation; do NOT change git config. Commits stay signed.
- **`try_complete` is imported by name into `order.py`, `gradient.py`.** Monkeypatching
  `complete.try_complete` won't intercept those call sites; patch `order.try_complete` etc.
- **`tests/challenges.py` strict-xfail contract:** a gap that starts passing causes a strict
  XPASS that FAILS the suite until you remove its `gap=` marker. That is intended — it forces
  you to consciously promote a fixed gap. Never edit a `.target.svg` to match pipeline output.

## Verification discipline (from AGENTS.md)

1. `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q` green before and after.
2. For any pipeline change, also `plate bench samples` AND `plate bench samples/challenges`,
   confirm the eight original samples stay byte-identical (or record the fidelity delta
   honestly), and render/inspect changed SVGs. Never remove the plain-VTracer baseline (`baseline.py`).
3. Add a regression test for every fix. When a gap closes, promote it (remove the `gap=`).

## Commands

```sh
cd /Volumes/Code/PLATE
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate bench samples -o /tmp/plate-bench
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate bench samples/challenges -o /tmp/plate-challenge-bench
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate doctor   # deps + LM Studio
```

## Still unverified (need a human / real inputs)

- **Illustrator import** (`docs/illustrator-checklist.md`): do top-level `<g>` become named
  layers, are circles/rects/gradients live and editable? Oldest open P0.
- **Real-world corpus**: gather 10–20 logos/clipart/scans into `samples/real/`, `plate bench`.
- Real LM Studio naming/grouping IS verified (qwen/qwen3.8-27b); naming accuracy (left/right
  eye) and ~6s/shape latency remain open. Do not repeat the stale "mock only" claim.
