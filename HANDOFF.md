# PLATE handover — 2026-10-29 (sessions 14–16 checkpoint)

Read `AGENTS.md`, then `STATUS.md`, then `ROADMAP.md`, then this file. This records
the immediate state at handover. Be skeptical of prose; verify with `pytest` and by
rendering.

## State at handover

- **This checkpoint commits sessions 14–16**, on `main`, based on `0a0fddc`.
  Commit title: `feat: recover straight and closed strokes and complete instrument panel`.
  Jessica explicitly requested the commit; no push was requested or made.
- Included source: `strokes.py`,
  `pipeline.py`, `complete.py`, `order.py`, `emit.py`, `metrics.py`, a config comment; tests: new
  `test_straight_strokes.py`, `test_occluded_strokes.py`, `test_parent_fragments.py`,
  `test_closed_strokes.py`, and the promoted panel marker in `tests/challenges.py`.
  Docs and the stroke-matcher diagnostic test are updated.
- **Tests: 199 passed, 6 xfailed** (strict expected structural gaps). Run with the
  renderer on:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q`
- No push. Commit/push only when Jessica asks (she asked for the commits below).

## Immediate continuation

Fix the documented 5px transparent-circle fragmentation before expanding loop
completion. Reproduced with a 420×320 image, circle (210,160), r115, width5:
295 opaque pixels lack a local assignment; nearest-label fallback borrows
transparency for 219 of them and produces four regions. Check wider existing
colour support only for unresolved pixels; preserve antialias blend rejection,
explicit palettes, speckle filtering and all independent targets. Then revisit
ROOT's inner ring and ORBIT's interrupted loops. Baseline verified again:
**199 passed, 6 xfailed** with the renderer enabled.

## Thin closed strokes (session 16, included in checkpoint)

- ROOT outer seal now matches its unchanged independent target as a native 18px
  circle stroke. **52 objects / 3 of 32 strokes / 559 anchors** (was 52/2/610).
  White/dark SSIM **0.9830/0.9863** (was **0.9806/0.9846**). Full ROOT target
  remains a strict xfail; its inner ring is merged/split among mint leaves.
- `fit_closed` requires one hole, one component, thin constant width (≤15% of the
  minimum radius), low boundary residual and full-footprint agreement. PNG coverage
  refines boundaries; ellipses use true Euclidean normal offsets. Small bites can
  complete beneath observed later shapes only with ≥90% free boundary and the
  completion switch on. Native circle/ellipse SVG emission and metrics support
  strokes. Thick rings/cutouts and off-centre/uneven holes are protected.
- Fit `Shape.full`, **not** the visible rim: a prototype using `vis` broke the
  instrument panel by converting full discs beneath smaller discs to annuli.
  Its independent contract caught this; final panel is byte-identical. A new
  nested-disc test guards hidden filled silhouettes. Opaque-background annuli
  remain ambiguous/full-disc + counter objects; do not casually reinterpret them.
- Thirteen new regressions; **199 passed, 6 xfailed** vs **186/6**. Original eight
  PLATE sample SVGs and every other challenge PLATE SVG are byte-identical. VTracer
  code is unchanged, but the ORBIT control varied across repeated identical runs
  (1473/3559 vs 1470/3745 objects/anchors); byte stability is not claimed for it.
- Latest benches: `/tmp/plate-closed-final-{samples,challenges}`; metrics
  `/tmp/plate-closed-final-metrics.json`. Rendered/inspected ROOT and all original
  samples; review sheets `plate-closed-ring.png`, `plate-closed-original-samples.png`
  in this chat's visualization folder. No target/golden edits.
- Next: interrupted loops and fragment reconciliation. ORBIT's back orbit is split
  into arcs; its front orbit's full silhouette is overfilled. ROOT inner ring
  shares colour with leaves and is fragmented/merged. Also a 5px transparent circle
  splits into four regions during segmentation, before this fitter runs. Complete
  transparent circles/ellipses at tested widths ≥6px work, including downscaling.

## Full instrument panel passes (session 15, included in checkpoint)

- **59 objects / all 27 strokes / 249 anchors / SSIM 0.9864** white and dark. The
  complete independent target passes unchanged: hidden silhouettes, styles, object
  types, topology and paint order. This is the first passing large composition.
- Straight fitting now accepts one hidden terminal under an aligned circular hub.
  Require real contact, relative T-junction evidence (15°), a fitted free cap, low
  free-boundary residual and source-colour support for the entire exposed core.
  Small gaps, taper and off-centre hubs are rejected; source scaling is tested.
- For a larger hub initially sorted before its needle, pipeline considers the
  earlier sibling circle only with T-junction support. Add stable paint edges
  **only after the stroke fit succeeds**. Do not reintroduce a broad order-stage
  fallback: it changed noisy_badge/shaded ordering despite rejected stroke fits.
- The extra object was an 861px navy chassis island. Merge a same-colour leaf
  into its immediate parent only when the parent's painted interior covers it and
  no earlier mask, fitted primitive or traced fringe needs its later repaint.
  A validated open stroke ignores filled-path bleed; otherwise use conservative
  trace bounds. Preserve pupils, transparent-hole islands and primitive residuals.
- Benchmarking caught unsafe early merge/order variants; all were corrected.
  **Only the panel SVG changes from session 14.** All eight original samples,
  every other challenge and every VTracer output are byte-identical. Targets and
  goldens are unchanged. `complete_hidden=false` now applies to curve endpoints too.
- Twenty-one new cases plus panel promotion: **186 passed, 6 xfailed** vs **164/7**.
  Latest bench folders: `/tmp/plate-hubs-final-{samples,challenges}`, metrics
  `/tmp/plate-hubs-final-metrics.json`. Reviewed images: `plate-completed-panel.png`
  and `plate-hubs-original-samples.png` in the chat visualization folder.

## Earlier straight-stroke work (session 14, included in checkpoint)

- `fit_straight` fits round-capped lines with PCA and bounded least squares.
  It uses source RGB antialias coverage or alpha, preserving Lanczos overshoot.
  Cap-local rectangle competition protects square-ended lettering; ellipse
  competition preserves genuine ellipses. The full proposed footprint is checked.
  Subpixel source boundaries are not distorted to match quantized region labels.
- Pipeline considers primitive approximations too, then retains the old open-curve
  fallback. Gradients/circles/holes/backgrounds are excluded. Straight endpoints
  touching later-painted circles are left alone until hidden-end fitting is added.
- Panel **24/27 strokes**, all 18 ticks and four screw slots independently matched.
  Anchors **303→259**, SSIM **0.9854→0.9862**. Remaining: three needles hidden by
  hubs, plus a separate **60-vs-59** object mismatch.
- Patch **1→7 strokes**, storefront **0→2**, ROOT **0→2** (anchors **902→610**,
  SSIM **0.9784→0.9806**). UI card has three recovered pill strokes, anchors
  **24→14**, SSIM **0.9714→0.9788**. Seven other original sample SVGs and all
  VTracer SVGs are byte-identical. Targets/goldens are unchanged.
- Fourteen regressions cover small/rotated/transparent strokes, independent ticks
  and slots, cap/ellipse/taper rejection, source scaling and disabling detection.
  Tiny opaque 3px marks without stable palette seeds can still vanish upstream;
  that separate thin-colour discovery gap is not fixed by stroke fitting.
- Benchmarks: `/tmp/plate-straight-final-{samples,challenges}`, baseline
  `/tmp/plate-straight-before-{samples,challenges}`, metrics
  `/tmp/plate-straight-final-metrics.json`. Reviewed images in the chat visualization
  folder: `plate-straight-strokes.png`, `plate-straight-original-samples.png`.

## Previous session 13 work (all committed)

First, the previous handover's verified-but-uncommitted work was committed as-is:
- `572983c` pool disconnected contours + merge flat fragments in completion (`edge_crossing_type` 7→5 objects).
- `f8a901c` three original logo challenge fixtures (EMBER/ORBIT/ROOT) + asset tests.
- `db027fe` docs for the above + `HANDOFF.md`.

Then two structural gaps were closed (each a root-cause fix, verified no-regression):

1. **`occlusion_chain` — chained-completion drift** (`ca92bbd`).
   The back disc completed via a Bézier bridge and drifted to (141.5,160.5) r93.1
   vs target (145,160) r95, because `complete.try_complete`'s occluder-coverage gate
   rejected the correct circle fit (RMS 0.25, 226° arc) at 89.6% vs the 90% floor —
   a disc hidden by a same-size neighbour legitimately recovers a ~10% sliver past
   the occluder. `evaluate()` now takes the fit residual and relaxes the coverage
   floors (Cm 0.90→0.85, Cv 0.70→0.65) ONLY for a primitive with RMS ≤ 0.5·tol; the
   bridge and weak fits keep strict floors, so shapes still cannot complete into mere
   neighbours. Back disc now (145.1,160.1) r94.6, drift 3.5px→0.1px.

2. **`perforated_plate` — compound-path topology** (`ccd6188`).
   `order._silhouettes` hole-filled a shape and removed only transparent pixels, so a
   genuine perforation containing a floating OPAQUE island (the middle hole holds a
   gold disc) kept the island's footprint as the plate colour — a stray 749px
   component. Now each hole-filled region is checked before transparency removal:
   a predominantly-transparent region (>50%) is a real perforation and is re-opened
   in full (island pixels dropped with it); mostly-opaque regions (a shape genuinely
   sitting behind another, e.g. a background under on-top shapes) stay filled so
   paint-order coverage is unchanged. Blue plate: 2 components → 1, three holes kept.

Both promoted from strict xfail. `overlap` stays <1px, `stack3` ordering/anchors
unchanged, donut evenodd ring intact, all eight original sample SVGs byte-identical.

## Remaining 6 gaps (all strict xfail; promote only when the independent target is met)

Current numbers in `STATUS.md`'s top table. In rough ROADMAP P1 order:

| Challenge | Gap |
| --- | --- |
| `complex_mission_patch` | 72 objects / 2 radial fragments / 7 strokes; target 45 with one radial planet + one linear hull, craters preserved |
| `complex_event_poster` | 83 objects; crossing lettering/ribbon/lines fragment underlying shapes |
| `complex_storefront` | 73 objects / 2 strokes; target 64, repeated windows/awning/lettering merge or fragment |
| `logo_ember_crest` | 51 objects (count matches) but shield full-silhouette IoU 0.8385; 2/7 strokes |
| `logo_orbit_wordmark` | 60 objects vs 34; orbital emblem + wordmark fragment; 3/7 strokes |
| `logo_root_seal` | 52 vs 56 objects; touching same-colour organics merge; 3/32 strokes, outer circle passes independently |

The next large stroke gap is **interrupted/merged closed loops**, especially ROOT
and ORBIT; logos need 7/7/32 strokes and recover 2/3/3. The panel's 27 strokes are complete.
Then address branched networks, other cap/join styles and non-circular/multiple
occluders. `stages/strokes.py` contains straight/open-curve and complete closed-loop recovery.

## Architectural decisions made with Jessica this session (IMPORTANT — honour these)

- **PLATE stays a CLASSICAL engine. It must run fully, correctly and deterministically
  with NO LM Studio, NO GPU, and NO heavy ML deps.** This is a hard invariant.
- **AI (LM Studio VLM) stays optional and cosmetic**: semantic names + grouping only,
  off by default (`vlm_url=""`), graceful fallback. It never touches geometry. Keep it
  that way. The ONE place a model could ever earn a geometric role is the provable
  "no signal" cases (splitting two touching same-colour shapes; merging posterized
  fragments that are semantically one object) — and only if a classical approach
  stalls. Do not force AI into segmentation/completion.
- **CPU only for now.** Jessica is interested in "use whatever hardware is available
  (CUDA/Metal/CPU)" for a future hosted converter, but explicitly chose to stick to
  CPU for now. Do NOT add GPU code. If revisited: build a device-capability layer with
  a guaranteed CPU fallback and within-tolerance CPU-parity tests, and PROFILE first —
  most of the hot path (contours, occlusion logic, Schneider fitting, VTracer) is
  branchy CPU code that does not move to GPU profitably; only palette assignment and
  bulk fits are GPU-shaped.

## Gotchas you will hit

- **System `python3` is 3.9 — too old.** Always use `.venv/bin/python` / `.venv/bin/pytest`
  (Python 3.11). `pip install -e ".[dev,render]"` is already done.
- **Rendering needs libcairo via a dyld shim on macOS.** The `plate` CLI self-handles it
  (re-exec with `DYLD_FALLBACK_LIBRARY_PATH`). But when you call the library directly in
  a script or run `pytest`, PREFIX with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`,
  or `have_renderer()` is False and all SSIM/silhouette checks silently skip.
- **git commits hang unless you bypass the commit template.** `commit.template` is set to
  `~/.stCommitMsg` and blocks non-interactive commits in this shell (symptom: the commit
  command hangs/times out and HEAD does not move). Commit with:
  `GIT_EDITOR=true git -c commit.template= -c core.editor=true -c gpg.program=/tmp/gpg-batch.sh commit -F <msgfile>`
  where `/tmp/gpg-batch.sh` is a wrapper: `#!/bin/sh` + `exec /opt/homebrew/bin/gpg --batch --no-tty "$@"`.
  GPG signing is ENABLED (`commit.gpgsign=true`); default gpg blocks on pinentry, so the
  `--batch --no-tty` wrapper is required. Do NOT change git config; these are per-invocation `-c` flags.
- **`try_complete` is imported by name into `order.py`, `gradient.py`.** Monkeypatching
  `complete.try_complete` won't intercept those call sites; patch `order.try_complete` etc.
- **`tests/challenges.py` strict-xfail contract:** a gap that starts passing causes a strict
  XPASS that FAILS the suite until you remove its `gap=` marker. That is intended — it forces
  you to consciously promote a fixed gap. Never edit a `.target.svg` to match pipeline output.

## Verification discipline (from AGENTS.md)

1. `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q` green before and after.
2. For any pipeline change, also `plate bench samples` AND `plate bench samples/challenges`,
   confirm the eight original samples stay byte-identical (or record the fidelity delta
   honestly), and render/inspect changed SVGs. Never remove the plain-VTracer baseline (`baseline.py`).
3. Add a regression test for every fix. When a gap closes, promote it (remove the `gap=`).

## Commands

```sh
cd /Volumes/Code/PLATE
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate bench samples -o /tmp/plate-bench
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate bench samples/challenges -o /tmp/plate-challenge-bench
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/plate doctor   # deps + LM Studio
```

## Still unverified (need a human / real inputs)

- **Illustrator import** (`docs/illustrator-checklist.md`): do top-level `<g>` become named
  layers, are circles/rects/gradients live and editable? Oldest open P0.
- **Real-world corpus**: gather 10–20 logos/clipart/scans into `samples/real/`, `plate bench`.
- Real LM Studio naming/grouping IS verified (qwen/qwen3.8-27b); naming accuracy (left/right
  eye) and ~6s/shape latency remain open. Do not repeat the stale "mock only" claim.
