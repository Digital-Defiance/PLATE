# Same-colour touching objects — is there a classical concavity splitter, or is this the ceiling?

**Mode:** read-only. No engine, target, golden or test file was modified during the
investigation. All probes lived under `/tmp` (`sc_probe.py` … `sc_probe4.py`, not
committed). Repo state when the measurements were taken: working tree carried the
in-flight Tasks 1–6 edits only; no new engine change was made for the measurement.

**Scope (R3 / Task 7).** The five authored same-colour merges the three prior
investigations flagged as the dominant structural gaps:

| merge | artwork | authored objects | prior report |
|---|---|---|---|
| EMBER cream face | `logo_ember_crest` | left-cheek + right-cheek + muzzle (`#f5edda`) | ember |
| ROOT navy tree | `logo_root_seal` | trunk + 6 roots + 5 branches (`#182e4c`) | root-storefront |
| ROOT teal leaves | `logo_root_seal` | leaf-4 + leaf-5 (`#267d83`) | root-storefront |
| STOREFRONT cream awning | `complex_storefront` | awning-panel-2/4/10/12/14 + background (`#f5edda`) | root-storefront |
| STOREFRONT teal leaves | `complex_storefront` | plant-1/2-leaf-1 + leaf-3 (`#267d83`) | root-storefront |

All PNGs map 1:1 to their viewBox, so authored coordinates sample directly as raster
pixels. Diagnostics prefix:
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python`.

---

## Summary answer

**No classical cue — including the concavity / convexity-defect splitter the design named
as the thing to investigate — separates the authored abutting same-colour cases. The
single most-likely FIXABLE candidate (a convexity-defect "pinch" splitter on one
same-colour component) was measured directly and fails on both counts: it does not fire at
the authored seams, and where it does fire it either cuts the wrong place or false-splits a
legitimately single object. This is the engine's most likely hard classical ceiling.**
Each in-scope merge lands in terminal state **(b) DOCUMENTED LIMIT**, pinned by an existing
raster-contiguity test; no FIXABLE sub-class was found, so no splitter is shipped (shipping
one would require weakening a gate or inventing geometry — forbidden by GC-5).

The headline measurements:

- **The authored same-colour joins are not concave.** Where two same-colour fills abut
  edge-to-edge (EMBER cheeks↔muzzle, the ROOT teal leaves, the STOREFRONT teal leaves), the
  shared boundary is a flat/convex shared edge, not a pinch. The deepest convexity defects
  of the merged component sit at *overlaid features' notches* and *decorative edges*, tens
  of pixels away from the authored seam.
- **Where a pinch splitter does fire, it cuts the wrong thing.** On the ROOT navy tree it
  fires on the 10 px gap *between two adjacent roots* (cut 93 px from the trunk seam); on
  the STOREFRONT awning it fires on the 9 px concave *scallop hem* at the awning's bottom
  edge (cut 69 px from the panel seam). Neither cut separates an authored object from its
  same-colour neighbour.
- **The same gate false-splits a legitimately single object.** A pinch gate loose enough to
  fire anywhere on the merged components also fires on the EMBER `name-ribbon` — a single
  rounded-rect whose overlaid letters create a notch that pairs into a false neck. So the
  splitter trades one unrecoverable merge for a new false split: a net loss.

This is the same verdict the EMBER, ROOT/storefront and patch/poster investigations reached
by inspection; this report adds the **direct measurement of the convexity-defect splitter
itself** (the one classical mechanism that had not yet been probed) so the LIMIT is
executable and the splitter is not re-attempted.

---

## The question, precisely

Segmentation assigns one region per colour-blob; `order`/`complete` only ever *merge*
same-colour siblings or complete *hidden* parts — nothing *splits* a contiguous
same-colour region into authored sub-shapes. A splitter would have to run on a single
same-colour component and cut it. The only classical mechanism with any prior (design §3.6)
is **concavity**: find a pinch/neck in the component's silhouette (two opposing deep
`cv2.convexityDefects`) and cut across it. The decisive questions:

1. **Does a separating neck exist AT the authored seam** for each merge?
2. **Does a gate tight enough to avoid false splits on legitimately single concave shapes
   (stars, rings, glyphs, concave frames) still fire on the real seams?**

If the answer to (1) is no, or the answer to (2) is no, there is no classical splitter and
the merge is a documented LIMIT.

---

## Evidence

### Part A — convexity defects of each merged component (`/tmp/sc_probe.py`, `sc_probe2.py`)

For each merged same-colour component I took the largest external contour, its convex hull,
and `cv2.convexityDefects`, then formed the tightest **neck** = the pair of opposing deep
defects (depth ≥ 8 px) whose connecting segment is shortest relative to their depth. A
classical pinch-splitter cuts that segment. "FIRES" means the neck segment is ≤ 1.2× the
smaller defect depth (a genuine pinch, not a shallow dent). `cut→seam` is the distance from
the proposed cut to the nearest authored same-colour seam.

| merge | neck seg | defect depths | fires? | cut → authored seam |
|---|---|---|---|---|
| EMBER cream cheeks+muzzle | 45.7 px | (89, 38) | **no** (seg too long) | 55 px |
| ROOT navy tree | 10.0 px | (145, 171) | **FIRES** | **93 px** (between two roots, not trunk↔root) |
| ROOT teal leaf-4+5 | 53.5 px | (20, 25) | **no** | 14 px |
| STOREFRONT cream awning 2+4 | 9.0 px | (21, 92) | **FIRES** | **69 px** (scallop hem, not the panel seam) |
| STOREFRONT teal leaf L | 44.9 px | (31, 12) | **no** | 16 px |

Reading it:

- **Three of five merges have no firing neck at all.** EMBER cream, the ROOT teal leaves and
  the STOREFRONT teal leaves abut along a flat/convex shared edge; the tightest opposing-
  defect pair is a long segment (45–54 px) across a shallow dent, not a pinch. There is no
  concavity to cut. (EMBER cream's *deepest single* defect, 89 px, is the notch where the
  navy nose/mouth descends into the face — an overlaid feature, not the cheek↔muzzle join.)
- **The two merges that fire cut the wrong place.** The ROOT navy tree fires on a tight
  10 px gap, but it is the gap *between two adjacent roots radiating from the trunk*, 93 px
  from any trunk↔root seam — cutting there would split one root pair, not free a root from
  the trunk. The STOREFRONT awning fires on a 9 px notch that is the decorative *scalloped
  hem* at the awning's bottom edge, 69 px from the vertical panel-2/panel-4 seam.

The authored seam between cream awning panels is not even a concavity: at `y=410` the cream
is two runs `x[180–229]` and `x[280–329]` separated by the *red* panel-3 (`/tmp/sc_probe3.py`);
the two cream panels fuse into one 8-connected component only *above and below* the short red
panel, through a wide cream bridge with no neck. There is nothing to pinch.

### Part B — false-split rate on legitimately single shapes (`/tmp/sc_probe2.py`, `sc_probe4.py`)

The same firing gate, run on a curated set of **single** authored objects (a splitter must
NOT fire on any of these):

| single object | area px | pinch fires? | note |
|---|---|---|---|
| EMBER fox silhouette (`#e88040`) | — | no | concave ears/jaw, but no opposing-defect pinch |
| EMBER crest star (`#e9bc59`) | 180 | no | 4 deep points, each < 8 px |
| EMBER shield frame navy | — | no | |
| **EMBER name-ribbon navy** | 118 870 | **FIRES** | letters notch a single rounded-rect → **FALSE split** |
| ROOT mint ring (`#a9d1b5`) | — | no | |
| ROOT gold ring | — | no | |
| STOREFRONT teal building | — | no | heavily concave window/door frame |
| STOREFRONT red panel-3 | 4 192 | no | |
| PATCH navy nine-cutout rim | 139 100 | no | |
| PATCH teal sky | — | no | |

**1 of 11** curated single objects false-splits — and it is exactly the kind of object the
merges share a colour with (a large navy rounded-rect interrupted by overlaid glyphs, the
EMBER `name-ribbon` the prior reports already flagged as letter-interruption
over-segmentation). So a pinch gate loose enough to fire on the ROOT tree / STOREFRONT
awning necks also shatters single objects elsewhere: the mechanism cannot be gated to
separate seams without producing false splits, and even when it fires on a merge it cuts the
wrong place. There is **no tight gate that fires on the real seams and spares single
shapes** — the real seams produce no firing neck at all (Part A).

### Why this is fundamental, not a tuning problem

The abutting same-colour join renders as a *straight or convex* boundary — two filled
regions sharing an edge produce no interior pinch, by construction. Convexity defects only
appear where a silhouette *re-enters* (ears, scallops, letters, inter-stroke gaps), which is
everywhere **except** the authored same-colour seams. The cue the splitter keys on is
negatively correlated with the thing we need to cut. No threshold rescues that: tightening
the gate removes the false fires but also removes the (already wrong-place) real fires;
loosening it adds more false splits. This is the measured reason the design named a
DOCUMENTED LIMIT as the honest prior, and the measurement confirms it.

Other classical channels were already measured absent by the three prior reports and are not
re-litigated here: colour (identical fills — the whole premise), luminance (same), alpha
(opaque, no notch), and silhouette concavity (this report). An ML/semantic model could guess
the sub-shapes, but GC-2 forbids using the VLM for geometry.

---

## Terminal state of each in-scope merge

Every in-scope same-colour merge reaches **(b) DOCUMENTED LIMIT**, already pinned by a
raster-contiguity test (no renderer; probes the input PNG directly with `scipy.ndimage`,
mirroring the EMBER precedent). The pins asserted green under `pytest -q`
(`tests/test_logo_assets.py tests/test_complex_scene_assets.py` → 26 passed):

| merge | terminal state | pin test |
|---|---|---|
| EMBER cream cheeks+muzzle (+ pupils) | (b) LIMIT | `test_ember_same_colour_face_features_are_one_raster_region` (`tests/test_logo_assets.py`) |
| ROOT navy tree (trunk+roots+branches) | (b) LIMIT | `test_root_tree_strokes_fuse_into_the_trunk_as_one_region` (`tests/test_logo_assets.py`) |
| ROOT teal leaf-4 + leaf-5 | (b) LIMIT | `test_root_tree_strokes_fuse_into_the_trunk_as_one_region` (same test, teal clause) |
| STOREFRONT cream awning panels | (b) LIMIT | `test_storefront_cream_awning_panels_merge_with_the_background` (`tests/test_complex_scene_assets.py`) |
| STOREFRONT teal plant leaves | (b) LIMIT | `test_storefront_same_colour_plant_leaves_are_one_region` (`tests/test_complex_scene_assets.py`) |

The ROOT-tree, ROOT leaf-4+5, STOREFRONT cream-awning and STOREFRONT teal-leaf pins
recommended by the root-storefront investigation were added alongside the ROOT Task-5/6 work
and are present and green; the EMBER pin is the original precedent. This investigation adds
the **convexity-defect splitter measurement** that closes the one remaining FIXABLE
hypothesis, so R3 is fully in a terminal state without a new pin being required.

**No FIXABLE sub-class was found.** Had one existed, the brief required a tightly-gated
splitter moving a `challenge_report`/bakeoff number with a positive regression and a
negative regression (no false splits on single objects). The measurement shows the negative
regression could not be satisfied (the EMBER name-ribbon false-fire), so no splitter is
shipped. No gate is weakened (GC-5); no target or golden is edited; the VLM is not used for
geometry (GC-2).

---

## The ceiling statement

**Same-colour separation of abutting/overlapping authored objects is the engine's most
likely hard classical ceiling.** When an artist places two same-colour fills edge-to-edge
with no separator — or paints a same-colour feature on top of a same-colour field — the
rasteriser produces a single contiguous region that carries no colour, luminance, alpha or
concavity cue marking the original boundary. Every classical pass in PLATE is, by design,
boundary-driven; with no boundary present in any channel there is nothing to key on, and the
one remaining candidate mechanism (concavity splitting) is measured here to point at the
wrong pixels. Recovering these sub-shapes would require inventing geometry or an ML model —
both out of scope (GC-2/GC-5). This is the honest ceiling: it is not a bug, a tuning gap, or
a thin-feature loss, but faithful rendering of artwork whose structure lives only in the
vector source.

---

## Recommendation

1. **Keep the five raster-contiguity pins as the terminal (b) state.** They encode the
   measured "these are one region in the pixels" fact and catch a regression or a silent
   gate-weakening "fix." No new pin is needed; all five exist and pass.
2. **Do not ship a convexity-defect splitter.** Measured: it fails to fire at the authored
   seams, misfires on inter-stroke gaps / decorative scallops, and false-splits a
   legitimately single object (EMBER name-ribbon). It cannot satisfy the positive + negative
   regression requirement without weakening a gate.
3. **Explicitly rejected (per brief, GC-2/GC-5):** weakening `color_merge` or any
   segmentation gate, adding a geometry-inventing splitter, editing targets/goldens, or
   using the VLM to guess the sub-shapes.

---

## Reproduction (read-only)

- Diffs: `… -m challenge_report logo_ember_crest` / `logo_root_seal` / `complex_storefront`.
- Probes (throwaway, under `/tmp`, not committed):
  - `sc_probe.py` — convexity-defect depths of each merged component and a few single shapes.
  - `sc_probe2.py` — the tightest opposing-defect **neck** per component, whether it fires,
    and its distance to the authored seam (the table in Part A).
  - `sc_probe3.py` — the cream awning seam reality check (cream runs split by the red panel).
  - `sc_probe4.py` — the false-fire census over 11 curated single objects (1/11 fires:
    EMBER name-ribbon).
- Pins: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python -m pytest -q tests/test_logo_assets.py tests/test_complex_scene_assets.py` → 26 passed.
- Core measurements: authored same-colour seams produce no firing neck (segs 45–54 px over
  shallow dents); the two firing merges cut 93 px / 69 px from the seam (inter-root gap,
  scallop hem); 1/11 single objects false-split. Verdict: LIMIT for all five, pinned.
