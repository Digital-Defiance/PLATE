# Scale, rotation and degradation sweep

This diagnostic measures independent artwork contracts, not just whole-image
similarity. It currently covers two small authored scenes: five disjoint
transparent marks (disc, rectangle, compound ring, 4px route, 4px-radius marker),
and an opaque background with three geometric objects. Targets live in
`src/plate/robustness.py`; none are copied from PLATE output.

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m plate.robustness \
  --output /tmp/plate-robustness-NEW
# Only the supported regression subset:
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m plate.robustness \
  --suite core --output /tmp/plate-robustness-core-NEW
```

Existing directories are refused. Each case saves its `input.png`, intended
`target.svg`, `actual.svg` and `report.json`; the root contains an aggregate JSON
report and visual `index.html`. Exit 0 means all selected contracts pass; exit 1
means measured misses. The full sweep deliberately includes stress cases and
currently exits 1. Unexpected exceptions currently stop the runner; add per-case
exception recording before using it as a fuzzing harness.

## Independent contracts

- Inputs use 4× supersampling/Lanczos. Uniform scale and rotation transform the
  original SVG into a canvas that retains the whole artwork, without clipping.
  Noise uses fixed NumPy seeds 17/204, blur uses premultiplied alpha, and contrast
  changes the authored colours before rasterization. Input pixels are reproducible;
  this is not a claim of determinism for every backend/pipeline code path.
- Complete objects match by silhouette assignment, independently of output names.
  Masks are evaluated in **authored base pixels**, normalizing source scale.
  Require IoU ≥.96 **or** XOR/perimeter boundary error ≤.75px, plus ≥90% detail
  coverage, exact connected-component/hole topology and colour delta-E ≤8.
- Primitive/anchor limits and editable-route/width checks accompany geometry.
  A marker with fewer than 30 source pixels need not be a native circle, but its
  coverage/topology contract still applies. Layer grouping is tested separately
  by the Illustrator checker.
- Whole-image SSIM against the clean intended target must reach .97 on white and
  dark. SSIM against the degraded observed PNG is also reported, diagnostically;
  avoiding noise is not penalized as a failure to reproduce the original noise.
- Regression tests deliberately delete a tiny marker, fill a ring hole or replace
  a stroke with a filled path, showing that similar-looking images still fail.
  Missing small details can leave global SSIM above .98.

## Current measurements — audited 2026-10-31

| Set | Cases | Before fix | After fix |
| --- | ---: | ---: | ---: |
| Core: scale/quarter turns and fixed working-size reduction | 36 | 24 pass | **36 pass** |
| Stress: smaller sizes, arbitrary rotations, seeded noise, blur, contrast, hairlines | 42 | 24 pass | **34 pass / 8 fail** |
| Combined | 78 | 48 pass | **70 pass / 8 fail** |

The fix rescues a previously absent unique colour in small isolated alpha
components. Edge dilation can erase every flat seed; RGB ringing also prevents
the existing repeated-colour fallback from collecting enough identical pixels.
Accept a new colour only from a stable eroded near-opaque interior (at least two
pixels, alpha ≥245, 90th-percentile RGB deviation ≤6), with no flat seed and within
the configured palette/speckle budgets. Explicit palettes stay authoritative.
This restores five objects at native size and makes all 36 core cases pass.

The subsequent campaign fixed mild sigma-2 noise (two seeds), half-size marker
geometry (four rotations) and the .7px blurred marker. The Oct-31 exposed-curve
retry leaves all 78 sweep verdicts unchanged. Fresh evidence:
`/tmp/plate-oct31-{before,after}-robustness/{report.json,index.html}`.

Remaining **8 stress failures** are preserved in the report:

| Cases | Remaining failure |
| --- | --- |
| Quarter-size marks, four rotations | Route and marker vanish under current speckle/contour floors |
| Marks blurred 1.2px | Marker is present but insufficient coverage under the current alpha/silhouette model |
| Opaque panels at 1/16 contrast | Current palette merge threshold absorbs foreground into background despite SSIM above .98 |
| 1px / 2px routes | Automatic palette admission loses both; explicit palette recovers the 2px route, while current 1px stroke fitting also misses the silhouette gate |

These are measured **default-setting/algorithm limitations**. The earlier claim
that all eight are "information-theoretic floors" is not established. A threshold
or unsuccessful attempted fix is not a proof that all automatic recovery methods
must fail. Preserve independent targets and acceptance gates. Existing pin tests
assert these failures; review those assertions explicitly if a valid future fix
improves them rather than treating failure itself as a permanent requirement.

These are **additional measured stress misses**, separate from the seven existing
strict-xfail authored-logo/scene contracts. Pytest gates the supported subset,
matcher regressions and current-limit reproductions. The complete sweep remains
red; passing tests do not turn its eight misses into successful reconstruction.

Historical initial-marker evidence: `/tmp/plate-robustness-{before,final}/`,
especially `report.json` and `index.html`. That phase's focused robustness/
segmentation run was **77 passed**, full suite **519 passed / 7 xfailed**. Its original
benches preserve all **24 PLATE + 24 VTracer SVGs byte-for-byte**:
`/tmp/plate-sweeps-benchmark-comparison.json`. Visual review:
`plate-robustness-marker-review.png` in this chat's visualization directory.

## Next coverage

Mild-noise detection and half-size/.7px marker recovery are fixed. Expand beyond these two
disjoint scenes to aspect-ratio extremes, gradients, occlusion and real artwork;
add direct native gradient/hidden-object/4× seam checks. Do not generalize 36 core
passes to every logo at these scales. Jessica allows scope expansion as useful,
provided additions and remaining work are recorded in ROADMAP and HANDOFF.

## Hairline-route floor analysis — 2026-10-31

Two remaining stress misses, the `marks` route at authored stroke-width 1px and 2px
(`marks-s1-…-line1` / `line2`), were investigated per-object with the renderer. Both
are **documented current limitations**. No tested automatic change was landed;
this does not prove every gate-preserving approach impossible. Pinned by
`test_hairline_route_1px_is_below_the_round_cap_half_width_floor` and
`test_hairline_route_2px_is_below_the_palette_admission_floor` in
`tests/test_robustness.py`.

- **1px route — geometric floor.** At `work_size` 1536 the 256×144 source is not
  upscaled (scale 1.0), so the 1px line stays a 2-working-px band at alpha ≈147
  everywhere (no pixel ≥200). Its colour `#141e2d` is ~129 RGB from the nearest
  palette entry and never admitted (route absent, 4 shapes, 0 strokes). Even when the
  palette is force-fed the authored colour, the route emits correctly (`fill=none`,
  stroke `#141e2d`, width 1.5) but silhouette fails: the thinnest round-capped stroke
  PLATE can emit is 1.5px (two rows) from `fit_straight`'s 0.75 half-width floor,
  versus the 1px (one row) authored target, giving IoU 0.5 / boundary deviation 1.0.
  Matches prior art (the quarter-size 1-working-px route).
- **2px route — palette-admission floor.** The 2px line is a 2-working-px band at
  alpha ≈243, again a distinct colour ~129 RGB from the palette, with no flat seed and
  no erodable interior, so no automatic seeding path admits it (route absent, 4 shapes,
  0 strokes). This is NOT a geometric floor: force-feeding the authored palette yields
  a stroke that passes EVERY route check (editable_stroke, width ≈2.01, silhouette
  IoU 1.0). It stays a floor because the currently-green `marks-s0p5-…-line4` route is
  geometrically identical (2-px band, max distance-transform 1.0, alpha 193/243/243)
  yet recovers via scene-dependent flat-core seeding. Earlier attempted admission
  rules changed green cases (including `panels` blur halos). The shared signature
  alone does not imply every admission rule must regress the half-size scene;
  retain this as an open algorithmic limitation, not a mathematical impossibility.

The combined sweep therefore stays **70/78** (core **36/36**); the two route cases
remain the last of the measured stress misses alongside the quarter-size routes, the
blur-1.2 marker, the one low-contrast panels case and four quarter-size rotations.
