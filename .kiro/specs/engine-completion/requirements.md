# Requirements — PLATE Engine Completion

The definitive final plan to drive PLATE's classical conversion engine as close to
100% complete as honestly possible. This is the point after which product development
on the engine stops. The document is intentionally exhaustive: it enumerates every
known engine-quality gap recorded in `ROADMAP.md`, `STATUS.md`, `docs/BAKEOFF.md`,
`docs/REAL-CORPUS.md` and the five investigation reports under `.agents/tasks/`, and
assigns each one a terminal state.

Repo baseline for this spec: `main @ 425fa19`, clean. Suite **565 passed / 7 xfailed /
0 xpassed**; robustness sweep **70/78 full, 36/36 core**; **9/16 authored structural
targets pass**, 7 strict-xfail gaps; **24 shipped sample+challenge SVGs** and the plain
VTracer baseline are the regression control.

---

## Definition of Done / Completion Criteria

For a classical, CPU-only, deterministic engine, **"100% / complete"** means: every
known engine-quality gap in scope (the requirements below) is resolved to exactly one
of two terminal states.

- **State (a) — FIXED.** A measurable improvement where a real diagnostic number moves
  in the right direction — a `plate bakeoff` composite / `hidden_completion`, a
  robustness-sweep count, a corpus SSIM, or a `challenge_report` object diff — **and**
  the improvement is backed by a regression test that pins the new number, with:
  - no acceptance gate weakened (no segmentation `color_merge`, stroke width/area floor,
    `snap_tolerance`, `_occludes` 15° threshold, gradient gate, or completion tolerance
    relaxed to manufacture a pass);
  - no authored target/golden SVG edited to match PLATE output;
  - no geometry invented (the VLM must never touch geometry — it is cosmetic
    naming/grouping only);
  - the full regression surface (below) preserved.

- **State (b) — DOCUMENTED LIMIT.** Proof, with measured pixel evidence, that no
  classical cue exists to recover the feature — recovering it would require inventing a
  boundary that is absent from the raster, or an ML model (e.g. SAM). The limit is
  pinned by a test (typically raster-only, no renderer) so it cannot silently drift or
  be falsely "fixed" by weakening a gate. The five existing investigation reports and
  the existing `test_robustness.py` "below-the-floor" pins are the precedent and
  template for this state.

**The engine is DONE when every in-scope requirement below is in state (a) or (b).**
This refuses to leave any gap in limbo, while refusing to pretend a raster contains
information it does not. State (b) is a first-class, valid outcome of "complete" — an
honest limit is a resolution, not a failure.

Every acceptance criterion in this document is phrased in this two-state form: a FIXED
criterion names the number to move and the tracking test; a LIMIT criterion names the
measured pixel fact and the pin test.

---

## Global constraints (non-negotiable invariants)

These bind every requirement. A change that violates any of them is not a valid state-(a)
fix regardless of the number it moves.

- **GC-1 Classical, CPU-only, deterministic.** No GPU, no heavy ML dependency, no new
  core dependency. Core deps are `numpy`, `scipy`, `opencv`, `pillow`, `scikit-image`;
  `cairosvg`/`potracer` are optional extras only. Output must be deterministic.
- **GC-2 VLM is cosmetic.** The LM Studio (VLM) path may only produce names and groups.
  It must never influence geometry, segmentation, completion, or primitive fitting.
- **GC-3 Coordinate convention.** Internal coordinates are pixel-centre (pixel `i` at
  integer `i`); SVG output is `(x+0.5)/scale`, `scale = work_px/source_px`. No change may
  break this.
- **GC-4 Regression surface preserved.** Every fix must keep all of:
  - the 24 shipped sample + challenge `*.plate.svg` **byte-identical** on their PNG
    inputs, unless a fidelity delta is explicitly justified, measured, and recorded;
  - the plain-VTracer baseline (`src/plate/baseline.py`) present — never removed (it is
    the `plate bench` control);
  - the robustness sweep **≥ 70/78 full and 36/36 core** (`python -m plate.robustness`);
  - the **7 strict-xfail structural gaps** still xfail with **0 xpassed**, unless a
    target is genuinely and fully met and its `gap=` marker in `tests/challenges.py` is
    correctly removed;
  - full `pytest -q` green before and after.
- **GC-5 No gate weakening, no target editing, no invented geometry.** Restates the
  state-(a) prohibitions as a global rule: these are never acceptable, in any
  requirement.

---

## Functional requirements

Each requirement is an in-scope engine-quality gap with a two-state acceptance criterion.
Requirements are grounded in a measured source (cited inline). The implementation order
is in `tasks.md`.

### R1 — JPEG robustness (occlusion recovery on JPEG input)

Source: `.agents/tasks/jpeg-occlusion-investigation.md`, `docs/BAKEOFF.md`,
`STATUS.md` bake-off section.

The measured reality at the shipped default on the seed-1 bake-off corpus is **3/10**
occluded objects recovered on JPEG-q55 variants (`hidden_completion` ≈ 0.30), **not** the
0/10 reported in `docs/BAKEOFF.md` (that figure came from a different corpus config and
misattributes the cause to the T-junction test). Root cause: the auto-denoiser never
fires on JPEG-q55 (`noise_fraction` 0.011–0.026 < the 0.04 gate; `interior_noise_fraction`
≈ 0, below the 0.002 lever), so JPEG ringing displaces the segmentation boundary and the
free-point primitive fit in `complete.try_complete` exceeds its tolerance and returns
`None`. The occlusion/T-junction test is exonerated. Contour smoothing after tracing does
not work (the displacement is bias, not jitter).

**Acceptance criterion (two-state, mixed):**
- **(a) FIXED** for the JPEG-addressable objects: a **format-keyed** JPEG denoise trigger
  (fires only when the decoded source is JPEG) raises JPEG-variant aggregate
  `hidden_completion` to **≥ 0.4 (floor), target ≥ 0.6 (stretch)**, pinned by a test in
  `tests/test_bakeoff.py`. Because the trigger fires on **no PNG**, the 24 shipped SVGs
  are byte-identical **by construction** and the PNG robustness sweep is untouched — this
  is how GC-4 is satisfied for this requirement.
- **(b) DOCUMENTED LIMIT** for the residual: the 3 objects in scene15 (×2) and scene23
  (×1) that recover **0 even on the clean render at every denoise level** are a
  pre-existing rect/polygon completion limit (R2 class), not a JPEG bug. Pin them with a
  test asserting the clean-render floor so they are never re-chased as JPEG failures.
- This requirement must also **correct `docs/BAKEOFF.md`** (replace the 0/10 figure and
  the T-junction attribution with the measured 3/10 and the `try_complete` primitive-fit
  cause).

### R2 — Rect / polygon amodal completion parity with circles

Source: `docs/BAKEOFF.md` ("where PLATE loses"), `STATUS.md` bake-off section.

On the corpus, occluded completion lags circles: occluded **rect 4/11, polygon 3/10,
rrect 5/12** recovered whole. The engine fits free points only; it does not extend the
free edges of a partly-hidden rectilinear shape by line intersection.

**Acceptance criterion:**
- **(a) FIXED:** extend free straight edges by intersection (not only fit free points)
  in the completion path, raising overall `hidden_completion` toward **≥ 0.8** on the
  bake-off corpus, with the per-kind rect/polygon/rrect recovery counts measurably up,
  pinned by `tests/test_bakeoff.py`. GC-4 holds (24 SVGs byte-identical, sweep ≥ 70/78).
- **(b) DOCUMENTED LIMIT** for any residual occluded rect/polygon whose free edges are
  too short or too occluded to determine a unique intersection: pin with measured
  evidence (free-edge pixel extent vs the ambiguity threshold).

### R3 — Same-colour touching objects merge

Source: `docs/BAKEOFF.md`; `.agents/tasks/ember-separation-investigation.md`;
`.agents/tasks/root-storefront-investigation.md`;
`.agents/tasks/patch-poster-fragmentation-investigation.md`.

Colour-only segmentation cannot split touching regions of identical fill. This is the
recurring blocker behind the EMBER face merges, the ROOT tree/leaf merges, and the
storefront cream-awning/teal-leaf merges — each already proven, pixel by pixel, to be one
contiguous raster component with no separating cue. This is the requirement where the
engine most likely hits a hard classical ceiling.

**Acceptance criterion (two-state):**
- Investigate whether **any** classical cue (concavity / convexity-defect splitting of a
  single same-colour component) can split touching same-colour regions **without an ML
  model**.
  - If yes for a measurable class: **(a) FIXED** — a scoped splitter gated tightly enough
    that it splits only on a real concavity cue, moving a `challenge_report` / bake-off
    number, pinned by a regression test, with GC-4/GC-5 held (no false splits on
    legitimately single objects).
  - If no (the likely outcome for the authored abutting cases): **(b) DOCUMENTED LIMIT**
    — the EMBER / ROOT / storefront same-colour merges are **already pinned** by raster
    -contiguity tests (`test_ember_same_colour_face_features_are_one_raster_region` and
    the ROOT/storefront pins recommended in the investigation). Reference those pins;
    add any missing pin so the general same-colour-abutting limit is executable.
- This requirement must state explicitly that same-colour separation is the engine's most
  likely hard classical ceiling, so a LIMIT outcome here is expected and honest.

### R4 — Realistic gradient under-detection

Source: `.agents/tasks/gradient-detection-investigation.md`; `docs/REAL-CORPUS.md`.

Only 2/14 real-corpus images emit any gradient. `real_radial_orb` collapses to 1 object
(SSIM 0.83): the failure is upstream of the gradient gates — `segment._build_palette`'s
count-floor (`counts >= 0.0004·len(px)`) plus `color_merge=8.0` discard the smooth ramp
(29 617 unique colours, none repeating ≥ the floor) before `gradient.detect` ever sees a
band, so it receives zero candidates. The affine radial fitter itself already accepts the
orb's falloff when given its pixels. `real_sunset_gradient` is a different, correct
rejection (the `_monotone_ok` gate rightly rejects a 94-band blob that pools foreground
into the sky).

**Acceptance criterion (two-state):**
- **(a) FIXED** for the orb class: add a **smooth-single-ramp region detector** (in
  `segment()` / as a pre-pass to `gradient.detect`) that recognises a 4-connected opaque
  blob with high luma span, low local Lab gradient, and a high unique-colour mass, and
  feeds the **existing** `fit_radial_gradient` / `fit_linear_gradient` on its raw pixels,
  accepting only at residual ≤ `grad_max_residual`. Gate-preserving **by construction**:
  it only *adds* gradients where there are currently zero; flat art fails the smoothness
  test and still flows the unchanged band path. `real_radial_orb` → 1 radial-gradient
  disc with SSIM measurably above 0.83; `shaded`, `t3_linear_grad`, `t3_radial_grad`,
  `t4_grad_behind_circle`, `discrete_palette`, `twin_gradients`, `gradient_badge`
  unchanged. Pinned by `tests/test_gradient_bands.py` / a new gradient test.
- **(b) DOCUMENTED LIMIT** for `real_sunset_gradient`: the `_monotone_ok` gate correctly
  rejects a non-ramp blob (per-channel backstep 149–363 vs budget 15.3). Pin it as a
  documented limit (ramp-vs-foreground separation would be new geometry beyond scope).

### R5 — Heavy sensor-noise collapse

Source: `docs/REAL-CORPUS.md` (`real_sensor_noise_badge` SSIM 0.355, collapses to 5
objects; `real_jpeg_artifacts` 269 objects / SSIM 0.554).

Denoising copes with mild noise (the shipped sigma-2 `interior_noise` fix) but not heavy
noise; heavy JPEG blocking explodes segmentation into hundreds of junk objects.

**Acceptance criterion (two-state):**
- Investigate whether stronger or better-triggered auto-denoise (or a pre-segmentation
  artifact guard) measurably improves `real_sensor_noise_badge` SSIM and/or the
  `real_jpeg_artifacts` object count **without** regressing the 24 shipped SVGs or the
  sweep (GC-4).
  - If a gate-preserving trigger exists: **(a) FIXED** — a measured SSIM/object-count
    improvement pinned by a test (e.g. in `tests/test_real_corpus.py` or
    `tests/test_robustness.py`).
  - If not: **(b) DOCUMENTED LIMIT** — heavy noise destroys the flat-colour structure the
    classical palette relies on; pin the measured collapse with evidence that any trigger
    catching it also re-denoises clean shipped art (the `noise_fraction` overlap already
    measured in the JPEG investigation is the precedent).

### R6 — ROOT scoped structural work (not limits)

Source: `.agents/tasks/root-storefront-investigation.md`; `STATUS.md` structural audit.

Two ROOT items are explicitly **scoped new geometry, not information limits**:
- **R6a** the inner-seal interrupted **circular** ring (`#a9d1b5` r≈275, broken into 22
  components, 13% of circumference occluded, emitted as 6 `Beige_*` extras) — the
  compound-ring family owned by `order._merge_compound_siblings` (circle arm);
- **R6b** the leaf-vein-11 thin-stroke split (a continuous ~3.4 working-px cream vein
  emitted as two primitives) — a thin-curved-stroke tracing improvement in
  `stages/trace` / `stages/strokes`.

**Acceptance criterion (two-state):**
- **(a) FIXED:** R6a reunites the inner-seal ring via the circle arm reusing the existing
  shared-occluder + common-circle evidence (not a gate relaxation), moving the ROOT
  `challenge_report` extras/IoU numbers; R6b emits the vein as one stroke. Each pinned by
  its own regression test, GC-4 held (ROOT is strict-xfail and other 23 SVGs
  byte-identical). Note: closing these need not promote ROOT out of xfail (its dominant
  gap is the R3 same-colour limit); the criterion is the measured per-object improvement.
- **(b) DOCUMENTED LIMIT:** if either resists a tight-gated fit (e.g. the vein is below
  the stroke width/area floor and raising the floor regresses shipped art), pin it with
  measured evidence instead.

### R7 — Long-tail quality items (ROADMAP P1 engine items)

Source: `ROADMAP.md` "P1 — further robustness", "P1 — quality work", item 3 diagnostics,
and `STATUS.md`. Each sub-item is an in-scope gap with its own two-state criterion;
`tasks.md` may batch same-class sub-items into one task but every sub-item must reach a
terminal state.

- **R7a Thin-colour / hairline discovery** for fully-antialiased features with no stable
  pre-dilation colour core. (a) extend thin-colour admission while retaining palette
  budgets and the gradient-band veto, moving a robustness-sweep case; or (b) pin the
  measured floor (geometric sub-pixel limit).
- **R7b Thin occluded rectangles:** a narrow bar split by a perpendicular cover fails
  hidden-area validation because rasterized perimeter pixels dominate the inferred extra
  area. (a) correct the pixel-boundary evaluation in hidden-area validation (not the
  occlusion thresholds), moving a completion number; or (b) pin.
- **R7c Palette pressure > 64 colours + k-means path** in `stages/segment.py`. (a) add a
  labelled mosaic fixture and verify the k-means path recovers it; or (b) pin the measured
  limit. (This is currently untested territory, so the first task is to measure it.)
- **R7d Nonuniform / soft alpha + shadows:** extend flat-region opacity support to
  varying alpha and soft shadows, validated on both backgrounds. (a) measured SSIM/object
  improvement on a soft-alpha fixture; or (b) pin (feathered alpha has no hard boundary).
- **R7e Scale consistency:** same authored logo at 1×/2×/4×, and the `work_size=200`
  gradient-loss case (badge → 10 flat objects / 0 gradients at a reduced working size).
  (a) make object recovery and gradient detection scale-consistent (reconcile gradient
  detection at low `work_size`); or (b) pin the measured scale floor.
- **R7f Ring / compound-path semantic naming** ("Red ring") without changing the even-odd
  topology of `t3_ring`. (a) add the name while asserting topology unchanged; or (b) pin.
  (Naming only — GC-2 untouched since this is classical naming, not geometry.)
- **R7g Two small open diagnostic items under ROADMAP item 3:**
  - the false split/merge on legitimately overlapping objects (identical overlapping
    back/front rectangles reported as two splits). **Verify first** whether commit
    `5692fa9` at `425fa19` already fixed this (STATUS says the diagnostic was fixed); if
    fixed, (a) is a pin asserting `diff_target(svg, svg)` reports zero false splits; if
    not, fix then pin.
  - the short curved butt-cap control that emits round caps. (a) fit a butt cap where the
    probe expects one, pinned by a square/butt-cap test; or (b) pin the measured limit.

### R8 — Engine-complete audit (closure)

A final audit requirement, not a code change. The engine is declared done only when:
- every requirement R1–R7 (and each sub-item) is recorded in a terminal state (a) or (b),
  with the moving number or the pin test named;
- the full regression surface (GC-4) is re-verified green from a clean tree;
- `STATUS.md` and `README.md` are updated to declare the classical engine complete, with
  an honest ceiling statement (how many items ended FIXED vs DOCUMENTED LIMIT) and the
  out-of-scope boundary below restated as the line where engine development stops.

---

## Declared out of scope — the boundary where engine development stops

These items require external resources that cannot run in-repo or are not the classical
engine. They are **not** part of "engine done". Declaring them out of scope does **not**
mean they are worthless — only that "engine complete" is defined without them because they
cannot be driven to a verifiable terminal state in-repo.

- **OOS-1 Illustrator desktop validation beyond the automated suite.** The automated
  24-case / 636-check suite already covers import, layers, names, order, geometry,
  strokes, linear/radial fills, edits and `.ai` round trips (Illustrator 30.8.2).
  Remaining live-shape widgets, direct gradient-stop edits, 4× seam checks and broader AI
  versions require a Mac with Illustrator and manual interaction. **Reason:** needs the
  owner's hardware + human interaction; no in-repo verifiable terminal state.
- **OOS-2 Real LM Studio VLM naming/grouping quality and latency.** The connection path
  is already verified and the VLM is cosmetic (GC-2). Judging name/group quality and
  latency needs a live vision model and human judgement. **Reason:** needs a live model +
  human judgement; not the classical engine.
- **OOS-3 External-tool bake-off entries** (Illustrator Image Trace, Vectorizer.AI,
  Inkscape). **Reason:** need those apps + manual SVG exports; cannot run in-repo.
- **OOS-4 PLATE identity logo structural target.** The hidden back-P geometry is not
  uniquely recoverable from the raster (already documented); stays strict-xfail
  permanently. **Reason:** information-theoretically ambiguous; a permanent documented
  limit, listed here so it is not mistaken for open engine work.
- **OOS-5 Product / infrastructure, not engine quality:** the hosted service; the
  browser / Pyodide shell (its own `.kiro/specs/browser-web-page` spec); PyPI / CI /
  packaging chores; PDF/AI export; the SAM segmenter; `--open` / `--watch`. **Reason:**
  product/infra scope, separate milestones; not engine conversion quality.

---

## Already-DONE baseline context (not re-planned)

Captured so the spec is exhaustive without re-opening settled work. These are the
state-(a)/(b) outcomes already landed at or before `425fa19`:

- the 15 robustness stress misses: **7 FIXED, 8 pinned LIMITS** (sweep 63→70/78);
- ORBIT 44→38 (compound-ring defrag) + residual monogram/flat-patch pins;
- mission_patch 72→70 (ellipse compound-merge) + pinned planet/poster gradient limits;
- EMBER 4/7 strokes + face same-colour merges pinned;
- the per-object challenge diagnostics (`tests/challenge_diff.py` / `challenge_report.py`);
- the real-artwork corpus (`samples/real/`, `docs/REAL-CORPUS.md`);
- the objective bake-off harness (`plate corpus` + `plate bakeoff`, `docs/BAKEOFF.md`).

These define the regression surface the in-scope work must preserve.
