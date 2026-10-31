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

## Current measurements — 2026-10-30

| Set | Cases | Before fix | After fix |
| --- | ---: | ---: | ---: |
| Core: scale/quarter turns and fixed working-size reduction | 36 | 24 pass | **36 pass** |
| Stress: smaller sizes, arbitrary rotations, seeded noise, blur, contrast, hairlines | 42 | 24 pass | **27 pass / 15 fail** |
| Combined | 78 | 48 pass | **63 pass / 15 fail** |

The fix rescues a previously absent unique colour in small isolated alpha
components. Edge dilation can erase every flat seed; RGB ringing also prevents
the existing repeated-colour fallback from collecting enough identical pixels.
Accept a new colour only from a stable eroded near-opaque interior (at least two
pixels, alpha ≥245, 90th-percentile RGB deviation ≤3), with no flat seed and within
the configured palette/speckle budgets. Explicit palettes stay authoritative.
This restores five objects at native size and makes all 36 core cases pass.

Remaining **15 stress failures** are preserved in the report:

| Cases | Remaining failure |
| --- | --- |
| Quarter-size marks, four rotations | Route and marker vanish at tiny source footprints |
| Half-size marks, four rotations | Marker source pixels survive, but rectangle snapping of its 12-pixel footprint achieves only about .846 circle coverage, below .90 |
| Marks blurred .7 / 1.2px | Marker absent / insufficient coverage |
| Opaque panels, noise sigma 2, two seeds | Jagged geometry, lost primitive form or too many anchors; stronger noise can trigger denoising and perform better |
| Opaque panels at 1/16 contrast | Foreground objects merge into background despite global SSIM above .98 |
| 1px / 2px routes | Thin route disappears |

These are **additional measured stress misses**, separate from the seven existing
strict-xfail authored-logo/scene contracts. They are not hidden with lower
thresholds or added as ordinary passing tests. Pytest gates the supported subset
and matcher regressions; the complete sweep remains red until its targets improve.

Evidence: `/tmp/plate-robustness-{before,final}/`, especially `report.json` and
`index.html`. The final focused robustness/segmentation run is **77 passed**.
The complete project suite is **519 passed / 7 xfailed**. Before/after original
benches preserve all **24 PLATE + 24 VTracer SVGs byte-for-byte**:
`/tmp/plate-sweeps-benchmark-comparison.json`. Visual review:
`plate-robustness-marker-review.png` in this chat's visualization directory.

## Next coverage

Investigate mild-noise auto-denoise thresholds and tiny-marker/source-coverage
fitting without relaxing the independent contracts. Expand beyond these two
disjoint scenes to aspect-ratio extremes, gradients, occlusion and real artwork;
add direct native gradient/hidden-object/4× seam checks. Do not generalize 36 core
passes to every logo at these scales. Jessica allows scope expansion as useful,
provided additions and remaining work are recorded in ROADMAP and HANDOFF.
