# ROOT seal & complex storefront structural-gap investigation — addressable vs information limit

**Mode:** read-only. No engine, target, test, golden or doc file was modified. All probes
lived under `/tmp` (not committed). Repo state: `main @ e2c612d`, working tree clean
(`git -C /Volumes/Code/PLATE status` empty before and after).

Both PNGs map 1:1 to their viewBox — `logo_root_seal.png` is 900×900 and its target
viewBox is `0 0 900 900`; `complex_storefront.png` is 960×800 and its viewBox is
`0 0 960 800` — so **authored SVG coordinates sample directly as raster pixels**. The
pipeline runs at `work_size=1536` (default `Config()`), so the working scale is
**1536/900 = 1.7067** for ROOT and **1536/960 = 1.600** for the storefront. Stroke widths
below are given in both authored (source) and working pixels.

Diagnostics reproduced with the trustworthy per-object report (commit 5692fa9):
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python -m challenge_report <name>`.

---

## Summary answer

**The dominant gaps in both targets are classical same-colour merges — genuine information
limits, exactly the EMBER class — not thin-feature losses and not addressable under the
existing gates.** The measured headline:

- **ROOT: all 12 missing roots/branches survive segmentation as pixels and are one single
  `#182e4c` connected component with the trunk** (comp 1, 22 705 px, bbox x[273–626]
  y[179–649], spanning every root tip down to y≈649 and every branch up to y≈179). They are
  **not** below the stroke floor — their measured working widths are 8.7–21.8 px, far above
  any floor. They are same-colour navy strokes fused to the same-colour navy trunk. **LIMIT.**
- **ROOT leaf-4 + leaf-5** are two adjacent **`#267d83`** leaves that render as one teal
  component (11 180 px). Same-colour touching organics, like EMBER's cheeks. **LIMIT.**
- **ROOT leaf-vein-11 SPLIT** is a thin-feature *tracing* artefact, not a merge: the cream
  vein is present and continuous in the raster (cream along its whole length) but is emitted
  as two primitives. A real but minor stroke-fit fragmentation, **addressable in principle**,
  not an information limit.
- **ROOT 7 Beige_\* extras**: 6 are `#a9d1b5` fragments of the **inner-seal-stroke** ring
  (all measured at r≈275 from (450,370)); 1 (+the vein split pieces) are `#efebd7` vein
  debris. The inner-seal is a thin interrupted *circular* stroke ring — the
  ORBIT/laurel-stem compound-ring family. **Addressable only as a scoped new-geometry change
  (the optional compound-ring arm already discussed), not a gate-preserving quick win.**
- **STOREFRONT 5 missing awning panels (2,4,10,12,14 — the even indices)**: the awning
  alternates red `#bb4b45` (odd) and cream `#f5edda` (even). **The cream panels are the same
  colour as the `#f5edda` background.** Panels 2+4 fuse into one cream component (12 873 px),
  10+12 into another (12 806 px), and **panel-14 fuses straight into the background** (comp 1,
  264 393 px). The odd red panels are distinct and all match. Same-colour merge. **LIMIT.**
- **STOREFRONT plant-leaf merges**: plant-1-leaf-1 + plant-1-leaf-3 are both `#267d83` and
  render as one teal component (4 543 px); plant-2-leaf-1 + plant-2-leaf-3 are both `#267d83`
  and render as one teal component (29 709 px) that also fuses into the teal building. Same
  colour touching leaves, like EMBER. **LIMIT.**
- **STOREFRONT 17 extras**: 11 teal, 3 cream, 2 navy, 1 gold — all over-segmentation of
  *already-matched* visible objects (the building fragmented by its windows/sign/awning/door,
  the cream background/awning, the navy sign between letters, the sun clipped by the roof).
  Thin-feature / letter-interruption fragmentation, the EMBER/poster class. Not a
  hidden-compound merge.

**Bottom line.** ROOT's and the storefront's structural deficits are **overwhelmingly
genuine classical information limits**: same-colour strokes/fills authored with no separator
render as single contiguous regions that no classical pass can carve without inventing
geometry. The only *engine-addressable* items are (a) the ROOT inner-seal interrupted-ring
family (an optional, scoped compound-ring/ellipse extension — the same family the
patch-orbit investigation ranked as new geometry, *not* a gate-preserving win) and (b) the
ROOT leaf-vein-11 thin-stroke split (a small tracing improvement). **Recommendation: pin the
same-colour merges (ROOT tree, ROOT leaf-4+5, storefront cream awnings, storefront teal
leaves) as documented information limits, mirroring EMBER; leave the inner-seal ring and the
vein split as noted optional scoped work. Do not weaken any gate, edit targets/goldens, or
use the VLM for geometry.**

---

## Per-family verdict tables

### logo_root_seal

| family | authored object(s) | measured cue | verdict | if ADDRESSABLE: stage + rule + gate-admits? / if LIMIT: pin assertion |
|---|---|---|---|---|
| tree strokes (roots+branches) | root-1..6, branch-1/2/3/6/7 (all `#182e4c`, w 6–10 src) | all 11 midpoints are `#182e4c` and lie in **comp 1 (22 705 px)**, the SAME component as the trunk; measured working widths 8.7–21.8 px (well above any floor) | **LIMIT** (same-colour merge, EMBER class) | pin: the trunk + all authored root/branch strokes are ONE 8-connected `#182e4c` component (probe the trunk at (450,500) and e.g. root-5 at its on-path midpoint, branch-3 at its midpoint → same label); they are not below any width floor, so the authored sub-strokes exist only in the vector source |
| twin teal leaf merge | leaf-4, leaf-5 (both `#267d83`) | both leaf interiors land on teal **comp 2 = 11 180 px** (one region); the leaf between them that could separate (leaf-3) is a *different* colour `#a9d1b5` | **LIMIT** (same-colour touching organics) | pin: leaf-4 interior (~(450,135)) and leaf-5 interior (~(498,150)) share ONE 8-connected `#267d83` component |
| leaf-vein-11 split | leaf-vein-11 (`#f5edda` stroke, w3 src ≈ 3.4 px measured work) | cream is CONTINUOUS along the whole authored vein path (sampled t=0→1, all cream, tol 24); the vein is **present** but emitted as two primitives (`Beige_rectangle_2` 3×54 rect + `Beige_ellipse_3`) | **ADDRESSABLE in principle** (thin-stroke tracing fragmentation, not a merge) | stage: `stages/trace`+`stages/strokes` (thin curved stroke broken at the bend). The EXISTING stroke gates (`fit_stroke` needs width ≥ 2 px and `mask.area ≥ 24·r²`; this ~3.4 px vein is marginal) do **not** admit it as one stroke today. A real but minor, scoped stroke-recovery improvement — not a gate-preserving quick win and not required to resolve this audit |
| mint inner-seal fragments | inner-seal-stroke (`#a9d1b5` circle r=275, w5 src) | 6 extras (`Beige_rectangle`, `_3`, `_4`, `_5`, `Beige_rounded_rectangle`, `Beige_shape_8`) all measured at **r = 274.4–275.0** from (450,370); the mint ring is broken into 22 disconnected components and 46/360 ≈ 13 % of its circumference is interrupted by the crossing navy branches/roots and leaves; it matched as an open arc at IoU 0.27 | **ADDRESSABLE only as scoped NEW geometry** (interrupted-ring compound family) | stage: `order._merge_compound_siblings` (circle arm) / `merge_ring_ellipses`. This is the laurel-stem/ORBIT compound-ring family explicitly called out. It is a *circle* ring (r=275), so the circle arm is the right owner, but reuniting it is new scoped work with its own regression test and `challenge_report` number — the same disposition the patch-orbit investigation gave: **not** a gate-preserving quick win. Not required to resolve this audit |
| `#efebd7` vein debris | leaf-vein-11 pieces | `Beige_ellipse_3` (ellipse) + `Beige_rectangle_2` (3×54 rect), `#efebd7` | same as the leaf-vein-11 split row (tracing fragmentation) | — (covered by the vein-split row) |

### complex_storefront

| family | authored object(s) | measured cue | verdict | if ADDRESSABLE: stage + rule + gate-admits? / if LIMIT: pin assertion |
|---|---|---|---|---|
| cream awning panels | awning-panel-2/4/10/12/14 (all `#f5edda`); odd panels are `#bb4b45` | odd red panels are each a distinct `#bb4b45` component (all match); **cream panels are the same colour as the `#f5edda` `background`**: panels 2+4 → one component 12 873 px, 10+12 → one 12 806 px, **panel-14 → the background component (264 393 px)** | **LIMIT** (same-colour merge; alternation survives only because red≠cream) | pin: adjacent cream awning panels share ONE `#f5edda` component with each other (probe panel-2 body (205,410) and panel-4 body (305,410) → same label) and panel-14 (805,410) shares the background's label (probe (10,10)); a red panel between two creams (e.g. panel-3 at (255,410)) is a SEPARATE `#bb4b45` component |
| left teal leaves | plant-1-leaf-1 + plant-1-leaf-3 (both `#267d83`) | both centres land on teal **comp 13 = 4 543 px** (one region, bbox x[93–156] y[527–639], standalone — clear of the building); separating leaf-2 is `#a9d1b5` | **LIMIT** (same-colour touching leaves) | pin: plant-1-leaf-1 centre (120,610) and plant-1-leaf-3 centre (140,580) share ONE 8-connected `#267d83` component |
| right teal leaves | plant-2-leaf-1 + plant-2-leaf-3 (both `#267d83`) | both centres land on teal **comp 9 = 29 709 px** (bbox x[555–836]); the leaves (cx 800/820, rx 17) overrun the building's right edge (x=790) and fuse into the same-colour `#267d83` building too | **LIMIT** (same-colour touching leaves + same-colour building) | pin: plant-2-leaf-1 centre (800,610) and plant-2-leaf-3 centre (820,580) share ONE `#267d83` component, and that component also contains a building-interior probe to its left, confirming the fuse |
| 17 extras | building / background / shop-sign / sun | 11 teal `#267d83` (building slivers between awning scallops, window frames, sign, door — e.g. Teal_polygon at y443–465, Teal_shape_6/7/8 at y454); 3 cream `#f5edda` (awning-end / background slivers); 2 navy `#182e4c` (sign pockets between shop-letters at y342–373); 1 gold `#e9bc59` (sun clipped by the roof at y≈175) | **LIMIT / over-segmentation of matched objects** (thin-feature + letter interruption) | not a hidden-compound merge: each family is the leftover pockets of an already-matched, fully-visible object cut by overlaid art (same class as EMBER's name-ribbon and the poster's letter counters). No reusable classical cue; `_merge_compound_siblings` would not admit them (no common circle/ellipse, side-by-side tiles). No pin needed beyond the family pins above |

---

## Evidence

### ROOT Q1 — the 12 missing roots/branches are a same-colour merge, not thin-feature loss

Authored (`samples/challenges/logo_root_seal.target.svg`): roots and branches are all
`#182e4c` open strokes, widths 6–10 src px, drawn radiating from the same `#182e4c`
`trunk-with-transparent-counter` fill. Measured on the PNG (`#182e4c`, tol 24, α≥128,
`scipy.ndimage` 8-connectivity):

- The whole navy artwork is **7 components**; the largest is **comp 1 = 22 705 px**, bbox
  **x[273–626] y[179–649]**. The trunk probe (450,500), every root on-path midpoint and
  every branch on-path midpoint return **comp 1** — one contiguous navy region. (Comps 4–7
  are the four `#182e4c` outlined-name letters at y≥734; comps 2–3 are two ~300 px specks.)
- Measured perpendicular band widths at the authored path midpoints (source → working):
  root-1 12.8→21.8, root-2 9.9→16.9, root-3 6.1→10.5, root-4 5.1→8.7, root-5 6.0→10.2,
  root-6 6.1→10.5, branch-1 7.4→12.6, branch-2 8.1→13.9, branch-3 8.0→13.7, branch-6
  8.1→13.9, branch-7 7.8→13.2. **Every one is far above the stroke-width floors** (the
  robustness pins put the floor around 1.5–2 working px). So these are **not** below-the-floor
  thin strokes, not speckle-filtered, and not dropped by edge dilation — they are present as
  pixels and simply fuse into the trunk because they are the **same colour touching the same
  colour** with no separator. This is the EMBER same-colour-merge class, not a thin-feature
  loss. No classical pass in `segment.py` (one region per colour-blob),
  `order.py`/`complete.py` (which only ever *merge* same-colour siblings or complete *hidden*
  parts) can carve the authored sub-strokes out of one contiguous navy blob without inventing
  the cut lines.

**Verdict: LIMIT.**

### ROOT Q2 — leaf-4 + leaf-5 merge; leaf-vein-11 split

- **leaf-4 + leaf-5 (both `#267d83`).** leaf-4 (translate 450,180 rot 0) and leaf-5
  (translate 505,190 rot 15) are adjacent and the **same** teal. Both interiors land on teal
  **comp 2 = 11 180 px** — one region. The leaf that sits between them, leaf-3, is
  `#a9d1b5` (a different colour) and so cannot act as a separator between the two teal leaves
  where they overlap. Identical to EMBER's cheeks/muzzle: two same-colour organics touching
  → one raster component. **Verdict: LIMIT.**
- **leaf-vein-11 split (`#f5edda` stroke, w3 src).** Sampling `#f5edda` (tol 24) along the
  authored vein path (`M-1 -13 Q-16 -43 -12 -81` under translate 510,340 rot 20), **every**
  sampled point t=0→1 is cream — the vein is fully present in the raster. Its measured band
  width is ≈2.0 src ≈ 3.4 working px. It is emitted as **two** primitives
  (`Beige_rectangle_2` 3×54 rect + `Beige_ellipse_3`), i.e. a thin curved stroke broken at
  its bend during tracing/stroke-fit, not a colour merge and not a loss. **Verdict:
  ADDRESSABLE in principle** (a scoped thin-stroke tracing improvement). The current stroke
  gates (`strokes.fit_stroke`: `width ≥ 2`, `mask.area ≥ 24·r²`, single component) do not
  recover a ~3.4 px curved vein as one stroke today; admitting it is its own measured change,
  not a gate-preserving quick win, and not required to close this audit.

### ROOT Q3 — the 7 Beige_\* extras

Emitted geometry (from `pipeline.run(...)`), by colour:

- `#a9d1b5` (6): `Beige_rectangle` (375,639 72×5), `Beige_rectangle_3` (324,622 46×5),
  `Beige_rectangle_4` (549,601 5×46), `Beige_rectangle_5` (283,598 35×5),
  `Beige_rounded_rectangle` (469,94 30×5), `Beige_shape_8` (path near (453,645)). All measured
  **r = 274.4–275.0 from (450,370)** — they lie on the **inner-seal-stroke** circle (r=275).
  The mint ring is broken into **22 disconnected components** (sizes 3850, 2366, 1495, …) and
  **46/360 ≈ 13 %** of its circumference is non-mint, interrupted where the crossing navy
  branches/roots and the leaves pass over it. The ring matched only as an open arc
  (`Beige_stroke_6`, IoU 0.2715, topology holes 0 vs wanted 1).
- `#efebd7` (the vein debris, `Beige_ellipse_3` + `Beige_rectangle_2`): the leaf-vein-11
  split pieces (see Q2).

The mint family is **the interrupted-ring compound family** — a thin same-colour ring sliced
by crossing occluders. It is a *circle* (r=275), so `order._merge_compound_siblings`'s circle
arm is the correct owner, but reuniting it is **scoped new geometry** with its own regression
test and benchmark number (the disposition the patch-orbit investigation assigned to the
analogous family), **not** a gate-preserving quick win, and explicitly optional. It is the
"laurel-stem-style ORBIT/ellipse compound-merge family already discussed."

### STOREFRONT Q4 — the 5 missing awning panels (even indices)

Authored: `awning-panel-N` alternate `#bb4b45` (odd N) and `#f5edda` (even N); the scene
`background` is `#f5edda`. Measured at each panel body (start = 130+50·(N−1), centre x =
start+25, y=410; `#` tol 24, 8-connectivity):

- **Red panels (odd)** are each a distinct `#bb4b45` component (sizes ~3050–4250) → all match.
- **Cream panels (even)** collapse: panel-2 and panel-4 both → **component 12 (12 873 px,
  bbox x[180–349] y[375–619])**; panel-10 and panel-12 both → **component 13 (12 806 px)**;
  **panel-14 → component 1 (264 393 px) = the background** (the corner probe (10,10) returns
  the same label, and `panel-14 == background` is True). panel-6 and panel-8 happen to stay
  distinct (boxed in by surrounding non-cream art) and match.

So the awning's alternation is only recoverable for the red stripes; the cream stripes are
the **same colour as each other and as the `#f5edda` background**, drawn abutting with no
separator, so they fuse. This is a textbook same-colour merge (EMBER class). **Verdict:
LIMIT.**

### STOREFRONT Q5 — the plant-leaf merges

Authored leaves are ellipses (rx 17, ry 53). Measured centres (8-connectivity):

- Left plant: plant-1-leaf-1 (`#267d83`, 120,610) and plant-1-leaf-3 (`#267d83`, 140,580)
  both → teal **comp 13 (4 543 px, bbox x[93–156] y[527–639])**, a standalone region clear of
  the building. The middle leaf (plant-1-leaf-2) is `#a9d1b5` and cannot separate the two
  teal leaves where they overlap.
- Right plant: plant-2-leaf-1 (`#267d83`, 800,610) and plant-2-leaf-3 (`#267d83`, 820,580)
  both → teal **comp 9 (29 709 px, bbox x[555–836])**. The building is `#267d83` and spans to
  x=790; the leaves (cx 800/820, rx 17, rotated) overrun that edge, so the two teal leaves
  fuse with each other *and* with the same-colour building.

Both are adjacent same-colour organics touching — the EMBER limit. (The matcher reports the
right-plant merge against the mint `Beige_ellipse_2`/leaf-2 because the teal leaf-3 vanished
into the building component and was not emitted as its own shape; the underlying cause is the
same-colour teal fuse.) **Verdict: LIMIT.**

### STOREFRONT Q6 — the 17 extras

By colour family (emitted geometry):

- **Teal `#267d83` (11):** `Teal_shape`, `Teal_shape_3`, `Teal_shape_4`, `Teal_shape_5`,
  `Teal_shape_6/7/8`, `Teal_polygon`/`_2`/`_3`/`_4`. All are slivers of the **building**,
  which is fragmented into comps 1/2/9 by everything painted on it: the awning scallop
  bottoms (Teal_shape_6/7/8 at y≈454; Teal_polygon tips at y 443–465), the window frames, the
  shop-sign, the door, and the display frames. Over-segmentation of one well-matched,
  fully-visible object.
- **Cream `#f5edda` (3):** `Cream_polygon_2` (awning left end ~(130–170, 346–375)),
  `Cream_shape_9` (awning scallop ~(148–170, 620–640)), `Cream_polygon_3` (right, ~(790–796,
  629–640)). Over-segmentation of the cream background / awning cream.
- **Navy `#182e4c` (2):** `Navy_rounded_rectangle` (495,344 16×29) and `Navy_rectangle_6`
  (581,342 14×32) — navy pockets inside the `shop-sign` (x 277–683, y 317–399) framed by the
  overlaid cream `shop-letter-*` glyphs. Letter-interruption fragmentation (EMBER name-ribbon
  class).
- **Gold `#e9bc59` (1):** `Gold_polygon_2` (pts ~(790,175)–(812,175)) — a corner of the
  `sun` (cx 790 cy 125 r 55) clipped where the `roof` edge (y≈175) crosses it.

None is a same-colour *hidden-compound* merge that `_merge_compound_siblings` would admit
(no shared common circle/ellipse; these are side-by-side pockets of visible fills). They are
thin-feature / letter-interruption over-segmentation — the documented EMBER/poster class.

---

## How much of each target is a genuine information limit vs addressable engine work

**logo_root_seal** (`matched=44 missing=12 extra=7 split=1 merged=1`, 51 vs 56):

- **Genuine information limit (same-colour merge; not addressable without inventing geometry
  or using the forbidden VLM path):** the 12 roots/branches fused into the trunk (comp 1) and
  the leaf-4+leaf-5 teal merge. That is **all 12 missing objects and the 1 merge** — the
  bulk of the deficit, and it is hard classical information loss.
- **Addressable (scoped, with its own benchmark number and regression test — NOT a
  gate-preserving quick win):** the inner-seal interrupted *circular* ring (the 6 mint
  extras), via the optional compound-ring arm; and the leaf-vein-11 thin-stroke split (1
  split, the `#efebd7` debris), via a scoped thin-curved-stroke tracing improvement.

**complex_storefront** (`matched=56 missing=8 extra=17 merged=2`, 73 vs 64):

- **Genuine information limit (same-colour merge):** the 5 cream awning panels fused into
  each other / the background, and the two teal plant-leaf merges. That is the 5 awning
  misses **and** both merges (which account for the plant-leaf misses) — the entire
  "missing" list and both merges are same-colour fusion.
- **Over-segmentation of already-matched visible objects (thin-feature / letter
  interruption, EMBER/poster class; no reusable cue the current gates can key on):** all 17
  extras. These are not a hidden-compound family and have no gate-preserving reunion.

So in both targets the structural deficit is **dominated by same-colour merges that are
faithful renderings of the authored artwork** (adjacent/abutting same-colour strokes and
fills with no separator), plus over-segmentation of visible objects by overlaid art. The
only engine-addressable items are the ROOT inner-seal ring and the ROOT vein split, both
scoped non-trivial changes, not quick wins.

---

## Recommendation

1. **Pin the same-colour merges as documented information limits**, mirroring EMBER
   (`test_ember_same_colour_face_features_are_one_raster_region`) and the patch/poster pins.
   Add, in the style of the existing pins (raster-only, no renderer):
   - **ROOT tree** → in `tests/test_logo_assets.py`: assert the trunk and the authored
     root/branch strokes are ONE 8-connected `#182e4c` component, AND that their measured
     working widths are above the stroke floor (so the reason is same-colour fusion, not
     thinness). Probe the trunk at (450,500) and, e.g., root-5 at its midpoint and branch-3
     at its midpoint → identical label; the leaf-4+leaf-5 teal merge → one `#267d83`
     component (probe ~(450,135) and ~(498,150)).
   - **STOREFRONT awnings** → in `tests/test_complex_scene_assets.py`: assert adjacent cream
     panels share one `#f5edda` component (probe panel-2 (205,410) and panel-4 (305,410)),
     panel-14 (805,410) shares the background label (probe (10,10)), and a red panel between
     them (panel-3 (255,410)) is a *separate* `#bb4b45` component — so the alternation
     survives for red only.
   - **STOREFRONT plant leaves** → assert plant-1-leaf-1 (120,610) and plant-1-leaf-3
     (140,580) share one `#267d83` component, and plant-2-leaf-1 (800,610) + plant-2-leaf-3
     (820,580) share one `#267d83` component that also contains a building-interior probe.

   These encode the measured "these are one region in the pixels" justification for why the
   structural targets legitimately stay xfail, and catch a regression or a silent
   gate-weakening "fix."

2. **Leave the ROOT inner-seal ring and the leaf-vein-11 split as optional, scoped engine
   work** — not part of this audit and not gate-preserving quick wins. If a future session
   pursues the inner-seal ring, treat it exactly like the patch orbits: the circle arm of
   `order._merge_compound_siblings` is the owner, admission must reuse the existing
   shared-occluder + common-circle evidence, and it ships as its own measured change
   (moving a `challenge_report`/`plate bench` number) with its own regression test.

3. **Explicitly rejected (per brief and AGENTS.md):** weakening any gate (segmentation
   `color_merge`, the stroke width/area floors, `_merge_compound_siblings`' circle/ellipse
   RMS/arc gates), editing the authored targets or goldens, or using the VLM to invent
   geometry. None of these would be a measured, gate-preserving win; each risks false merges
   or splits across the rest of the suite.

**Rigor note.** The missing roots/branches are emphatically **not** too thin to survive: they
are present in the raster at 8.7–21.8 working px and sit in the same navy component as the
trunk. The honest reason they are unrecoverable is same-colour fusion with no separating cue,
not resolution.

---

## Reproduction (read-only)

- Diffs: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python -m challenge_report logo_root_seal` and `… complex_storefront`.
- Probes (throwaway, under `/tmp`, not committed). Core measurements:
  - ROOT: navy `#182e4c` = 7 components, largest (trunk+roots+branches) = 22 705 px bbox
    x[273–626] y[179–649]; all 11 root/branch midpoints in that component; measured working
    widths 8.7–21.8 px; leaf-4+leaf-5 teal = one 11 180 px component; leaf-vein-11 cream
    continuous along its path, emitted as 2 primitives; 6 mint extras at r 274.4–275.0 from
    (450,370), mint ring = 22 components, 46/360 circumference interrupted.
  - STOREFRONT: red odd panels each distinct `#bb4b45`; cream panels 2+4 → comp 12
    (12 873 px), 10+12 → comp 13 (12 806 px), panel-14 → background comp 1 (264 393 px);
    plant-1-leaf-1/3 → teal comp 13 (4 543 px), plant-2-leaf-1/3 → teal comp 9 (29 709 px,
    fused with building); 17 extras = 11 teal building slivers + 3 cream bg/awning + 2 navy
    sign-letter pockets + 1 gold sun-clip.
  - Scales: ROOT 1536/900 = 1.7067; STOREFRONT 1536/960 = 1.600. Both PNG↔viewBox 1:1.
