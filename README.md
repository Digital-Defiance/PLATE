# PLATE — Primitive-aware Layered Amodal Tracing Engine

Local, open-source CLI that turns a PNG/JPG into an **Illustrator-friendly SVG**: real objects,
named nested layers, correct stacking order, hidden parts completed, and true primitives
(a circle is one `<circle>` with 4 anchors — not 90 path points). By Digital Defiance (501(c)(3)). MIT.

> Status: working classical engine (v0.0.1). AI naming/grouping via LM Studio is implemented but
> **untested against a real LM Studio** (only a mock). See `STATUS.md` and `ROADMAP.md`.
> Picking this up with a coding agent? Start with **`AGENTS.md`**.

## Install (macOS, Python ≥ 3.10)
```bash
cd /Volumes/Code/PLATE
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,render]"     # dev = pytest, render = cairosvg + scikit-image (metrics/reports)
plate doctor                        # checks deps and whether LM Studio is reachable
pytest -q                           # 11 tests should pass
```
(`cairosvg` needs the cairo library: `brew install cairo` if rendering fails.)

## Use
```bash
plate trace logo.png -o logo.svg --report         # + logo.report.html (source vs SVG, layer tree, metrics)
plate trace art.jpg --preset illustration
plate trace art.png --set simplify=1.2 --set max_colors=12     # ANY lever via --set
plate trace art.png --vlm-url http://localhost:1234/v1         # semantic names + groups via LM Studio
plate batch ./pngs -o ./svgs                                   # folder, keeps structure
plate sweep art.png simplify 0.4 0.8 1.6                       # try a lever, tabulate anchors vs SSIM
plate bench samples                                            # PLATE vs plain VTracer, editability + fidelity
plate trace art.png --baseline                                 # plain VTracer control
```
Per-image overrides: put `art.plate.json` next to `art.png` (e.g. `{"simplify": 2.0, "max_colors": 8}`).

## What it does (pipeline)
1. **Segment** – exact flat-colour palette (Lab-merged), anti-aliased edge pixels assigned by colour coverage; auto bilateral denoise for noisy/JPEG input.
2. **Contain** – nesting tree (parent = smallest silhouette containing the shape) → nested Illustrator groups.
3. **Occlusion + amodal completion** – T-junction test finds which neighbour hides which shape; the hidden outline is reconstructed (circle/ellipse/rect fit, else tangent-continuous Bézier).
4. **Paint order** – topological sort; small restricted bleed under later shapes to avoid hairline seams.
5. **Primitive snapping** – circle, ellipse, rect, rounded rect, polygon (≤14 vertices), ring (two circles, even-odd); otherwise
6. **Bézier tracing** – sub-pixel contours, corner detection, Schneider fit → minimal anchors.
7. **Names** – classical ("Navy circle") or semantic via a local VLM (optional). Output has `id`, `data-name`, `inkscape:label`.

## Measured (`plate bench samples`, synthetic set; lower anchors/shape is better)
| image | PLATE anchors (/shape) | VTracer anchors (/shape) | PLATE prim% | SSIM P / V |
|---|---|---|---|---|
| overlap | 12 (4.0) | 27 (9.0) | 100 | .994 / .990 |
| stack3 | 16 (4.0) | 56 (14) | 100 | .997 / .986 |
| face | 44 (5.5) | 82 (10) | 100 | .993 / .991 |
| badge | 86 (8.6) | 389 (32) | 70 | .944 / .961 |
| ui_card | 24 (4.8) | 198 (33) | 100 | .971 / .991 |
| noisy_badge | 115 (11.5) | 2707 (13) | 70 | .868 / .891 |
| shaded (gradient) | 77 | 31 | 93 | .918 / .934 |

Honest read: big wins on editability for flat art; slightly lower pixel fidelity on some; gradients/photos are out of scope for now.

## Levers
See `src/plate/config.py` (every lever documented in-line, presets: logo, illustration, lineart, max, compact).

## Docs
`AGENTS.md` (handoff) · `ROADMAP.md` · `STATUS.md` · `docs/SPEC.md` · `docs/METRICS.md` · `docs/illustrator-checklist.md`
