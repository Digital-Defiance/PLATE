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

- [ ] 1. JPEG robustness: format-keyed denoise trigger + correct the docs (R1).
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

- [ ] 2. Pin the JPEG clean-render floor as a documented limit (R1 state (b)).
      The 3 objects (scene15 ×2, scene23 ×1) recover 0 even on the clean render at every
      denoise level — a pre-existing rect/polygon completion limit (Task 4 class), not a
      JPEG bug. Add a pin asserting the clean-render floor so they are never re-chased as
      JPEG failures.
      Files: `tests/test_bakeoff.py` (or `tests/test_pipeline.py`).
      Acceptance (b): pin test asserts the measured clean-render non-recovery of those
      objects; references Task 4 as the owning class.
      Verify: `pytest -q` runs the new pin green; REGS holds.

- [ ] 3. Realistic gradient: smooth-single-ramp region detector (R4 state (a)).
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

- [ ] 4. Rect/polygon amodal completion by free-edge intersection (R2 state (a)).
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

- [ ] 5. ROOT inner-seal interrupted circular ring via the circle arm (R6a state (a)).
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

- [ ] 6. ROOT leaf-vein-11 thin-stroke split (R6b).
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

- [ ] 7. Same-colour touching objects: investigate a concavity splitter, else pin (R3).
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

- [ ] 8. Heavy sensor-noise / JPEG-artifact collapse: improve or pin (R5).
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

- [ ] 9. Long-tail quality batch A — completion & segmentation sub-items (R7a, R7b, R7c).
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

- [ ] 10. Long-tail quality batch B — alpha, scale, naming (R7d, R7e, R7f).
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

- [ ] 11. Long-tail quality batch C — open diagnostic items (R7g).
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

- [ ] 12. Engine-complete audit + declare done (R8).
      Confirm every requirement R1–R7 (and each sub-item) is recorded in a terminal state
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
