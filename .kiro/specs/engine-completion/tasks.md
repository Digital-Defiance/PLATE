# Implementation Plan — PLATE Engine Completion

Ordered by value and confidence: fully-specified, byte-safe wins first; investigate-or-pin
items where their evidence is ready; the long tail; then the closing audit. Every task
follows the measure-first methodology in `design.md` and must land in terminal state (a)
FIXED-with-a-number-and-test or (b) DOCUMENTED-LIMIT-with-a-pin, preserving the regression
surface (GC-4) and never weakening a gate / editing a target / inventing geometry (GC-5).

Diagnostics prefix used below (abbreviated `DIAG`):
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python`.
Worktree runs use `PYTHONPATH=<worktree>/src` + the `DYLD_FALLBACK_LIBRARY_PATH` prefix.
Regression surface check (`REGS`): `pytest -q` green (565+/7 xfail/0 xpass),
`python -m plate.robustness` ≥ 70/78 full & 36/36 core, 24 shipped SVGs byte-identical on
PNG inputs, VTracer baseline present, 7 strict-xfail gaps intact.

---

- [x] 1. JPEG robustness: format-keyed denoise trigger + correct the docs (R1).
      Done 2026-11-01: `_is_jpeg` + `level = 2 if noisy else (1 if jpeg else 0)` in
      `load_image`; pinned by `test_jpeg_variant_hidden_completion_meets_floor` (3/10 → 4/10,
      0.33 → 0.42; floor met, 0.6 stretch not); `docs/BAKEOFF.md` corrected.
      Re-audited 2026-11-01 against the exact seed-1/q55 corpus with the JPEG trigger
      disabled vs enabled: 3/10 → 4/10 objects, mean per-scene 0.333333 → 0.416667.
      Task 1's ≥0.4 acceptance floor is met; the ≥0.6 stretch remains unmet. Task 2's
      residual pin is now done (see below). Evidence: `/tmp/plate-continue/task1-audit.json`.
      Measure first: `plate corpus -o /tmp/jpeg-bo -n 24 --seed 1` then
      `plate bakeoff /tmp/jpeg-bo/images --truth /tmp/jpeg-bo/truth -o /tmp/jpeg-bo/out`;
      confirm JPEG-variant aggregate `hidden_completion` ≈ 0.30 (3/10). Add a JPEG-keyed
      trigger to the auto-denoise branch in `load_image` (one fixed bilateral pass when the
      decoded source is JPEG; `open_rgba` already exposes `im.format`). It must fire on no
      PNG. Then correct `docs/BAKEOFF.md`: replace the 0/10 figure and the T-junction
      attribution with the measured 3/10 and the `complete.try_complete` primitive-fit
      cause.
      Files: `src/plate/imageio.py`, `docs/BAKEOFF.md`, `tests/test_bakeoff.py`.
      Acceptance (a): JPEG-variant `hidden_completion` ≥ 0.4 floor (target ≥ 0.6), pinned
      in `tests/test_bakeoff.py`; 24 shipped SVGs byte-identical by construction.
      Verify: re-run the bakeoff above and confirm the number rose; `pytest -q tests/test_bakeoff.py`
      new test passes; REGS holds.

- [x] 2. Pin the JPEG clean-render floor as a documented limit (R1 state (b)).
      The 3 objects (scene15 ×2, scene23 ×1) recover 0 even on the clean render at every
      denoise level — a pre-existing rect/polygon completion limit (Task 4 class), not a
      JPEG bug. Add a pin asserting the clean-render floor so they are never re-chased as
      JPEG failures.
      Files: `tests/test_bakeoff.py` (or `tests/test_pipeline.py`).
      Acceptance (b): pin test asserts the measured clean-render non-recovery of those
      objects; references Task 4 as the owning class.
      Done 2026-11-01: 14 tests directly render independent truth SVGs as PNG and verify
      scene15 ×2 / scene23 ×1 recover 0 at denoise -1/0/1/2/3/4/6. This pins a measured
      R2/Task 4 completion/matching limitation, not an information-theoretic impossibility;
      update the pin when Task 4 improves recovery. Full 651/7 xfail, sweep 70/78, core
      36/36, 48 default/control SVGs unchanged.
      Verify: `pytest -q` runs the new pin green; REGS holds.

- [x] 3. Realistic gradient: smooth-single-ramp region detector (R4 state (a)).
      Measure: `plate bench samples/real` confirms `real_radial_orb` → 1 object, 0
      gradients, SSIM ≈ 0.83. Add a smooth-ramp pre-pass that detects a 4-connected opaque
      blob with high luma span, low local Lab gradient (median ≈ 6.64 on the orb), and high
      unique-colour mass, then fits the EXISTING `geometry.fit_radial_gradient` /
      `fit_linear_gradient` on its raw pixels, accepting only at residual ≤
      `grad_max_residual`. Emit one gradient `Shape` and skip adding its colours to the flat
      palette. Additive by construction — flat art fails the smoothness test and flows the
      unchanged band path; the gradient gates are unchanged.
      Files: `src/plate/stages/segment.py` and/or `src/plate/stages/gradient.py`,
      `tests/test_gradient_bands.py` (or a new gradient test).
      Acceptance (a): `real_radial_orb` → 1 radial-gradient disc, SSIM measurably > 0.83,
      pinned; `shaded`→1 radial, `t3_linear_grad`/`t3_radial_grad`/`t4_grad_behind_circle`
      exact counts + `<linearGradient>` unchanged, `discrete_palette`→0,
      `twin_gradients`/`gradient_badge` unchanged.
      Verify: `DIAG -m pytest -q tests/test_gradient_bands.py tests/test_controls.py`;
      `plate bench samples/real` shows the orb improved; REGS holds.
      Done 2026-11-01 (a): new additive pre-pass `gradient.detect_ramp_region` (run at the
      top of `detect()`) flags a region by the measured smooth-ramp signature (luma span
      ≥120, interior Lab-gradient median ≤8, unique-colour frac ≥0.03, max repeat frac ≤0.05),
      carves the ramp blob from its flat surround, fits the existing radial/linear gradient on
      the eroded interior (orb radial residual 0.0307) and accepts only at residual ≤
      `grad_max_residual`, emitting one gradient Shape + the flat remainder (no palette colour
      added). `real_radial_orb` 1 obj/0 grad/SSIM 0.8276 → 2 shapes / 1 radial disc / SSIM
      0.9455 (beats VTracer 0.9094). Unchanged: `shaded`→1 radial (0.9557), `discrete_palette`
      →0, `twin_gradients`→2, `gradient_badge`→1, `real_sunset_gradient`→0 (`_monotone_ok`
      rejects it), t3/t4 controls and 24 shipped SVGs. Pins:
      `test_smooth_single_ramp_region_recovers_the_orb_as_one_radial_gradient` and
      `test_flat_art_does_not_trigger_the_smooth_ramp_pre_pass` in `tests/test_gradient_bands.py`.
      Full suite 660/7 xfail; robustness core 36/36, full 70/78.

- [x] 4. Rect/polygon amodal completion by free-edge intersection (R2 state (a)).
      Measure: from the Task 1 corpus, record occluded rect 4/11, polygon 3/10, rrect 5/12
      and overall `hidden_completion`. In the completion path, extend partly-hidden
      rectilinear free edges by line intersection (not only fitting free points) before the
      existing primitive validation in `try_complete`/`evaluate`. Do not loosen the
      primitive-fit tolerance or the 15° `_occludes` threshold.
      Files: `src/plate/stages/complete.py`, `tests/test_bakeoff.py` (+ a focused
      completion test).
      Acceptance (a): overall `hidden_completion` toward ≥ 0.8 with per-kind rect/polygon/
      rrect counts measurably up, pinned; residual ambiguous cases pinned as (b) with
      measured free-edge extent evidence.
      Verify: re-run the bakeoff; new/updated `tests/test_bakeoff.py` passes; REGS holds
      (24 SVGs byte-identical, sweep ≥ 70/78).
      Done 2026-11-01 (a)+(b): measured first on the seed-1/n=24 corpus — occluded circle
      14/16, ellipse 4/8, rect 6/11, polygon 2/10, rrect 6/12; overall 32/57; mean per-scene
      `hidden_completion` 0.5486. Added a free-edge line-intersection reconstruction to
      `complete.try_complete`: the ordered contour's free runs (cls==0) are split into near-
      straight edges by an incremental turning-angle corner detector, collinear fragments are
      merged, a two-orthogonal-family quadrilateral (rect/rrect/rotated rect) and a chained
      convex polygon are reconstructed by extending and intersecting adjacent non-parallel free
      edges, and each is fed to the EXISTING `evaluate` (primitive-fit tol and the 15° `_occludes`
      threshold untouched; GC-5 held). The occluder-coverage test for this candidate only (a) tests
      against all touching neighbours, not just the 15°-flagged ones, and (b) dilates the coverage
      mask by 1px to absorb the sub-pixel rasterisation seam (the R7b "rasterised perimeter
      dominates the extra" artefact — fraction floors 0.85/0.9/0.65/0.7 unchanged). Measured after:
      polygon 2→3/10, overall 32→33/57, mean `hidden_completion` 0.5486→0.5625, bake-off composite
      0.852→0.857; no per-kind count dropped; PLATE still beats VTracer/Potrace. The quad path
      produces mathematically exact rects (rms 0) for several more occluded rects/rrects that stay
      (b) near-misses: rounded rectangles lose their corner rounding to a sharp reconstructed quad
      (scene09 best IoU 0.89), and stacked corners covered by a neighbour giving R no local
      T-junction (no paint-order edge → correctly rejected). Pins: four unit cases in
      `tests/test_free_edge_completion.py` (reconstruct the hidden corner; the free-point fit alone
      falls short; end-to-end rect completion; and a NEGATIVE regression — an abutting
      non-overlapping neighbour is NOT completed across the seam), plus
      `tests/test_bakeoff.py::test_free_edge_lifts_occluded_rectilinear_completion` (floor pin) and
      `::test_free_edge_residual_rrect_is_a_measured_near_miss` (the 0.85–0.90 rrect band, state
      (b)). `docs/BAKEOFF.md` updated. Full suite 666 passed / 7 xfailed / 0 xpassed; robustness
      full 70/78, core 36/36; 24 shipped SVGs byte-identical (challenge/logo/control/complex-scene
      asset tests all green).

- [x] 5. ROOT inner-seal interrupted circular ring via the circle arm (R6a state (a)).
      Measure: `DIAG -m challenge_report logo_root_seal` shows 6 `Beige_*` extras at
      r≈275 from (450,370), ring matched as an open arc at IoU 0.27. Reunite via the circle
      arm of `order._merge_compound_siblings`, reusing the existing shared-occluder (15°
      T-junction) + common-circle (`fit_circle`, `rms<=0.02·r`, `arc>=160°`) evidence — no
      gate relaxation. Ship with a positive regression (the ring reunites) and negative
      regressions (contaminated / no-occluder hulls rejected).
      Files: `src/plate/stages/order.py`, `tests/test_interrupted_loops.py` (or
      `tests/test_logo_assets.py`).
      Acceptance (a): ROOT inner-seal extras drop / ring IoU rises (moved
      `challenge_report` number), pinned; other 23 SVGs byte-identical; ROOT may remain
      xfail (its dominant gap is the Task 7 same-colour limit) — the criterion is the
      per-object improvement, not promotion.
      Verify: `DIAG -m challenge_report logo_root_seal` shows the improvement; new tests
      pass; REGS holds. If a tight-gated fit is impossible without contamination, convert to
      (b): pin the measured ring-interruption evidence.
      Done 2026-11-01 (a): measured first — the inner-seal `#a9d1b5` ring was 6 `Beige_*`
      extras matched as an open arc at IoU 0.2715, topology (1,0). Root cause: the circle arm's
      common-circle fit on the pooled cluster already passed (rms/r 0.0052, arc 345°) but the
      merge was vetoed because five short arc slivers (areas 140–358) each snap to a tiny
      rect/rrect (a few-degree arc looks locally rectangular). Fix (circle arm only, GC-5 held,
      no gate loosened): classify each member ON/OFF the fitted ring by its pixels' median
      distance to the centre (`max(6, 0.08·r)` tolerance); exempt an ON-ring member from the
      veto ONLY when it snaps to rect/rrect (a boxy sliver) — a circle/ellipse snap is a genuine
      complete curved object and still vetoes (keeps `samples/badge.png` byte-identical);
      when a large OFF-ring same-colour leaf is pooled into the hull (area ≥ 25% of the total
      on-ring mass) reunite ONLY the on-ring arcs and re-fit `fit_circle` on exactly those with
      the SAME rms≤0.02·r / arc≥160° gates, so adjacent leaves keep their identity (the ellipse
      arm gained the same off-band leaf guard). Result: inner-seal IoU 0.2715 → 0.4073, topology
      (1,0) → (7,0), extras 7 → 1 (the remaining `Beige_ellipse_3` is the Task 6 leaf-vein
      split), object count 51 → 45, matched stays 44 (leaf-3/leaf-6 NOT swallowed). ROOT stays
      xfail (dominant gap is the Task 7 same-colour limit). Pins in
      `tests/test_interrupted_loops.py`: positive on the real asset
      (`test_root_inner_seal_arcs_reunite_into_one_ring_without_swallowing_leaves`), a synthetic
      positive (`test_circular_ring_crossed_by_a_shared_occluder_reunites`) and two negatives
      (`test_off_ring_same_colour_disc_is_not_merged_into_the_ring`,
      `test_arcs_without_a_shared_occluder_are_not_reunited`); `test_strokes.py` count pin
      updated (ROOT 51 → 45 shapes, strokes ≥ 8). Full suite 670 passed / 7 xfailed / 0 xpassed;
      robustness core 36/36, full 70/78; 24 shipped SVGs byte-identical except `logo_root_seal`.

- [x] 6. ROOT leaf-vein-11 thin-stroke split (R6b).
      Measure: `DIAG -m challenge_report logo_root_seal` shows the continuous ~3.4
      working-px cream vein emitted as two primitives. Attempt a scoped thin-curved-stroke
      fit so it emits as one stroke (`strokes.fit_stroke` currently needs `width>=2`,
      `mask.area>=24·r²`; the vein is marginal).
      Files: `src/plate/stages/trace.py` and/or `src/plate/stages/strokes.py`, a focused
      stroke test.
      Acceptance: (a) the vein emits as one stroke (moved split count), pinned; OR (b) pin
      the measured below-floor evidence if admitting it would require lowering the stroke
      width/area floor (which regresses shipped art).
      Verify: `DIAG -m challenge_report logo_root_seal`; new test passes; REGS holds.

- [x] 7. Same-colour touching objects: investigate a concavity splitter, else pin (R3).
      Read-only investigation first (template: the ember / root-storefront / patch-poster
      reports): does any classical cue (concavity / convexity-defect splitting of one
      same-colour component) split touching same-colour regions without an ML model, with
      pixel evidence? For any measurable FIXABLE class: (a) a tightly-gated splitter moving
      a `challenge_report`/bakeoff number with a positive + negative regression (no false
      splits on legitimately single objects). For the authored abutting cases (expected
      outcome): (b) reference the existing EMBER pin
      (`test_ember_same_colour_face_features_are_one_raster_region`) and add the ROOT-tree,
      ROOT leaf-4+5, storefront cream-awning and storefront teal-leaf raster-contiguity pins
      recommended in the root-storefront investigation.
      Files: `.agents/tasks/<same-colour-split-investigation>.md`, possibly
      `src/plate/stages/segment.py`/`order.py`, `tests/test_logo_assets.py`,
      `tests/test_complex_scene_assets.py`.
      Acceptance: each in-scope same-colour merge reaches (a) or (b); state explicitly this
      is the engine's most likely hard classical ceiling.
      Verify: investigation report committed; pins/fix run green under `pytest -q`; REGS
      holds. No gate weakened (GC-5).

- [x] 8. Heavy sensor-noise / JPEG-artifact collapse: improve or pin (R5).
      Measure: `plate bench samples/real` confirms `real_sensor_noise_badge` SSIM 0.355 (5
      objects) and `real_jpeg_artifacts` 269 objects / SSIM 0.554. Investigate whether a
      stronger/better-triggered denoise or a pre-segmentation artifact guard measurably
      improves either WITHOUT regressing the 24 SVGs or the sweep.
      Files: `src/plate/imageio.py` and/or `src/plate/stages/segment.py`,
      `tests/test_real_corpus.py` or `tests/test_robustness.py`.
      Acceptance: (a) measured SSIM/object-count improvement pinned; OR (b) pin the measured
      collapse with evidence that any catching trigger re-denoises clean shipped art (the
      `noise_fraction` overlap precedent).
      Verify: `plate bench samples/real`; new test passes; REGS holds.
      Done 2026-11 (b) DOCUMENTED LIMIT: measured first at work_size=1536.
      `real_sensor_noise_badge` noise_fraction 0.8703 (far above the 0.04 auto gate, so the
      global branch ALREADY fires at full strength — two bilateral passes); SSIM auto 0.3519
      vs heavy denoise=6 0.3532 (swing <0.01, non-monotonic to 0.3558 at level 8) — the
      collapse is information loss, not a missed trigger. `real_jpeg_artifacts` noise_fraction
      0.0352 (BELOW the 0.04 gate, not a decoded JPEG so the R1 format trigger does not fire);
      denoise makes the object count worse not better (level 1 → 526 objects / SSIM 0.5468,
      level 4 → 296 / 0.5628 vs baseline 269 / 0.5542). The `noise_fraction` overlap precedent
      proven concretely: a global gate low enough to catch the JPEG collapse (≤0.0352) newly
      denoises shipped `logo_orbit_wordmark` (nf 0.0399, inside the (0.0352, 0.04] band) and
      clean `noisy_badge.png` (nf 0.0781); re-denoising logo_orbit_wordmark changes its shipped
      SVG (20360 → 26250 bytes), so any catching trigger breaks the 24-SVG byte-identity (GC-4).
      Pinned by four tests in `tests/test_real_corpus.py`:
      `test_sensor_noise_badge_collapse_is_not_a_denoise_trigger_gap`,
      `test_sensor_noise_badge_stays_collapsed_even_at_maximum_denoise`,
      `test_jpeg_artifact_collapse_sits_below_the_gate_and_overlaps_shipped_art`,
      `test_lowering_the_gate_to_catch_jpeg_artifacts_changes_a_shipped_svg`. No source/gate
      change (GC-5 held). REGS: full suite 675 passed / 7 xfailed / 0 xpassed, robustness full
      70/78 & core 36/36, 24 shipped SVGs byte-identical by construction.

- [x] 9. Long-tail quality batch A — completion & segmentation sub-items (R7a, R7b, R7c).
      For each: measure with the relevant diagnostic, then fix-and-pin or pin-as-limit.
      R7a thin-colour/hairline discovery for fully-antialiased features (extend the
      isolated-alpha-component admission in `segment.py` keeping palette budgets + the
      gradient-band veto, moving a sweep case; or pin the sub-pixel floor). R7b thin
      occluded rectangles (correct the pixel-boundary evaluation in hidden-area validation
      in `complete.py`, NOT the `_occludes` threshold; or pin). R7c palette pressure >64
      colours: add a labelled mosaic fixture (a `scripts/` generator) and verify the k-means
      path in `segment.py` recovers it, or pin the measured limit.
      Files: `src/plate/stages/segment.py`, `src/plate/stages/complete.py`,
      `scripts/` (mosaic generator), `tests/test_segment.py`, `tests/test_robustness.py`.
      Acceptance: each sub-item in (a) with a moved number + pin, or (b) with a measured pin.
      Verify: `python -m plate.robustness` and focused `pytest -q tests/test_segment.py`;
      REGS holds.
      Done 2026-11-02: all three sub-items reached a terminal state; REGS held
      (full suite 688 passed / 7 xfailed / 0 xpassed, robustness full 70/78 with the failing
      set IDENTICAL to baseline & core 36/36, 24 shipped SVGs byte-identical — challenge/
      control/logo/complex asset tests all green). No gate weakened, 15° `_occludes` untouched
      (GC-5).
      • R7a — (b) DOCUMENTED SUB-PIXEL FLOOR. Measured the isolated-alpha-component admission in
        `segment.py`: a fully anti-aliased isolated mark is admitted at ≥3 working px but a 2 px
        mark is almost all fringe (no flat seed, no stable alpha≥245 erodable core) so its colour
        is NOT admitted (cream ≥20 RGB from every palette entry vs <20 at 3 px). Forcing the 2 px
        case would require lowering the admission gate, which the existing route pins prove
        regresses the green marks-s0p5 line4 route and the panels blur halos. Pinned by
        `tests/test_segment.py::test_fully_antialiased_mark_at_or_above_the_floor_is_admitted`
        (width 3/4/5 admitted) and `::test_fully_antialiased_2px_mark_is_below_the_isolated_
        alpha_admission_floor`, alongside the existing `tests/test_robustness.py::
        test_hairline_route_1px_*` / `_2px_*` floors (the route form of the same limit).
      • R7b — (a) FIXED, moved number. Measured in `complete.py`'s `evaluate`: for a thin
        occluded rect the reconstructed "extra"'s rasterised 1 px PERIMETER is an area-independent
        constant (~130 uncovered px, 0 interior at every bar height) that drags the occluder-
        coverage fraction below the 0.85 floor as the bar narrows (full-extra coverage 0.69 @6px →
        0.86 @20px), so a perfectly-fit rect (RMS<<tol) was wrongly rejected. Fix: for RECT
        candidates only, when the band is thin (perimeter ≥25% of area) evaluate the coverage
        floor on the eroded INTERIOR of extra and admit only when that interior is ≥0.98 under the
        occluders. The 0.85/0.65 floors, the occluder set (Cm/Cv) and the 15° `_occludes`
        threshold are all unchanged (corrects the pixel-boundary evaluation, GC-5 held). Measured:
        an 8–16 px occluded bar now completes to one `<rect>` (was 2 fragments / no completion);
        the 20 px control (already completing) and every shipped SVG are unchanged; the
        complex_instrument_panel challenge and the bake-off rrect near-miss pin stay green. Pinned
        by `tests/test_free_edge_completion.py::test_thin_occluded_bar_completes_into_one_rect`
        (8/12 px), `::test_thick_occluded_bar_was_already_completing` (20 px control) and the
        negative `::test_thin_bar_abutting_a_non_overlapping_neighbour_is_not_completed`.
      • R7c — (a) FIXED/VERIFIED, moved number, with a new `scripts/` generator. Added
        `scripts/make_mosaic.py` (a labelled, deterministic high-cardinality flat-mosaic fixture;
        wrote `samples/fixtures/mosaic_130.{png,json}`). Measured the two palette paths in
        `_build_palette`: a ≤96-colour mosaic is honoured verbatim by the flat-palette branch at
        the default budget (n=90 → 84/90 recovered), while a 130-colour mosaic exceeds the
        FLAT_PALETTE_CEILING (96) and falls to the k-means fallback bounded by `max_colors` — at
        the default `max_colors=16` it collapses to 0/130 (the documented default ceiling), but
        the k-means path DOES recover it once the budget is raised: `max_colors=96` → 73/130,
        `max_colors=130` → 113/130. Pinned by `tests/test_segment.py::
        test_flat_mosaic_up_to_the_ceiling_is_recovered_verbatim_at_default_budget`,
        `::test_high_cardinality_mosaic_collapses_to_max_colors_at_the_default_budget` and
        `::test_kmeans_path_recovers_a_high_cardinality_mosaic_when_the_budget_is_raised`.

- [x] 10. Long-tail quality batch B — alpha, scale, naming (R7d, R7e, R7f).
      R7d nonuniform/soft alpha + shadows: extend flat-region opacity support, validate on
      both backgrounds (measured SSIM/object improvement on a soft-alpha fixture; or pin
      feathered-alpha limit). R7e scale consistency: run the same authored logo at 1×/2×/4×
      and reconcile the `work_size=200` gradient-loss case (badge → 10 flat/0 gradients);
      make detection scale-consistent or pin the measured scale floor. R7f ring/compound
      semantic naming ("Red ring") in `name.py` WITHOUT changing `t3_ring` even-odd topology
      (assert topology unchanged).
      Files: `src/plate/stages/segment.py`, `src/plate/pipeline.py`,
      `src/plate/stages/gradient.py`, `src/plate/stages/name.py`,
      `tests/test_controls.py`, `tests/test_gradient_bands.py`.
      Acceptance: each sub-item in (a) with a moved number + pin, or (b) with a measured pin;
      GC-2 untouched (naming is classical, not geometry).
      Verify: focused `pytest -q` for the touched tests + `DIAG` bench where fidelity is
      claimed; REGS holds.
      Done 2026-11-02: all three sub-items reached a terminal state. REGS held — full suite
      693 passed / 7 xfailed / 0 xpassed (was 688/7/0, +5 new pins), robustness full 70/78
      (failing set IDENTICAL to baseline) & core 36/36, the 24 shipped SVGs untouched (the
      naming change only edits a path's id/data-name/inkscape:label, never its geometry/
      fill/order/topology, and the shipped-SVG checks are structural/pixel, not name-byte).
      No gate weakened (GC-5); GC-2 untouched (naming is classical, not geometry).
      • R7f — (a) FIXED, moved classical name. Measured first: t3_ring emitted one even-odd
        `path` named "Red shape" (evenodd=True, two subpaths = one outer + one hole, 8 anchors).
        Added `name.shape_word(node)` (used by `pipeline.run`'s classical base-name line in
        place of `KIND_WORD[n.kind]`): a path with `evenodd` and exactly two subpaths (`d.count
        ("M")==2`, i.e. one outer contour + one interior hole = an annulus) reads as a "ring".
        Pure naming over the geometry the tracer already produced — the even-odd fill and the
        two subpaths are byte-identical (golden diff: ONLY id/data-name/inkscape:label
        "Red shape"→"Red ring"; the `d`, `fill-rule="evenodd"` and coords unchanged). t3_ring
        now names "Red ring"; three shipped logos (orbit_wordmark, plate, root_seal) gain "…
        ring" names on their existing even-odd holes with NO geometry change (their asset tests
        stay green). Pinned by the t3_ring branch in `tests/test_controls.py` (name == "Red ring"
        AND evenodd is True AND d.count("M")==2 — asserts topology unchanged); control golden
        `tests/golden/controls/t3_ring.svg` refreshed for the intentional name change.
      • R7e — (b) DOCUMENTED SCALE FLOOR. Measured first on `gradient_badge.png` (source
        400×360): at work_size=200 the ramp is lost (9 flat shapes / 0 gradients); it recovers to
        exactly 5 shapes / 1 gradient at work_size≥250 and is scale-consistent up to the default
        1536. Root cause instrumented: the band path joins adjacent thin bands into one ramp only
        when each step's Lab dE ≤ `grad_step_de`(14.0); at work_size=200 the ramp posterizes into
        only ~9 coarse bands whose per-step dE is 17–60 (measured), so every band stays a
        singleton component and none reaches `grad_min_bands`(6). This is a true scale floor, not
        a bug: recovering it needs `grad_step_de` (a calibrated gate, GC-5) raised enough to merge
        genuinely distinct flat colours, and detection is itself unstable just above the floor
        (work_size=220 over-detects TWO gradients on this single-ramp badge). The 1×/2× source
        rescales are scale-consistent at the default work_size (both 5 shapes / 1 gradient); the
        4× nearest upscale lands on the work_size downscale boundary and aliases differently —
        the same low-effective-resolution floor from the other side. No source change (both
        `gradient.py` and `segment.py` left untouched — the honest measure-first outcome). Pins in
        `tests/test_gradient_bands.py`:
        `test_gradient_detection_is_scale_consistent_above_the_measured_work_size_floor`
        (lost at 200; exactly 1 gradient / 5 shapes at 250/300/400/768/1536) and
        `test_authored_logo_gradient_recovery_is_consistent_at_1x_2x_source_scale`.
      • R7d — (b) DOCUMENTED FEATHERED-ALPHA LIMIT, validated on both backgrounds, new `scripts/`
        generator. Added `scripts/make_soft_alpha.py` (deterministic RGBA fixtures with real
        varying alpha; wrote `samples/fixtures/soft_{uniform_overlay,feathered_disc,shadow_card_
        fx}.png`). Measured first: flat-region opacity support (`pipeline._opacity` +
        `segment._faint_objects`) models ONE opacity from a shape's interior — a single flat
        coverage composites identically on every background, so the SUPPORTED uniform case is
        correct on BOTH white and black (soft_uniform_overlay 1 shape, SSIM 1.000/1.000; the
        existing `test_translucent_overlay_keeps_its_opacity` already asserts this for alpha
        64/128/191). A NONUNIFORM / feathered alpha has no hard silhouette boundary: one opacity
        cannot match two backgrounds at once, and `_faint_objects` deliberately admits a faint
        region only when its interior sits at one steady level (90th-pct dev ≤8), so a
        continuously-ramping alpha keeps its binary-threshold treatment. Measured limit:
        soft_feathered_disc SSIM 0.856 white / 0.721 black (both below the uniform case AND
        asymmetric → one opacity can't serve both); soft_shadow_card_fx 0.902 white / 1.000 black
        (the soft-shadow band only shows on white). Extending the silhouette below the alpha≥128
        contract to catch the feather would grow every antialiased rim and break the 24 shipped
        SVGs (GC-4) — same precedent as the existing hairline/soft-shadow floors. No source change
        (`segment.py` opacity path left untouched). Pins in `tests/test_inputs.py`:
        `test_uniform_flat_region_opacity_is_correct_on_both_backgrounds`,
        `test_feathered_nonuniform_alpha_cannot_match_both_backgrounds_at_once`,
        `test_soft_drop_shadow_band_is_the_measured_feathered_limit`.

- [x] 11. Long-tail quality batch C — open diagnostic items (R7g).
      First VERIFY whether commit `5692fa9` (present at `425fa19`) already fixed the false
      split/merge on legitimately overlapping objects: build identical overlapping back/front
      rectangles and run `diff_target(svg, svg)`; if it reports zero false splits, (a) add a
      pin asserting that; if not, fix `tests/challenge_diff.py` then pin. Second: the short
      curved butt-cap control that emits round caps — fit a butt cap where the probe expects
      one in `strokes.py` (pinned by a square/butt-cap test), or pin the measured limit.
      Files: `tests/challenge_diff.py`, `tests/test_challenge_diff.py`,
      `src/plate/stages/strokes.py`, `tests/test_straight_strokes.py` or
      `tests/test_closed_strokes.py`.
      Acceptance: both items in a terminal state ((a) verified+pinned, or fixed+pinned, or
      (b) pinned).
      Verify: focused `pytest -q` for the touched tests; REGS holds.
      Done 2026-11-02: both items in a terminal state; no source change (test-only), so the
      24 shipped SVGs are byte-identical by construction and no gate was touched (GC-5 held).
      REGS: full suite 696 passed / 7 xfailed / 0 xpassed (was 693/7/0, +3 new pins),
      robustness full 70/78 & core 36/36 (failing set identical to baseline), VTracer baseline
      present.
      • Item 1 — (a) VERIFIED + PINNED. Confirmed `5692fa9` IS an ancestor of HEAD
        (`git merge-base --is-ancestor 5692fa9 HEAD`); it derives split/merge from the Hungarian
        assignment rather than raw IoU ≥ PRESENCE_FLOOR. Measured the task's exact control —
        identical overlapping back/front rectangles (raw overlap IoU 0.25), `diff_target(svg, svg)`
        — matched=2, split=[], merged=[], missing=[], extra=[]: ZERO false splits/merges. Pinned by
        `tests/test_challenge_diff.py::test_r7g_identical_overlapping_rects_self_diff_reports_zero_false_splits`
        (asserts the overlap is non-trivial, >0.2, before asserting zero false splits, so the pin
        cannot pass vacuously), alongside the existing
        `::test_overlapping_objects_self_diff_has_no_split_or_merge`.
      • Item 2 — (b) DOCUMENTED LIMIT. Measured a short curved butt-cap control (width 4.04 px,
        same `_curve` fixture as the round/square controls): the butt cap emits strokes=1 with
        `stroke-linecap="round"` — identical to the round control — because `strokes._flat_terminal`
        keys on a straight cap front spanning ≥ 0.75·width. The butt cap's front IS confidently
        straight (SVD residual 0.017–0.032 at a tight front fraction) but its measurable flat span
        is only ~2.0–2.75 px, below the 0.75·width = 3.03 px floor, so it reads as round; the
        square cap (flat front a full half-width beyond the terminal) DOES clear the span floor and
        is correctly rejected (strokes=0, the existing `test_short_square_cap_curve_stays_filled`).
        Pinned as a limit, not fixed: catching the butt cap requires lowering that calibrated span
        gate or adding a butt-cap emission path, and all 24 shipped challenge targets use
        `stroke-linecap="round"` exclusively (measured: 90 round, 0 butt/square) — no shipped
        artwork benefits while relaxing the gate risks the short round-cap strokes it guards
        (GC-5). Pinned by
        `tests/test_exposed_curve_refit.py::test_short_butt_cap_curve_emits_a_round_cap_measured_limit`
        (mirror False/True).

- [x] 13. Real-artwork clean-line mode, opt-in `smooth` preset (R9).
  - [x] 13.1 Levers + preset: `upscale`, `edge_smooth`, `straighten`, `snap_max_px`,
        `rescue_detail`, `rescue_min_area`; `PRESETS["smooth"]`; `find_corners` dedup fix.
        Files: `config.py`, `imageio.py`, `bezier.py`, `stages/trace.py`, `stages/primitives.py`.
  - [x] 13.2 Fine-detail rescue (`stages/rescue.py`, wired in `pipeline.py`): per-pixel best-fit
        ink, fringe/boundary-blend exclusion, absorption of small same-colour fragments, and
        bridging of tapering gap tips back to their region (fixes the floating specks).
  - [x] 13.3 Bake-off `topology` metric, report-only (`bakeoff/score.py`, `bakeoff/runner.py`);
        `tests/test_topology_metric.py`.
  - [x] 13.4 Research Force logo fixture (`samples/fixtures/`) + `tests/test_research_force_logo.py`.
  - [x] 13.5 Smoothness metric for the bake-off (e.g. curvature sign changes or deviation from a
        locally fitted line/arc per unit outline length) so wobble is a number, not an eyeball;
        then measure `--preset smooth` on the synthetic corpus and the real corpus.
        **Done 2026-11-01 (a):** `score.smoothness(ren, ref)` sums each solid colour outline's
        absolute turning per unit length and reports the render's EXCESS over the reference
        (`wobble`); `smoothness = 1/(1+8*wobble)` in [0,1], 1 = as smooth as the source. One-sided
        (a crisp render of a wavy source is not penalised) and blend-aware (soft JPEG vs crisp
        render agree), reusing the topology palette/class-map machinery. Report-only: NOT in
        `DEFAULT_WEIGHTS`, so composites never move; carried through `fidelity()`, `summarise`
        and the HTML report label. New opt-in `plate-smooth` bake-off adapter runs PLATE under
        the `smooth` preset so smooth-vs-default is measurable side by side (not a default tool).
        Measured (seed-1 synthetic corpus, n=24): plate smoothness 0.9942 / wobble 0.00074,
        plate-smooth 0.9958 / wobble 0.00054 - smooth is marginally smoother, composite flat.
        Real corpus (samples/real, 14 imgs): plate 0.9854, plate-smooth 0.9843; the metric
        isolates `real_jpeg_artifacts` (0.80, genuine ringing wobble) from clean images (1.000),
        and surfaces that smooth adds minor contour detail on `real_soft_shadow_card` (0.975) -
        an honest measured observation, not hidden. Six pins in `tests/test_smoothness_metric.py`.
        Files: `bakeoff/score.py`, `bakeoff/runner.py`, `bakeoff/adapters.py`.
  - [x] 13.6 Narrow gaps near the logo's spine come out slightly short and wavy (mask blur +
        along-outline smoothing). **Ownership sub-fix done 2026-11-01:** `rescue.reconnect_tips`
        runs before ordering/tracing, assigns supported connected tips to one non-fragment
        same-colour region, rebuilds masks/rid, rejects multiple targets, gradient/nonopaque
        pixels, donor splits and whole foreign-object erasure. Isolated dots/periods remain
        in the fine-detail pass. Fifteen regressions in `tests/test_rescue.py`; full suite
        615 passed/7 xfailed, full/core sweep 70/78 and 36/36, all 48 default/control SVGs
        byte-identical. Logo 246 working pixels reassigned; spine overlay pixels 35 → 0;
        anchors 647 → 624, topology stays 0/0. Bake-off composite .846217 → .848961.
        Follow-up done: a unique opaque source-colour core can anchor a small gap; mark its
        region `detail_owner` to avoid later fragment absorption and use fine-detail tracing.
        Require eroded nearly-unmixed core area ≥ max(rescue_min_area, 6 source px² scaled).
        When only a tiny lobe would detach, recover a safe subset pixel by pixel, requiring
        target adjacency and connected four-neighbour donor pixels; keep articulation pixels.
        Substantial splits and whole foreign-object erasure remain rejected; no prior test/gate
        weakened. Seven new cases, full suite 622/7 xfail, same sweep/default outputs.
        Under-bar overlays 141 → 50, anchors 624 → 600, SSIM .976205 → .977287, topology 0/0.
        Bounded corner-reference follow-up: in clean mode, refine existing sharp outer corners
        using a matching unblurred contour, preserving existing flank-fit gates and bounding
        displacement. No new corners or mask edits. Fifteen independent endpoint/control tests;
        full 651/7 xfail, same sweep/defaults. Logo left/right tip y 805/806 → 807/806 (source
        807/807), SSIM .977287 → .977355, anchors/topology unchanged. Smooth bake-off effectively
        flat (.849341 → .849337); recovery unchanged, tiny fidelity tradeoff recorded.
        **Still open:** remaining 50 under-bar overlay pixels and right gap tip 1px short.
        Global spatial-blur reduction and blanket final-pass tip suppression each created two
        extra pieces and were rejected. Do not relax guards to force closure; `/tmp/plate-tips2/`
        holds both experiments and current source/before/after crop measurements.
        Investigate width-aware smoothing. Tried and rejected
        2026-11-01: clamping each smoothing move to 35 % of the gap across a fold — no gain on a
        synthetic noisy-wedge test (1/12 vs 0/12 pinched), so do not re-try it as-is.
        Historical cause: a bridged tip was a separate "fine detail" sliver over the covering
        shape. The implemented ownership fix removes this at supported spine joins; cases
        rejected by the safety checks still use the prior detail layer.
  - [x] 13.7 User check in Illustrator of `plate trace logo.jpeg --preset smooth --set upscale=2`.
        2026-11-01, rated "decent": cream (luma) edges smooth; pink and blue (colour) edges lumpy
        and slightly thin; blue bar's square end rounded; small knobs at bridged gap tips; dark
        slivers under the blue bar step where a tip is bridged. Recorded in STATUS.md.
  - [x] 13.8 JPEG colour-edge repair (2026-11-01): opt-in `jpeg_edges`, enabled by `smooth`,
        decoded-JPEG-only. Luma alone barely helped: edge dilation/chroma blur often puts the
        opposite flat seed beyond the old two-working-pixel neighbourhood. Chromatic pairs
        (RGB-difference channel span ≥25% of norm) with BT.601 luma separation ≥32 use seed
        radius `max(4, ceil(4*scale))`; RGB residuals still choose the pair, luma assigns its
        ≥50% owner, including the detail-core retry. Other pairs retain the old rules.
        Rejected widening every pair: it created a six-pixel dark pocket near (592, 829).
        Seventeen regressions (`tests/test_jpeg_edges.py`): independent pink/blue JPEG-q85 line/
        arc masks at 1×/2×, luma/chroma disagreement, low contrast, RGB pair choice, PNG identity,
        format-not-extension gating, override. Boundary errors 156–236 → 36–60 (1×),
        686–810 → 43–86 (2×). Logo SSIM .975168 → .976148, topology 0 extra/1 missing → 0/0.
        Same-corpus `smooth` bake-off .846317 → .846217 (flat, not a structural gain); weights
        unchanged. All 24 PLATE + 24 VTracer default SVGs byte-identical. Some bends/joins remain
        imperfect; 13.6 and 13.5 stay open. New output in `out/research-force/`; see STATUS for
        the final full-suite validation: 583 → 600 passed, 7 xfailed, no exclusions. No native
        Illustrator acceptance of this revision yet.
        **Terminal state 2026-11-01 (b) - DOCUMENTED LIMIT.** The ownership sub-fix above
        already cleared the floating spine knobs: the logo under `smooth` now measures topology
        0 extra / 0 missing, SSIM 0.977355, edge_f1 0.999358, anchors 348, and new-metric
        smoothness 0.9736 / wobble 0.0034. The residual (~50 under-bar overlay pixels, right gap
        tip ~1 px short) is sub-piece wobble that produces no extra/missing piece and that
        SSIM/edge-F1 cannot see. All three broad fixes were tried and rejected: global mask-blur
        reduction and blanket final-pass tip suppression each created two extra dark pieces; the
        35%% fold clamp showed no gain on the synthetic noisy-wedge test. Do NOT relax the
        topology/foreign-object guards to force closure. Pinned by
        `tests/test_research_force_logo.py::test_outline_smoothness_is_measured_and_bounded`
        (0.90 <= smoothness <= 1.0, wobble <= 0.01) plus the existing no-specks/periods pins.
      Acceptance: R9 (a) pins green; 13.5–13.7 each end in (a) or (b).
      Verify: `pytest -q tests/test_research_force_logo.py tests/test_topology_metric.py`; REGS holds.

- [x] 14. Update bake-off to include verifying some pixel accurate renderings of SVG back to PNG for verification and doing comparison? How can we check for good quality objects, lack of artifacts, smooth lines and curves where appropriate, etc?
      Done 2026-11-02 — terminal state (a) FIXED-with-number-and-test (+ (b) DOCUMENTED the
      already-present verification). Measured first: the bake-off already answers all three
      questions on every scored SVG — (1) pixel round-trip via `score.fidelity` (renders the SVG
      back to PNG with `raster.render_svg`, computes `ssim`/`mae`/`edge_f1`), (2) good objects /
      lack of artifacts via `topology` (`topo_extra` specks/splits/pinched tips, `topo_missing`
      drops/merges), (3) smooth lines/curves via `smoothness`/`wobble`; all three flow through
      `score_svg` → `summarise`. Measured gap found end-to-end: `smoothness` (one of the three
      asked-for signals) was computed and aggregated and had a `METRIC_LABEL`, but was SILENTLY
      DROPPED from `report.html` — the column loop keys off the normalised set and smoothness is
      report-only (not in `normalise`/`DEFAULT_WEIGHTS`), so it never became a column (topology
      survives only because it has a `normalise` branch). Measured: on the seed-1 n=4 corpus the
      HTML contained "Same pieces as source" but NOT "Outline smoothness". Fix (report-only,
      `bakeoff/runner.py::report_html` only): surface `smoothness` from the raw aggregate as an
      explicit `w=0` column beside topology. After: HTML now shows "Outline smoothness"; composites
      unchanged by construction (smoothness/topology absent from `DEFAULT_WEIGHTS`; `normalise`
      never emits smoothness) — plate composite 0.890921, smoothness(raw) 0.9986 vs vtracer
      0.9921 on the same corpus. No pipeline/emit/segment/gate code touched → 24 shipped SVGs
      byte-identical by construction (GC-4/GC-5 held). Pins (`tests/test_bakeoff.py`):
      `test_quality_signals_are_computed_by_score_svg` (score_svg yields all three families),
      `test_quality_signals_survive_the_full_bakeoff` (summarise carries them AND report.html
      shows all four quality columns; composite untouched), and
      `test_artifacts_and_wobble_are_measured_end_to_end` (score_svg catches a same-colour speck
      as topo_extra; a matching render scores smoothness 1.0/wobble 0.0). Per-metric behaviour
      stays pinned in `tests/test_topology_metric.py` + `tests/test_smoothness_metric.py`.
      `docs/BAKEOFF.md` updated (smoothness added to the measured-metrics table + a "Verification
      (Task 14)" section). REGS: full suite 699 passed / 7 xfailed / 0 xpassed (was 696/7/0,
      +3 pins); robustness full 70/78 & core 36/36 (failing set identical to baseline); VTracer
      baseline present.
      Files: `src/plate/bakeoff/runner.py`, `tests/test_bakeoff.py`, `docs/BAKEOFF.md`.

- [x] 15. Engine-complete audit + declare done (R8).
      Confirm every requirement R1–R7 and R9 (and each sub-item) is recorded in a terminal state
      (a) or (b) with its moving number or pin test named. Re-verify the full regression
      surface from a clean tree. Update `STATUS.md` and `README.md` to declare the classical
      engine complete, with an honest ceiling statement (count of FIXED vs DOCUMENTED LIMIT
      outcomes) and the OOS-1..5 boundary restated as the line where engine development
      stops.
      Files: `STATUS.md`, `README.md` (and `ROADMAP.md` to mark the P1 engine items closed
      or pinned).
      Acceptance: a written per-requirement terminal-state ledger; REGS green from a clean
      tree; README/STATUS state "engine complete" with the ceiling and boundary.
      Verify: `pytest -q` green (7 xfail / 0 xpass); `python -m plate.robustness` ≥ 70/78 &
      36/36; 24 shipped SVGs byte-identical; the ledger shows no item in limbo.

---

## Requirement → task traceability

- R1 → Tasks 1, 2
- R2 → Task 4 (+ Task 2 pins its clean-render residual)
- R3 → Task 7
- R4 → Task 3
- R5 → Task 8
- R6 → Tasks 5 (R6a), 6 (R6b)
- R7 → Tasks 9 (R7a/b/c), 10 (R7d/e/f), 11 (R7g)
- R8 → Task 12
- R9 → Task 13
