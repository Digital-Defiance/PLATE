# PLATE handover — 2026-10-31 (diagnostics fix + ORBIT defrag + EMBER limit)

Read `AGENTS.md`, then `STATUS.md`, then `ROADMAP.md`, then this file. This records
the immediate state at handover. Be skeptical of prose; verify with `pytest` and by
rendering.

## Latest checkpoint — structural-target work (supersedes the section below)

- On `main`, **five commits past `origin/main`, NOT pushed** (Jessica pushes herself):
  `09c2d0a` (preserved exposed-curve whisker fix + docs — the "uncommitted files" the
  section below asked to preserve are now committed), `5692fa9` (diagnostics split/merge
  fix), `1390e5b` (ORBIT defrag), `6895bfe` (gap-wording refresh), `02533d1` (EMBER
  limit pin + investigation report). Suite **555 passed / 7 xfailed / 0 xpassed**;
  sweep **70/78**, core **36/36**; **9/16** structural targets pass (none newly promoted).
- **Diagnostics are now trustworthy.** The split/merge classifier previously counted any
  IoU≥0.1 overlap as fragmentation (distinct overlapping objects miscounted as splits).
  Fixed in `tests/challenge_diff.py` (a split now excludes any actual that is another
  expected's 1:1 match). Use `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests
  .venv/bin/python -m challenge_report <name>` to rank the remaining targets.
- **ORBIT advanced 44→38 objects** via `order._merge_compound_siblings` (interrupted
  same-colour ring fragments, existing gates + tight circle-fit). 4 extras remain
  (monogram-O + flat patches), unmergeable without weakening a gate. Still xfail.
- **EMBER face same-colour merges are a measured information limit** (not a bug): cheeks+
  muzzle are one cream raster component, pupils fuse into their navy eye-masks, nose+mouth
  one navy component — authored sub-shapes exist only in the vector source, not the 1:1
  raster. Pinned by `test_ember_same_colour_face_features_are_one_raster_region`. Full
  evidence: `.agents/tasks/ember-separation-investigation.md`. Do NOT invent geometry or
  use the VLM for geometry; do NOT weaken a gate to force it.

**Do next:** re-measure ROOT / mission-patch / storefront / poster with the fixed
`challenge_report` diagnostic and pick the one with the most *addressable* (not
information-limit) gap. ROOT and the scenes share the same-colour-separation and
gradient-band blockers; apply the EMBER investigation discipline — measure the raster
signal first, fix only what has a real classical cue, pin the rest as limits. The 3 gold
EMBER laurel-stem extras are an optional ORBIT-style compound-merge avenue for a stroke
session. PLATE identity stays aspirational (hidden geometry unrecoverable). Everything in
the "Structural-target progress" section of STATUS.md is current.

## Prior checkpoint — audit and exposed-curve recovery (historical)

- **Safe wrap-up requested at 6% usage. Final suite: 549 passed/7 xfailed**, no
  warnings/skips, 165.32s (`/tmp/plate-oct31-final-tests.txt`). No jobs from this
  session remain running. No further feature work was started during wrap-up.
- **Uncommitted files to preserve:** `src/plate/stages/strokes.py`, new
  `tests/test_exposed_curve_refit.py`, `HANDOFF.md`, `STATUS.md`, `ROADMAP.md`,

- **Safe wrap-up requested at 6% usage. Final suite: 549 passed/7 xfailed**, no
  warnings/skips, 165.32s (`/tmp/plate-oct31-final-tests.txt`). No jobs from this
  session remain running. No further feature work was started during wrap-up.
- **Uncommitted files to preserve:** `src/plate/stages/strokes.py`, new
  `tests/test_exposed_curve_refit.py`, `HANDOFF.md`, `STATUS.md`, `ROADMAP.md`,
  `README.md`, `docs/ROBUSTNESS.md`. No PNGs, authored targets or goldens changed.
  HEAD remains `286c713`; no commit/push requested or performed.
- Audit began with a clean tree at `286c713`. Reproduced **541 passed/7 xfailed**,
  **70/78 full sweep**, **36/36 core**, and the seven strict structural gaps.
  Latest changes in this session are UNCOMMITTED; do not commit/push unless asked.
- Fixed EMBER's fourth whisker: a rejected skeleton-centreline fit can now retry
  against the original PNG's subpixel boundary as one bounded cubic. Only fully
  exposed curves rejected by the existing .95 IoU gate are eligible; a consistent
  source boundary, round caps and the unchanged footprint gates are required.
  Accepted existing fits are untouched; hidden completion is not expanded.
- **EMBER: 3→4 editable strokes, 455→447 anchors**, 51 objects unchanged. All four
  whiskers independently match their authored paths. White/dark SSIM improves
  **.9665/.9685→.9666/.9686**. The full shield/stem/merged-object contract stays
  xfail. The other **23 PLATE SVGs and all 24 VTracer SVGs are byte-identical**;
  full sweep remains 70/78 with identical per-case verdicts. Illustrator 30.8.2
  passes the changed SVG's import/edit/AI roundtrip workflow.
  Final evidence: `/tmp/plate-oct31-final-{samples,challenges,robustness}/`,
  `/tmp/plate-oct31-final-comparison.json`, `/tmp/plate-oct31-illustrator/report.json`.
- Eight new regressions cover mirrored opaque/transparent curves, square-cap
  protection, missing source evidence and all four EMBER whiskers. Four fail when
  the new retry is disabled; focused stroke suite **50 passed**. Final full-suite
  verification and artifact paths are recorded in STATUS.
- **Audit correction:** the eight remaining sweep failures are measured limits
  of current defaults/algorithms, not proven information-theoretic impossibilities.
  Low contrast is merged by `color_merge`; the 2px route passes with an explicit
  palette. Neither observation proves automatic recovery impossible. Preserve
  gates and the recorded repros; any future valid improvement must review the
  tests that currently assert failure. Do not call 70/78 complete recovery.
- **Diagnostic caveat:** `diff_target(svg, svg)` falsely labels two identical,
  overlapping rectangles as splits, because split detection treats any IoU≥.1
  overlap as fragmentation. Reproduce with a 100×100 back rectangle and a 50×50
  front rectangle at (20,20). Fix split/merge classification with overlapping
  self-comparison regressions before using those counts to rank scene fixes.
- A short curved **butt-cap** probe also emits round caps in the current accepted
  path; this predates the retry. Square-cap and existing taper/branch guards pass.
  Broader cap handling remains open; do not infer it from the new tests.

Next: fix misleading split diagnostics, then EMBER's laurel/stem separation or
ORBIT's compound emblem. Continue the real-art/colour/native queue below. Do not
reopen unchanged accepted fits merely to normalize output or lower quality gates.
Baseline command: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q`.
Object report from repo root:
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python -m challenge_report logo_ember_crest`.

## Previous campaign — seven stress fixes, eight measured limitations

Jessica's direction (2026-10-30): work the conversion-quality gaps; Homebrew/executable
delivery is a separate packaging track and v0.1.0 already shipped (tag at `55701bd`,
brew tap `Digital-Defiance/homebrew-tap`). An installable command does not establish
reconstruction quality. This supersedes older sections calling engine work deferred.

**Repository reconciliation:** HEAD is now on `main` six commits past the v0.1.0 tag
`55701bd`, NOT pushed (Jessica pushes herself). Full suite **541 passed / 7 xfailed /
0 xpassed**; robustness sweep **70/78** full, **36/36** core; **9/16** structural
targets pass. The six commits are: `c4a0c8e` mild-noise denoise, `76cbc46` challenge
diff, `fdf90d1` half-size markers, `083c9a7` blur-0.7, `0d1a73b` hairline pins, plus
the doc commit for this handoff. All reviewed, green, and gate-preserving.

**DONE this phase (do not redo):**

- **Seven of 15 stress misses fixed; eight still fail** with default settings.
  Their reproductions are pinned by tests. Sweep 63/78 → 70/78. The earlier
  "information-theoretic" classification was too strong; see the audit above.
  Do not weaken gates to force a pass.
- **Per-object challenge diagnostics** — `tests/challenge_diff.py` (non-raising
  `diff_target` → matched/missing/extra/split/merged + per-object silhouette IoU,
  topology, primitive/fill, stroke-vs-fill, paint order) and `tests/challenge_report.py`
  (`python -m challenge_report <name>|--all`). `assert_target` attaches the diff to
  `TargetMismatch`. Use this to measure incremental progress on the targets below.

**Do these next, in order:**

1. **Close the seven structural targets, one measurable issue at a time**, using the
   new per-object diff to see exactly what is missing/extra/split rather than a bare
   count mismatch. The table below is the per-target gap. ORBIT and EMBER are closest.
   The recurring blockers are same-colour organic separation, complex-scene gradient
   bands, and compound-emblem fragmentation — all genuine engine work in
   `stages/{segment,gradient,complete,strokes,order}.py`. PLATE identity's hidden back-P
   geometry is NOT uniquely recoverable from the raster; document the information limit
   rather than inventing geometry, and leave it xfail.
2. **Broaden empirical coverage.** Add a redistributable 10–20-image real-artwork
   corpus with per-image results. Expand independent fixtures to extreme aspect
   ratios, overlapping gradients, soft/varying alpha/shadows, branching lines,
   caps/joins/dashes/widths and lettering. Add per-case exception collection to the
   robustness runner before malformed-input/fuzzing expansion.
3. **Close colour/input and native-editing gaps.** Implement/test ICC/gamma-aware
   sRGB normalization and explicit pre-decode resource limits; expand damaged-file
   tests. Extend Illustrator automation to direct gradient-stop edits, isolated
   hidden shapes/compound holes, live-shape controls and 4× seam checks. Broader
   Illustrator-version validation remains open.

| Independent structural target | Current gap to work |
| --- | --- |
| Mission patch | 72 objects vs 45; fragmented planet/gradient bands, missing linear hull ramp, completion and 8/10 strokes |
| Storefront | 73 vs 64; merged/split repeated details, curves/corners and 3/4 strokes |
| Event poster | 83 vs 44; crossing type/ribbon fragments underlying objects; 0/6 strokes |
| EMBER | 51/51 counts conceal shield IoU .8383; now 4/7 strokes (all four whiskers), stems and merged mouth remain open |
| ORBIT | 44 vs 34; compound emblem/ambiguous ramp fragments; radial core and all 7 strokes already pass |
| ROOT | 51 vs 56; touching same-colour leaves/rings/branches and only 9/32 strokes |
| PLATE identity | 11/11 counts conceal rear-P geometry mismatch and 1/3 registration strokes; exact hidden P geometry is not uniquely observable, so document that limit rather than invent evidence |

**Acceptance for each change:** full pytest before/after; a regression for each
bug; before/after core + full robustness reports; `plate bench samples` and
`plate bench samples/challenges` retaining VTracer; visual inspection on light/dark
backgrounds; applicable per-object/topology/stroke checks and native checks for
affected SVG features. Use STATUS's latest full test count, **36/36 core**,
**70/78 full sweep**, **9/16 structural targets**. Report case-level improvements
and regressions. Do not lower gates, replace authored targets with traced output,
or count aggregate SSIM/Illustrator interchange as reconstruction success.

Hosted-service implementation (uploads/queue/isolated workers, accounts/quotas,
Stripe, deployment/CI/monitoring) remains unbuilt and separately tracked in
ROADMAP. Packaging and service work do not close this quality queue. Keep STATUS,
ROADMAP and this handoff current as the scope expands.

## Authorized expanded scope — explicit owner instruction

Jessica authorizes expanding the quality/coverage quest beyond the initial PNG
matrix as useful. Every expansion and outstanding item must be recorded in both
ROADMAP and this handoff. Do not interpret the earlier hosted-service pivot as
prohibiting further engine fixes or coverage work. At the usage limit she asked
for this verified wrap-up first; the next session can resume the expanded quest.

**Already expanded and implemented:** independent PNG encoding/alpha/precision
coverage (111 cases and loader fixes), native Illustrator automation/real layers,
and an independent scale/rotation/noise/blur/contrast/detail sweep (78 scenarios,
56 regression tests and isolated-marker palette recovery). The checkpoint below
records exact measurements, files and remaining failures.

**Expanded work still planned, not completed:**

- Seven stress fixes have landed; eight default-config failures remain documented
  limits. Investigate further only with independent evidence and unchanged gates.
- Broaden deterministic sweeps to aspect-ratio extremes, overlapping/completed
  shapes, gradients, soft/varying alpha, branching/same-colour decomposition,
  stroke caps/joins/dashes/widths and lettering. Keep independent object/topology/
  detail contracts; do not declare success from aggregate SSIM or matching counts.
- Gather a representative redistributable real-artwork corpus and record failures
  by artwork family. Add richer ICC/gamma colour handling, malformed/chunk/fuzzing
  inputs, per-case exception reporting and pre-decode memory/time/size limits.
- Extend native Illustrator checks to gradient-stop edits, isolated hidden shapes
  and compound holes, live-shape controls, 4× seams and broader versions/inputs.
- Hosted upload/queue/isolated workers, accounts/quotas/ownership/expiry, Stripe,
  deployment/CI/monitoring remain a separate unimplemented product milestone.

These are authorization and queued scope, not claims that the features exist.
The seven authored structural gaps and eight default-config stress misses remain open. Do not
promise universal PNG recovery, original fonts/live text or unknowable hidden
authoring geometry. Sigma-2 noise and half-size/blur-.7 markers are fixed. Resume
the structural/diagnostic queue above with before/after benches.

## Robustness checkpoint — verification retained; work is now committed

- **519 passed / 7 xfailed**, no warnings/skips. Final full log
  `/tmp/plate-sweeps-final-tests.txt` (134.87s); baseline 463/7. New robustness tests:
  **56**; focused robustness + segmentation **77 pass**. Changed Python files
  pass Ruff; `git diff --check` clean. No failing ordinary test is being left behind.
- **Original checkpoint HEAD was `4f8e8d1`; work is now committed through
  `649343a` as recorded above.** Preserve the previous PNG phase
  (`imageio.py`, `tests/png_fixtures.py`, `tests/test_png_matrix.py`, PNG coverage
  docs) AND this phase (`segment.py`, new `plate/robustness.py`,
  `tests/test_robustness.py`, `docs/ROBUSTNESS.md`, updated README/ROADMAP/STATUS).
  The original continuation stopped before committing; a later session committed
  it. No asset/target/golden changes. Jessica permits scope expansion as useful,
  provided additions and remaining items are tracked in ROADMAP and this handoff.
  Her requested safe wrap-up at 8% usage was completed; resume using the queue above.
- New independent robustness runner:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m plate.robustness --output NEW_DIRECTORY`.
  All 78 cases intentionally include stress failures; **exit 1 is expected**.
  Add `--suite core` for the supported 36-case subset. Output directories must be
  new. Each case saves PNG, authored target SVG, traced SVG and JSON; aggregate
  `report.json`/`index.html` expose every missing object and failed contract.
- Two simple authored scenes cover transparent marks (disc/rectangle/compound
  ring/route/tiny marker) and opaque panels. Scales .25/.5/1/2/4, quarter/arbitrary
  rotations, work-size reduction, fixed-seed noise, premultiplied blur, contrast
  and 1/2px hairlines. Match objects by silhouette, not names; evaluate in
  authored-base pixels, with ≥.90 detail recall, topology, colour, primitive/anchor
  and stroke contracts plus clean-reference SSIM ≥.97 on both backgrounds.
  Observed-noisy-PNG SSIM is diagnostic, not a demand to reproduce noise.
- Found/fixed missing unique-colour marker: `segment.py` admits a stable eroded
  near-opaque interior from a separate alpha component lacking flat seeds. Alpha
  ≥245, ≥2 interior samples, 90th-percentile RGB deviation ≤3; keep explicit
  palettes, palette budget and speckle thresholds authoritative. This repairs
  palette discovery, not arbitrary amodal/geometry inference. Source ownership
  survives at native/half size, but half-size 12-pixel dots still snap rectangular
  and miss the independent circle-coverage gate. Do not lower that gate.
- **Core 24→36/36; full 48→63/78**. Fifteen stress misses remain red: quarter-size
  route/marker loss (4 rotations); half-size marker recall ~.846 (4); marker blur
  .7/1.2px (2); opaque sigma-2 noise seeds 17/204 (2); 1/16 contrast merging all
  foreground despite global SSIM >.98 (1); 1/2px routes (2). These are NOT the
  existing seven structural xfails and are not hidden in pytest passes. Tests gate
  the core subset and deliberately broken matcher examples. Full report remains red.
- Evidence `/tmp/plate-robustness-{before,final}/` and
  `/tmp/plate-sweeps-{before,after}-{samples,challenges}/`. All **24 PLATE and 24
  VTracer benchmark SVGs byte-identical**; compare JSON
  `/tmp/plate-sweeps-benchmark-comparison.json`. Visual review
  `plate-robustness-marker-review.png` in this chat's visualization directory.
  Native-marker and reduced-work-size marker SVGs pass Illustrator checks at
  `/tmp/plate-sweeps-illustrator/`. No pending dialog/script is known.
- **Recommended next investigation:** mild-noise detection: sigma-2 opaque inputs
  lose clean primitives/anchors while stronger noise can trigger denoising and do
  better. Then tiny-marker alpha-aware fitting and thin-route preservation. Expand
  beyond these two disjoint scenes to aspect ratios, gradients/occlusion and real
  art. Add per-case exception recording before fuzzing (current runner stops on
  unexpected exceptions), native gradient edits/isolated holes/4× seams and richer
  ICC/gamma handling. Service remains design-only; original seven geometry gaps
  remain open. See `docs/ROBUSTNESS.md` and ROADMAP for the complete scope.

## Previous checkpoint — PNG matrix and transparent colour keys fixed

- Jessica asked to continue buildout/coverage. This continuation adds **111 PNG
  cases** and loader fixes; it is **uncommitted**, on HEAD `4f8e8d1` at the last
  check. No commit/push requested for this continuation. Preserve prior native-layer
  and audit work, already committed at `4f8e8d1`.
- New `tests/png_fixtures.py` independently encodes raw samples into PNG bytes,
  without Pillow/OpenCV encoders. `tests/test_png_matrix.py` tests all 15 legal
  type/depth combinations in ordinary/Adam7 form, filters 0–4, tRNS/palette alpha,
  packed/tiny/interlace/IDAT cases, source-sample exactness and equivalent traces.
  Fifteen encodings of an independent transparent cutout must match one reference
  SVG exactly. Full list and policy in `docs/PNG-COVERAGE.md`.
- Initial 80 cases: **21 failed before the fix**. `imageio.py` now expands gray
  2/4-bit tRNS keys into the same range as Pillow's pixels; keeps full PNG 16-bit
  channels using existing OpenCV `IMREAD_UNCHANGED`, compares exact transparency
  before quantization, then normalizes all channels/alpha with nearest `sample/257`.
  Grayscale tRNS needs a manual full-sample mask because OpenCV may omit alpha.
  Preserve metadata for a single EXIF transpose; catch full-depth decoder failures
  as readable input errors. No new core dependencies or geometry changes.
- Remaining cases cover PNG EXIF, ICC/gamma sample policy, hidden transparent RGB
  with/without downsampling, APNG default/first image, invalid formats and damaged
  streams/decoder failures. **ICC/gamma transformations are still not implemented**;
  samples are traced as encoded RGB, implicitly SVG sRGB, so non-sRGB artwork may
  differ from colour-managed viewers. APNG animation is outside static SVG scope.
  ICC profile fixture generation skips if optional Pillow LittleCMS is absent;
  it is present here, so the current run has no skips.
- Full suite **463 passed/7 xfailed, no warnings**, baseline 352/7. Final log
  `/tmp/plate-png-matrix-final-tests.txt`; initial red log
  `/tmp/plate-png-matrix-red-tests.txt`. Focused input/audit/matrix run: 152 passed
  before the last decoder-exception test; full final suite includes that test.
  New/changed Python files pass Ruff. Targets, goldens and source assets unchanged.
- Both benches run before/after: **all 24 PLATE and 24 VTracer SVGs byte-identical**.
  `/tmp/plate-png-{before,after}-{samples,challenges}/` and
  `/tmp/plate-png-benchmark-comparison.json`. Four independent transparency repros
  improve to **SSIM 1.0 on white and dark**; artifacts/HTML/metrics at
  `/tmp/plate-png-matrix-review/`. Visually checked `plate-png-transparency-review.png`
  in this chat's visualization directory. All four new Illustrator import/edit/AI
  round trips pass at `/tmp/plate-png-matrix-illustrator/`; original 636 native
  checks remain applicable to the unchanged original 24 SVGs.
- Next coverage step: deterministic scale/rotation/noise/blur/low-contrast sweeps
  with per-object geometry/topology/detail checks, not just global SSIM; retain
  expected limits rather than weakening targets. Also gather the real-artwork
  corpus. Wider ICC/gamma handling, malformed-chunk/fuzzing/decode limits, soft
  alpha/shadows and native gradient/hidden-object/4× checks remain in ROADMAP.
  The seven hard structural gaps and service design-only status are unchanged.

## Previous checkpoint — native layers pass; PNG reconstruction is not universal

- Jessica requested this checkpoint be committed after updating README/ROADMAP/
  HANDOFF. Use `git log -1` for the resulting commit. Engine base was `dceaae2`;
  separate Homebrew/release commits `35793cf` and `e0d525e` are preserved. No push
  requested. This checkpoint includes the previously pending dark-16-bit loader fix, its 19
  regressions, audit docs, new Illustrator runner/tests and reviewed control goldens.
- **Do not claim every meaningful PNG is covered.** README's coverage table is
  the public boundary: graphic artwork is the target; photographic/painterly
  reconstruction, original live text/fonts and unknowable hidden authoring data
  are not launch guarantees. Decode success, render fidelity and editable-object
  correctness are distinct. **9/16 desired-SVG contracts pass, 7 remain strict
  xfails**, despite all fidelity floors passing. The 24 Illustrator successes
  below establish SVG interchange, not full source reconstruction.
- Fixed native Illustrator layers directly in SVG: Adobe namespace
  `http://ns.adobe.com/AdobeIllustrator/10.0/`, `i:layer="yes"` on top-level groups
  alongside Inkscape markers. Standalone root objects get named `… layer` wrappers;
  nested semantic groups stay groups. Wrapper IDs are minted after every original
  object/gradient ID, preserving IDs/refs and geometry. No native postprocessing or
  core Illustrator dependency. `illustrator_layers=false` stays ungrouped.
- **Illustrator 30.8.2: 24/24 workflows, 636/636 checks pass** including all complex
  scenes/logos. Exact real layer order, membership, nested groups and drawable
  order are checked. Names, geometry, strokes/linear-radial gradients, edits and
  AI save/reopen pass. Minimum interchange SSIM .9928; ORBIT .9960, 34 real layers,
  44 objects/345 anchors/7 strokes/1 gradient. Face has 2 layers. Ordinary pytest
  never launches Illustrator. Run from the repo root:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m plate.illustrator --output NEW_DIRECTORY samples/*.png samples/challenges/*.png`.
- **352 passed/7 xfailed, no warnings** in the final full suite; baseline 341/7.
  Added 11 regressions for layer serialization, ID collisions, hierarchy/membership
  and hidden object/layer order; 26 headless Illustrator/layer tests total. Changed
  Python files pass Ruff. Full log `/tmp/plate-illustrator-layers-final-clean-tests.txt`.
- Both benches run before/after; all 24 have identical original IDs, geometry,
  gradients and paint hierarchy after stripping new layer markup, and identical
  white/dark render pixels. VTracer byte-identical. All 15 control goldens were
  independently reviewed for identical trees/pixels before their layer-only refresh;
  authored target SVGs and source PNGs remain untouched. Visual review:
  `plate-illustrator-layer-review.png` in this chat's visualization directory.
- Evidence: `/tmp/plate-illustrator-layers-all/` (JSON/PNGs/AI),
  `/tmp/plate-layers-{before,after}-{samples,challenges}/`,
  `/tmp/plate-layer-render-comparison.json`, `/tmp/plate-layer-controls-review.json`,
  `/tmp/plate-layer-import-probe/`. Fresh post-fix document-preservation probe also
  passes (`/tmp/plate-illustrator-layer-preservation/preservation.json`); unsaved
  state/marker geometry/colour and active document/UI setting unchanged, cleanup
  leaves zero documents. No pending dialog or script is known. An earlier nested
  `$.evalFile` wrapper timed out without a visible dialog; its cause is unidentified.
- Next quality work: representative real-artwork corpus, PNG bit-depth/palette/
  alpha/interlacing/ICC-gamma matrix, scale/noise/low-contrast/detail sweeps, soft
  alpha/shadows, harder gradients/strokes/decomposition, and direct gradient edits,
  isolated hidden-object/hole and 4× seam checks. ROADMAP lists concrete gates.
  Service remains design-only; its existing priority is not silently reversed by
  this coverage audit. Hard geometry research remains deferred.

## Initial Illustrator automation — historical, before native-layer fix

- New uncommitted `src/plate/illustrator.py`, `_illustrator_check.jsx` and
  `tests/test_illustrator.py`. Run from the repo root on macOS:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m plate.illustrator --output NEW_DIRECTORY`.
  Requires Illustrator/Automation permission. Headless pytest never launches it.
  It copies/generates SVGs, inspects native objects, exports PNGs, saves/reopens AI,
  and tests translate/recolour/stroke-width edits against independent SVG references.
- Illustrator **30.8.2**: **8/8 default workflows complete, 197/200 checks pass**.
  Five fully pass; face/gradient badge/ORBIT fail only actual-layer mapping.
  All imports use one real `Layer 1`, retaining named nested `GroupItem`s.
  Native names/hierarchy, geometry, strokes and gradient fills survive AI reopen;
  exported pixels are identical before/after saving. Render SSIM minimum .9928;
  ORBIT .9960, 44 vector objects/345 anchors/7 strokes/1 gradient. These are SVG
  interchange checks; seven desired tracing contracts remain xfailed.
- Evidence `/tmp/plate-illustrator-verified/`: report/illustrator/manifest JSONs,
  per-case PNGs, edited SVG references and `roundtrip.ai`. Full checklist and
  limits in `docs/illustrator-checklist.md`; README/AGENTS/ROADMAP corrected.
  Final suite **341 passed/7 xfailed**, Ruff clean for new Python files.
  Logs `/tmp/plate-illustrator-resume-before.txt` and
  `/tmp/plate-illustrator-final-tests.txt`. No converter changes.
- **Existing-document preservation now verified:** a separate-call probe at
  `/tmp/plate-illustrator-preservation/` created a copied AI with an unsaved marker,
  ran the normal checker, then compared native observations. Active document,
  dirty flag, object count, marker anchors/bounds/RGB and interaction setting all
  matched exactly. Only the test copy closed; owned-sentinel cleanup succeeded
  and zero documents remained. Evidence: `preservation.json`, `before.txt`,
  `after.txt`, probe scripts and `check/report.json` (only the known layer failure).
  An earlier nested `$.evalFile` sentinel wrapper completed its inner checks but
  timed out; Jessica confirmed no visible dialog. Cause remains unidentified.
  Both the default run and separate-call preservation test work normally. Do not
  blindly retry a timed-out script or kill Illustrator; timeout does not cancel it.
  The earlier host-array issue is fixed by explicit array copying; avoid conditional
  `[hostObject]` expressions in ExtendScript. JSON is unavailable there, so the
  template includes a small serializer.
- Next desktop work: layer mapping/native AI
  promotion; live-shape widgets, gradient-stop edits, high-zoom seams and wider
  input coverage remain. Service code is still design-only. Preserve all prior
  uncommitted loader/audit work below. No commit/push requested or performed.

## Current checkpoint — both audit bugs fixed

HEAD is now `dceaae2` (version 0.1.0). This separate release commit landed during
verification and includes the batch fix, packaging and output-error changes. The
loader fix, new regression file and audit docs remain uncommitted:

- `imageio.py`: declared 16-bit normalization, even for values ≤255; retain PNG
  depth before EXIF copy for legacy mode-I decoding. General integer/float policy
  unchanged. `uint16` 200 now maps to 8-bit 1 rather than 200.
- `cli.py`: complete valid batch files, print counts, return 1 on any failure;
  retain 0 for all-success and 2 for empty input. The existing output-error patch
  was preserved. New tests are in `tests/test_audit_bugs.py` (19 cases).
- **326 passed/7 xfailed**, baseline 307/7; focused input/audit tests 42 passed.
  Both benches rendered; **all 24 PLATE SVGs are byte-identical** to the audit.
  Dark-16 reference MAE **199→0**, SSIM **.0102→1.0**. Evidence:
  `/tmp/plate-bugfix-final-tests.txt`, `/tmp/plate-bugfix-{samples,challenges}`,
  `/tmp/plate-bugfix-review/metrics.json`. Visuals: `plate-dark16-fix.png` and
  `plate-bugfix-original-samples.png` in this chat's visualization directory.
- Loader/new tests pass Ruff; the CLI still has its pre-existing S110 finding.
  No commit/push made by this bugfix session. Preserve the remaining uncommitted work.

[docs/AUDIT.md](docs/AUDIT.md) retains the original findings and their resolution.
The service remains design-only; follow SERVICE.md with resource-bounded workers,
upload/result isolation, accounts/quotas, Stripe and deployment/CI. Illustrator
and real-corpus validation remain open. Nine of 16 structural targets pass; all
16 fidelity floors pass. ROOT has 9/32 strokes, EMBER 3/7, ORBIT 7/7. Hard geometry
gaps remain deferred. Historical checkpoints below retain older measurements.

## ⟹ DIRECTION CHANGE (session 25): pivot from engine gaps to the hosted service

Jessica has decided PLATE's next phase is a **donation-supported hosted PNG→SVG service**
for her 501(c)(3), NOT continuing to close the remaining synthetic logo/scene gaps. The
engine is considered **done-enough**: it produces excellent layered SVGs across the tested fixture suite,
and the remaining 7 strict-xfail gaps are the hard tail (same-colour organic separation,
complex-scene gradients) with diminishing returns for the actual goal.

- **The agreed service design is in `docs/SERVICE.md`.** Read it before doing service work.
  Summary: classical converter as the service; free tier 7 conversions/day (full quality,
  no watermark) + a no-account demo; recurring-donation supporter tier (via Stripe, already
  set up) removes the daily limit; AI naming is a LATER supporter perk (carries compute
  cost), not in the launch. Hosting: a managed container platform (Render/Fly) recommended.
  Accounts: magic-link/OAuth. The engine stays the open-source MIT CPU-only core; the
  service is a SEPARATE layer.
- **Compliance boundary:** the donation-vs-subscription framing and receipt wording need the
  nonprofit's tax/legal advisor's sign-off — build it framing-agnostic (see SERVICE.md).
- The engine gap work below (ORBIT/ROOT/EMBER/complex scenes) is NOT abandoned, just
  deprioritised. If anyone resumes it, the hard common blocker is same-colour separation.
- Investigation note (session 25): EMBER's gap is NOT one fix — independent causes are
  shield-field silhouette (0.84 IoU), gold stems merged with same-colour laurel leaves, and
  2 whiskers + mouth fitting to only ~0.88 IoU (< the 0.95 stroke gate). Do not nudge the
  0.95 IoU gate to grab a marginal whisker — it protects stroke acceptance across the whole
  suite; the real issue there is curve-fit quality on short sharply-curved strokes.

## Historical state at session-24 handover

- **HEAD is `3ed2bd1`** (`feat: add PLATE identity as an independent tracing
  challenge`), the session-24 branding/fixture/tests/handover commit. Working tree
  CLEAN; everything committed and GPG-signed.
- **`main` is PUSHED and up to date with `origin/main` at `3ed2bd1`.** (Earlier
  handovers said "no push"; the repo has since been pushed.) Continue to commit/push
  only when Jessica asks.
- Session 23 recovery is committed as **`2aa79bc`** (base `7300232`).
- Sessions 20–21 are committed as **`71f6740`**. Session 22's crossed-curve source
  and tests are committed as **`3c0a8e1`**; session-22 docs are `7300232`.
- Recent lineage: `a2579f0` (session-19 docs) ← `c5762b2` (session-19 tests) ←
  `7f0210c` (session-19 feat: stroked loops across crossings) ← `ea4330e` (docs) ←
  `632bb1c` (session 18, mixed-content holes) ← `ebf8762` (session 17) ←
  `a56c13e` (sessions 14–16) ← `0a0fddc`.
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
   circle and seven strokes pass together. Keep all seven full gaps active — session
   24 added `logo_plate` (the PLATE brand fixture) as a 7th strict xfail; it is an
   ASPIRATIONAL target (its back-P hidden compound geometry is not uniquely
   recoverable from the raster), so do not expect to promote it.
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

## Remaining 7 gaps (all strict xfail; promote only when the independent target is met)

Current numbers in `STATUS.md`'s top table. In rough ROADMAP P1 order:

| Challenge | Gap |
| --- | --- |
| `complex_mission_patch` | 72 objects / 2 radial fragments / 8 strokes; target 45 with one radial planet + one linear hull, craters preserved |
| `complex_event_poster` | 83 objects; crossing lettering/ribbon/lines fragment underlying shapes |
| `complex_storefront` | 73 objects / 3 strokes; target 64, repeated windows/awning/lettering merge or fragment |
| `logo_ember_crest` | 51 objects (count matches) but shield full-silhouette IoU 0.8383; 4/7 strokes |
| `logo_orbit_wordmark` | 44 objects vs 34; full radial core and all 7/7 strokes recovered; compound emblem and ambiguous patches remain |
| `logo_root_seal` | 51 vs 56 objects; touching same-colour organics merge; 9/32 strokes, outer circle passes independently |
| `logo_plate` | PLATE brand fixture (session 24); 11/11 objects but back-P silhouette IoU 0.1387 (visible strips, hidden compound geometry not uniquely recoverable from raster); registration strokes merge, 1/3 strokes. Aspirational authoring target. |

The next stroke work includes ROOT's touching ring/leaves and EMBER's missing
strokes; EMBER/ORBIT/ROOT need 7/7/32 strokes and recover 4/7/9. The panel's 27 strokes are complete.
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
