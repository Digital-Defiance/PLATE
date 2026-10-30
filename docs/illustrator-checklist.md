# Illustrator verification

## Automated local integration

On macOS with Illustrator installed, run from the repository root:

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python -m plate.illustrator \
  --output /tmp/plate-illustrator-NEW
```

Use a new output directory for each run. Optional positional inputs replace the
default eight fixtures; inputs can be rasters or PLATE-generated SVGs with unique
object/group IDs and pixel dimensions. Requires the render dependencies and macOS
Automation permission for Illustrator. Ordinary `pytest` never opens Illustrator.
The harness uses Adobe's AppleScript/ExtendScript interface; no UI clicking or
Accessibility permission is needed.

The runner copies/generates SVGs into the new directory, opens only those copies,
exports PNGs, saves `.ai` files, closes/reopens them, and performs independent
move/recolour/stroke-width edits. It closes its own documents without saving edits
and restores the prior active document and interaction setting. It refuses existing
output directories. A timeout does **not** cancel the script inside Illustrator:
inspect the app before retrying; do not launch overlapping runs. If Illustrator is
waiting on a dialog, dismiss/resolve it before continuing.

Artifacts: `manifest.json`, `illustrator.json` (native DOM observations), `report.json`
(checks and SSIM scores), and per-case input/edited SVGs, exported PNGs and
`roundtrip.ai`. Exit **0** means every check passes, **1** means measured failures,
and **2** means a bridge failure. Missing/misordered real layers fail explicitly;
named groups cannot substitute for them.

### Verified on Illustrator 30.8.2 — 2026-10-30

Evidence: `/tmp/plate-illustrator-layers-all/report.json` (temporary local artifacts).
**24/24 workflows and all 636 checks pass**, including all original samples,
authored challenges, four complex scenes and four logos. The default eight-case
run also passes (`/tmp/plate-illustrator-real-layers/report.json`).

| Fixture | Vector objects | Native strokes | Gradient fills | Actual layers | Lowest render SSIM |
| --- | ---: | ---: | ---: | ---: | ---: |
| face | 8 | 0 | 0 | 2 | .9976 |
| overlap | 3 | 0 | 0 | 3 | .9992 |
| donut_alpha | 2 | 0 | 0 | 2 | .9976 |
| shaded | 5 | 0 | 1 | 5 | .9928 |
| perforated_plate | 2 | 0 | 0 | 2 | .9989 |
| gradient_badge | 5 | 0 | 1 | 3 | .9979 |
| stroked_route | 4 | 1 | 0 | 4 | .9990 |
| logo_orbit_wordmark | 44 | 7 | 1 | 34 | .9960 |

Verified automatically:

- [x] Named vector objects, real layer membership and nested group parentage survive import.
- [x] Actual layer stack and drawable paint order match SVG paint order exactly.
- [x] ID underscores become spaces; numeric deduplication suffixes remain. Import
  names come from IDs, so `data-name` is not an exact independent label guarantee.
- [x] Expected object/stroke/gradient counts, no embedded/placed rasters, canvas size.
- [x] Circles/ellipses import as four-anchor paths. This does **not** establish
  Illustrator's live-shape widgets.
- [x] `.ai` reopening preserves names, hierarchy, anchor/control-point geometry,
  bounds, opacity and recorded style metadata. Exported PNGs are identical at the
  pixel-array level before/after the round trip.
- [x] Moving a named object +10px and recolouring it magenta visibly changes the
  export and matches an independently edited SVG. Native stroke widths can be
  increased 50% in stroke-bearing cases, with matching renders.
- [x] Imported, reopened and edited exports meet SSIM ≥.98 on white and dark
  backgrounds against Cairo renderings of the corresponding SVGs. This measures
  SVG interchange, separately from raster-to-SVG conversion fidelity.
- [x] Existing-document preservation: a separate-call probe left a copied `.ai`
  document open with an unsaved marker while the normal checker ran. Before/after
  observations match exactly: active document, dirty flag, object count, marker
  anchors/bounds/RGB and interaction setting. Only the test copy closed; cleanup
  then closed the owned sentinel normally. Evidence:
  `/tmp/plate-illustrator-layer-preservation/preservation.json` and its probe scripts
  (repeated successfully after the layer fix).
  An earlier nested `$.evalFile` wrapper timed out; its cause remains unidentified.
  Jessica confirmed there was no visible dialog. The normal runner succeeded with
  and without the existing document.
- [x] **Actual Illustrator layers:** emitter uses `i:layer="yes"` with
  `xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/"`, alongside Inkscape markers.
  Standalone roots get named `… layer` containers, so backgrounds stay separate;
  original object IDs remain stable. Top-level groups become actual layers,
  nested semantic groups stay groups. No Illustrator postprocessing is required.
  The original Inkscape-only marker failed; Adobe 9.0/10.0 namespace probes and
  standalone-leaf/wrapper probes exposed the supported mapping. Evidence:
  `/tmp/plate-layer-import-probe/`. All 24 before/after SVGs have identical geometry,
  IDs, gradient definitions and paint hierarchy after removing the new layer
  annotations/containers; Cairo pixels match exactly on both backgrounds, and
  VTracer outputs are byte-identical (`/tmp/plate-layer-render-comparison.json`).
- [x] Linear and radial gradient import, including `twin_gradients` in the full corpus.

## Remaining checks

- [ ] Live ellipse/rectangle/rounded-corner widgets, beyond anchor counts.
- [ ] Direct gradient-stop edits and wider opacity/blend coverage.
- [ ] Explicit isolate/move-occluder test proving the hidden silhouette and compound
  holes in the native document. Existing topology tests/render comparisons cover
  the SVGs but are not a full native hidden-object contract.
- [ ] Automated high-resolution/400% seam checks; current desktop exports are 1×.
- [ ] Broader real-image corpus and supported Illustrator versions.

These checks establish interchange of the SVGs PLATE emits. They do not prove
complete PNG object recovery: seven independent tracing contracts still fail.
See README's coverage table and ROADMAP's quality gates before making broader claims.

Manual checks can supplement these: select underlying shapes in `overlap`, inspect
transparent counters in `perforated_plate`, try live-shape controls and zoom to
400%. Record the Illustrator version and observations in `STATUS.md`.

Adobe documents the scripting entry points at
[Illustrator developer resources](https://developer.adobe.com/illustrator/) and
[installing/running scripts](https://helpx.adobe.com/illustrator/desktop/automate-visualize-data/automate-actions/install-and-run-scripts.html).
