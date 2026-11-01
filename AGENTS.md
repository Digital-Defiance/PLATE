# AGENTS.md — handoff for a coding agent (local LLM or otherwise)

You are continuing **PLATE**, a CLI that converts raster images to Illustrator-friendly layered SVG. Read this file, then `STATUS.md`, then `ROADMAP.md`. Be skeptical: verify with tests and by rendering, don't trust docs blindly.

## Ground rules
- Python ≥3.10, deps: numpy, scipy, opencv, pillow (+cairosvg/scikit-image for render/metrics). No heavy ML deps in core.
- Run `pytest -q` before and after every change. Add a test for each bug fixed. Keep it green.
- Visual check is mandatory for pipeline changes: `plate bench samples -o /tmp/b` then open `/tmp/b/*.plate.svg` (or `plate trace X --report`).
- Never commit/push unless the owner (Jessica) asks. At end of session update `STATUS.md`.
- Don't delete the plain-VTracer baseline; it is the control in `plate bench`.
- Prefer small, measurable changes; every change should move a number in `plate bench` or `plate bakeoff` (see `docs/BAKEOFF.md`). Don't tune the bake-off weights to flatter PLATE; fix the weakness instead.

## Map of the code (`src/plate/`)
| file | role |
|---|---|
| `config.py` | frozen `Config` dataclass = all levers; `PRESETS`; `load()` (preset → toml → CLI) |
| `imageio.py` | load, resize to `work_size`, auto bilateral denoise (`noise_fraction`) |
| `stages/segment.py` | palette + coverage-based edge assignment → `Shape`s |
| `stages/order.py` | containment tree, occlusion test (calls complete), topological paint order, bleed |
| `stages/complete.py` | amodal completion (T-junction test, circle/ellipse/rect/Bézier bridge) |
| `stages/primitives.py` | `snap` (circle/ellipse/rect/rrect/polygon), `snap_ring`, `normalize` |
| `stages/trace.py` + `bezier.py` | sub-pixel contours, corners, Schneider fit |
| `stages/name.py`, `stages/emit.py` | names; SVG writer (id + data-name + inkscape:label; top-level groups = layers) |
| `pipeline.py` | `run(path, cfg, labels)` orchestrates; returns `Result` (svg, nodes, shapes, stats) |
| `vlm.py` | LM Studio client: `name_shapes`, `group_shapes`, `apply_groups`, `describe` |
| `metrics.py`, `report.py`, `raster.py` | editability + fidelity metrics, HTML report, cairosvg render |
| `bakeoff/` | `corpus.py` (synthetic truth scenes), `score.py` (metrics, composite, weights), `adapters.py` (plate/vtracer/potrace + external discovery), `runner.py` (run, summary, profiles, HTML report) |
| `cli.py` | trace / batch / sweep / bench / corpus / bakeoff / doctor |
| `tests/` | `test_bakeoff.py`, `test_pipeline.py` (ground truth), `test_vlm.py` (+`mock_vlm.py`), `test_config.py` |
| `scripts/make_samples.py` | generates synthetic `samples/*.png` (has ground truth numbers) |

## Conventions (easy to get wrong)
- Internal coords are **pixel-centre** (pixel i at integer i). SVG output = `(x+0.5)/scale`; `scale = work_px/source_px`.
- `Shape.full` = complete silhouette (after amodal completion), `Shape.vis` = visible pixels, `Shape.draw` = what gets traced (full + restricted bleed). Primitives are snapped from `full`, paths traced from `draw`.
- Children list order = paint order bottom→top. Background = root covering ≥60% of canvas, kept as its own layer.
- Occlusion decisions use the *relative* T-junction angle test (`complete._occludes`, threshold 15°), validated by a parameter sweep; don't replace with absolute-angle tests (they failed).
- Primitive snap accepts by mean boundary deviation = |xor|/perimeter; polygons need ≤14 vertices and 0.45×tolerance (tight, so curved shapes stay Béziers).
- Illustrator 30.8.2: 24 cases/636 native checks pass, including actual layers and AI round trips. Top-level groups need Adobe `i:layer="yes"` (10.0 namespace) as well as Inkscape markers; standalone roots use layer containers, nested semantic groups stay groups. See `docs/illustrator-checklist.md`. This does not certify all PNG reconstruction; 7 structural gaps remain.

## Environment note
The original author's sandbox could not reach LM Studio; later sessions verified a real naming/grouping connection (see `STATUS.md`). Automated tests use `tests/mock_vlm.py`; current live availability was not rechecked in the project audit. LM Studio serves an OpenAI-style API at `http://localhost:1234/v1` (start the server in the LM Studio "Developer" tab and load a vision model).

## Suggested first session
1. `pip install -e ".[dev,render]" && pytest -q && plate bench samples`; then `plate corpus -o /tmp/bo/corpus && plate bakeoff /tmp/bo/corpus/images --truth /tmp/bo/corpus/truth -o /tmp/bo/out` to see the objective bake-off scores (PLATE vs VTracer/Potrace; `docs/BAKEOFF.md`).
2. Do the P0 items in ROADMAP.md (real LM Studio naming accuracy/latency, real-image corpus). Record outcomes in STATUS.md.
3. Then the bake-off-driven P1 items in ROADMAP (JPEG robustness, same-colour splitting, rect/polygon completion). Re-run `plate bakeoff` after each and update `docs/BAKEOFF.md`.
