# Authored PNG → SVG challenges

These twelve scenes begin as independently authored SVGs in
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

## Complex compositions

Four larger scenes combine the interactions above. Their targets use **44–64
objects**, with fixed geometry and custom outlined lettering: no installed fonts,
external assets, or model generation are needed. Every target object has visible
pixels; none is included solely as a completely hidden authoring artefact.

The table below records the initial baseline, before the geometry validation fix.

| Composition | PNG / desired SVG | Target objects → initial objects | Gradients: target → initial | Initial SSIM, white / dark |
| --- | --- | --- | --- | --- |
| Mission patch, 960×960 | [PNG](../samples/challenges/complex_mission_patch.png) · [SVG](../samples/challenges/complex_mission_patch.target.svg) | 45 → 55 | 2 → 0 | 0.9628 / 0.9644 |
| Storefront, 960×800 | [PNG](../samples/challenges/complex_storefront.png) · [SVG](../samples/challenges/complex_storefront.target.svg) | 64 → 68 | 0 → 0 | 0.9515 / 0.9485 |
| Instrument panel, 960×800 | [PNG](../samples/challenges/complex_instrument_panel.png) · [SVG](../samples/challenges/complex_instrument_panel.target.svg) | 59 → 37 | 0 → 0 | 0.9665 / 0.9665 |
| Event poster, 960×960 | [PNG](../samples/challenges/complex_event_poster.png) · [SVG](../samples/challenges/complex_event_poster.target.svg) | 44 → 57 | 1 → 1 | 0.9283 / 0.9283 |

- **Mission patch:** nine genuinely transparent rim cutouts, two gradients, eight
  stars, crossing orbital strokes, solar-panel details, a spacecraft over a planet,
  and a ribbon with outlined type.
- **Storefront:** repeated framed windows, fourteen alternating scalloped awning
  panels, an overlapping sign, lamps, a door, and foreground plants. Each awning
  panel is one continuous object; there is no invisible split between its stripe
  and scallop.
- **Instrument panel:** three nested gauges, eighteen tick strokes, three needles,
  four screw slots, two signal routes, and connected indicator lights. Small strokes
  are important even when their total pixel area barely affects SSIM.
- **Event poster:** a gradient disc behind large outlined letters, an occluded ring,
  rotated ellipse, diagonal ribbon, six crossing lines, repeated dots, and footer.

All four structural contracts are strict expected feature gaps. Appearance checks
remain active. After fixing geometry validation, the regression floors are 0.95
for the patch, panel and storefront, and 0.94 for the poster. **The desired fidelity
remains ≥0.95**; the poster floor records current behaviour, not success against
the goal. The original eight fixtures retain their 0.95 floors.

[`scripts/make_complex_scenes.py`](../scripts/make_complex_scenes.py) authors both
targets and PNGs. `scripts/make_challenges.py` can also rerasterize the checked-in
targets. Tests protect object counts, gradient/stroke counts, image dimensions,
self-contained vector artwork, and all nine transparent cutouts.

### Diagnosis and suggested fix order

1. **Validate geometry candidates safely—implemented.** Completion now checks
   containment before unioning observations into the candidate. Primitive snapping
   compares the full candidate footprint, including geometry outside the source
   crop; non-finite and implausibly large fits are rejected before allocation.
   The poster footer previously became an ellipse centred at x≈480 with rx≈663,
   despite its source rectangle spanning x=60…900. It now emits a live rectangle
   with half-width 420 and half-height 50. Model ranking and additional corner
   constraints remain possible future improvements.
2. **Preserve thin features during segmentation.** All eighteen 5px gauge ticks
   have zero cream-colour coverage immediately after `segment()`, before fitting
   or SVG output. Whole thin regions can be classified as edges, leaving no local
   flat seeds for their colour. Add reliable palette-colour seeds/fallbacks for
   these regions and protect narrow components. A focused tick/slot fixture should
   pin both the visible detail and topology.
3. **Recover editable strokes.** Surviving constant-width regions need a centreline
   and width model, followed by stroke-cap/join support in the scene model/emitter.
   Recover raster detail first; an SVG stroke feature cannot reconstruct regions
   that segmentation has already erased.
4. **Fit gradients jointly across occlusion.** Gradient candidates currently require
   connected visible bands and are fitted before occlusion analysis. Test linking
   compatible fragments separated by an established occluder, fitting one model,
   then recovering one silhouette. Preserve independent opposite ramps and discrete
   palette swatches as negative controls.
5. **Complete across multiple edge-crossing occluders.** Keep the relative T-junction
   test, but pool supported free-boundary fragments and score a shared primitive
   against all visible pixels and inferred occluders. Retain genuine holes; reject
   geometry added outside supported occlusion. Start with the small text/gradient
   controls before requiring whole complex scenes to pass.

Diagnostic sweeps before the geometry fix: patch `max_colors=16/32/64` all produce 55 objects, zero gradients,
SSIM 0.9628. Panel `denoise=0` still produces 37 objects and SSIM 0.9665; disabling
primitive snapping gives 37 objects and SSIM 0.9660. These are evidence against a
simple palette-size or denoising preset fix. Detailed causal work remains; the
gradient/occlusion changes above are proposed approaches rather than implemented
solutions. Segmentation has not been changed.

### Geometry validation results (2026-10-29)

| Scene | SSIM before → after | Result |
| --- | --- | --- |
| Event poster | 0.9283 → **0.9493** | Footer remains a live rectangle; oversized ellipse rejected |
| Storefront | 0.9515 → **0.9623** | Pavement remains rectangular; anchors decrease 576 → 567 |
| Instrument panel | 0.9665 → **0.9666** | Full structural target remains unmet |
| Mission patch | 0.9628 → **0.9628** | Gradient/occlusion work remains |

Original `samples/*.png` outputs are byte-identical to the previous run. The
plain-VTracer baseline is unchanged. Six regression cases in
`tests/test_geometry_validation.py` cover long rectangles at several aspect ratios,
valid versus observation-discarding completion candidates, and the real poster
footer. All structural target SVGs and expected-gap markers are unchanged.

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

Nine demonstrated structural gaps use **strict xfail**, limited to `TargetMismatch`. Pipeline
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
.venv/bin/python scripts/make_complex_scenes.py  # re-author the four large scenes
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
