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

## Where PLATE loses (the useful part)
Complete-object recovery on the corpus: free circles 13/17, **occluded rect 4/11, occluded polygon 3/10, occluded rrect 5/12**, and
**JPEG-damaged scenes: 0/10 occluded objects recovered**. Causes found: (1) touching objects of the *same colour* merge into one
region (colour-only segmentation can't split them) → needs SAM or geometric splitting; (2) amodal completion is weaker for
rectangles/polygons than circles; (3) JPEG noise breaks the T-junction occlusion test. These are tracked in ROADMAP.md (P1 "bake-off driven").
Goal: `hidden_completion` ≥ 0.8 and JPEG parity, tracked by `tests/test_bakeoff.py` + this table.
