# PLATE handover — 2026-10-29

Read `AGENTS.md`, `STATUS.md`, then `ROADMAP.md`. This file records the immediate
handover state. Jessica asked for complex logo fixtures and another handover;
both are prepared. **The logo images are finished on disk. No image-generation
service or ability is needed to continue.**

## Finished logo assets

All live in `samples/challenges/`, as transparent PNG + independently authored
desired `.target.svg` pairs:

- `logo_ember_crest`: 800×960, 51 objects, 7 strokes. Faceted fox, shield with four
  true cutouts, 12 laurel leaves, layered ribbon and outlined EMBER.
- `logo_orbit_wordmark`: 1200×480, 34 objects, one radial gradient, 7 strokes.
  Compound monogram, crossing orbital ellipses, satellites and ORBIT/STUDIO lettering.
- `logo_root_seal`: 900×900, 56 objects, 32 strokes, no gradients. Organic tree,
  15 leaves/veins, branches/roots, counter-cut trunk, circular strokes and ROOT.

Generator: `scripts/make_logo_challenges.py` (reuses `Scene` and the custom glyphs
from `scripts/make_complex_scenes.py`). It authors SVGs, renders at 4×, downsamples
with Lanczos and preserves alpha. No fonts, external assets or PLATE output.
Do not overwrite targets with generated pipeline SVGs to make tests pass.

Preview already visually reviewed:
`/Users/jessica/.codex/visualizations/2026/10/29/01a1897a-34f5-7170-b9dc-01807c8b7ce2/plate-complex-logos.png`

## Verification and current failures

Full suite after logo integration: **148 passed, 9 strict expected structural gaps**.
Integrity and fidelity tests remain active for expected gaps. Tests require the
render extra/libcairo for silhouette matching. Local mock HTTP-server tests need
sandbox escalation in this environment; that has been approved routinely.

| Logo | Actual / desired objects | Actual / desired strokes | SSIM white / dark | First structural failure |
| --- | --- | --- | --- | --- |
| EMBER | 51 / 51 | 2 / 7 | 0.9662 / 0.9678 | shield full-silhouette IoU 0.8385 |
| ORBIT | 60 / 34 | 3 / 7 | 0.9787 / 0.9846 | fragmented emblem/lettering |
| ROOT | 52 / 56 | 0 / 32 | 0.9784 / 0.9836 | merged/lost organic shapes and strokes |

The other six gaps: perforated plate topology; chained-circle drift; complex
mission patch, storefront, instrument panel and event poster. See STATUS's top
table for current numbers. New logo fidelity floors: EMBER 0.96, ORBIT/ROOT 0.97.
Nine asset checks protect exact target inventories, dimensions, portable vectors,
true transparency and pixel-identical PNG/SVG pairing.

Bench ran with plain VTracer preserved:
`/tmp/plate-logo-bench/` and `/tmp/plate-logo-bench.txt`.
Detailed logo-only baseline: `/tmp/plate-logos/baseline.json`.
Temporary artifacts may disappear; source PNGs/SVGs and this note are in the repo.

## Git and existing uncommitted work

HEAD: **`4da8ab0 fix: merge compatible gradient fragments behind occluders`**.
Previous commit: `03a133f feat: recover thin curves and editable SVG strokes`.
No push. No commit was requested in the logo turn, so keep current work uncommitted
until Jessica asks. Inspect `git status`; do not discard any pending changes.

Pending work includes the prior session's verified completion implementation:

- `complete.py` pools external contours of disconnected shapes/occluders; relative
  T-junctions are computed within each contour, never across component boundaries.
  Bézier bridging remains restricted to one contour.
- `order.merge_fragments` rejoins flat same-colour siblings only after supported
  primitive, containment and hidden-area checks. `Segmentation.rebuilt` reindexes
  ownership and clears stale ordering/completion fields. Pipeline reruns ordering.
- `edge_crossing_type` was promoted to passing unchanged: 7→5 objects, 55→36 anchors,
  SSIM 0.9914→0.9931. Badge SSIM 0.9922→0.9924. Original sample SVGs and all VTracer
  outputs were byte-identical; no target or golden refreshes.
- Tests: `tests/test_fragment_completion.py` and an added geometry regression.
- New logo generator, six PNG/SVG files, `tests/test_logo_assets.py`, challenge
  registrations and updated README/ROADMAP/STATUS/docs are also pending.

## Next work

1. Use the new logos to test stroke/compound-path/completion changes. ROOT exposes
   missing closed strokes, thin veins and touching same-colour branches. EMBER
   demonstrates why correct object counts alone are insufficient.
2. Mission-patch gradient recovery needs coherent outer/clamped bands **and crater
   preservation**. The third crater at (515,470) is already absorbed into a detected
   gradient; simple colour-based growth would erase hard-edged objects. Joining
   only the two detected gradients still fails safely. Current patch: 72 objects,
   2 radial fragments instead of a radial planet plus linear hull, SSIM 0.9815.
3. A thin bar split by a perpendicular cover can fail completion because rasterized
   perimeter pixels dominate hidden-area checks. Fix pixel-boundary evaluation
   before relaxing any containment/occlusion thresholds.
4. Per-object challenge diagnostics remain useful: the matcher currently stops on
   object-count errors, concealing partial progress. Keep targets independent.

Illustrator import and a real-image corpus remain unverified. Real LM Studio
naming/grouping was verified earlier; do not repeat the stale AGENTS environment
claim that only mocks have ever run. No core heavy ML dependency should be added.

## Commands

```sh
cd /Volumes/Code/PLATE
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python scripts/make_logo_challenges.py
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate bench samples/challenges -o /tmp/plate-logo-bench
```

Run pytest before and after changes. For pipeline changes also benchmark original
`samples/` and inspect rendered SVGs. Never remove the plain-VTracer baseline.
