# Authored PNG → SVG challenges

These eight scenes begin as small, hand-authored SVGs in
[`samples/challenges/`](../samples/challenges/). Rasterizing each at 4× resolution
and downsampling produces its PNG input. The `.target.svg` is the desired editable
output, authored independently of PLATE. It is never refreshed from pipeline output.

This complements the existing controls, some of which deliberately pin current
behaviour. Here the target remains the goal even when PLATE currently fails it.

| Scene / input | Desired SVG | Verified result (2026-10-29) | White-background SSIM |
| --- | --- | --- | --- |
| [Nested dial](../samples/challenges/nested_dial.png) | [Target](../samples/challenges/nested_dial.target.svg): background + seven full circles; nested housing, bezel, face, hub and three repeated markers | Pass; 8 objects | 0.9916 |
| [Perforated plate](../samples/challenges/perforated_plate.png) | [Target](../samples/challenges/perforated_plate.target.svg): one connected compound path with three transparent holes + one circle island | Gap: plate path has a stray second component, despite correct holes and 2 objects | 0.9902 |
| [Occlusion chain](../samples/challenges/occlusion_chain.png) | [Target](../samples/challenges/occlusion_chain.target.svg): three recovered full circles + foreground panel + background, in paint order | Gap: back circle centre drifts ≈3.5px; full silhouette IoU ≈0.946 | 0.9853 |
| [Twin gradients](../samples/challenges/twin_gradients.png) | [Target](../samples/challenges/twin_gradients.target.svg): two separate rectangles with opposite linear gradients, two overlaid circles, background | Pass; 5 objects, 2 gradients | 0.9882 |
| [Gradient badge](../samples/challenges/gradient_badge.png) | [Target](../samples/challenges/gradient_badge.target.svg): one full radial-gradient circle behind a crossing ribbon, two rivets, background | Gap: 6 objects / 2 gradient discs instead of 5 objects / 1 disc | 0.9936 |
| [Edge-crossing type](../samples/challenges/edge_crossing_type.png) | [Target](../samples/challenges/edge_crossing_type.target.svg): full circle behind three outlined block letters, plus background | Gap: disc fragments; 7 objects instead of 5 | 0.9851 |
| [Discrete palette](../samples/challenges/discrete_palette.png) | [Target](../samples/challenges/discrete_palette.target.svg): eight hard-edged, flat rectangles + background; zero gradients | Pass; 9 rectangles | 0.9963 |
| [Stroked route](../samples/challenges/stroked_route.png) | [Target](../samples/challenges/stroked_route.target.svg): one open path with editable 16px stroke, two endpoint circles, background | Gap: route becomes a filled outline | 0.9917 |

All eight currently clear an SSIM floor of 0.95 on **both white and dark backgrounds**.
That does not imply that the editable structure is correct: the badge's duplicate
discs are a particularly clear example.

## What is enforced

[`tests/challenges.py`](../tests/challenges.py) holds the desired contracts;
[`tests/test_challenges.py`](../tests/test_challenges.py) exercises the full pipeline.

- Exact number of drawable objects; live circle/rectangle/ellipse types.
  Outlined polygonal letters may be paths or polygons.
- Match individual objects by full silhouette using optimal assignment. Require
  IoU ≥0.96 or xor/boundary ≤0.75px to accommodate small antialiased markers.
  Hidden parts count: a visible crescent is insufficient when the target is a circle.
- Exact connected-component and hole counts for each object, including transparency.
- Gradient fill kind per matched object, and preserved open strokes with the right width.
- Relative paint order of overlapping objects. Disjoint objects may reorder.
- Valid unique IDs, resolved gradient references, no embedded raster fallback.
- Appearance against the PNG on two backgrounds, regardless of structural gap status.

Five demonstrated gaps use **strict xfail**, limited to `TargetMismatch`. Pipeline
crashes and fidelity regressions still fail normally. A fully met target produces
XPASS and fails the suite until its gap marker is removed. Do not replace the target
SVG with today's output to make a test pass.

The reference IDs explain author intent; semantic names, OCR, and a particular group
hierarchy are not asserted. PNGs do not uniquely specify an SVG's original authoring
history. These contracts choose a useful editable reconstruction. The block lettering
is explicit vector geometry, so the fixture has no font or OCR dependency.

## Reproduce

```sh
# On macOS, the direct Python/library calls need this for Homebrew cairo.
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
.venv/bin/python scripts/make_challenges.py
.venv/bin/pytest -q tests/test_challenges.py
.venv/bin/plate bench samples/challenges -o /tmp/plate-challenges
```

The render extra and libcairo are required to regenerate PNGs. Checked-in PNGs let
the pipeline and SVG integrity checks run without the renderer; silhouette and
appearance checks explicitly skip when it is unavailable. The plain-VTracer bench
control remains available and unchanged.

Useful next scenes: a 70-colour mosaic (palette pressure), the same logo at 1×/2×/4×
(scale consistency), a semitransparent drop shadow over two different backgrounds,
and a ring partially hidden by another ring (topology plus amodal completion).
