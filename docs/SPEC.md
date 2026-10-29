# PLATE spec

## 1. Goal
Best-in-class raster -> SVG for *editability in Illustrator*, run locally on a
MacBook (M4 Max, 64 GB). Quality is defined by the measurable metrics in
`METRICS.md`, not by pixel similarity alone.

## 2. Non-goals
No GUI/desktop app (CLI only). No cloud inference. No photo-realistic vectorization
in v1 (flat art, logos, line art, simple illustration first). No custom model
training before Phase 6.

## 3. CLI
```
plate trace IMG [-o OUT.svg] [--preset logo|illustration|lineart] [--config plate.toml]
            [--simplify PX] [--max-colors N] [--group-depth N] [--baseline]
plate sweep IMG --simplify 0.5,1,2 --max-colors 8,16   # variants + comparison report
plate report IMG                                       # HTML: original | SVG | error heatmap | layer tree | anchors/shape
plate batch DIR -o OUTDIR
plate bench DIR                                        # score vs baselines (METRICS.md)
plate doctor
```
Every lever in `config.py` is also a TOML key and a flag. Layer overrides via a
sidecar `IMG.plate.json` (rename / merge / reorder / delete layers), re-applied on
re-run without redoing AI stages.

## 4. Pipeline (all stage outputs cached on disk by image hash + stage + relevant config)
1. **segment** - SAM 3 masks (open-vocabulary prompts allowed). SLOW, cached.
2. **order/name** - local VLM via LM Studio (OpenAI-compatible): occlusion graph,
   stacking order, nested grouping to `group_depth`, human names. SLOW, cached.
3. **complete** - amodal completion of occluded regions (off-the-shelf inpainting first).
4. **trace** - VTracer 1.0 per layer, `simplify`, seam-free.
5. **primitives** - geometric fitting (circle/ellipse/rect/rounded-rect/line/mirror
   symmetry); accept only under tolerance. No AI.
6. **refine** - render, diff vs source, locally refit/add anchors where error is high.
7. **emit** - named nested `<g>` layers, real `<circle>/<rect>` where fitted.

Re-running with different curve/color levers only re-executes stages 4-7 (seconds).

## 5. Levers
See `src/plate/config.py` (single source of truth). Presets: logo, illustration, lineart.

## 6. Tech
Python >= 3.10, `uv`/`pipx` install. Core deps: vtracer, pillow, numpy. Optional
`[ai]` extra: torch (MPS), transformers, openai client. Models: SAM 3 (check weights
license before release), a Qwen-VL class model through LM Studio.

## 7. Illustrator compatibility (must be verified by hand, then by test)
Layer names appear in Layers panel; groups nest; clip paths/masks avoided; `fill`
as attribute not CSS classes; no `<use>` indirection; units px, viewBox preserved.
Keep a `docs/illustrator-checklist.md` of confirmed behavior as we learn it.

## 8. Phases
| # | Deliverable | Exit criterion |
|---|---|---|
| 0 | skeleton + baseline VTracer | `plate trace --baseline` works (DONE) |
| 1 | Test run: SAM 3 + VLM + VTracer script on 5-10 images | Opened in Illustrator; written verdict on what works |
| 2 | Core engine: per-layer trace, primitives, named nested layers, emit | Beats baseline on layer-count + anchor metrics |
| 3 | Cache, sweep, report, batch, overrides | Re-tune loop is seconds |
| 4 | Hidden-shape completion | Moving a covering object reveals a complete shape |
| 5 | Benchmark vs Image Trace / Vectorizer.AI / VTracer | Published numbers + sample set |
| 6 | (optional) trained models | Only if 1-5 show a clear ceiling |

## 9. Risks
Hidden-shape completion quality with untrained models; gradients/shading; model
weight licenses (SAM 3, VLM) constrain redistribution; Illustrator quirks.

## 10. Prior art to study (do not copy blindly; check licenses)
VTracer 1.0 (MIT), LayerPeeler (SIGGRAPH Asia 2025; code partly unreleased),
AmodalSVG (2026), SemLayer (2026), StarVector, Vectorizer.AI (closed, benchmark target).


> Superseded in parts by `AGENTS.md`/`STATUS.md` (the pipeline in this spec is implemented; the AI stages are LM Studio VLM + optional SAM).
