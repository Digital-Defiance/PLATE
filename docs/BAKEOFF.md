# Bake-off: objectively scoring PLATE against other tools

```bash
plate corpus -o bo/corpus -n 24 --seed 1                      # synthetic scenes + exact ground truth
plate bakeoff bo/corpus/images --truth bo/corpus/truth -o bo/out
open bo/out/report.html                                       # ranking, per-metric table, per-image gallery
```
Real images (no ground truth): `plate bakeoff my_pngs/ -o bo/real` — structure metrics are skipped and the
composite renormalises over what exists. Add other tools by exporting their SVGs to a folder named
`IMAGE.TOOL.svg` (e.g. `scene03.illustrator.svg`, `scene03.vectorizer-ai.svg`) and passing `--external DIR`.

## What is measured (all normalised to 0–1, higher = better)
| family | metric | meaning |
|---|---|---|
| fidelity | `ssim` | SSIM of the render vs the *clean* reference (truth render if known, else the source). Normalised (ssim−0.85)/0.14 |
| | `edge_f1` | Canny-edge F1 with 2 px tolerance |
| topology (report-only, weight 0) | `topology` | same solid pieces as the reference: same-colour pieces matched by overlap; `topo_extra` = specks, pinched-off tips, splits; `topo_missing` = dropped dots/periods, merges. Blend pixels are ignored on both sides, so a soft JPEG and a crisp render compare fairly |
| structure (truth only) | `obj_visible_f1` | an SVG element whose *visible* region (minus later elements) matches a true object's visible region at IoU ≥ 0.9; F1 over objects vs elements — over-segmentation lowers precision |
| | `obj_complete_f1` | same, but the element's *whole* shape vs the object's complete silhouette → rewards hidden-part completion |
| | `hidden_completion` | of objects that are partly hidden, the share recovered whole |
| | `order_acc` | stacking order right for matched, overlapping pairs |
| editability | `anchor_eff` | 1 − (anchors per shape − 4)/36, clipped. Rects/circles = 4 → 1.0 |
| | `primitive_ratio` | share of elements that are true `<circle>/<ellipse>/<rect>/<polygon>` |
| | `named` | share of elements/groups with a *meaningful* name (generic `path12`, `Layer_1`, `XMLID_3` do not count) |
Also recorded, not in the composite: `primitive_acc` (right primitive kind for matched objects), `anchor_ratio_vs_ideal`, `mae`, bytes, seconds.

Composite = weighted mean over available metrics (`DEFAULT_WEIGHTS` in `bakeoff/score.py`; override with `--weights w.toml`).
The report also re-ranks under **five weightings** (balanced, geometry-only, fidelity-first, editability-first, structure-first)
so you can see whether a ranking is an artefact of the weights.

## Method safeguards
- The ground-truth SVG itself must score perfect structure (tested). A tool that returns only visible cut-outs must lose `complete` credit (tested).
- Scoring is tool-agnostic: it parses any SVG, renders each element alone with cairosvg, never looks at tool-specific hints.
- Names/primitives obviously favour a layered tool; the **geometry-only** profile removes that credit.
- Corpus is flat vector art; it says nothing about photos or gradients. Use real images for that, and treat the synthetic score as a regression test for *editability and structure*, not a universal ranking.

## Results (24-scene corpus, seed 1; 6 are JPEG-damaged variants) — `plate 0.0.1`
| tool | composite | geometry-only | fidelity-first | editability-first | structure-first | anchors/shape |
|---|---|---|---|---|---|---|
| plate | **0.788** | **0.786** | **0.906** | **0.829** | **0.704** | 10.0 |
| vtracer (stacked) | 0.500 | 0.644 | 0.787 | 0.369 | 0.430 | 23.0 |
| vtracer (cutout) | 0.489 | 0.631 | 0.758 | 0.313 | 0.443 | 34.2 |
| potrace-color (8 colours) | 0.428 | 0.557 | 0.697 | 0.314 | 0.368 | 100.2 |

Not yet in the table (need the Mac): Illustrator Image Trace, Vectorizer.AI, Inkscape trace — **please add them**.

## Real logo: Research Force (2026-11-01, `samples/fixtures/research_force_logo.jpeg`)
One real JPEG logo, scored against the source (no ground truth, so no structure metrics). The two
external SVGs were supplied by the user: one from a vectorizer website, one from Adobe.

| tool | SSIM | edge F1 | extra / missing pieces | shapes | anchors | colours | size |
|---|---|---|---|---|---|---|---|
| PLATE default | 0.960 | 0.930 | 3 / 32 | 49 | 563 | 4 | 29 KB |
| PLATE `smooth`, before JPEG edge repair | 0.975 | 1.000 | 0 / 1 | 32 | 662 | 4 | 30 KB |
| PLATE `--preset smooth --set upscale=2`, JPEG edge repair | **0.976** | **1.000** | **0 / 0** | **32** | **647** | 4 | 29 KB |
| PLATE `smooth`, JPEG repair + supported tip ownership | **0.976** | **0.999** | **0 / 0** | **32** | **624** | 4 | 28 KB |
| vectorizer website | 0.719 | 1.000 | 0 / 1 | 371 | 3787 | 46 | 125 KB |
| Adobe | 0.934 | 0.856 | 2 / 11 | 116 | 1648 | 23 | 125 KB |

What the files show about each process:
- **Vectorizer**: stacked shapes (no holes, lower shapes run under upper ones), one path per shape,
  lines and curves mixed. Every small piece survives (periods, the dot in the V, gap tips). It keeps
  anti-aliased edge colours as separate thin shapes (46 colours), which is where the junk at the book
  corners comes from, and it shifts the colours (background `#00292d` vs `#0c282c` in the source),
  which alone drops its SSIM to 0.72.
- **Adobe**: cut-out model (the background is one compound path with holes where objects sit, so
  moving an object leaves a hole); every segment is a cubic, even straight ones, written one per line
  with 6 decimals — hence 2,067 lines, though it has fewer than half the vectorizer's segments. It drops
  everything under a noise size: the tagline periods, the dot in the V, the ends of the narrow gaps.
  That is a large part of why it looks clean.
- **PLATE default** loses the 2 px tagline entirely (32 missing pieces); `--preset smooth` keeps it,
  draws the fewest shapes, uses only the source's 4 colours, and has no stray pieces. The remaining
  "missing" piece before JPEG edge repair was a 1 px seam the JPEG only half shows. Not measured by any number here: outline
  smoothness (see ROADMAP "Outline smoothness metric").

### JPEG colour-edge experiment (2026-11-01, Kiro 13.8)

Opt-in `jpeg_edges` is now enabled by `smooth`. Luma-only coverage barely helped because the
normal two-pixel neighbourhood often had just one flat colour seed. Chromatic pairs with enough
luma contrast now use a wider, scale-aware seed search; RGB still ranks pairs and luma places
their boundary. Achromatic/low-contrast pairs keep the old calculation. All-pair widening was
rejected because it produced a new dark pocket. Decoded format gates the change; PNGs and
defaults are unaffected. No bake-off weights or existing regression floors changed.

Independent JPEG-q85 pink/blue line/arc masks: boundary errors **156–236 → 36–60** at 1×,
**686–810 → 43–86** at 2× (`tests/test_jpeg_edges.py`). Logo MAE **1.39781 → 1.35239**;
SSIM **0.975168 → 0.976148**, all counted pieces preserved. Enlarged renders show an improved
blue terminal/colour-band boundary, with some rounded bends and gap-tip joins still imperfect.
This revision has not been accepted in Illustrator.

The same 24-scene seed-1 corpus, `smooth` at native working scale (not 2×), measures:

| metric | previous `smooth` | JPEG edge repair |
|---|---:|---:|
| composite | 0.846317 | 0.846217 |
| SSIM | 0.989624 | 0.989619 |
| whole-object F1 | 0.700787 | 0.700787 |
| hidden completion | 0.548611 | 0.548611 |

All 18 PNG SVGs are byte-identical; the six JPEGs change. The corpus result is effectively flat,
including a small composite decrease; this is a targeted real-logo/thin-edge improvement,
not a broad hidden-completion win. Separate default benches confirm all 24 PLATE and 24 VTracer
SVGs remain byte-identical. Evidence: `/tmp/plate-resume/before-smooth-bakeoff/`,
`/tmp/plate-resume/after-smooth-bakeoff-final/`, and `/tmp/plate-resume/default-comparison.json`.

### Gap-tip ownership (2026-11-01, partial Task 13.6)

With `rescue_detail`, source-supported tips now join their one non-fragment same-colour
region before ordering/tracing; no separate overlay is needed there. Gradients/nonopaque
pixels, ambiguous targets, whole foreign-object removal and donor splits are rejected.
Logo: 246 working pixels reassigned, spine overlay pixels **35 → 0**, serialized anchors
**647 → 624**, SSIM **0.976148 → 0.976205**, MAE **1.35239 → 1.34431**, topology still **0/0**.
The dot/periods survive. Enlarged renders were inspected; native Illustrator review is pending.

Same 24-scene seed-1 `smooth` bake-off: composite **0.846217 → 0.848961**, whole-object F1
**0.700787 → 0.706323**, hidden completion unchanged **0.548611**, SSIM slightly down
**0.989619 → 0.989577**. Weights and acceptance gates unchanged. Full tests **615 passed /
7 xfailed**; sweep **70/78**, core **36/36**; all 24 PLATE + 24 VTracer defaults byte-identical.

Task 13.6 remains open: an under-bar gap has only small fragment anchors; another join would
detach an 8-working-pixel blue island, so the guard rejects it. The under-bar detail overlay
remains, and vertical gap ends remain 1–2 source pixels short. These are unresolved algorithm
cases, not claimed information limits. Evidence: `/tmp/plate-continue/` (especially
`inspect-blue2.log`, `after-smooth-bakeoff/`, `default-comparison.json`, `robustness/`).

## Where PLATE loses (the useful part)
Complete-object recovery on the corpus: free circles 13/17, **occluded rect 4/11, occluded polygon 3/10, occluded rrect 5/12**, and
**JPEG-damaged scenes: 3/10 occluded objects recovered** at the original default (aggregate `hidden_completion` 0.33; an earlier
0/10 here came from a different corpus config), **4/10 (0.42) since the JPEG-keyed denoise** (`load_image` runs one bilateral pass
when the source is a JPEG; it never fires on PNG). Causes found: (1) touching objects of the *same colour* merge into one
region (colour-only segmentation can't split them) → needs SAM or geometric splitting; (2) amodal completion is weaker for
rectangles/polygons than circles; (3) JPEG ringing displaces region boundaries enough that the primitive fit in
`complete.try_complete` exceeds its tolerance (the T-junction occlusion test is not the cause). These are tracked in ROADMAP.md (P1 "bake-off driven").
Goal: `hidden_completion` ≥ 0.8 and JPEG parity, tracked by `tests/test_bakeoff.py` + this table.
