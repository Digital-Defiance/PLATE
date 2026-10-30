# PLATE handover — 2026-10-29 (session 13)

Read `AGENTS.md`, then `STATUS.md`, then `ROADMAP.md`, then this file. This records
the immediate state at handover. Be skeptical of prose; verify with `pytest` and by
rendering.

## State at handover

- **HEAD: `7aa28ae`** (`docs: record compound-path topology fix (perforated_plate)`), branch `main`.
- **Working tree is CLEAN.** Everything is committed and GPG-signed. There is NO
  pending uncommitted work this time (unlike the previous handover).
- **Tests: 150 passed, 7 xfailed** (strict expected structural gaps). Run with the
  renderer on:
  `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q`
- No push. Commit/push only when Jessica asks (she asked for the commits below).

## What changed this session (all committed)

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

## Remaining 7 gaps (all strict xfail; promote only when the independent target is met)

Current numbers in `STATUS.md`'s top table. In rough ROADMAP P1 order:

| Challenge | Gap |
| --- | --- |
| `complex_instrument_panel` | 60 objects / 2 strokes; target 59 with **27 editable strokes** (straight marks, closed loops, branched nets, cap/join inference) |
| `complex_mission_patch` | 72 objects / 2 radial fragments; target 45 with one radial planet + one linear hull, craters preserved |
| `complex_event_poster` | 83 objects; crossing lettering/ribbon/lines fragment underlying shapes |
| `complex_storefront` | 73 objects; target 64, repeated windows/awning/lettering merge or fragment |
| `logo_ember_crest` | 51 objects (count matches) but shield full-silhouette IoU 0.8385; 2/7 strokes |
| `logo_orbit_wordmark` | 60 objects vs 34; orbital emblem + wordmark fragment; 3/7 strokes |
| `logo_root_seal` | 52 vs 56 objects; touching same-colour organics merge; 0/32 strokes |

The single biggest lever across these is **stroke coverage** (ROADMAP P1 #2):
panel needs 27 strokes and has 2; logos need 7/7/32 and recover 2/3/0. Straight
marks currently stay as live rects/polygons; closed/branched strokes are unimplemented.
`stages/strokes.py` is where open-curve stroke recovery lives today.

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
