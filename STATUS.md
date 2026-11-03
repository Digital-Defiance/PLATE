# STATUS (update this at the end of every work session)

Last updated: 2026-11-03 (expandable layer/object tree) · Version 0.1.0 · Tests: 841 passed, 7 expected feature gaps.




## Expandable layer/object tree — 2026-11-03 (publication approved)

Owner noticed the demo looked as if PLATE found only two objects. The SVG actually has
**10 drawable objects**; the browser glue discarded every group's children and the list
showed only two top-level entries. Prepared from **`ad9d757`** on `main`; Jessica explicitly
approved publication on 2026-11-03. GitHub Pages deployment verification is recorded separately.
Existing Kiro metadata is excluded.

- `_summarise_layers` now includes actual recursive group contents, preserving names and
  sibling-local bottom-to-top order. Top-level names/kinds/order and the four-key result
  envelope remain unchanged; no synthetic SVG layer wrappers are added to the object tree.
  `LayerInfo.children` is optional so older flat summaries still render safely.
- The panel is now **Layers & objects**. Native keyboard-accessible details/summary controls
  expand/collapse groups, with drawable-descendant counts (folders are not objects). Results
  with ≤30 drawable objects start fully expanded; larger results open top-level groups and
  collapse deeper folders. Empty/legacy groups do not get misleading empty expand controls.
  Names remain inert text at every depth. A bounded scrolling pane handles larger artwork.
- Actual browser demo: **2 root rows → 13 tree rows (10 objects + 3 groups)**. All ten objects
  are exposed; group counts are **9 / 5 / 4**. The SVG markup is **byte-identical before/after**
  this change. Verified mouse collapse, Enter-key expansion, and 390px mobile layout with
  content width 390px (no horizontal overflow). Source/converted images and the full tree
  were rendered/inspected together; exported geometry/layers have not changed.
- Real reload testing caught a **cached same-version engine wheel**: new UI initially received
  the old flat summary. The static build now hashes all `src/plate/**/*.py` plus pyproject.toml
  and embeds that source revision in the same-origin wheel URL query. Changes to Python or
  packaging fetch a fresh wheel even while package version stays 0.1.0; unchanged content
  reuses cache. Scientific dependency pins are untouched. The same local origin that reproduced
  the stale summary then received the new nested data without manually clearing its cache.
- **Validation:** before **838 passed / 7 xfailed** (453.81s), after **841 passed / 7 xfailed**
  (479.20s); no skips/exclusions/xpasses. Focused conversion module **46 passed**; final three
  hierarchy pins rerun after test lint cleanup. Browser tests **270 → 278 passed**; TypeScript
  typecheck/build, new Python test Ruff and `git diff --check` pass. Three Python regressions
  failed against the old summary; four of five tree UI regressions failed (the legacy-flat
  control already passed). Three more tests cover source-revision invalidation and wheel URLs.
- Evidence: `out/web-review/layer-tree-demo.png`, `layer-tree-mobile.png`,
  `layer-tree-validation.json`; `/tmp/plate-layer-tree-{before,after}-pytest.txt`,
  `/tmp/plate-layer-tree-{before,after}-web.txt`, focused/red logs. Local review:
  `http://127.0.0.1:8765/`. No new pipeline/bake-off/robustness changes or claims; the separate
  Research Force browser/native discrepancy and proposed batch workflow remain follow-ups.


## Website published — 2026-11-03

- Owner approved shipping the reviewed website work. Signed feature commit **`7378dd0`**
  was pushed to `origin/main`; unrelated Kiro execution metadata was excluded.
- GitHub Pages build and deploy both succeeded:
  https://github.com/Digital-Defiance/PLATE/actions/runs/41702484129
- Verified https://plate.digitaldefiance.org/ serves the new welcome, object/layer explanation,
  direct picker, example and new presets. The public example completed with SVG preview,
  named layers and an enabled download. Switching to Line art updated that same image
  without selecting it again. Production screenshot: `out/web-review/published-website.png`.
  Existing validation remains **838 Python passed /
  7 xfailed**, **270 browser tests passed**; no code changes after that validation.
- The known Research Force browser/native quality discrepancy remains documented below.
  Batch support remains a proposal; no batch functionality was included in this release.


## Browser welcome, preset recipes and retained-image updates — 2026-11-03

Owner asked for a clearer/more attractive live website, easier settings, Research Force-style
presets and adoption strategy; then explicitly asked for settings changes to re-render. Prepared
on `main` from `934e1aa`; Jessica explicitly approved committing and pushing this checkpoint
on 2026-11-03. GitHub Pages deploys from the push; deployment verification is recorded separately.
Existing Kiro execution metadata edits are excluded. No PDF/AI exporter (owner declined).

- Replaced the unexplained first-use experience with an explicit PNG/JPG → editable layered SVG
  heading, object/stroke/named-layer explanation, three steps, optional inline SVG help and a
  primary image-picker button. No modal/account gate. Included a real same-origin badge example
  that runs through intake/the worker. Styled the settings and tucked technical controls into
  Fine-tune. Mobile checked at 390px, no horizontal overflow.
- Settings now retain one source image and debounce changes for 350ms. One request at a time;
  latest pending config/image wins, superseded results/errors cannot overwrite current output.
  Preserve source bytes across worker transfers, invalidate old downloads immediately, and clear
  timers/listeners on dispose. A newly selected image replaces pending work; stale intake reads
  cannot replace a newer selection. Nine controller tests cover queue/transfer/race/cancel/retry.
- Exposed existing `smooth` and `max` presets. Browser-only `logo-detail` recipe emits
  `{preset: "smooth", upscale: 2}`; the Python web glue adds a bounded 1–2 `upscale` lever.
  No core/default config or tracing algorithms changed. Preset display values now follow the
  chosen recipe instead of retaining old slider positions. Runtime warm-up no longer leaves
  Done / 100% before image selection. 2× is labeled slower/more memory.
- **Real browser checks:** example conversion, switching to line art, slider changes,
  background toggle, reset and Research Force at smooth+2× all completed without re-selecting
  the image for settings changes. Named layers/preview/download appeared. The primary picker
  was tested with the fixture, and an actual `research_force_logo.svg` downloaded successfully.
- **Quality discrepancy remains:** actual browser Research Force SVG has SSIM **.975083**,
  edge F1 **.996153**, topology **1 extra / 3 missing**, 43 shapes/594 serialized anchors;
  native same-recipe rerun has SSIM **.977355**, edge F1 **.999358**, topology **0/0**,
  39 shapes/600 serialized anchors. Config mapping is tested; root cause of cross-runtime
  output differences is **not established**. Do not claim platform byte/topology parity or
  use this as a flawless quality showcase. Compare decoding and numerical libraries next;
  do not weaken gates. Native Illustrator acceptance of this web output was not checked.
- **Validation:** before full Python **832 passed / 7 xfailed** (446.73s), after **838 passed /
  7 xfailed** (483.68s), no skips/xpasses/exclusions. Browser tests **256 → 270 passed**;
  TypeScript typecheck/build and `git diff --check` pass. Nine existing Ruff findings in the
  touched Python files have the same rule counts before/after; no unrelated lint cleanup.
  No pipeline changes: the prior 70/78 robustness/36 core engine audit is not re-certified
  as a fresh sweep here. Six new Python cases pin scale bounds and the logo recipe.
- Plan: `docs/WEB-EXPERIENCE.md` separates implemented work from acquisition/product proposals.
  Priorities: shape/layer inspection and editing, browser/native JPEG discrepancy, compact
  returning-user intro, permission-cleared real examples, factual comparison/use-case pages,
  community demos and privacy-preserving activation measurement. No telemetry/outreach added.
- Evidence: `out/web-review/` holds SVGs/quality JSON and welcome screenshots; detailed test
  logs `/tmp/plate-web-rerender-{before,after}-{pytest,web-tests}.txt`. Local build served at
  `http://127.0.0.1:8765/` for review. Deploy remains the existing GitHub Pages workflow.


## THE CLASSICAL ENGINE IS COMPLETE (Task 15 / R8) — 2026-11-02

This is the closure audit for the engine-completion spec. It is an audit, not a code
change: **no source touched, no gate moved, GC-5 held.** Every in-scope engine-quality
gap (R1–R7, R9, and each sub-item) is now recorded in exactly one terminal state —
**(a) FIXED** (a real diagnostic number moved, pinned by a regression test) or
**(b) DOCUMENTED LIMIT** (measured pixel proof that no classical cue exists, pinned so it
cannot silently drift). Nothing is left in limbo. This is the line after which classical
engine development stops; everything past it is the out-of-scope boundary (OOS-1..5) below.

### Ceiling statement (the honest count)

Across the 20 in-scope terminal-state outcomes: **9 FIXED (a) · 11 DOCUMENTED LIMIT (b).**
(Plus R8, this audit, and Task 14, the bake-off verification harness — infrastructure, not
an engine-gap outcome.) A LIMIT is a first-class resolution: it is a measured proof that
the raster does not contain the information, not a failure or a deferral. The largest
cluster of limits — R3, and the ROOT/EMBER/storefront structural gaps behind it — is the
engine's hard classical ceiling: colour-only segmentation cannot split touching regions of
identical fill without inventing a boundary that is absent from the pixels (that needs an
ML segmenter such as SAM, which is out of scope, OOS-5).

### Regression surface — re-verified green from the tree (GC-4)

- `pytest -q`: **699 passed / 7 xfailed / 0 xpassed** (the 7 strict-xfail structural gaps
  intact: mission_patch, storefront, event_poster, EMBER, ORBIT, ROOT, PLATE identity).
- `python -m plate.robustness`: **full 70/78**, **core 36/36** (failing set identical to
  the spec baseline).
- **24 shipped sample + challenge SVGs** preserved (the asset-contract and brand byte-compare
  tests in `test_logo_assets.py` / `test_complex_scene_assets.py` / `test_challenges.py` are
  all green); the plain-**VTracer baseline** (`src/plate/baseline.py`) is present.

### Per-requirement terminal-state ledger

Every item names its moving number (state a) or its pin test (state b).

| Req | Item | State | Evidence / moving number | Pin test · task |
|---|---|---|---|---|
| **R1** | JPEG occlusion recovery | **(a) FIXED** | JPEG-variant `hidden_completion` 0.333→0.417 (3/10→4/10); floor 0.4 met, 0.6 stretch not | `test_bakeoff.py::test_jpeg_variant_hidden_completion_meets_floor` · T1 |
| R1 | residual clean-render misses | **(b) LIMIT** | scene15 ×2 / scene23 ×1 recover 0 on the clean render at every denoise level (an R2/T4 completion limit, not a JPEG bug) | 14 clean-render pins in `test_bakeoff.py` · T2 |
| **R2** | rect/polygon amodal completion | **(a) FIXED** | free-edge line-intersection: polygon 2→3/10, overall 32→33/57, `hidden_completion` 0.549→0.562, composite 0.852→0.857 | `test_free_edge_completion.py` (4 cases) + `test_bakeoff.py::test_free_edge_lifts_occluded_rectilinear_completion` · T4 |
| R2 | residual rrect near-miss | **(b) LIMIT** | reconstructed sharp quad loses corner rounding (best IoU 0.85–0.90 band) | `test_bakeoff.py::test_free_edge_residual_rrect_is_a_measured_near_miss` · T4 |
| **R3** | same-colour touching merge | **(b) LIMIT** | the hard classical ceiling — no concavity/defect cue splits an abutting same-colour component without inventing a boundary (EMBER/ROOT/storefront) | raster-contiguity pins in `test_logo_assets.py` / `test_complex_scene_assets.py`; investigation `.agents/tasks/same-colour-split-investigation.md` · T7 |
| **R4** | realistic gradient (orb) | **(a) FIXED** | smooth-ramp pre-pass: `real_radial_orb` 1 obj/0 grad/SSIM 0.8276 → 1 radial disc/SSIM 0.9455 (beats VTracer 0.9094) | `test_gradient_bands.py::test_smooth_single_ramp_region_recovers_the_orb_as_one_radial_gradient` + flat-art negative · T3 |
| R4 | `real_sunset_gradient` | **(b) LIMIT** | `_monotone_ok` correctly rejects a 94-band non-ramp blob (backstep 149–363 vs budget 15.3) | flat-art negative pin in `test_gradient_bands.py` · T3 |
| **R5** | heavy sensor-noise / JPEG-artifact collapse | **(b) LIMIT** | noise destroys the flat-colour structure; a gate low enough to catch it re-denoises shipped `logo_orbit_wordmark` (breaks byte-identity) | 4 pins in `test_real_corpus.py` (`..._is_not_a_denoise_trigger_gap`, `..._even_at_maximum_denoise`, `..._below_the_gate_and_overlaps_shipped_art`, `..._changes_a_shipped_svg`) · T8 |
| **R6a** | ROOT inner-seal ring | **(a) FIXED** | circle-arm reunion: inner-seal IoU 0.2715→0.4073, topology (1,0)→(7,0), extras 7→1 | `test_interrupted_loops.py` (1 real + 1 synthetic positive, 2 negatives) · T5 |
| **R6b** | ROOT leaf-vein-11 split | **(b) LIMIT** | sub-pixel segmentation, not a stroke-floor: the ~3.4px vein is cut upstream (one physical cream region, radius ≤3.5px) | `test_logo_assets.py::test_root_leaf_vein_11_splits_at_a_subpixel_bend_not_a_stroke_floor` · T6 |
| **R7a** | thin-colour / hairline discovery | **(b) LIMIT** | sub-pixel floor: a 2px fully-AA mark has no stable colour core (admitted at ≥3px) | `test_segment.py` (admitted ≥3px / below-floor 2px) + `test_robustness.py::test_hairline_route_*` · T9 |
| **R7b** | thin occluded rectangles | **(a) FIXED** | corrected pixel-boundary (interior-coverage) eval in hidden-area validation: an 8–16px occluded bar completes to one `<rect>` (was 2 fragments) | `test_free_edge_completion.py::test_thin_occluded_bar_completes_into_one_rect` (+ control + negative) · T9 |
| **R7c** | palette pressure >64 / k-means | **(a) FIXED** | new `scripts/make_mosaic.py` fixture; k-means path recovers 73/130 (`max_colors=96`), 113/130 (130) | 3 pins in `test_segment.py` (verbatim ≤ceiling / default-budget collapse / k-means recovery) · T9 |
| **R7d** | nonuniform / soft alpha + shadows | **(b) LIMIT** | one flat opacity cannot match two backgrounds (feathered disc SSIM 0.856 white / 0.721 black); new `scripts/make_soft_alpha.py` | 3 pins in `test_inputs.py` (uniform OK both bg / feathered can't match both / soft-shadow band) · T10 |
| **R7e** | scale consistency | **(b) LIMIT** | measured work_size gradient floor: `gradient_badge` lost at 200, consistent 1 grad/5 shapes ≥250 (per-step dE 17–60 vs `grad_step_de` 14 at w=200) | 2 pins in `test_gradient_bands.py` (scale-consistent above floor / 1×–2× source) · T10 |
| **R7f** | ring / compound-path naming | **(a) FIXED** | classical `name.shape_word`: even-odd + 2 subpaths → "ring"; `t3_ring` "Red shape"→"Red ring", topology byte-identical | `test_controls.py` t3_ring branch (name + evenodd + `d.count("M")==2`) · T10 |
| **R7g·1** | overlapping-object false split/merge | **(a) FIXED** (verified) | `5692fa9` confirmed at HEAD; `diff_target(svg,svg)` on identical overlapping rects (IoU 0.25) → 0 false splits | `test_challenge_diff.py::test_r7g_identical_overlapping_rects_self_diff_reports_zero_false_splits` · T11 |
| **R7g·2** | short curved butt cap | **(b) LIMIT** | butt cap's flat front span ~2.0–2.75px < the 0.75·width = 3.03px gate; all 24 shipped targets use `round` caps only | `test_exposed_curve_refit.py::test_short_butt_cap_curve_emits_a_round_cap_measured_limit` · T11 |
| **R9** | real-artwork clean-line `smooth` preset | **(a) FIXED** | opt-in levers (default + 24 SVGs unchanged by construction); logo SSIM ≥0.97, edge F1 ≥0.99, topology 0/0, both periods + V dot, ≤700 anchors; report-only `topology`+`smoothness` metrics (weight 0) | `test_research_force_logo.py`, `test_topology_metric.py`, `test_smoothness_metric.py` (13.1–13.8 all done) · T13 |
| R9 | outline-wobble residual | **(b) LIMIT** | sub-piece wobble (~50 under-bar px, right tip ~1px short) creates no extra/missing piece; SSIM/edge-F1 cannot see it; 3 broad fixes tried and rejected | `test_research_force_logo.py::test_outline_smoothness_is_measured_and_bounded` (0.90≤smoothness≤1.0, wobble≤0.01) · T13.8 |

**Tally: 9 FIXED (a) · 11 DOCUMENTED LIMIT (b) = 20 outcomes, 0 in limbo.** Task 14
(bake-off round-trip/quality verification — `fidelity`/`topology`/`smoothness` surfaced
end to end) and R8 (this audit) are infrastructure/closure, not engine-gap outcomes.

### Out-of-scope boundary (OOS-1..5) — the line where engine development stops

These need external resources that cannot reach a verifiable in-repo terminal state, so
"engine complete" is defined without them. Not worthless — just not classical-engine quality.
- **OOS-1** Illustrator desktop validation beyond the automated 24-case / 636-check suite
  (live-shape widgets, direct gradient-stop edits, 4× seam checks, broader AI versions) —
  needs a Mac with Illustrator + human interaction.
- **OOS-2** real LM Studio VLM naming/grouping quality + latency — the path is verified and
  the VLM is cosmetic (GC-2); judging quality needs a live vision model + human judgement.
- **OOS-3** external-tool bake-off entries (Illustrator Image Trace, Vectorizer.AI, Inkscape)
  — need those apps + manual SVG exports.
- **OOS-4** PLATE identity logo structural target — hidden back-P geometry is not uniquely
  recoverable from the raster; stays strict-xfail permanently (a permanent documented limit).
- **OOS-5** product / infra, not engine quality — hosted service; browser/Pyodide shell
  (its own spec); PyPI/CI/packaging; PDF/AI export; the SAM segmenter; `--open` / `--watch`.

Continued on `codex/logo-quality`; nothing pushed (owner pushes). Audit evidence: this run's
`pytest -q` (699/7/0), `plate.robustness` (70/78 full, 36/36 core), and the intact xfail set
listed above.

## ROOT inner-seal interrupted circular ring (Task 5 / R6a) — FIXED (a) — 2026-11-01
Continued on `codex/logo-quality`; nothing pushed. Closes R6a in terminal state (a).
- **Problem (measured first).** `DIAG -m challenge_report logo_root_seal` showed the
  `#a9d1b5` inner-seal circular ring (r≈278 from (450,369)) split into **6 extra `Beige_*`
  arc fragments**, matched only as an open arc at **IoU 0.2715**, topology **(1, 0)**. The
  circle arm of `order._merge_compound_siblings` already clusters the arcs (shared 15° T-junction)
  and the pooled convex-hull common-circle fit passes (rms/r 0.0052, arc 345°), but the merge
  was vetoed: five short arc slivers (areas 140–358) each snap to a tiny **rect/rrect** on their
  own, because a few-degree arc looks locally rectangular, and the existing veto treats any
  member snapping to a closed primitive as a finished object.
- **Fix (no gate relaxed, GC-5).** In the circle arm only: (1) classify each member by its
  pixels' MEDIAN distance to the fitted centre as ON the ring (within `max(6, 0.08·r)`) or OFF;
  (2) exempt from the veto an ON-ring member that snaps to a **rect/rrect** (the boxy-sliver false
  positive) — a member snapping to a **circle/ellipse** is a genuine complete curved object and
  still vetoes (keeps e.g. `samples/badge.png` byte-identical, where a nearly-whole disc lies on
  the same circle); (3) when a large same-colour OFF-ring leaf was pooled into the hull
  (`big_off_ring`, area ≥ 25% of the total on-ring mass — stable whether arcs are split or
  merged), reunite ONLY the on-ring arcs and re-fit the circle on exactly those with the SAME
  `fit_circle` rms≤0.02·r / arc≥160° gates, so adjacent leaves keep their identity. The ellipse
  arm gained the same off-band leaf guard. All reuse the existing fit; no threshold loosened.
- **Result.** `logo_root_seal`: the 7 on-ring arcs reunite into one compound path — **inner-seal
  IoU 0.2715 → 0.4073**, topology **(1, 0) → (7, 0)**, **extras 7 → 1** (the remaining
  `Beige_ellipse_3` is the separate Task 6 leaf-vein split); object count 51 → 45; `matched`
  stays 44 with leaf-3/leaf-6 NOT swallowed. ROOT stays xfail (its dominant gap is the Task 7
  same-colour limit) — the criterion is the per-object improvement, met.
- **Pins.** `tests/test_interrupted_loops.py`: one positive on the real asset
  (`test_root_inner_seal_arcs_reunite_into_one_ring_without_swallowing_leaves`), one synthetic
  positive (`test_circular_ring_crossed_by_a_shared_occluder_reunites`) and two negatives
  (`test_off_ring_same_colour_disc_is_not_merged_into_the_ring` — contaminated hull;
  `test_arcs_without_a_shared_occluder_are_not_reunited` — no shared occluder). `test_strokes.py`
  stroke/shape-count pin updated (ROOT 51 → 45 shapes, strokes ≥ 8).
- **Validation.** Full suite **670 passed / 7 xfailed / 0 xpassed**; robustness **core 36/36,
  full 70/78**; **24 shipped SVGs byte-identical except `logo_root_seal`** (orbit, mission_patch,
  badge and the other 20 confirmed unchanged by md5).
## Smooth single-ramp region detector (Task 3 / R4) — FIXED (a) — 2026-11-01
Continued on `codex/logo-quality`; nothing pushed. Closes R4 in terminal state (a).
- **Problem (measured first).** `real_radial_orb` is a blue radial-gradient orb on a flat
  near-white ground. Its ramp colours never repeat (29617 unique colours, max repeat frac
  0.0098), so the count-floor palette keeps only the ground colour `(239,234,224)`; `segment()`
  emits **one** full-canvas region and `gradient.detect()`'s band path sees zero candidates.
  Baseline: **1 object, 0 gradients, SSIM 0.8276**.
- **Fix.** New additive pre-pass `gradient.detect_ramp_region`, run at the top of `detect()`.
  It flags a region by the measured smooth-ramp signature — luma span ≥120 (orb ~245), interior
  Lab-gradient median ≤8 (orb 6.66 = smooth, not noisy), unique-colour frac ≥0.03 (orb 0.060)
  and max single-colour repeat frac ≤0.05 (orb 0.0098) — carves the ramp blob out of its flat
  surround (largest 4-connected run >16 RGB from the region colour), fits the EXISTING
  `fit_radial_gradient`/`fit_linear_gradient` on the eroded blob interior (orb radial residual
  **0.0307**), and accepts only at residual ≤ `grad_max_residual` (0.06). On accept it replaces
  the one region with a gradient `Shape` (the blob) + the flat remainder; no palette colour added.
- **Result.** `real_radial_orb` → **2 shapes, 1 radial-gradient disc + flat background, 100%
  prim, SSIM 0.9455** (0.8276 → 0.9455; now beats VTracer's 0.9094). `<radialGradient>` emitted.
- **Additive by construction.** Flat art / discrete palettes / already-posterized ramps all
  carry a large repeated-colour mass (discrete_palette 0.53, twin_gradients 0.50, gradient_badge
  0.57) so they fail the signature and keep the unchanged band path. Verified unchanged:
  `shaded`→1 radial (SSIM 0.9557), `discrete_palette`→0, `twin_gradients`→2, `gradient_badge`→1,
  `real_sunset_gradient`→0 (still correctly rejected by `_monotone_ok`). t3/t4 gradient controls
  and the 24 shipped SVGs unchanged (test_controls + full suite green).
- **Pins.** `tests/test_gradient_bands.py::test_smooth_single_ramp_region_recovers_the_orb_as_one_radial_gradient`
  (one radial disc, `<radialGradient>`, SSIM > 0.83 and ≥ 0.90) and
  `::test_flat_art_does_not_trigger_the_smooth_ramp_pre_pass` (discrete_palette → 0 gradients).
- **Validation.** Full suite **660 passed / 7 xfailed** (was 658; +2 pins, xfail unchanged);
  robustness **core 36/36, full 70/78**; `plate bench samples/real` shows the orb improved.

## Outline smoothness metric (13.5) + 13.6 pinned as a documented limit — 2026-11-01

Continued on `codex/logo-quality` from checkpoint **`cfe42e2`** (clean tree, 651/7 reproduced);
nothing pushed. This closes the two items the prior handover left open under R9/Task 13.

- **13.5 (a) — bake-off smoothness metric.** `score.smoothness(ren, ref)` traces every solid
  same-colour outline (reusing the topology palette/class-map, so blends are excluded) and sums
  its absolute turning (direction change) per unit arc length, resampled at a fixed step so
  single-pixel staircase jitter does not dominate. It reports the render's EXCESS turning over
  the reference as `wobble`; `smoothness = 1/(1+8·wobble)` in [0,1], 1 = as smooth as the source.
  One-sided (a crisp render of a wavy source is not penalised) and blend-aware (soft JPEG vs
  crisp render agree). **Report-only:** not in `DEFAULT_WEIGHTS`, so every composite is unchanged;
  carried through `fidelity()`, `summarise` and the HTML report label, exactly like `topology`.
- New opt-in **`plate-smooth`** bake-off adapter runs PLATE under the `smooth` preset so
  smooth-vs-default is measurable side by side. It is NOT a default `--tools` entry (slower).
- **Measured.** Seed-1 synthetic corpus (n=24): plate smoothness **0.9942** / wobble 0.00074,
  plate-smooth **0.9958** / wobble 0.00054 — smooth marginally smoother, composite flat
  (0.8515 vs 0.8493, report-only). Real corpus (`samples/real`, 14 imgs): plate **0.9854**,
  plate-smooth **0.9843**; the metric isolates `real_jpeg_artifacts` (**0.80**, real ringing
  wobble) from clean images (1.000) and surfaces that smooth adds minor contour detail on
  `real_soft_shadow_card` (**0.975**). That small smooth-lower aggregate is a real, recorded
  observation, not hidden. Six pins in `tests/test_smoothness_metric.py`.
- **13.6 (b) — DOCUMENTED LIMIT.** The earlier ownership sub-fix already cleared the floating
  spine knobs. The logo under `smooth` now measures **topology 0 extra / 0 missing**, SSIM
  **0.977355**, edge_f1 **0.999358**, anchors **348**, smoothness **0.9736** / wobble **0.0034**.
  The residual (~50 under-bar overlay pixels, right gap tip ~1 px short) is sub-piece wobble
  that creates no extra/missing piece and that SSIM/edge-F1 cannot see. All three broad fixes
  were tried and rejected before (global mask-blur reduction and blanket tip suppression each
  made 2 extra dark pieces; the 35% fold clamp showed no synthetic gain). Pinned by
  `tests/test_research_force_logo.py::test_outline_smoothness_is_measured_and_bounded`
  (0.90 ≤ smoothness ≤ 1.0, wobble ≤ 0.01). Do not relax the topology/foreign-object guards.
- With 13.5/13.6 terminal, **parent Task 13 (R9) and its sub-items 13.1–13.8 are all done.**
- **Validation:** baseline **651 passed / 7 xfailed** reproduced on a clean tree; after
  **657 passed / 7 xfailed** (+6 smoothness pins, xfail unchanged); core robustness **36/36**.
  The default `plate` conversion path is untouched (changes are bake-off scoring + an opt-in
  tool only), so the 48 default/control SVGs are unaffected. New code matches the project's
  existing Ruff style (the only flag is the same `dict()`-literal rule the committed
  `score.py`/`test_topology_metric.py` already use). Native Illustrator acceptance of the
  logo revision remains outstanding; do not claim R9 visually verified in Illustrator.

## Bounded sharp-corner recovery + Task 2 residual pin — 2026-11-01

Continued on `codex/logo-quality` from signed checkpoint **`d5d0bf6`**; nothing pushed.

- In clean/`edge_smooth` tracing, refine an **already detected sharp corner** against the
  unblurred mask contour. Require matching contour count and outer area within 5%, matching
  convex/concave sense, the existing straight-flank line-fit gates, and displacement bounded by
  max(2.5, 3·mask sigma) working pixels. Only extend a supported tip; do not add corners or alter
  masks. Holes keep their existing tracing; default mode never requests this reference.
- Independently authored triangles and concave notches at 2×/4× reproduce >1 source-pixel tip
  loss without the reference, and <0.2px error with it. Fifteen regressions also cover rotations,
  reversed winding, round boundaries, distant references and the displacement bound. The 15
  new corner cases failed before implementation; no prior tests/gates were weakened.
- Logo: left/right vertical-tip bottom y **805/806 → 807/806**, versus source-luma y **807/807**.
  SSIM **0.977286920 → 0.977354943**, MAE **1.285310984 → 1.281820893**. Still 39 editable
  shapes, 600 serialized anchors, 4 colours, topology **0 extra / 0 missing**, both periods/V dot.
  Spine overlays remain 0; under-bar overlays remain 50 source pixels.
- Same 24-scene `smooth` bake-off: composite **0.849340515 → 0.849336896** (effectively flat),
  SSIM **0.989570306 → 0.989566773**; object F1 **0.707263801** and hidden completion
  **0.548611111** unchanged. Scene16 improves, scene19 JPEG regresses slightly. Weights unchanged.
- **Task 2 done:** 14 pins render the independent truth SVGs directly to clean PNGs (not
  re-encoded JPEGs), then test denoise -1/0/1/2/3/4/6. The two occluded objects in scene15 and
  one in scene23 still recover 0. These are measured completion/matching limitations owned by
  **R2 / Task 4**, not proven information-theoretic impossibilities. Update pins when that work
  improves recovery. Task 1 remains done at its 0.4 floor; the 0.6 stretch remains unmet.
- Rejected scratch colour repairs: widening achromatic pair eligibility globally damaged many
  labels; restricting to third-colour pixels barely helped; a local repair reduced under-bar
  overlays 50 → 38 but worsened SSIM to .976646. None is shipped. The gray JPEG pixels currently
  assigned to blue merit segmentation work; do not erase the connectivity-protected island.
- **Validation:** baseline **622 passed / 7 xfailed** (324.16s), after **651 passed / 7 xfailed** (371.99s);
  no exclusions/skips/xpasses; focused **42 passed**. Full/core robustness **70/78 / 36/36**;
  all **24 PLATE + 24 VTracer default SVGs byte-identical**. Sample renders and enlarged
  source/before/after logo crops inspected. New corner test passes Ruff; `git diff --check` passes.
- New artifacts: `out/research-force/logo.plate-corner-reference.{svg,png,report.html}`,
  `logo-corner-reference-comparison.png`, `corner-reference-validation.json`. Earlier artifacts
  preserved. Detailed evidence: `/tmp/plate-tips3/` and `/tmp/plate-tips3-before-tests.txt`.
- **Still open:** Task 13.6 (50 under-bar overlay pixels, right tip 1px short), 13.5 smoothness
  scoring, and native Illustrator acceptance of the new revision. Do not claim R9 complete.

## Small-gap anchors and safe partial reconnection — 2026-11-01

Continued on `codex/logo-quality` from **`4c887d3`** (the preceding ownership checkpoint).
Both preceding commits, `c036114` and `4c887d3`, are committed/signed; nothing pushed.

- Small gaps no longer require a large region when there is **one unique solid source core**.
  Erode the candidate by `ceil(scale)` working pixels; require opaque pixels within 12 RGB of
  the region colour, with area ≥ max(`rescue_min_area`, 6 source pixels² scaled to work area).
  Multiple solid-core anchors remain ambiguous and are rejected. A promoted `Shape.detail_owner`
  survives reindexing, is not absorbed into the later fine-detail overlay, and uses the same
  gentler trace profile as fine detail. No new public lever or default behaviour.
- If a proposed full transfer would split off only a tiny donor lobe (below that area threshold),
  attempt a **safe subset**: each transferred pixel must touch the target and leave the donor's
  local four-connected neighbourhood connected. Keep articulation pixels/foreign objects.
  Larger donor splits still reject the entire proposal. All previous guards/tests retained.
- Logo: under-bar overlay pixels **141 → 50**; spine overlays stay **0**. SSIM
  **0.976205 → 0.977287**, MAE **1.344313 → 1.285311**, serialized anchors **624 → 600**.
  There are **39 separately editable shapes** (previously 32; several gaps now have their own
  region rather than sharing a compound detail path), 4 colours, topology still **0 extra / 0 missing**.
- Same 24-scene `smooth` bake-off: composite **0.848961 → 0.849341**, whole-object F1
  **0.706323 → 0.707264**, hidden completion unchanged **0.548611**; SSIM slightly lower
  **0.989577 → 0.989570**. Scene03 JPEG improves (.753250 → .772350); scene23 JPEG regresses
  (.687155 → .677159). Keep both results visible; no weights or acceptance floors changed.
- Rejected scratch experiments: reducing spatial mask blur globally recovered one vertical tip
  but introduced **2 extra pieces**; suppressing all connected tips in the final detail pass also
  introduced **2 extra dark pieces**, at approximately (259,671) and (342,672). Neither is shipped.
  Do not claim the remaining overlay can simply be deleted, or retry the earlier fold clamp as-is.
- **13.6 remains open:** 50 under-bar overlay pixels and the **1–2 source pixel vertical-tip
  shortfall** remain. Source-luma bottom y=807; current left/right y=805/806. These are measured
  algorithm cases, not claimed information limits. 13.5 smoothness scoring and Task 2's clean-render
  residual pin also remain open; native Illustrator acceptance of the new logo is outstanding.
- **Validation:** before **615 passed / 7 xfailed** (322.25s), after **622 passed / 7 xfailed**
  (321.90s), no exclusions/skips/xpasses; focused **45 passed**. Seven new cases cover unique/weak/
  ambiguous small anchors, safe partial transfer, whole foreign-object preservation and owned
  tracing; four failed before implementation, three protected already-correct behaviour.
  Full/core sweep **70/78 / 36/36**; all **24 PLATE + 24 VTracer default SVGs byte-identical**.
  Samples and enlarged source/before/after logo crops rendered and inspected; Ruff for new rescue/
  test code and `git diff --check` pass.
- New artifacts: `out/research-force/logo.plate-small-gaps.{svg,png,report.html}`,
  `logo-small-gaps-comparison.png`, `small-gaps-validation.json`. Earlier artifacts preserved.
  Detailed evidence: `/tmp/plate-tips2/`, `/tmp/plate-tips2-{before,after}-tests.txt`.

## Gap-tip ownership + Task 1 audit — 2026-11-01

- Owner requested a commit, Task 1 verification and continued work. Committed the smooth-logo,
  topology and JPEG-edge checkpoint as **`c036114`** on **`codex/logo-quality`**. No push.
  Browser-page draft specs and Kiro execution metadata were left outside this scoped commit.
- **Task 1 really meets its written floor:** same six seed-1/q55 JPEGs with the format trigger
  disabled/enabled recover **3/10 → 4/10** objects; mean per-scene `hidden_completion`
  **0.333333 → 0.416667**, above the **0.4** floor. The **0.6 stretch remains unmet**, and
  Task 2's residual clean-render pin remains open. `/tmp/plate-continue/task1-audit.json`.
- Implemented the ownership part of **13.6**: after segmentation/gradient detection, before
  ordering/tracing, `rescue.reconnect_tips` gives a connected source-supported tip to its one
  non-fragment same-colour region. Rebuild visible/full masks and region IDs together. Reject
  ambiguous multiple targets, gradient/nonopaque pixels, whole foreign-object erasure and
  donor splits. Fine isolated dots/periods remain in the later rescue pass. Default off under
  the existing `rescue_detail` lever; no new default behaviour.
- Logo: **246 working pixels** reassigned; the separate dark fine-detail pixels at the spine
  joins fall **35 → 0**. Enlarged renders show the knobs gone at those joins. Topology stays
  **0 extra / 0 missing**, both periods/V dot survive; SSIM **0.976148 → 0.976205**, MAE
  **1.35239 → 1.34431**, serialized anchors **647 → 624**, 32 shapes, 4 colours.
- **13.6 stays open for measured residuals.** Under the blue bar, one gap has only small
  fragment anchors, so no eligible target; extending another would detach an **8-working-pixel
  blue island**, so the connectivity guard rejects it. Those overlays remain (141 source
  pixels in the inspected under-bar crop). Vertical gap ends remain 1–2 source pixels short
  by a source-luma crop check. These are remaining algorithm cases, not claimed information
  limits; do not relax topology safeguards or repeat the rejected fold clamp.
- Same 24-scene `smooth` bake-off: composite **0.846217 → 0.848961**, whole-object F1
  **0.700787 → 0.706323**, hidden completion unchanged **0.548611**; SSIM slightly lower
  **0.989619 → 0.989577**. No weight/target changes; improvements on scenes 11/21/23.
- **Validation:** baseline **600 passed / 7 xfailed** (366.77 s), after **615 passed /
  7 xfailed** (368.61 s), no exclusions/skips/xpasses. Fifteen new ownership regressions
  cover rotations, fragments/reindexing, dots, ambiguous joins, donor bridges, gradients,
  alpha and pre-trace integration (14 original cases failed before implementation; the
  fragment/reindex case was then added). Full sweep **70/78**, core **36/36**. All **24 PLATE
  + 24 VTracer default SVGs byte-identical**. Sample/full-logo/enlarged crops rendered and
  inspected; new rescue/test code passes Ruff, `git diff --check` passes.
- New artifact: `out/research-force/logo.plate-gap-tips.{svg,png,report.html}`;
  comparison `out/research-force/logo-gap-tips-comparison.png`. Previous SVGs preserved.
  Evidence/logs: `/tmp/plate-continue/`, `/tmp/plate-continue-{before,after}-tests.txt`.
  A fresh native Illustrator review is still outstanding for the new logo.
- Next: remaining under-bar/short-tip cases in **13.6**, smoothness metric **13.5**, and
  Task 2's explicit residual pin. Do not describe all of R1 or R9 as complete.

## JPEG colour-boundary repair — 2026-11-01

Task 1 re-audit (owner requested before committing this checkpoint): exactly reproduced
3/10 → 4/10 JPEG objects, mean per-scene hidden completion 0.333333 → 0.416667 with
the format-keyed trigger disabled/enabled. **Task 1 is done at its ≥0.4 floor**; the
≥0.6 stretch and Task 2 residual-limit pin remain open. Evidence:
`/tmp/plate-continue/task1-audit.json`. This checkpoint is being committed on
`codex/logo-quality`; subsequent gap-tip work will be recorded separately.

Resumed from Jessica's approval at the end of the shared Claude conversation. The current
`STATUS.md` and spec task list matched that session's final checksums; `HANDOFF.md` predated it.
Preserved all earlier uncommitted work. No push requested or performed.

- Added opt-in `Config.jpeg_edges`, enabled by `smooth`, gated on decoded JPEG format via
  `Loaded.is_jpeg` (renamed JPEG/PNG files are tested). Defaults and all PNG paths are unchanged.
- The previous diagnosis was incomplete: **luma alone barely helped**. The two-working-pixel
  seed neighbourhood often contained only one colour after edge dilation/chroma blur. For
  chromatic pairs, search up to `max(4, ceil(4*scale))` working pixels; retain RGB residuals to
  select the pair, then use BT.601 luma for its 50% boundary. Require luma separation ≥32 and
  RGB-difference channel span ≥25% of its norm. Cream/dark, grayscale and near-equal-luma
  pairs retain the old neighbourhood and coverage. The detail-core retry retains these rules.
- All-pair widening was rejected: it added a six-pixel dark pocket near (592, 829). The
  chromatic-pair gate preserves the brightness edges and avoids that regression.
- Independent JPEG-q85 pink/blue line/arc fixtures: boundary errors fall **156–236 → 36–60**
  at 1× and **686–810 → 43–86** at 2×. Seventeen regressions also protect luma/chroma
  disagreement, multi-colour pair selection, low contrast, PNG identity, format gating and overrides.
- Research Force logo, `--preset smooth --set upscale=2`: SSIM **0.975168 → 0.976148**,
  MAE **1.39781 → 1.35239**, topology **0 extra / 1 missing → 0 / 0**. Output: 32 shapes,
  647 serialized anchors. Rendered and inspected the full logo and enlarged colour/spine crops.
  This is an improvement, not a claim that all bends/junctions are clean or Illustrator-certified.
- Same 24-scene seed-1 bake-off, `smooth` at native working scale: composite
  **0.846317 → 0.846217**, SSIM **0.989624 → 0.989619**; whole-object F1 **0.700787** and
  hidden completion **0.548611** unchanged. All 18 PNG SVGs byte-identical; six JPEGs change.
  Weights untouched. Corpus results are effectively flat; the gain is on the real logo/thin edges.
- **Validation:** full baseline **583 passed / 7 xfailed** (366.12 s), final full suite
  **600 passed / 7 xfailed** (367.62 s), no exclusions/skips/xpasses. All 28 focused tests pass;
  all **24 PLATE + 24 VTracer default SVGs** byte-identical to the pre-session source snapshot.
  Rendered and inspected the sample contact sheet; new segmentation/test code passes Ruff;
  `git diff --check` passes. The 17 new tests failed before the implementation was added.
  The first sandbox suite had 582 pass/7 xfail and one local-server bind denial; that test passes
  with loopback access. Full reruns use that access rather than excluding the test.
- Artifacts: `out/research-force/logo.plate-smooth.{svg,png,report.html}` and
  `out/research-force/logo-jpeg-edges-comparison.png`, with measurements in `validation.json`.
  Detailed before/after evidence and logs:
  `/tmp/plate-resume/`, `/tmp/plate-resume-{before-tests-unrestricted,after-tests}.txt`.
- Next: **13.6** (assign supported gap-tip pixels to their owning region before tracing,
  rather than overlaying separate slivers) and **13.5** (a genuine smoothness metric).
  The earlier Illustrator rating applies to the previous SVG; this revision needs a fresh look.

## Clean-line mode for real logos (`--preset smooth`) + topology metric — 2026-11-01

Driven by the Research Force logo (now a fixture: `samples/fixtures/research_force_logo.jpeg`,
`tests/test_research_force_logo.py`). Kiro spec: engine-completion **R9 / Task 13** (13.1–13.4
done; 13.5 smoothness metric and 13.6 junction waviness open; 13.7 checked as "decent"). Task 1 (R1,
JPEG-keyed denoise) done and `docs/BAKEOFF.md` corrected (3/10 → 4/10, 0.33 → 0.42).

- New opt-in levers (all off by default, so default output and the 24 shipped SVGs are unchanged):
  `upscale`, `edge_smooth`, `straighten`, `snap_max_px`, `rescue_detail`, `rescue_min_area`;
  `PRESETS["smooth"]`. New `stages/rescue.py` (fine detail such as a 2 px tagline; absorbs small
  same-colour fragments; bridges tapering gap tips back to their region so they no longer float as
  specks). `find_corners` dedup fix (circular index distance).
- Bake-off: report-only `topology` metric (`topo_extra` / `topo_missing`; weight 0, composites
  unchanged); `tests/test_topology_metric.py`.
- Logo, `--preset smooth --set upscale=2`: SSIM 0.975, edge F1 1.000, 0 extra / 1 missing piece,
  32 shapes, 4 colours (default: 0.960 / 0.930 / 3 extra, 32 missing — the tagline is lost).
  Comparison with a vectorizer website and Adobe in `docs/BAKEOFF.md`.
- Tried and rejected: capping smoothing moves at 35 % of the gap across a fold (no gain on a
  synthetic noisy-wedge test). The dark specks came from the fine-detail pass, not from smoothing.
- Illustrator check by the user (Kiro 13.7): **"decent"**. Cream edges smooth; pink/blue edges
  lumpy and thin, blue bar end rounded — traced to JPEG's half-resolution colour: the pink band's
  segmentation mask is ragged while a luma threshold of the same image is clean. Next: Kiro 13.8
  (place colour edges from luma on JPEG), then 13.6 (gap tips owned by the gap's region).

## Objective bake-off harness — 2026-10-31

Added `plate corpus` + `plate bakeoff` (new `src/plate/bakeoff/` package: `corpus.py`,
`score.py`, `adapters.py`, `runner.py`; `docs/BAKEOFF.md`; `tests/test_bakeoff.py`) to
score PLATE against other tools on a synthetic corpus with EXACT ground truth across
fidelity, structure (object/complete/hidden/order via visible-region IoU) and editability,
with a weighted composite re-ranked under five weight profiles and an HTML report.

**Results (24-scene corpus, seed 1; 6 JPEG-damaged):** PLATE composite **0.79**, first under
ALL five weightings — vtracer-stacked 0.50, vtracer-cutout 0.49, potrace-color 0.43. PLATE
anchors/shape 10 vs 23/34/100; hidden-parts recovered 46% vs ~8%; clean SSIM 0.988 (near-tie
with VTracer 0.990). Full method + table in `docs/BAKEOFF.md`.

**Weaknesses the bake-off surfaced (now the top ROADMAP "P1 — bake-off driven" items):**
JPEG-damaged scenes recover 0/10 occluded objects and score worse than VTracer on damaged
input (T-junction occlusion test breaks on block noise); occluded rect/polygon/rrect completion
lags circles (4/11, 3/10, 5/12); touching same-colour objects merge (the same blocker behind the
EMBER/ROOT/storefront structural limits).

**Reconcile note:** the bake-off work arrived as an uncommitted pile that had also reverted
several shipped fixes. Those were restored while keeping the bake-off feature: `cli.py` uses
`open_rgba` again (16-bit/EXIF/clean-error loader), batch exit code, `main()` error handling,
macOS dyld re-exec and the robust doctor cairosvg probe; `pyproject.toml` keeps version 0.1.0,
`scikit-image` as a core dep, and authors/Homepage, plus the new `bakeoff` extra (+`potracer`).
The new CLI keeps `.gif` out of `IMG_EXT` (bake-off-era choice). Packaging guards pass.

## Structural audit closed + real-artwork corpus — 2026-10-31

Two things landed since the complex-scene round. `main` is further past `origin/main`
(NOT pushed; Jessica pushes). Suite **565 passed / 7 xfailed / 0 xpassed**.

### Structural-target audit CLOSED (all 7 dispositioned, honestly)
Every strict-xfail target now has a definitive disposition — addressed where a real
classical cue exists, pinned as a measured information limit otherwise, with no gate
weakened and no geometry invented:
- ORBIT 44→38 (compound-ring defrag) + residual monogram/flat-patch limits
- mission_patch 72→70 (ellipse compound-merge) + pinned planet/poster gradient limits
- EMBER face merges, ROOT tree+leaves, storefront cream-awnings+teal-leaves — all
  same-colour information limits, pinned with raster-measured tests (`9d0ef62`,
  `79ef445`, the EMBER pin). poster gradient-disc — overlay-sliced limit, pinned.
- PLATE identity — aspirational (hidden geometry unrecoverable), stays xfail.
Optional scoped engine work remaining (NOT limits, NOT quick wins): the ROOT
inner-seal interrupted circular ring (compound-ring arm) and the ROOT leaf-vein-11
thin-stroke split. Investigation reports: `.agents/tasks/{ember-separation,
patch-poster-fragmentation,root-storefront}-investigation.md`.

### Real-artwork evaluation corpus ADDED (`9ddea19`, diagnostic, not a gate)
`scripts/make_real_corpus.py` authors 14 deterministic, deliberately-messy PNGs under
`samples/real/` (gradients, soft shadows, sensor noise, JPEG artifacts, anti-aliased
type/thin strokes, >16-colour/near-duplicate palettes, extreme aspect ratios,
translucent overlaps, textured backgrounds). `plate bench samples/real` + the
per-image table in `docs/REAL-CORPUS.md` are the diagnostic; `samples/real/CREDITS.md`
holds the CC0 drop-in manifest (zero real images placed — sandbox can't fetch; slot
ready). No oracle, no SSIM floor, no CI gate (`tests/test_real_corpus.py` only asserts
existence + bench runs without crashing). 24 engine SVGs byte-identical; engine untouched.

**What the corpus revealed (the point — PLATE's untuned real-world weak spots):**
- **Sensor noise is catastrophic:** `real_sensor_noise_badge` SSIM **0.355**, collapses
  to 5 objects. Denoising copes with mild noise (the sigma-2 fix) but not heavy noise.
- **JPEG block artifacts explode segmentation:** `real_jpeg_artifacts` **269 objects /
  1679 anchors / 13.7s**, SSIM 0.554 — hundreds of junk objects, slow.
- **Realistic gradients are under-detected:** only 2/14 images emit any gradient;
  `real_radial_orb` (a smooth radial) collapses to **1 object**, SSIM 0.83. Smooth
  real-world shading is not triggering gradient detection.
- **Texture/thin-type flatten:** `real_textured_bg` and `real_thin_strokes_type` each
  collapse to 1 object. Clean-ish graphic art still scores 0.91–0.96 (fine).

These are the highest-value next targets (far more impactful than the structural long
tail): a heavy-noise/JPEG-robustness pass (pre-decode or segmentation guard against
artifact explosion) and realistic-gradient detection sensitivity. See docs/REAL-CORPUS.md.



## Complex-scene progress — 2026-10-31 (session continues)

Re-measured the four remaining structural targets with the trustworthy diagnostic,
then a read-only investigation (`.agents/tasks/patch-poster-fragmentation-investigation.md`)
separated addressable work from information limits. Outcome: three limits pinned, one
genuine engine win landed. On `main`, now nine commits past `origin/main` (NOT pushed).

- **Target landscape (trustworthy diffs):** event_poster 83/44 (0 missing, 39 extra —
  26 are one overlay-sliced gradient disc); mission_patch 72/45 (1 missing, 28 extra,
  3 splits); storefront 73/64 (8 missing awning/leaves, 2 same-colour leaf merges);
  root_seal 51/56 (12 missing thin roots/branches — the hardest, thin-feature + same-colour).
- **Pinned two gradient-object limits** (`9d0ef62`): mission_patch shaded-planet (rim
  360-enclosed by sky → 0 free boundary points, `_grow_radial_bands` can't fit) and
  event_poster gradient-disc (sliced into ≥2 disconnected components by opaque overlays,
  fails `_single_object`). Both are single authored objects the raster faithfully
  fragments; reunion needs inventing occluded geometry. Raster-measured pins added.
- **Landed the ellipse-compound-merge** (`1717bd7`): the one addressable win. Extended
  `order._merge_compound_siblings` with an ellipse admission arm (as strict as the circle
  arm: RMS ≤ 0.02·min-axis, arc ≥ 160°, shared-occluder via the unchanged 15° T-junction,
  angle normalization + plausibility bounds). **mission_patch 72 → 70, split 3 → 1**:
  back-orbit and front-orbit reunite as native `<ellipse>` strokes. 3 regressions
  (1 positive, 2 negative rejecting contaminated/no-occluder hulls). ORBIT's circle-arm
  result and all other 23 SVGs byte-identical; patch SSIM 0.9755. Still xfail (70≠45).
- **Residual patch/poster gap is now dominated by documented limits:** overlay-sliced
  gradient objects and letter/stroke-interrupted fills, with no gate-preserving reunion.
  The honest position is diminishing returns on the structural long tail.

Next: ROOT and storefront remain, both dominated by same-colour-separation and thin-feature
loss (ROOT especially — 12 missing thin roots/branches). Apply the measure-first discipline:
pin genuine limits rather than force them. PLATE identity stays aspirational.

## Structural-target progress — 2026-10-31 (session continues)

Picked up the handoff queue after the exposed-curve work was committed. On `main`,
five commits past `origin/main` (NOT pushed; Jessica pushes): `09c2d0a` preserved
whisker fix + docs, `5692fa9` diagnostics fix, `1390e5b` ORBIT defrag, `6895bfe`
gap-wording refresh, `02533d1` EMBER limit pin. Suite **555 passed / 7 xfailed /
0 xpassed**; sweep **70/78**, core **36/36**; 9/16 structural targets still pass
(none newly promoted — progress is partial and honest).

- **Fixed the split/merge diagnostic bug** (`5692fa9`): `diff_target` counted any
  IoU≥0.1 overlap as fragmentation, so distinct overlapping objects were miscounted
  as splits/merges (`diff_target(svg,svg)` reported false splits). Now a split
  excludes any actual that is another expected's 1:1 match. EMBER false split
  21→0, merged 4→3 (genuine only). Diagnostics-only; challenge SVGs byte-identical.
- **ORBIT compound-emblem defrag** (`1390e5b`): `logo_orbit_wordmark` **44→38
  objects**. New strictly-gated `order._merge_compound_siblings` reunites same-colour
  interrupted-ring fragments using the existing 15° T-junction/containment gates plus
  a tight circle-fit; resolved the badge-ring split (1→0) and 4 cutout-tab extras
  (badge-ring IoU .257→.726). All 34 matched objects + 7 strokes + gradient core
  unchanged; 23 other challenge SVGs + 8 samples byte-identical. 4 extras remain
  (monogram-O fragments + flat pink/tan patches) — left unmerged because closing
  them needs a weakened gate. Still xfail (38≠34), not forced.
- **EMBER same-colour face merges = measured information limit** (`02533d1`): a
  read-only investigation (report in `.agents/tasks/ember-separation-investigation.md`)
  proved cheeks+muzzle are one 23,344px cream component, each pupil is fused into
  its same-colour navy eye-mask, and nose+mouth are one navy component — the authored
  sub-shapes exist only in the vector source, not the 1:1 raster. No classical cue;
  separating them would invent geometry (forbidden). Pinned with a raster-contiguity
  test (`test_ember_same_colour_face_features_are_one_raster_region`). Stays xfail.
  Note: the 3 gold laurel-stem *extras* are an optional ORBIT-style compound-merge
  avenue for a future stroke session — not attempted here.

Next candidates: ROOT / mission-patch / storefront / poster not yet re-measured with
the fixed diagnostics; most share the same-colour-separation + gradient-band blockers.
PLATE identity remains aspirational (hidden geometry unrecoverable; leave xfail).

## Audit and exposed-curve recovery — 2026-10-31

- Jessica requested wrap-up at 6% usage. **Final full suite: 549 passed/7 xfailed**,
  no warnings/skips, 165.32s (`/tmp/plate-oct31-final-tests.txt`); earlier post-fix
  run also 549/7 (165.48s). Final suite includes the complete-footprint safeguard.
  Final benches/sweep at `/tmp/plate-oct31-final-{samples,challenges,robustness}/`
  match the visually/natively checked outputs byte-for-byte; comparison evidence
  `/tmp/plate-oct31-final-comparison.json`. `git diff --check` passes. All owned
  jobs completed; no commit/push. HANDOFF lists every pending file and next repro.
- Started clean at `286c713`. Fresh baseline: **541 passed/7 xfailed**, no warnings/
  skips, 160.20s (`/tmp/plate-oct31-before-tests.txt`); full sweep reproduced
  **70/78**, **36/36 core**. Seven complex targets remain strict expected gaps.
- Fixed EMBER's rejected fourth whisker with a bounded single-cubic retry against
  the PNG's original subpixel boundary. Retry only a fully exposed curve rejected
  by existing centreline fitting; require one coherent source contour, boundary
  RMS ≤.2px/max residual ≤.6px, round-cap evidence, a complete uncropped footprint
  and the unchanged IoU ≥.95 / boundary-deviation gates. Existing accepted fits
  and occluded-curve fitting are unchanged. No core dependency added.
- **EMBER 3→4 strokes, 455→447 anchors, 51 objects unchanged**. All four whiskers
  meet their independent authored contracts. White/dark SSIM **.9665/.9685 →
  .9666/.9686**. The full logo still fails shield/stem/merged-object requirements;
  no structural xfail promoted. All other **23 PLATE** and all **24 VTracer** SVGs
  byte-identical. Evidence `/tmp/plate-oct31-{before,after}-{samples,challenges}/`,
  `/tmp/plate-oct31-benchmark-changes.json`, `/tmp/plate-oct31-whisker-metrics.json`.
- Eight new tests: mirrored opaque/transparent curves, square caps, missing source
  evidence and EMBER's four whiskers. Disabling the retry gives **4 failed/4 passed**
  (`/tmp/plate-oct31-refit-isolated-red-tests.txt`); focused suite **50 passed**
  (`/tmp/plate-oct31-refit-focused-tests.txt`). New test file passes Ruff; the
  changed source retains the same two pre-existing Ruff findings (I001/B023).
- Full robustness sweep remains **70/78 with zero per-case verdict changes**:
  `/tmp/plate-oct31-{before,after}-robustness/`. Visually inspected full and zoomed
  source/before/after comparison `plate-oct31-whisker-review.png` in this chat's
  visualization directory. Changed SVG passes Illustrator **30.8.2** import/edit/
  AI roundtrip (`/tmp/plate-oct31-illustrator/report.json`); no pending script known.
- Audit corrections: eight sweep failures are measured algorithm/default limits,
  **not proven information-theoretic impossibilities**. In particular, 2px route
  geometry passes with an explicit palette; low contrast is merged by a configured
  threshold. Current pin tests assert these failures and need explicit review if a
  future gate-preserving method improves them. README/ROBUSTNESS/HANDOFF/ROADMAP
  now state eight actual misses rather than claiming complete recovery.
- New follow-ups: `diff_target(svg, svg)` wrongly reports splits for identical
  overlapping back/front rectangles (100×100 background, 50×50 foreground at
  (20,20)); overlap-based classification needs regression/fix. A short curved
  butt-cap probe already emits round caps in an accepted path; square-cap controls
  remain green. Both are open, not silently certified by the new retry.
- Work is uncommitted; no commit/push requested. Next: diagnostic false splits,
  then EMBER's laurel/stem or ORBIT compound-emblem recovery; real artwork, colour
  management, input limits, broader native editing and hosted service remain open.

## Previous stress-miss campaign — seven fixes, eight measured limits (2026-10-30)

All 15 robustness "stress misses" recorded at the start of this phase were investigated:
**7 fixed, 8 still failing and documented as current limits** (each pinned by
a test so it cannot silently drift). The full sweep rose **63/78 → 70/78**; core
held **36/36** throughout; every landed change kept the **24 shipped sample/challenge
SVGs byte-identical**, all **7 strict-xfail structural gaps intact**, and **no gate
weakened**. Full suite **519 → 541 passed / 7 xfailed / 0 xpassed**. The per-object
challenge diagnostic (below) also landed, making the remaining structural targets
measurable. Six commits on `main` after the v0.1.0 tag (`55701bd`), not yet pushed.

| Group | Cases | Outcome |
| --- | --- | --- |
| sigma-2 opaque noise (seeds 17/204) | 2 | FIXED — interior-noise denoise trigger (`imageio.py`) |
| half-size markers (4 rotations) | 4 | FIXED — circle/ellipse fit before rect in tiny-mask snap (`primitives.py`) |
| blur 0.7px marker | 1 | FIXED — alpha-recovery colour-spread gate `>3`→`>6` (`segment.py`) |
| quarter-size route/marker | 4 | FLOOR — 2px marker < speckle, 1 working-px route < poly/stroke floors |
| blur 1.2px marker | 1 | FLOOR — alpha≥128 silhouette erodes to .846 coverage; fixing it breaks shipped SVGs |
| low contrast 1/16 | 1 | FLOOR — foreground ~5 Lab dE < `color_merge`; separating it breaks shipped SVGs |
| hairline routes 1px/2px | 2 | FLOOR — 1px geometric (`fit_straight` 0.75 half-width); 2px palette-admission |

Each per-change note (with measured evidence and the pin/regression test names) is
recorded in the dated sections below. Next front: the 7 structural targets
(patch, storefront, poster, EMBER, ORBIT, ROOT, PLATE) — now measurable via the
per-object challenge diff — plus the real-artwork corpus and colour/input work.

## Blur & low-contrast robustness — 2026-10-30 (branch `fix/blur-contrast-detection`)

- Target: 3 stress misses — marks marker blur 0.7 & 1.2, panels 1/16 low-contrast
  foreground. One is a real segmentation miscalibration (fixed); two are documented
  floors with measured evidence (NOT faked, no gate weakened).
- FIXED — blur 0.7 (`marks-...-b0p7`): the 5px gold marker is consumed by edge
  dilation and has no flat palette seed, so it depends on the isolated-alpha-component
  fallback in `stages/segment.py`. That fallback rejected it on one gate: interior p90
  colour spread `> 3`. At sigma 0.7 the stable gold core measures 4.12 — stable, not a
  ramp — so a legitimate marker was discarded (4 shapes, want 5). Loosened the gate to
  `> 6` (single line; the `> 8` `_faint_objects` line untouched). Marker now recovers as
  a native `<circle>` at coverage 1.0. A genuinely variable ramp island (interior spread
  far above 6) is still rejected — guarded by
  `test_isolated_island_with_a_variable_ramp_interior_stays_out_of_the_palette`.
- DOCUMENTED FLOOR — blur 1.2 (`marks-...-b1p2`): the marker IS present (flat seeds
  survive at sigma 1.2, gold enters the palette normally), but the blur erodes its
  alpha>=128 opaque silhouette to 44 px vs the target's 52 px -> detail_coverage 0.846 <
  0.90. Measured threshold sweep: alpha>=128 -> 44px (.846); alpha>=110 -> 52px (1.0);
  alpha>=96 -> 52px. Reaching .90 requires growing the silhouette below the alpha>=128
  contract shared by the evaluator and segmentation; that single global threshold would
  grow every antialiased rim and break the 24 shipped SVGs. Below the recoverable floor
  for the alpha>=128 silhouette contract. Pinned by
  `test_blur_1p2_marker_is_below_the_alpha128_silhouette_floor`.
- DOCUMENTED LIMIT — contrast 1/16 (`panels-...-c0p0625`): every foreground collapses
  to within ~5 Lab dE of the background (#878788): disc #7a7e84 dE 4.98, panel #857b7c
  dE 5.81, detail #7a817e dE 4.84 — all below the `color_merge = 8.0` floor, so
  `_build_palette` merges them into the single background entry (1 shape; reference SSIM
  still passes, so this is purely object separation). The only separating lever,
  color_merge <= 4.5, is global and changes shipped `samples/shaded.png` (2533 -> 2100
  bytes) and splits near-identical colours in real art. A foreground within ~5 dE of its
  background is below the floor that protects real artwork — a fundamental palette limit,
  not a bug. Pinned by `test_contrast_1_over_16_foreground_is_below_the_colour_merge_floor`.
- Results: sweep 69/78 -> 70/78 (core unchanged 36/36; sweep exits 1 by design). The
  ONLY changed verdict is `marks-...-b0p7` -> PASS; no previously-green case regressed
  (verified by per-case diff of `/tmp/bc-before` vs `/tmp/bc-after`). Full suite 535 ->
  539 passed / 7 xfailed, 0 xpassed (the +4 are the new blur-0.7 recovery, the ramp
  over-loosening guard, and the two measured-floor pin tests). All 24 shipped
  sample+challenge PLATE SVGs byte-identical to the fdf90d1 baseline. Changed Python:
  `stages/segment.py` (one line) + `tests/test_robustness.py` (ruff clean). No
  commit/push beyond the focused branch commit; owner Jessica to decide merge.


## Mild-noise denoise blind spot fixed — 2026-10-30

- Root cause: `imageio.load_image` auto-denoise fired only when
  `noise_fraction > 0.04`. That global median-residual fraction is confounded by
  edge density, so mild Gaussian noise (sigma 2) on the opaque `panels` scene
  measured only ~0.018 and never tripped the bilateral filter, while sigma 4/8
  (0.28/0.73) did and passed. The uncleaned sigma-2 boundaries pushed circles/rects
  past `snap_tolerance`, so they were emitted as Beziers — lost primitives, inflated
  anchors. Failing cases: `panels-s1-r0-n2-...-seed17` and `-seed204`.
- Fix (trigger only; no gate/tolerance weakened): added
  `interior_noise_fraction(rgb, alpha)` beside `noise_fraction` in `imageio.py`. It
  runs the same `>6` residual test but only on pixels >=3px from any Sobel edge
  (distance_transform_edt), returning 0.0 when <100 interior pixels remain. Uniform
  noise reaches flat interiors; anti-aliased edge residual does not, so this cleanly
  separates mild noise (sigma 2 >= 0.0049) from clean edge-dense art (0.0000). The
  auto branch now fires when `noise_fraction > 0.04` OR `interior_noise_fraction >
  cfg.interior_noise`. New frozen `Config` lever `interior_noise = 0.002`. Classical,
  CPU-only, deterministic; no new dependency (scipy.ndimage already in use).
- Results: sweep 63/78 -> 65/78, the two sigma-2 panels cases flip to full PASS
  (disc/panel/detail primitive+anchors+silhouette+detail_coverage all true;
  stats primitives 2/1 -> 4, anchors 35/49 -> 16), zero previously-green case
  regressed, core suite 36/36. Full `pytest -q`: 522 passed / 7 xfailed (was 519/7),
  no new xpasses. All 24 shipped sample+challenge PLATE SVGs byte-identical to main
  (no sample's denoise decision changes; max interior estimate on any sample 0.0008).
  New tests in `tests/test_robustness.py`:
  `test_mild_noise_panels_recovers_primitives_at_sigma_2` (seeds 17, 204) and
  `test_interior_noise_estimator_separates_mild_noise_from_clean_edges`.

## Handoff priority reconciliation — 2026-10-30

- Jessica requested explicit remaining-gap instructions beyond Homebrew delivery.
  HANDOFF and ROADMAP now direct the next agent through mild-noise damage, the
  other 13 stress misses, diagnostics/seven complex structural targets, real-art
  and broader feature coverage, colour/input limits and native editing checks.
  Earlier service-first/deferred-engine wording is superseded by this direction;
  the unimplemented hosted service remains a separate milestone.
- Review began with a clean tree at `649343a`: prior PNG/marker fixes (`9f0df0f`),
  robustness runner (`30339d5`) and docs (`649343a`) have been committed by the
  intervening session. Earlier uncommitted-work notes below are historical.
- Saved full-sweep JSON independently rechecked: **63/78 pass, 15 fail**; current
  challenge definitions retain **seven strict expected gaps**. Corrected stale
  HANDOFF stroke counts (patch 8, storefront 3, EMBER 3, ROOT 9). These edits change
  documentation only; no engine/targets/packaging changes or commit/push requested.
- Full suite before and after: **519 passed/7 xfailed**, no warnings/skips
  (135.13s / 133.60s). Logs `/tmp/plate-handoff-priority-{before,after}.txt`.
  `git diff --check` passes; only HANDOFF/ROADMAP/STATUS changed. No new pipeline
  render check was needed for these documentation-only edits.

## Small-marker geometry recovery — 2026-10-30 (branch `fix/small-marker-geometry`)

- Half-size route markers now recover as a native `<circle>`. Mechanism: the
  tiny-mask branch of `stages/primitives.py::snap` (the `area < 30` path that used
  to emit a full-bbox rect for any fully-filled blob) now first tries `fit_circle`
  (then `fit_ellipse`) on the padded contour, accepting it only when it clears the
  SAME gates as the normal path (coverage > 5.5, full-primitive deviation ≤ tol)
  AND strictly beats the rect's deviation. Ambiguous solid squares (2×2, 8×8) still
  snap to rects — `tests/test_inputs.py::test_tiny_solid_image_is_one_canvas_rect`
  stays green. No gate weakened: detail-coverage ≥.90, circle-coverage, snap
  tolerance, anchors ceiling, speckle and stroke/contour floors are all unchanged.
- Sweep: **63/78 → 67/78** (core unchanged at 36/36; sweep still exits 1 by design).
  Fixed exactly the 4 `marks-s0p5-{r0,r90,r180,r270}` cases: marker object now
  `actual_name=Gold_circle`, `coverage=1.0`, `detail_coverage=True` (was
  `Gold_rectangle`, coverage 0.846, detail_coverage False). No other case changed.
- STILL FAILING, below the information floor (documented, NOT faked): the 4
  `marks-s0p25-*` quarter-size cases. At scale 0.25 the gold marker has only 2
  opaque (alpha≥128) pixels — dropped by `filter_speckle=6` in segmentation
  (`present=false`), and 2 pixels carry no uniquely inferable circle. The dark
  route survives segmentation but is a 1-working-px-tall sliver: its zero-area
  contour is rejected by the `poly_area>=4` floor and `fit_straight` deliberately
  rejects 1-px rows. Recovering either would require weakening a gate, so they
  stay red. `work_size` only downscales, so it cannot add information here.
- Tests: full suite **519 → 523 passed / 7 xfailed, 0 xpassed** (the +4 are the new
  half-size circle regressions). New regression
  `tests/test_robustness.py::test_half_size_marker_recovers_as_a_circle_with_full_coverage`
  (×4 angles) fails on base, passes after; and the existing marker-survival test
  now asserts `detail_coverage` at both scales (.5 and 1). Benches: the 24 shipped
  PLATE SVGs (`samples` + `samples/challenges`) are byte-identical to the 55701bd
  baseline. Change localized to `primitives.py` + two project tests; `segment.py`
  untouched (no collision with the concurrent noise branch). No commit/push beyond
  the focused branch commit; owner Jessica to decide merge.

## Handoff priority reconciliation — 2026-10-30

- Jessica requested explicit remaining-gap instructions beyond Homebrew delivery.
  HANDOFF and ROADMAP now direct the next agent through mild-noise damage, the
  other 13 stress misses, diagnostics/seven complex structural targets, real-art
  and broader feature coverage, colour/input limits and native editing checks.
  Earlier service-first/deferred-engine wording is superseded by this direction;
  the unimplemented hosted service remains a separate milestone.
- Review began with a clean tree at `649343a`: prior PNG/marker fixes (`9f0df0f`),
  robustness runner (`30339d5`) and docs (`649343a`) have been committed by the
  intervening session. Earlier uncommitted-work notes below are historical.
- Saved full-sweep JSON independently rechecked: **63/78 pass, 15 fail**; current
  challenge definitions retain **seven strict expected gaps**. Corrected stale
  HANDOFF stroke counts (patch 8, storefront 3, EMBER 3, ROOT 9). These edits change
  documentation only; no engine/targets/packaging changes or commit/push requested.
- Full suite before and after: **519 passed/7 xfailed**, no warnings/skips
  (135.13s / 133.60s). Logs `/tmp/plate-handoff-priority-{before,after}.txt`.
  `git diff --check` passes; only HANDOFF/ROADMAP/STATUS changed. No new pipeline
  render check was needed for these documentation-only edits.

## Robustness sweep checkpoint — 2026-10-30

- Jessica requested continued coverage work, then a safe wrap-up at 8% usage.
  She explicitly permits scope expansion if recorded in ROADMAP/HANDOFF. Stopped
  adding features at this verified checkpoint; no commit/push in this continuation.
  HEAD remains `4f8e8d1`. Both this phase and the prior PNG fixes remain uncommitted.
- New `python -m plate.robustness --output NEW_DIRECTORY` diagnostic: independent
  two-scene source SVGs, 4× rasterization, scale/rotation, fixed-seed noise, proper
  premultiplied blur, contrast and hairlines. Saves all inputs, target/actual SVGs,
  per-case/aggregate JSON and visual HTML. Evaluates masks in authored-base pixels,
  per-object coverage ≥.90, topology, colour, native primitives/anchor budgets,
  editable strokes and both-background fidelity. Input RNG is reproducible; no
  universal backend-determinism claim. Full scope: `docs/ROBUSTNESS.md`.
- Fixed a novel-colour marker disappearing with SSIM still near .99: edge dilation
  consumes its flat seeds and RGB ringing defeats repeated-colour admission.
  `segment.py` now admits a stable eroded near-opaque interior for an isolated
  component with no flat seed, respecting explicit palettes, palette budget and
  speckle threshold. No geometry thresholds or independent targets were relaxed.
  Native/half-size quarter-turn source ownership is tested. Half-size markers
  still fail their independent circle-coverage target; this remains reported.
- **36/36 core cases pass** (before 24/36). **63/78 full cases pass** (before
  48/78), with **15 stress failures** retained: quarter-size route/marker loss (4),
  half-size marker geometry (4), .7/1.2px blur (2), opaque sigma-2 noise (2),
  1/16 contrast (1) and 1/2px routes (2). The full command intentionally exits 1;
  `--suite core` selects the passing regression subset. These are separate from
  the seven pre-existing strict-xfail logo/scene contracts, which remain unchanged.
- Added **56 robustness tests**; focused robustness/segmentation **77 passed**.
  Baseline full suite **463 passed/7 xfailed**; final **519 passed/7 xfailed**,
  no warnings/skips, 134.87s. Logs `/tmp/plate-sweeps-{before,final}-tests.txt`,
  `/tmp/plate-robustness-{red,focused}-tests.txt`. Changed Python files pass Ruff.
- Before/after benches: **all 24 PLATE and 24 VTracer SVGs byte-identical**, no
  source/target/golden changes. Evidence `/tmp/plate-sweeps-{before,after}-{samples,challenges}/`
  and `/tmp/plate-sweeps-benchmark-comparison.json`. Sweep evidence:
  `/tmp/plate-robustness-{before,final}/{report.json,index.html}`. Visually inspected
  `plate-robustness-marker-review.png` in this chat's visualization directory.
  New native-marker and downsampled-marker SVGs also pass Illustrator import/edit/
  AI roundtrip checks (`/tmp/plate-sweeps-illustrator/`).
- Next: mild-noise auto-denoise detection, tiny-marker/route fitting without
  weakening .90 coverage, then broader scenes/aspect ratios/real artwork and
  native editing. Runner exceptions are not yet collated per case; add that before
  fuzzing. Colour management and hosted-service implementation remain open.

## Static PNG encoding coverage and precision fixes — 2026-10-30

- Continued Jessica's coverage buildout with an independent byte-authored PNG
  matrix: all **15 legal colour/depth combinations**, ordinary/Adam7 rows, all
  five scanline filters, tRNS keys, palette alpha/implicit opaque tails, packed
  rows, tiny/empty interlace passes and split IDAT. Expected pixels are computed
  from original integer samples; the fixture writer does not use Pillow/OpenCV
  encoders. Fifteen equivalent encodings must yield the same editable cutout SVG.
  New files: `tests/png_fixtures.py`, `tests/test_png_matrix.py`; full inventory and
  interpretation policy: [docs/PNG-COVERAGE.md](docs/PNG-COVERAGE.md).
- The first 80 tests reproduced **21 failures**. Fixed lost grayscale **2/4-bit
  tRNS** (Pillow expands pixels but leaves the key in the source range), grayscale
  **16-bit tRNS** (normalization lost transparency), and **RGB 16-bit tRNS** (Pillow
  reduces precision before the exact match). Use the existing OpenCV unchanged
  decoder to retain full 16-bit samples, compare tRNS exactly, and consistently
  round all RGB/alpha channels to 8 bits (`sample/257`). Near-key opaque samples
  that collapse to the same 8-bit RGB stay opaque. Preserve EXIF and apply it once.
  Dependency failures are readable `ImageLoadError`s, without a lossy fallback.
- **111 new cases total**, including PNG EXIF, sample-based gAMA/sRGB/valid ICC
  handling, hidden-RGB trace invariance at native/reduced working sizes, APNG
  first/default-image policy, invalid type/depth, CRC/deflate and decoder failures.
  ICC/gamma transforms remain **unimplemented**; the tests document normalized
  encoded samples, not colour-managed appearance. APNG animation is not reconstructed.
  ICC fixture generation uses optional Pillow LittleCMS; it is available in this
  run, so there are no skips. These fixtures are not complete conformance/fuzzing
  or decode-resource-limit coverage.
- Baseline full suite **352 passed/7 xfailed**; final **463 passed/7 xfailed**,
  no warnings/skips, 126.69s. Focused input/audit/matrix checks: **152 passed** before
  adding the final decoder-exception case; the full suite includes that case.
  Changed Python files pass Ruff. Logs `/tmp/plate-png-matrix-{before,final}-tests.txt`,
  `/tmp/plate-png-matrix-{red,focused}-tests.txt`.
- Four independent transparent-cutout repros render at **SSIM 1.0 on white/dark**
  after the fix; before white/dark scores were gray2 **.7192/.6740**, gray4
  **.8740/.5691**, gray16 **.9173/.5467**, RGB16 **.8100/.5927**. Metrics, HTML
  reports and before/after SVGs: `/tmp/plate-png-matrix-review/`. Rendered and
  visually inspected `plate-png-transparency-review.png` in this chat's visualization
  directory. Four new Illustrator workflows also pass (report
  `/tmp/plate-png-matrix-illustrator/report.json`), preserving real layers, names,
  holes/rendering, edits and AI reopening. The native check still does not prove
  arbitrary source reconstruction.
- Both original/challenge benches run before/after. **All 24 PLATE and 24 VTracer
  SVGs are byte-identical**; fixtures/targets/goldens untouched. Evidence:
  `/tmp/plate-png-{before,after}-{samples,challenges}/`,
  `/tmp/plate-png-benchmark-comparison.json`. Prior 24-case/636-check Illustrator
  verification remains applicable to those unchanged SVGs.
- README/ROADMAP/HANDOFF updated. Remaining coverage: real artwork, scale/noise/
  low-contrast/detail sweeps, richer colour management/metadata/fuzzing, soft alpha,
  harder gradients/strokes and direct native-edit/4× seam checks. Seven structural
  targets remain strict gaps. Service implementation is still absent. No commit
  or push in this continuation; HEAD remains `4f8e8d1` at the latest check.

## Native Illustrator layers fixed; coverage remains bounded — 2026-10-30

- Jessica asked whether PLATE covers every meaningful PNG: **no**. README now
  distinguishes decoding, rendered appearance and editable reconstruction, with
  a coverage/limitations table. ROADMAP adds explicit real-corpus, PNG/colour-mode,
  scale/noise/detail, alpha/stroke/gradient and native-editing validation gates.
  **9/16 authored structural targets pass; 7 remain strict expected gaps.** Photos,
  textures, exact original fonts/live text and arbitrary hidden authoring geometry
  are outside the launch guarantee. The existing hosted-service direction remains;
  service code is still absent and hard geometry research remains deferred.
- Found a direct SVG layer fix empirically: `i:layer="yes"` in Adobe's 10.0
  namespace imports real Illustrator layers. Inkscape-only markers do not. Emit
  both markers on top-level groups and add named `… layer` containers for standalone
  roots, including backgrounds. Nested semantic groups stay groups. Allocate wrapper
  IDs after original object/gradient IDs so existing IDs/references are preserved;
  `illustrator_layers=false` retains ungrouped output. No native postprocessing or
  Illustrator dependency is added to the conversion pipeline.
- Illustrator **30.8.2: 24/24 cases, all 636 checks pass**. The default eight cases
  also pass. Checker now verifies exact layer names/order, object layer membership,
  nested groups and drawable paint order; native layer records replace only
  explicitly marked SVG groups in the expected hierarchy. Existing tests still
  reject same-named groups masquerading as layers. Face has 2 actual layers;
  ORBIT has 34, retaining 44 objects/345 anchors/7 strokes/1 gradient. Minimum
  SVG-interchange SSIM across all native imports/reopens/edits: **.9928**.
- Both before/after benches ran, with VTracer retained. All **24** SVGs have exactly
  unchanged geometry, original IDs, gradient definitions and paint hierarchy after
  removing the new layer annotations/containers. White/dark Cairo renders are
  **pixel-identical**; all VTracer SVGs are **byte-identical**. Render comparison
  inspected in this chat's visualization directory: `plate-illustrator-layer-review.png`.
  Reviewed all **15 control goldens** independently the same way before refreshing
  their intended layer-only serialization changes. Desired targets/PNG fixtures
  are unchanged.
- Added **11 regressions** (4 emitter, 7 checker), for a total 26 headless
  Illustrator/layer cases. Baseline full suite **341 passed/7 xfailed**; final
  **352 passed/7 xfailed**, no warnings, in 125.20s. Focused 26 pass; changed Python
  files pass Ruff. Logs `/tmp/plate-illustrator-layers-{before,final-clean-tests}.txt`.
  The intermediate post-fix suite passed with 15 expected golden-drift warnings;
  the final run follows the reviewed golden refresh.
- Repeated existing-document preservation after the fix: all native checks pass,
  unsaved marker state/geometry/colour, active document and interaction setting
  match exactly. Only test documents close; final document count zero. Evidence:
  `/tmp/plate-illustrator-layer-preservation/preservation.json`.
- Evidence: `/tmp/plate-layer-import-probe/`,
  `/tmp/plate-illustrator-layers-all/{report,illustrator,manifest}.json`,
  `/tmp/plate-layers-{before,after}-{samples,challenges}/`,
  `/tmp/plate-layer-render-comparison.json`, `/tmp/plate-layer-controls-review.json`.
  Jessica requested updated README/ROADMAP/HANDOFF and a commit of this checkpoint;
  the prior loader fix, 19 audit regressions and audit docs are included. No push requested.

## Initial automated Illustrator verification — historical, before layer fix

- Added opt-in `python -m plate.illustrator --output NEW_DIRECTORY`. On macOS it
  drives Illustrator through AppleScript/ExtendScript, opens generated/copied SVGs,
  inspects the native DOM, exports PNGs, saves/reopens `.ai`, and verifies named
  object movement, recolouring and 50% stroke-width changes against independently
  edited SVGs. Existing output directories are refused; only owned test documents
  are closed. Ordinary tests never launch Illustrator. See
  [docs/illustrator-checklist.md](docs/illustrator-checklist.md).
- Live Illustrator **30.8.2**, eight fixtures including ORBIT: **8/8 workflows
  complete, 197/200 checks pass**, five cases fully pass. Named vectors, hierarchy,
  expected object/stroke/gradient counts, four-anchor circles/ellipses, and exact
  recorded geometry/metadata survive `.ai` reopening. Imported/reopened PNG pixels
  are identical. All imported/reopened/edited renders clear .98 SSIM on white/dark;
  lowest **.9928** (shaded), ORBIT **.9960**, with all **7 native strokes** and
  **1 gradient fill**. This measures SVG interchange, not source-PNG tracing quality.
- **Confirmed export limitation:** every SVG imports into one real `Layer 1`.
  Face, gradient badge and ORBIT retain correctly named/nested groups but fail the
  actual-layer check. `inkscape:groupmode` does not create Illustrator layers.
  README/agent/checklist claims corrected; the checker stays red for this gap.
  Native live-shape widgets, direct gradient edits, high-zoom seams and a real-image
  corpus remain unverified. An extra nested sentinel wrapper timed out after its
  inner checks; Jessica confirmed no visible dialog. A subsequent **separate-call
  preservation test passed** using the normal runner: an already-open copied AI
  with unsaved changes retained its dirty flag, object count, marker anchors/bounds/
  RGB, active-document state and interaction setting exactly. Only the test copy
  closed; the owned sentinel was then cleaned up normally. Evidence/scripts:
  `/tmp/plate-illustrator-preservation/`, including `preservation.json` and the
  before/after observations. Final document count zero. Nested-wrapper timeout
  cause remains unidentified; a timeout does not cancel an in-app script.
- Fixed a reproduced ExtendScript host-object compatibility problem in the harness:
  conditional array literals could return undefined for `PathItem`s. Explicit
  copying into a JavaScript array completes all eight cases. Added **15 headless
  checker tests**, covering lost objects/names/strokes/gradients, rasterization,
  primitive anchors, actual layers versus groups, hierarchy, hidden-geometry
  roundtrip changes, duplicate names, missing artifacts and output preservation.
- Before this continuation: **338 passed/7 xfailed** (12 initial checker tests);
  final: **341 passed/7 xfailed**; new Python files pass Ruff. Logs:
  `/tmp/plate-illustrator-resume-before.txt`, `/tmp/plate-illustrator-final-tests.txt`.
  Desktop artifacts: `/tmp/plate-illustrator-verified/{report,illustrator,manifest}.json`
  plus per-case PNGs and `.ai` files. Additional probe:
  `/tmp/plate-illustrator-document-guard/`. Converter output/targets unchanged.
  No commit/push; prior loader/audit changes preserved.

## Audit reliability fixes — 2026-10-30

- Fixed the two reproduced audit bugs. Declared 16-bit integer images always use
  0..65535 normalization, including dark inputs and both byte orders. Retain PNG
  bit-depth context before EXIF copying so older Pillow mode-I PNGs also scale
  correctly. General integer/float inputs retain their previous policy.
- Batch converts all valid files even when others fail, prints success/failure
  totals, and exits **1 if any file failed / 0 if all succeeded**. Empty input still
  exits 2. The pre-existing top-level output-error handler was preserved and its
  input tests remain green.
- Added **19 regression cases**. Before the fix, 12 of these failed; after it,
  **42 focused input/audit tests pass**. Baseline full suite **307 passed/7 xfailed**
  (includes the pre-existing output-permission and packaging changes); final full
  suite **326 passed/7 xfailed**. Logs: `/tmp/plate-bugfix-{before,final}-tests.txt`,
  `/tmp/plate-bugfix-focused-tests.txt` and `/tmp/plate-bugfix-red-tests.txt`.
- Both benches rendered and inspected: `/tmp/plate-bugfix-{samples,challenges}`.
  All **24 PLATE fixture SVGs are byte-identical** to the audit baseline, with
  VTracer retained. Independent dark-16 reference: **MAE 199→0, SSIM .0102→1.0**.
  Review: `/tmp/plate-bugfix-review/metrics.json`, `plate-dark16-fix.png` and
  `plate-bugfix-original-samples.png` in this chat's visualization directory.
- Loader/new regression file pass Ruff. CLI lint findings were checked against
  HEAD; pre-existing S110 remains. Separate doctor edits removed F541. Audit/status/roadmap
  updated; hosted service and real-world/Illustrator validation remain next.
  Concurrent release commit `dceaae2` landed during verification and included the
  batch fix along with packaging/version/output-error work. Loader, new regressions
  and audit docs remain uncommitted. No commit/push made by this bugfix session.

## Project audit — 2026-10-30 (historical snapshot; issues fixed above)

- Full current-state audit: [docs/AUDIT.md](docs/AUDIT.md). Engine HEAD `101b63d`;
  fresh full suite **303 passed / 7 xfailed**. The concurrent output-permission
  test was added after collection and checked separately with the input-test module.
- Fresh original/challenge benches: **24 inputs**, VTracer retained; **9/16 desired
  structural targets pass**, **16/16 challenge fidelity floors pass on both backgrounds**.
  Current ORBIT **44/345/7** objects/anchors/strokes; EMBER **51/455/3**; ROOT
  **51/526/9**; PLATE **11/121/1**. Panel **59/249/27** remains structurally passing.
- Reproduced two issues: low-valued 16-bit PNGs bypass normalization (sample 200
  becomes 8-bit 200 instead of 1); batch prints conversion failures but exits 0.
  These remain unfixed. Concurrent CLI/output-permission edits were preserved.
- The agreed next milestone is the hosted service, whose code is still absent.
  Fix the two reliability issues, then build a resource-bounded classical conversion
  slice and add accounts/quotas/Stripe/deployment. Illustrator and real-corpus
  validation remain open; seven hard geometry gaps remain deferred.
- Evidence: `/tmp/plate-audit-tests.txt`, `/tmp/plate-audit-input-tests.txt`,
  `/tmp/plate-audit-{samples,challenges}`, `/tmp/plate-audit-results.json`.
  Local sample timings span .191s (face), 3.630s (ORBIT), 5.220s (mission) under
  concurrent testing; service capacity is not established. No engine changes,
  commit or push made by this audit.

## Circular compound-path holes → arcs (session 25)

- `trace.mask_to_path` traced every hole as Béziers, so a round transparent
  perforation became a ~300-point/15-anchor Bézier chain despite being a perfect
  circle. Now each interior hole that fits a circle tightly (rms ≤ ~0.35·scale,
  ≥350° coverage, real radius) is emitted as two SVG arcs (4 anchors) — compact and
  exactly round/editable under resize. Outer contour and non-circular holes keep
  Bézier tracing (guarded, so square/irregular holes are untouched).
- `perforated_plate`: **44 → 20 anchors**, path 1546 → 272 chars, SSIM 0.9943 →
  **0.9961**, still matches its target. All eight original samples byte-identical
  (none have circular transparent holes). Two regressions added. Commit `e9d66af`.

## Adaptive stroke refit (session 25)

- `fit_stroke` could reject a short, sharply curved stroke when Schneider fitting at
  the default tolerance (0.45) collapsed it to a single underfitting cubic scoring
  below the 0.95 IoU gate (EMBER whiskers: 1 segment, IoU 0.887). It now refits at
  progressively tighter tolerances (0.45, 0.3, 0.15), keeping the first that clears
  the gate (else the best). The retry only RAISES the IoU of a stroke about to be
  rejected — a stroke already passing at 0.45 is untouched — so existing accepted
  strokes are unchanged and the acceptance gate itself was NOT relaxed.
- EMBER navy strokes **2 → 3**; ROOT strokes **3 → 9** (real whisker/root curves),
  object counts (EMBER 51, ROOT 51) and SSIM steady; both still strict xfail. All
  eight original samples byte-identical; instrument panel stays 59/27.
- Investigation note: EMBER whisker id=15 peaks at IoU 0.947 even at the tightest
  tolerance — a genuine marginal miss, left rejected (do NOT lower the 0.95 gate for
  it; the gate protects stroke acceptance across the whole suite). Commit `1f54ffe`.
- Session 25 earlier investigated same-colour separation (ROOT): found the 5 mint
  leaves are already found correctly; the 51-vs-56 deficit is a scatter of small
  thin fragments + the teal inner-seal ring merging — NOT one splittable problem.
  Per-gap crack-difficulty assessment is in HANDOFF. `logo_plate` is unreachable by
  design (hidden back-P geometry not recoverable from the raster) — leave xfail.
- Suite **279 passed, 7 xfailed** (was 277/7).

## PLATE identity and tracing fixture (session 24)

- Designed the **registration P**: three offset teal/vermilion/ink compound P
  plates with a shared transparent circular counter, a fine registration mark,
  and original outlined PLATE lettering. Authored directly as editable SVG;
  no font dependency, external artwork or generated raster geometry.
- Brand assets in `assets/brand/`: primary and reversed lockups, square symbol,
  monochrome lockup/symbol, transparent PNGs, preview and usage notes. Named
  layers retain the full plates. Illustrator import remains unverified.
  `scripts/make_plate_brand.py` regenerates these plus the exact same primary
  artwork as `samples/challenges/logo_plate.{png,target.svg}`. PNGs use 4×
  supersampling and Lanczos. Existing assets/targets/goldens remain unchanged.
- Desired **11 objects / 3 strokes**. Current result **11 objects / 125 anchors /
  1 stroke**, SSIM **0.9906 white / 0.9956 dark**. Rear P shapes remain strips
  (back full-silhouette IoU **0.1387**); the registration mark merges and some
  square corners round off. This aspirational hidden-geometry contract cannot
  be uniquely inferred from the raster. New strict structural xfail records the
  gap; SVG integrity and ≥0.98 fidelity on both backgrounds remain active.
  VTracer control: **333 objects / 824 anchors / white SSIM 0.9337**.
- Tests protect exact brand/fixture identity, authored object/stroke inventory,
  independent SVG/PNG pairing, complete plate topology, layers and transparent
  icon/P/A counters. Baseline **270 passed / 6 xfailed**; final **277 / 7**.
  Tests require the documented cairo environment; the sandbox cannot bind the
  mock VLM's localhost server, so the full suite uses approved expanded access.
- Ran both benches: `/tmp/plate-brand-{samples,challenges}`. Rendered and
  inspected the brand presentation and source/PLATE comparison
  (`/tmp/plate-brand/comparison.png`); report `/tmp/plate-brand/logo_plate.report.html`.
  No pipeline edits. Branding and handover committed together at Jessica's
  request; use `git log -1 --oneline` for the commit. No push. Session 23's
  separate recovery commit is `2aa79bc`; its work remains intact.

## Fragmented cream-highlight recovery (session 23)

- Recovery source/tests/docs committed together at Jessica's request (base
  `7300232`; use `git log -1 --oneline` for the resulting commit). Added
  `stages/curves.py`, changed `pipeline.py`, added `tests/test_fragmented_curves.py`
  and narrowed the lower-highlight selector now that two cream strokes exist.
  Separate PLATE branding changes were left uncommitted. No push.
- **All seven ORBIT strokes now pass together with its radial core**, including
  native geometry, widths, topology and paint order against unchanged targets.
  The split upper cream highlight (one long arc + one tiny exposed cap) becomes
  one complete editable cubic. **45→44 objects, 6→7 strokes, 352→345 anchors**.
  White/dark SSIM **.9844/.9923→0.9846/0.9925**; SVG **17,218→16,860 bytes**.
- Merge only same-colour sibling leaves under an independently fitted later native
  closed stroke. Measure width only on sections clear of the crossing, constrain a
  shared cubic using both fragments' free boundaries, and require a nearby remote
  cap, tight residuals, ≥95% exposed IoU, source-backed exposed cores and a short
  hidden area. Unsupported gaps, flat caps, unrelated dots, mismatched colour/
  parentage and earlier/unproved loops are rejected. Rebuild/reindex disjoint
  observed ownership and share ordinary open-stroke SVG emission.
- Render review caught a layering regression: generic foreign-owner constraints
  treated navy antialias fringes as occluders. The pooled curve now constrains only
  its explicitly validated gold loop. New assertions keep both cream highlights
  above the navy monogram. Fidelity improves after this correction.
- **22 new cases** include all seven real-logo strokes/core, an independent synthetic
  full curve, flat caps/dots/offsets, disable switches, sibling/colour/paint-model
  guards, and 1/3/6px exposed gaps both away from and beside the crossing (opaque
  and transparent). Baseline **248 passed/6 xfailed**; final **270 passed/6 xfailed**.
  All eight original and fourteen other challenge PLATE SVGs remain byte-identical;
  targets/goldens/VTracer code unchanged. Full ORBIT target remains a strict xfail
  (34 objects); correct stroke count alone does not satisfy it.
- Both benches rendered/inspected: `/tmp/plate-fragment-{samples,challenges}`;
  baseline `/tmp/plate-fragment-before-{samples,challenges}`; metrics
  `/tmp/plate-fragment-metrics.json`; final tests `/tmp/plate-session23-final2-tests.txt`.
  Review sheets in this chat's visualization folder: `plate-fragment-highlight.png`
  and `plate-fragment-original-samples.png`.
- Next: compound navy badge/monogram (eight/three substantial visible regions),
  ambiguous radial patches, ROOT's touching inner ring/leaves and mission-patch
  clamped bands/craters/linear hull. This new pooling supports a long arc plus a
  small cap under a known later loop; two long disconnected curves, arbitrary
  occluders, unknown ordering and branching still need separate evidence/work.

## Crossed cream-highlight recovery (session 22)

- Committed sessions 20–21 as `71f6740` at Jessica's request. This session's
  crossed-curve source/tests are committed as `3c0a8e1`; this handoff update
  accompanies them. No push.
- **ORBIT's lower cream highlight now passes its unchanged full-stroke target**
  together with the gold front orbit, including relative paint order. The curve's
  rounded terminal is clipped by that loop; treating the cut edge as a free boundary
  previously distorted the skeleton fit. Upper highlight remains split and filled.
- Precompute independently accepted closed-stroke fits. `fit_crossed_curve` is a
  fallback for a single unbranched, stable-width curve under a known later native
  circle/ellipse stroke. Require exactly one exposed cap, ≥65% free boundary,
  bounded cubic controls, free-edge RMS ≤0.35px/max ≤0.85px, exposed IoU ≥0.95,
  local hidden area and no unsupported exposed extension. Source antialias edges
  retain flat-cap corners lost by binary ownership; the regression rejects a butt
  cap that initially fooled the binary fit. Ordinary stroke thresholds unchanged.
- **ORBIT: 5→6 of 7 editable strokes, 357→352 anchors**, still 45 vs 34 objects.
  White/dark SSIM **.9843/.9922→.9844/.9923**; SVG **17,388→17,218 bytes**.
  Eleven new cases cover the real logo, full curve/width at 1×/2× source resolution,
  flat caps, taper, both disable switches, detached covers and 1/3/6px exposed gaps.
  Baseline **237 passed/6 xfailed**; final **248 passed/6 xfailed**.
- Both benches rendered and inspected: `/tmp/plate-crossed-{samples,challenges}`;
  baseline `/tmp/plate-crossed-before-{samples,challenges}`; metrics
  `/tmp/plate-crossed-metrics.json`; tests `/tmp/plate-session22-final-tests.txt`.
  All eight original and fourteen other challenge PLATE SVGs are byte-identical.
  Targets/goldens/VTracer code unchanged. Review sheets in this chat's visualization
  folder: `plate-crossed-highlight.png`, `plate-crossed-original-samples.png`.
- Next: compound navy badge/monogram (eight/three substantial regions), the split
  upper cream highlight, and ambiguous gradient patches. This fallback cannot pool
  disconnected curves, infer two hidden caps or repair unknown paint order. An opaque
  ring's separate background-colour counter can still prevent native loop recovery;
  that existing counter/ordering gap is outside this change. ROOT's touching inner
  ring/leaves and mission-patch clamped gradients remain open.

## Radial-gradient band recovery (session 21; committed in session 22)

- Historical checkpoint: HEAD was `72702cd`; sessions 20–21 were uncommitted
  then. They are now committed as `71f6740` (session 22). No push.
- Extend an existing radial-gradient seed to disconnected source bands only when
  an affine RGB/radius model explains each band's spatial colour variation better
  than a flat fill. Eroded source samples reject constant foreground details and
  noisy matching-colour craters. Require a shared circular free boundary (RMS
  ≤0.5px, ≥270° coverage), local relative T-junction evidence, and observed foreign
  paint over the inferred hidden interior. Unsupported gaps and incompatible ramps
  remain separate. Both gradient/completion disable switches are respected.
- `Shape.verified_prim` preserves the source-validated full circle through ownership
  reindexing and ordering. Observed gradient openings in a foreground ring remain
  holes when the gradient is the same ancestor on both sides; a distinct child
  repaint still permits the underlying full disc. Clear stale filled primitives
  when reopening those holes. Native circle/gradient and both orbital ellipse
  targets pass together, including topology and relative paint order.
- **ORBIT: 57→45 objects, 500→357 anchors**, retaining all five editable strokes
  and one gradient. White/dark SSIM **.9816/.9889→.9843/.9922**. SVG bytes
  **24,755→17,388**. The gradient is now one complete editable radial circle;
  tiny ambiguous patches remain separate. Full target stays a strict xfail (34/7).
- Nine new regressions: clean/noisy flat craters, incompatible ramps, uncovered
  gaps, both disable switches, actual ORBIT gradient/orbits, and ancestor-vs-child
  hole ownership. Baseline **228 passed/6 xfailed**; final **237 passed/6 xfailed**.
  All eight original PLATE sample SVGs and fourteen other challenge PLATE SVGs are
  byte-identical to the session-20 baseline. Targets/goldens/VTracer code unchanged.
- Both benches rendered and inspected: `/tmp/plate-core-{samples,challenges}`;
  baseline `/tmp/plate-core-before-{samples,challenges}`; metrics
  `/tmp/plate-core-metrics.json`; final test log `/tmp/plate-core-final-tests.txt`.
  Review sheets in this chat's visualization folder: `plate-gradient-core.png`
  and `plate-core-original-samples.png`. `_grow_radial_bands` is deliberately
  limited to an existing affine radial seed and circular silhouette; nonlinear,
  clamped and general elliptical ramps remain work.
- Next: compound navy badge/monogram recovery (eight and three substantial visible
  regions respectively), two cream highlight strokes, and small ambiguous patches.
  The wordmark itself did not show substantial splitting. ROOT's inner ring still
  shares colour with leaves and needs decomposition; mission-patch bands/craters
  and linear hull remain unresolved.

## Interrupted ellipse recovery (session 20; committed in session 22)

- Historical checkpoint: HEAD was `72702cd`; the new source, tests and docs were
  uncommitted then (now `71f6740`, session 22). On takeover the front orbit was
  already a stroked ellipse, so work proceeded to the mint back orbit. No push.
- Added `stages/loops.py`: pool two long, curved, same-colour sibling leaf arcs
  with matching widths. Require relative T-junction evidence at both terminals
  of each arc, a shared ellipse fit to separate free contours, and actual foreign
  artwork covering the inferred hidden sections. Reattach small matching fragments
  only after the large arcs establish geometry. Preserve disjoint visible ownership
  when rebuilding segmentation; apply stable paint constraints for the recovered loop.
- Source coverage/alpha validates the exposed core, including collinear Lanczos
  overshoot on already-owned pixels. This rejects 1/3/6px openings that could fit
  within binary edge tolerance. Background-matching gaps, incompatible centres and
  widths are rejected. `strokes=false` and `complete_hidden=false` disable pooling.
- **ORBIT back orbit now independently matches its authored stroked ellipse.**
  Four visible mint fragments become one object. Both back/front ellipses pass
  full silhouette, width, topology and relative paint-order checks. Total:
  **60→57 objects, 4→5 editable strokes, 539→500 anchors**; white/dark SSIM
  **.9812/.9882→.9816/.9889**. Full ORBIT target remains a strict expected failure
  (target 34 objects/7 strokes). ROOT remains 51 objects/3 strokes.
- Twelve new regressions cover rotation, 2× source scaling with downsampling,
  reindexed ownership, disable switches, narrow transparent gaps, background gaps,
  incompatible arcs, and both ORBIT loop contracts. **228 passed, 6 xfailed**
  (baseline **216/6**). All eight original PLATE sample SVGs and fourteen other
  challenge PLATE SVGs are byte-identical. Targets/goldens/VTracer code unchanged.
- Both benches rendered and inspected: `/tmp/plate-pooled-final-{samples,challenges}`;
  comparison baseline `/tmp/plate-pooled-before-{samples,challenges}`;
  metrics `/tmp/plate-pooled-final-metrics.json`. Review sheets
  `plate-pooled-orbit.png`, `plate-pooled-original-samples.png` in this chat's
  visualization folder. The baseline was generated with only the new recovery
  stage disabled, preserving the session-19 front-orbit fitter.
- Next: ORBIT's gradient core and compound navy shapes are the main remaining
  fragmentation. A source-visible ownership probe found at least 12 substantial
  regions in the gradient core, eight in the badge ring and three in the monogram.
  The wordmark did not show substantial splitting in that probe. Its two cream
  highlights also remain filled paths. ROOT's inner ring touches same-colour leaves
  and needs decomposition; this conservative sibling-leaf merge cannot split it.

## Stroked loops crossing other artwork (session 19)

- **HEAD is `c5762b2`.** On takeover, session 18's verified mixed-content-hole work
  was committed (`632bb1c`); the commit-hang was diagnosed as the global
  identity-prompt `pre-commit` hook (`core.hooksPath` → `~/.git-templates/hooks`,
  an osascript GUI), bypassed with `-c hooks.skipidentityprompt=true` — NOT the
  commit template; gpg signing works once the hook is skipped (see HANDOFF).
- Closed the handover's primary ORBIT continuation item: the gold **front orbit**
  now recovers as one editable stroked **ellipse** (width 6.06 vs target 6, rx/ry
  190/62). `fit_closed` previously required every boundary sample < 0.85px, every
  pixel within 1px, and ≥90% free boundary — all violated by a thin stroke threaded
  through the badge ring/core/satellites/wordmark (~2% boundary smear up to 2.8px,
  ~37% near later covers), even though its visible arcs over-determine the ellipse
  (free-only fit RMS 0.26, footprint XOR 0.017). Three guarded relaxations, each
  still backed by a strong independent gate: scattered-outlier boundary tolerance
  (`_boundary_ok`: ≤5% and longest contiguous run ≤12 — a notch is a long run and
  still fails), stray-pixel allowance within 3px up to 1% of the loop (XOR ≤ 0.06
  still caps gross error), and free-boundary gate 0.9 → 0.5. Commits `7f0210c`
  (feat) + `c5762b2` (tests).
- ORBIT now emits **2 ellipses / 4 strokes** (was 1 / 3). **Its overall structural
  gap stays OPEN** (strict xfail): still 60 objects vs target 34 — the mint **back
  orbit** fragments into disconnected arcs (needs interrupted-arc completion, which
  `fit_closed` explicitly does not do), and the wordmark/emblem still fragment.
- Suite **216 passed, 6 xfailed** (213 + 3 new regressions). Panel stays 59/27,
  ROOT 51/3, all eight original samples and the other challenges unchanged. No
  target/golden edits.

## Mixed-content holes (session 18, committed `632bb1c`)

- Session 18 changes are now committed. Jessica
  requested wrapping up at 2% remaining usage. No commit/push this session.
- Fixed `order._silhouettes` treating a hole as solid when opaque interior artwork
  occupied more than half of it. Preserve the whole hole when it has a clear
  transparent core surviving two erosion steps, as well as the existing majority-
  transparent case. Fully opaque interiors and 1–2px alpha fringes retain prior
  behaviour. No stroke-fitting thresholds were changed.
- **ORBIT front loop: four false holes → one genuine hole**, removing the borrowed
  opaque core from its complete silhouette. Total anchors **603→600**; objects
  remain 60, editable strokes remain 3. White/dark SSIM **.9811/.9870→.9812/.9882**.
  Isolated emitted geometry IoU with the authored orbit improves **.1503→.8630**;
  it remains a compound path rather than the desired editable ellipse.
- Seven regressions: 5/10/20px clear voids inside mostly opaque holes, fully opaque
  and 1/2px fringe negatives, and ORBIT's complete front-loop topology/geometry.
  **213 passed, 6 xfailed** (baseline **206/6**). All eight original PLATE sample
  SVGs and fourteen other challenge PLATE SVGs are byte-identical to session 17.
  Independent targets, goldens and VTracer code are unchanged.
- Ran both benches; rendered and inspected the isolated loop, full composition
  and original samples. Outputs `/tmp/plate-void-final-{samples,challenges}`;
  metrics `/tmp/plate-void-final-metrics.json`; review sheets `plate-orbit-hole.png`
  and `plate-void-original-samples.png` in this chat's visualization folder.
- Remaining: the front ellipse still has gradient-crossing segmentation outliers
  (45 boundary points beyond .85px; worst ≈2.82px). Some wrongly assigned boundary
  pixels are actually solid gold in the PNG. Fix local colour/coverage assignment
  rather than relaxing constant-width/notch guards. The mint back orbit remains
  split, and ROOT inner-ring/leaf separation remains unresolved. Six full
  structural targets still fail; do not promote them based on this partial fix.

## Alpha-contour continuity (session 17)

- Committed sessions 14–16 and their refreshed handoff as **`a56c13e`**, as Jessica
  requested. Continued with the documented thin transparent-loop failure.
- A 5px circle lost 219 opaque pixels when unresolved edge labels borrowed nearby
  transparency. Reuse a supported wider colour explanation for unresolved pixels
  beside transparency; genuinely unsupported near-palette cores can seed the
  existing fallback even within its ordinary resampling halo. Keep existing
  solid/two-colour competition, palette limits and speckle cleanup.
- **5px circle: four objects / 26 anchors → one editable circle / four anchors**;
  SSIM **0.9929→0.9996**. All foreground alpha pixels survive in tested 3/5px
  circles/ellipses. Opaque colour/gradient boundaries are excluded from the repair:
  an initial broad variant broke gradient reconstruction and was discarded.
- Cleaner alpha contours made ORBIT's motion curves snap to polygons. Curved
  fitting now also considers polygons bordering transparency, preserving all
  three motion strokes against their unchanged independent targets. A source-cap
  test rejects a confidently flat front spanning most of the width; this prevents
  the descriptor's square-ended U from acquiring rounded stroke caps. Opaque
  primitives retain their previous eligibility; broader variants changed panel
  title/footer rectangles and were rejected by existing regressions.
- Final measured changes (white/dark SSIM):

  | Image | Objects | Anchors before → after | Strokes | SSIM before → after |
  | --- | --- | --- | --- | --- |
  | donut_alpha | 2 | 13 → 11 | 0 | .9864/.9897 → .9939/.9954 |
  | perforated_plate | 2 | 38 → 44 | 0 | .9907/.9922 → .9943/.9957 |
  | ORBIT | 60 | 617 → 603 | 3 | .9787/.9846 → .9811/.9870 |
  | EMBER | 51 | 463 → 446 | 2 | .9663/.9678 → .9663/.9683 |
  | ROOT | 52 → 51 | 559 → 522 | 3 | .9830/.9863 → .9830/.9867 |

  ROOT's two previously disconnected mint regions join through restored observed
  pixels. **51 is still short of the 56-object target**; this does not resolve
  semantic separation of its ring/leaves. EMBER white MAE changes slightly
  (2.123→2.135); full structural gaps remain for all three logos.
- Seven new regression cases; **206 passed, 6 xfailed**. All seven opaque original
  PLATE sample SVGs and eleven other challenge SVGs are byte-identical. The panel
  remains **59 objects / 27 strokes / 249 anchors / SSIM .9864**, fully passing.
  VTracer implementation and all independent targets are unchanged.
- Refreshed **only** the soft `t3_ring` control snapshot after verifying unchanged
  one-object/even-odd topology and eight anchors, with SSIM **.9884→.9983**. This
  removes its intentional geometry-drift warning; no desired-output targets changed.
- Both benches rendered and reviewed: `/tmp/plate-alpha-final-{samples,challenges}`;
  metrics `/tmp/plate-alpha-final-metrics.json`, `/tmp/plate-alpha-thin-loop-metrics.json`;
  review sheets `plate-alpha-final-bench.png`, `plate-alpha-thin-loops.png` in this
  chat's visualization folder. Next: ROOT inner ring and ORBIT interrupted orbits,
  true same-colour object separation, branched strokes and opaque counters. No push.

## Sessions 14–16 checkpoint

Jessica requested committing the accumulated straight-stroke, instrument-panel
and closed-stroke work. This checkpoint includes those changes and their updated
handoff, roadmap and regressions; verified again at **199 passed, 6 xfailed**.
No push. Next diagnosed issue: unresolved opaque pixels in a 5px transparent circle
borrow transparency during nearest-label filling, splitting one loop into four
regions (219 opaque pixels lost). Preserve palette/antialias safeguards when fixing.

## Thin closed strokes (session 16)

- Added conservative circle/ellipse stroke recovery from complete silhouettes with
  one hole. Fits use PNG coverage where available and true normal distance to an
  ellipse (offset ellipses are not simply ellipses with enlarged axes). Require thin,
  constant width, low local boundary residual and agreement of the whole footprint.
  Emit native `<circle>`/`<ellipse>` with `fill="none"` and source-scaled width;
  SVG metrics now count these strokes as well as open paths.
- **ROOT outer seal matches its unchanged independent target as an 18px circle
  stroke.** Total **2→3 of 32 strokes**, **610→559 anchors**, 52 objects unchanged.
  White/dark SSIM **0.9806/0.9846→0.9830/0.9863**. Full ROOT target still fails.
- Small boundary bites may complete only beneath observed later-painted shapes,
  with at least 90% free boundary; `complete_hidden=false` disables this. Thick
  rings, genuine cutouts, off-centre holes and nonuniform shapes remain protected.
  A visible-only prototype incorrectly reinterpreted the panel's filled bezels;
  the structural test caught it. Final fitting uses `Shape.full`, preserving the
  entire hidden disc. Added an independent nested-disc regression.
- Thirteen regressions cover circles, rotated ellipses, downscaling, target
  silhouette/style/width, rendered fidelity, disable switches, small covered bites,
  cutouts, thick/uneven rings and filled discs. **199 passed, 6 xfailed**, baseline
  **186/6**. All eight original PLATE SVGs and all other challenge PLATE SVGs are
  byte-identical to session 15; the complete instrument-panel target still passes.
- Ran both benches and visually inspected ROOT plus all original sample renders.
  Outputs `/tmp/plate-closed-final-{samples,challenges}`; metrics
  `/tmp/plate-closed-final-metrics.json`; review sheets `plate-closed-ring.png` and
  `plate-closed-original-samples.png` in this chat's visualization folder. VTracer
  implementation is unchanged; ORBIT's control varied between repeated runs
  (1473/3559 vs 1470/3745 objects/anchors), so control byte stability is not claimed.
- Remaining: ROOT's interrupted/merged inner ring and tree networks; ORBIT's
  interrupted orbits; opaque-background annulus/counter interpretation; thin
  transparent features split during segmentation (a 5px circle splits into four
  regions). Closed-stroke fitting does not reunite those fragments. HEAD remains
  `0a0fddc`; sessions 14–16 are uncommitted. No push or target/golden changes.

## Completed instrument panel (session 15)

- **First large composition to pass its unchanged independent structural target:**
  `complex_instrument_panel` now has **59 objects / 27 editable strokes / 249 anchors**.
  Previous step: 60 / 24 / 259. White/dark SSIM **0.9862→0.9864**. All three needles
  have full round-capped centrelines under their hubs, with correct paint order.
- Hidden straight-terminal fitting requires actual contact, alignment, the existing
  relative T-junction threshold (15°), a supported free cap, and a low-residual fit
  to the unoccluded boundary. An offset of at most one working pixel accommodates
  hub-fit error without bending the shaft. Visible core colours are checked against
  source coverage and the hub/stroke blend, so small gaps do not become connections.
- A larger hub can precede a smaller needle in area-based order. Earlier sibling
  circles are considered only with observed T-junction evidence; pipeline adds
  stable paint constraints **only after** the complete stroke fit succeeds. No
  global reordering of rejected strokes or unrelated shapes is introduced.
- Removed the extra 861px navy chassis island by merging its ownership into its
  same-colour immediate parent. Require a leaf child inside the parent's painted
  interior, and reject merging if earlier silhouettes, fitted primitives or traced
  fringes need the child's later repaint. This protects pupils, transparent holes,
  primitive-fit residuals and the original badge's navy repair strip.
- Benchmarking caught unsafe initial merge/order variants that degraded badge and
  noisy_badge. Those variants were corrected. Final verification: **all eight
  original sample SVGs, all other challenge SVGs and every VTracer SVG are
  byte-identical to session 14**. Only the panel changes. No target/golden edits.
- `complete_hidden=false` now also prevents endpoint completion in both straight
  and curved stroke fitters. Twenty-one new cases cover orientations, source
  scaling, full target matching, appearance, 1/3/6px gaps, off-centre/taper rejection,
  layer direction, disabling completion, parent islands and overpainting guards.
  Suite **186 passed, 6 xfailed** (baseline **164/7**); panel gap marker removed.
- Ran both benches and inspected the full panel, its isolated hidden needle
  geometry, and all original sample renders. SVGs:
  `/tmp/plate-hubs-final-{samples,challenges}`; metrics:
  `/tmp/plate-hubs-final-metrics.json`. Review sheets in this chat's visualization
  folder: `plate-completed-panel.png`, `plate-hubs-original-samples.png`.
- HEAD remains `0a0fddc`; session 14 and 15 work is uncommitted. CPU-only classical
  geometry and optional cosmetic VLM behaviour are unchanged.

## Straight round strokes (session 14)

- Added `strokes.fit_straight`: fit a capsule to subpixel foreground/background
  coverage (or source alpha), using classical PCA + bounded least squares. Preserve
  Lanczos overshoot when estimating the edge; a quantized pixel row must not distort
  a reliable subpixel fit. Compare cap-local error with a square-ended rectangle
  and overall fit with an ellipse. Require full-model mask agreement; subpixel
  boundary differences are allowed only with a reliable low-residual source fit.
- Pipeline tries straight recovery on primitive approximations as well as paths.
  Gradients, circles, holes and backgrounds are excluded. Straight endpoints near
  later-painted circles are conservatively left alone until their hidden geometry
  can be fitted. Existing open-curve endpoint completion remains unchanged.
- **Panel: 2→24 of 27 intended strokes**, including all 18 gauge ticks and four screw
  slots, each passing its independent target's silhouette/style/width contract.
  Anchors **303→259**, SSIM white/dark **0.9854→0.9862**. The three needles remain
  incomplete beneath hubs; the separate 60-vs-59 object mismatch remains open.
- Patch: **1→7 strokes**, **794→782 anchors**, SSIM unchanged **0.9815 / 0.9830**.
  Storefront: **0→2 strokes**, **576→572 anchors**, **0.9738 / 0.9752** unchanged.
  ROOT: **0→2 strokes**, **902→610 anchors**, SSIM **0.9784→0.9806** white,
  **0.9836→0.9846** dark; its name rules are now two-anchor lines. Other logo
  SVGs are unchanged. All seven full structural targets remain unmet.
- Original samples: seven SVGs byte-identical. UI card's three pill-like marks
  become strokes, preserving rounded caps previously flattened by snapping:
  **24→14 anchors**, SSIM **0.9714→0.9788**. Primitive ratio drops to 40% because
  strokes replace primitives; object count stays 5. Every VTracer SVG is unchanged.
- Fourteen new tests cover short/rotated/transparent strokes, independent tick and
  slot contracts, rejection of butt/square caps, ellipse/taper rejection, source
  scaling and the disable switch. Full suite **164 passed, 7 xfailed** (baseline
  **150/7**). No goldens or target SVGs changed. Palette-fixed synthetic fitting
  tests isolate segmentation; discovery of fully antialiased unseeded colours
  remains separate work (a tiny opaque 3px stroke can still be lost upstream).
- Both benchmark folders rendered and inspected. SVGs:
  `/tmp/plate-straight-final-{samples,challenges}`; comparison baseline:
  `/tmp/plate-straight-before-{samples,challenges}`; metrics:
  `/tmp/plate-straight-final-metrics.json`. Review sheets in this chat's visualization
  folder: `plate-straight-strokes.png`, `plate-straight-original-samples.png`.
- No commit/push requested or made; HEAD remains `0a0fddc`. Updated HANDOFF and
  removed stale nine-gap counts. CPU-only classical geometry remains the invariant;
  old AI geometry/preset experiments are explicitly parked in ROADMAP.

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


## Earlier geometry backlog — current priorities are at the top of this file

Geometry safety, thin-detail recovery and initial open-stroke support are complete.
All 18 ticks and four screw slots are editable straight strokes; both panel routes
are continuous editable curves, and all three needle endpoints are reconstructed.
The full instrument-panel target passes (59 objects, 27 strokes). The
independent `stroked_route`, `gradient_badge` and `edge_crossing_type` targets pass.
The badge has one full radial disc behind its ribbon, and the lettering has one
full disc behind its three letters. Three original complex logo fixtures are now
generated and committed (34–56 target objects). The six historical strict expected failures below
remain open; they are desired structural targets, not pipeline crashes.
The PLATE identity is the seventh; see HANDOFF's current seven-gap table.
Appearance/integrity checks remain active. Current scene SSIM: mission patch
**0.9815**, storefront **0.9738**, instrument panel **0.9864**, poster **0.9715**.
All four clear 0.95 on white and dark backgrounds. Current regression floors:
patch/panel 0.97, storefront/poster 0.96. The other three scene targets remain unmet; historical
sections below retain their earlier measurements.

Implementation order (details and acceptance checks in `ROADMAP.md`):

1. ORBIT's seven intended strokes now pass; recover ROOT's inner ring joined to leaves and EMBER's missing strokes; extend to non-sibling/non-leaf fragments, branched networks and other cap/join styles. Both ORBIT orbital ellipses now pass. Preserve full discs under nested objects and opaque counters. The panel's 27 strokes and full object contract pass.
2. Recover hairlines/fully antialiased colours without stable cores; repeated stable new colours and seeded-head curves are already supported.
3. Extend the affine radial-band recovery beyond supported circular silhouettes to clamped/nonlinear ramps and the mission patch. Preserve hard-edged craters, separate ramps and flat swatches.
4. Extend the implemented contour pooling/flat-fragment merging to complex letters/ribbons. Chained-circle drift is fixed.
5. Extend hole/component preservation to overlapping rings and soft alpha; refine corners, primitive selection and complex object recovery. The perforated-plate target passes.
6. Improve per-object failure diagnostics so partial progress is visible despite count mismatches.

| Remaining challenge | Current failure / required target |
| --- | --- |
| `complex_mission_patch` | 72 objects / 2 radial fragments / 8 strokes; target 45 with one radial planet + one linear hull, correct occlusion/strokes/cutouts |
| `complex_storefront` | 73 objects / 3 strokes; target 64, retaining repeated windows, awning panels, lettering, curves and small details |
| `complex_event_poster` | 83 objects; fidelity 0.9715 and one gradient, but target 44 still needs full underlying shapes, holes, strokes and lettering |
| `logo_ember_crest` | 51 objects matches count, but shield silhouette IoU 0.8383; 3 of 7 editable strokes recovered |
| `logo_orbit_wordmark` | 44 objects vs target 34; full radial core and all 7/7 strokes recovered; compound badge/monogram and ambiguous patches remain |
| `logo_root_seal` | 51 objects vs target 56; touching organic shapes merge; 9 of 32 strokes recovered, outer circle passes independently |

Illustrator native vectors/layers/groups/strokes/gradient fills and AI round trips
now pass automated checks (see the current checkpoint above). Live-shape widgets
and a 10–20-image real-world corpus remain unverified.
Real LM Studio naming/grouping **is verified**; naming accuracy
and request latency remain work. Other deferred items (palette pressure, soft
alpha/shadows, scale consistency, text, product/export/release) remain
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
1. **Illustrator follow-up**: all 24 automated 30.8.2 import/edit/AI-roundtrip cases, actual layers/order/membership and existing-document preservation pass. Verify live-shape widgets, direct gradient edits, native isolated hidden-shape/hole contracts and high-zoom seams. See `docs/illustrator-checklist.md`.
2. **Real-world images** (logos, clipart, scans). Only synthetic samples tested. Collect 10–20 real ones into `samples/real/` and run `plate bench`.
3. VLM naming quality: the model names both eyes "Left Eye" (dedupe suffixes → "Left Eye 2") rather than distinguishing left/right; naming is ~6s/shape (one request per shape → 47–65s for the face). Prompt/throughput tuning is open.

## Known weaknesses
- Hairline-route stress cases (`marks` route at authored 1px and 2px) are documented floors, not bugs. At default work_size the 256-wide source is not upscaled, so both render to a 2-working-px band (1px → alpha ≈147, 2px → alpha ≈243) whose distinct colour #141e2d is ~129 RGB from the palette and never admitted. The 1px case is a geometric floor (force-admitted it still fails silhouette: 1.5px min round-cap stroke vs 1px target, IoU 0.5); the 2px case is a palette-admission floor (force-admitted it passes every route check, but the geometrically identical, currently-green marks-s0p5 line4 route blocks any seeding rule). Pinned by `test_hairline_route_1px_is_below_the_round_cap_half_width_floor` and `test_hairline_route_2px_is_below_the_palette_admission_floor`; see docs/ROBUSTNESS.md. Sweep stays 70/78, core 36/36.
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

<!-- SPIKE:browser-web-page:begin -->

## Browser web page — Phase 1 spike measurements

Corpus: 24 scenes, seed 1. Bakeoff_Tolerance (composite band): 0.01. These are the raw spike measurements; the done-definition is asserted by task 5.

### Run setup

| setting | value |
|---|---|
| Run date (UTC) | 2026-11-03T00:51:53.020Z |
| Host | Darwin 25.6.0 arm64, Apple M4 Max |
| Browser | Chromium 149.0.7827.55 via Playwright 1.61.1, headless, fresh profile (cold cache: bring-up includes fetching Pyodide and the packages from the CDN) |
| Node | v22.22.2 |
| Pyodide | 314.0.7 pinned in web/src/worker.ts and web/package.json, loaded as an ES module in a module worker from https://cdn.jsdelivr.net/pyodide/v314.0.7/full/ |
| PLATE wheel | plate_svg-0.1.0-py3-none-any.whl (sha256 95c69960f3ae8832…), built with `uv build --wheel` from 2815cc0 plus uncommitted working-tree changes; installed in Pyodide with micropip deps=False |
| CLI reference venv (.venv) | Python 3.11.14; numpy 2.4.6, scipy 1.17.1, opencv-python-headless 5.0.0.93, pillow 13.0.0, scikit-image 0.26.0, cairosvg 2.9.1, plate-svg 0.0.1 (cv2.__version__ 5.0.0); plate imported from src/plate (editable install of this working tree) |
| Python command prefix | DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib (cairocffi does not search Homebrew's lib dir; cairosvg needs it for driver.py prepare/score) |
| Spike working dir | /tmp/plate-spike (manifest, corpus, browser SVGs, serve/ build outputs) |
| Diagnostic rerun venv | /tmp/plate-pyodide-venv/bin/python (see the diagnostic section) |

Browser runtime as reported by the warm worker: Pyodide 314.0.7, Python 3.14.2.

| distribution (in Pyodide) | version |
|---|---|
| `numpy` | 2.4.6 |
| `scipy` | 1.18.0 |
| `opencv-python` | 4.11.0.86 |
| `pillow` | 12.2.0 |
| `scikit-image` | 0.26.0 |
| `micropip` | 0.11.1 |
| `plate-svg` | 0.1.0 |

Reproduce (from the repository root):

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/driver.py prepare -o /tmp/plate-spike
# diagnostic venv with Pyodide 314.0.7's library versions (outside the repo):
~/.local/bin/uv venv --python 3.14.2 /tmp/plate-pyodide-venv
~/.local/bin/uv pip install --python /tmp/plate-pyodide-venv/bin/python numpy==2.4.6 scipy==1.18.0 opencv-python-headless==4.11.0.86 scikit-image==0.26.0 pillow==12.2.0
(cd web && npm ci && npx tsx spike/run.ts --dir /tmp/plate-spike --diag-python /tmp/plate-pyodide-venv/bin/python)
# run.ts itself runs, in order:
#   ~/.local/bin/uv build --wheel --out-dir /tmp/plate-spike/serve
#   esbuild bundles web/src/worker.ts and web/spike/page.ts into the same dir
#   DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/driver.py score -o /tmp/plate-spike
#   then, only when a scene is outside tolerance:
#   ~/.local/bin/uv pip install --python /tmp/plate-pyodide-venv/bin/python --no-deps --reinstall <the built wheel>
#   /tmp/plate-pyodide-venv/bin/python web/spike/diagnose.py convert -o /tmp/plate-spike
#   diagnose.py decode inside Pyodide under Node (npm pyodide 314.0.7)
#   DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/diagnose.py compare -o /tmp/plate-spike
```

### Package load results (Requirement 2.1)

A package passes when Pyodide loaded it and its top-level module imported.

| package | load |
|---|---|
| `numpy` | pass |
| `scipy` | pass |
| `opencv-python` | pass |
| `pillow` | pass |
| `scikit-image` | pass |

Runtime bring-up (one-time `init`, timed apart from the scenes): **6.03s**, ready.

### Per-scene timings + SVG classification (Requirements 2.2, 2.3)

`seconds` is the wall-clock time of one convert request on the warm worker (`plate.web.convert_bytes`: noise pre-check plus `pipeline.run`); `engine s` is the engine's own `stats.t_total` for the same call.

| scene | seconds | engine s | opencv-python | svg vs CLI | composite diff |
|---|---|---|---|---|---|
| scene00 | 0.55 | 0.46 | pass | byte-identical | 0.0000 |
| scene01 | 0.56 | 0.52 | pass | byte-identical | 0.0000 |
| scene02 | 0.52 | 0.48 | pass | byte-identical | 0.0000 |
| scene03_jpg | 0.52 | 0.48 | pass | outside-tolerance | 0.0202 |
| scene04 | 0.27 | 0.24 | pass | byte-identical | 0.0000 |
| scene05 | 0.36 | 0.33 | pass | byte-identical | 0.0000 |
| scene06 | 0.49 | 0.46 | pass | byte-identical | 0.0000 |
| scene07_jpg | 0.38 | 0.36 | pass | within-tolerance | 0.0000 |
| scene08 | 0.39 | 0.36 | pass | byte-identical | 0.0000 |
| scene09 | 0.30 | 0.27 | pass | byte-identical | 0.0000 |
| scene10 | 0.31 | 0.28 | pass | byte-identical | 0.0000 |
| scene11_jpg | 0.77 | 0.74 | pass | outside-tolerance | 0.0214 |
| scene12 | 0.31 | 0.28 | pass | byte-identical | 0.0000 |
| scene13 | 0.32 | 0.28 | pass | byte-identical | 0.0000 |
| scene14 | 0.55 | 0.52 | pass | byte-identical | 0.0000 |
| scene15_jpg | 0.38 | 0.35 | pass | within-tolerance | 0.0017 |
| scene16 | 0.32 | 0.29 | pass | byte-identical | 0.0000 |
| scene17 | 0.41 | 0.38 | pass | byte-identical | 0.0000 |
| scene18 | 0.26 | 0.23 | pass | byte-identical | 0.0000 |
| scene19_jpg | 0.70 | 0.67 | pass | outside-tolerance | 0.0984 |
| scene20 | 0.37 | 0.34 | pass | byte-identical | 0.0000 |
| scene21 | 0.32 | 0.29 | pass | byte-identical | 0.0000 |
| scene22 | 0.41 | 0.38 | pass | byte-identical | 0.0000 |
| scene23_jpg | 1.52 | 1.49 | pass | outside-tolerance | 0.0266 |

Per-scene conversion time over 24 timed scene(s): min **0.26s**, median **0.39s**, max **1.52s**. Slowest scene: **scene23_jpg** at **1.52s**.

Classification counts: byte-identical 18, within-tolerance 2, outside-tolerance 4, missing-browser-svg 0. Scenes that failed to convert: **0**. Largest composite diff: **scene19_jpg** (0.0984).

<!-- SPIKE:browser-web-page:decision:begin -->

### Phase 1 spike decision points (task 3.3)

**Verdict: SPIKE NOT MET — HALT before any Phase 2 work.** The following decision point(s) tripped their threshold (Requirements 2.4, 2.5, 2.3). A human must decide before Phase 2+ proceeds.

- **svg-equivalence** — 4 scene(s) did not match the CLI SVG within Bakeoff_Tolerance (outside-tolerance, unscored, or failed to convert).
  - scenes: scene03_jpg, scene11_jpg, scene19_jpg, scene23_jpg

<!-- SPIKE:browser-web-page:decision:end -->

<!-- SPIKE:browser-web-page:diagnostic:begin -->

### Diagnostic: outside-tolerance scenes rerun natively with Pyodide's library versions

- Native rerun (`web/spike/diagnose.py convert`): Python 3.14.2 (macOS-26.6.2-arm64-arm-64bit-Mach-O); numpy 2.4.6, scipy 1.18.0, opencv-python-headless 4.11.0.86, pillow 12.2.0, scikit-image 0.26.0, plate-svg 0.1.0; plate from `/tmp/plate-pyodide-venv/lib/python3.14/site-packages/plate`, installed from the same wheel the browser ran.
- CLI reference: Python 3.11.14 (macOS-26.6.2-arm64-arm-64bit); numpy 2.4.6, scipy 1.17.1, opencv-python-headless 5.0.0.93, pillow 13.0.0, scikit-image 0.26.0, plate-svg 0.0.1.
- Decoder check (`diagnose.py decode`): run inside Pyodide (Python 3.14.2) under Node, which uses the same WebAssembly package builds as the browser.
- JPEG codec behind Pillow: Pyodide IJG libjpeg (Pillow reports jpg 9.0); CLI venv libjpeg-turbo (Pillow reports jpg 6.2); rerun venv libjpeg-turbo (Pillow reports jpg 6.2).

A gap comes from **library versions** when the native rerun reproduces the browser SVG, and from **Pyodide** when the rerun reproduces the CLI SVG instead. When the rerun matches neither byte for byte, the composites decide: the side the rerun stays within 0.01 of. `decoded pixels` compares the RGBA output of the engine's decoder (`imageio.open_rgba`) with the CLI venv's.

| scene | rerun == browser | rerun == CLI | CLI composite | browser composite | rerun composite | decoded pixels, rerun | decoded pixels, Pyodide | gap comes from |
|---|---|---|---|---|---|---|---|---|
| scene03_jpg | no | yes | 0.7846 | 0.8049 | 0.7846 | same | differ: 7.4% of pixels, max abs diff 49 | **Pyodide** |
| scene11_jpg | no | yes | 0.8131 | 0.8345 | 0.8131 | same | differ: 6.1% of pixels, max abs diff 62 | **Pyodide** |
| scene19_jpg | no | yes | 0.8321 | 0.9305 | 0.8321 | same | differ: 7.5% of pixels, max abs diff 80 | **Pyodide** |
| scene23_jpg | no | no | 0.6189 | 0.5923 | 0.6189 | same | differ: 6.7% of pixels, max abs diff 61 | **Pyodide** |

Attribution: Pyodide 4.

For every scene above, the native rerun decodes the input exactly as the CLI venv does, while the decoder output inside Pyodide differs, so the conversion already starts from different pixels in the browser. The JPEG codecs behind Pillow are listed above.

<!-- SPIKE:browser-web-page:diagnostic:end -->

<!-- SPIKE:browser-web-page:gate:begin -->

### Phase 1 gate (task 5)

**Owner decision (Jessica, 2026-11-03):** accept the JPEG decoder difference. PNG output must match
the CLI byte for byte; JPEG differences caused only by the decoder are allowed and documented; the
0.01 Bakeoff_Tolerance stays. This amends the original done-definition, which required every
converted corpus image to be byte-identical or within tolerance of the CLI.

**Amended rule.** A PNG must convert byte-identically in the browser and on the CLI. A JPEG may
differ from the CLI only because the browser's JPEG decoder produces different pixels than the CLI's
(the browser's Pillow uses IJG libjpeg 9; the CPython wheels use libjpeg-turbo — see the diagnostic
above). The decoder-only attribution is proven by running the unchanged engine on the EXACT pixels
Pyodide decoded and getting the browser SVG back, byte-identical or within Bakeoff_Tolerance.

**Proof (requested first; it decides the gate).** For every JPEG scene, the unchanged engine was
rerun natively in the diagnostic venv (Python 3.14.2 with Pyodide 314.0.7's library versions, the
same wheel the browser installed) on the exact RGBA pixels Pyodide decoded, fed in by patching
`plate.imageio.open_rgba` in `web/spike/diagnose.py` only — the engine is never edited, and the JPEG
file stays on disk so `_is_jpeg` still sees a JPEG. The call goes through `plate.web.convert_bytes`
(the browser's entry point), so the noise pre-check sees the same pixels too. The result is compared
with the browser SVG in `browser/<scene>.svg`. The Pyodide-decoded pixels for all six JPEG scenes
were produced by `diagnose.py decode` run inside Pyodide under Node (the pinned npm `pyodide`
314.0.7, the same WebAssembly builds as the browser); the four previously-decoded scenes reproduced
their earlier digests byte-for-byte, confirming the decode is deterministic.

Reproduce (from the repository root), after a spike run has written `browser/<scene>.svg`,
`manifest.json` and `classification.json` under `/tmp/plate-spike`:

```bash
# 1. Pyodide-decoded RGBA for all six JPEG scenes (inside Pyodide under Node):
#    diagnose.py decode -o /spike --label pyodide-proof --scenes scene03_jpg … scene23_jpg
#    (run.ts's pyodideDecode mounts the spike dir and web/spike into Pyodide the same way)
# 2. Reinstall the freshly built browser wheel into the diagnostic venv:
~/.local/bin/uv pip install --python /tmp/plate-pyodide-venv/bin/python --no-deps --reinstall /tmp/plate-spike/serve/plate_svg-0.1.0-py3-none-any.whl
# 3. Rerun the engine on those exact pixels (diagnostic venv = Pyodide's library versions):
/tmp/plate-pyodide-venv/bin/python web/spike/diagnose.py same-pixels -o /tmp/plate-spike --decode-label pyodide-proof
# 4. Score the same-pixels SVGs against the browser SVGs (CLI venv; scoring needs cairosvg):
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/diagnose.py same-pixels-report -o /tmp/plate-spike
```

Proof result per JPEG scene (`same-pixels` SVG vs the browser SVG; the spike's CLI classification is
shown for context):

| scene | spike classification vs CLI | same-pixels vs browser | composite diff | proof |
|---|---|---|---|---|
| scene03_jpg | outside-tolerance | byte-identical | 0.0000 | PASS |
| scene07_jpg | within-tolerance | byte-identical | 0.0000 | PASS |
| scene11_jpg | outside-tolerance | byte-identical | 0.0000 | PASS |
| scene15_jpg | within-tolerance | byte-identical | 0.0000 | PASS |
| scene19_jpg | outside-tolerance | byte-identical | 0.0000 | PASS |
| scene23_jpg | outside-tolerance | byte-identical | 0.0000 | PASS |

All 6 of 6 JPEG scenes reproduced the browser SVG **byte-identically** from the same decoded pixels,
including the 4 the spike scored outside-tolerance against the CLI. Every JPEG difference from the
CLI is therefore decoder-only: given the browser's pixels, the engine produces the browser's SVG.

**All three done-definition conditions hold under the amended rule:**
- **Packages:** every required package load result is pass (`numpy`, `scipy`, `opencv-python`,
  `pillow`, `scikit-image`), per the package-load table above.
- **Timing:** every per-scene conversion time is at or below 60 s (min 0.26 s, median 0.39 s, max
  1.52 s for scene23_jpg), per the per-scene table above.
- **Equivalence:** every PNG is byte-identical to the CLI (18/18), and every JPEG difference is
  decoder-only, proven above (6/6 JPEG scenes reproduce the browser SVG from the browser's decoded
  pixels).

**Note on the recorded verdict.** `web/spike/decision.ts` still evaluates the original rule
(byte-identical or within tolerance of the CLI for every scene), so the decision section above
records NOT MET / HALT and rerunning `run.ts` will again print HALT for the outside-tolerance JPEG
scenes. That original verdict is kept as a historical record; `decision.ts` is unchanged. The gate
here is the amended, owner-accepted judgement.

Spike done-definition: MET (amended by owner decision)

<!-- SPIKE:browser-web-page:gate:end -->

<!-- SPIKE:browser-web-page:end -->
