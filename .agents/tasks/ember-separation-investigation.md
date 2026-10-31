# EMBER same-colour merge investigation — are the merges fixable or information limits?

**Mode:** read-only. No engine, target, or test files were modified. Throwaway probes
lived under `/tmp`. Repo state: `main @ 6895bfe`, clean.

**Scope:** the `logo_ember_crest` strict-xfail structural target
(`samples/challenges/logo_ember_crest.target.svg`), its input raster
(`samples/challenges/logo_ember_crest.png`), and the classical stages that could act on
the merges (`src/plate/stages/segment.py`, `order.py`, `complete.py`).

---

## Summary answer

The input PNG is 800×960 and the target SVG viewBox is `0 0 800 960`, so **authored SVG
coordinates map 1:1 to raster pixels** — every authored vertex can be sampled directly in
the raster.

Of the three merged groups, **two are genuine classical information limits** and **one is
a tracing/topology artefact, not a colour merge**:

| feature group | merged into | measured separating signal | verdict | if FIXABLE: stage + rule |
|---|---|---|---|---|
| left-cheek + right-cheek + muzzle (`#f5edda`) | `Cream_shape` | **None.** All three are one 8-connected cream component of **23 344 px** (label 2). No seam, no stroke, no alpha edge, no concavity-neck between them — the only interruptions are the navy facial features sitting *on top*. | **LIMIT** | — |
| left-pupil + right-pupil (`#182e4c` r=5) | eye-mask navy (not emitted separately) | **Effectively none.** Each pupil is 8-connected (even at strict ≤14 tol) to its eye-mask navy; left pupil + left mask are **one 2 991 px component** (label 6). A 1-px antialiased cream line sits directly above the pupil (y=367) but does **not** ring it; pupil fuses to the mask on top/below. | **LIMIT** | — |
| nose + mouth (both `#182e4c`) | `Navy_shape_2_2` | **None at the colour level** — nose+mouth are one 1 106 px navy component (label 10); no cream gap on the x=400 column (continuous navy y=448→493). The features are *geometrically* distinct (filled triangle vs round-cap open stroke) but **the raster renders them touching**. | **LIMIT (colour)** / borderline topology | see §4 — not worth attempting |

The extra `shield-four-transparent-cutouts`/`name-ribbon` merge and the 6 extra objects are
**over-segmentation of thin strokes and letter-interrupted fills**, a different failure
class from the same-colour face merges (see §5).

**Bottom line:** the face-feature merges that the gap text calls out (cheeks, pupils,
muzzle, mouth) are **classical information limits**. The authored artwork places adjacent
same-colour fills with no separator and places r=5 navy pupils on a navy mask; the raster
therefore contains **one contiguous region** in each case. Separating them would require
*inventing* a boundary that is not present in any channel (colour, luminance, alpha,
silhouette concavity). That is precisely the class the project already documents with
pin-tests (the `test_robustness.py` "below-the-floor" stress cases). **Recommendation:
document these as information limits with a pin-test; do not attempt an engine fix, and do
not use the VLM for geometry.** One narrowly-scoped, gate-preserving avenue exists only for
the *gold laurel-stem* extras (§5) and is optional.

---

## Evidence

### Q1 — cheeks + muzzle (cream `#f5edda`)

Authored geometry shares vertices with no separator: `left-cheek … L400 493`,
`right-cheek … L400 493`, `muzzle … L400 527` (`target.svg`). Measured:

- **One connected component.** Classifying cream as `|rgb−#f5edda|∞ ≤ 20 ∧ α≥128` and
  labelling (`scipy.ndimage.label`, 8-connectivity): the probes at left-cheek (315,440),
  right-cheek (485,440) and muzzle (400,500) all return **label 2, size 23 344 px**. They
  are literally the same region.
- **No seam at the junctions.** Horizontal scan at y=485 across x=320→470 is continuous
  cream except a single navy run at x=397–403 — that run is the *nose/mouth* descending
  into the face, not a cheek↔muzzle divider. Vertical scan at x=400 is cream y=416→446,
  navy y=447→494 (nose+mouth block on top), cream y=495→526. The cream reads as one field
  interrupted only by overlaid navy/orange features.
- **No sub-pixel cue.** The darkest "between" pixels found along the shared edges are
  ordinary antialias variants of cream (e.g. `(242,234,216)`, `(244,236,217)`), well
  within the cream cluster; there is no darker/lighter ridge, no stroke, no alpha notch.

**Verdict: LIMIT.** There is no classical cue in `segment.py` (palette/edge assignment),
`order.py` (decomposition) or `complete.py` (amodal completion) that could cut a contiguous
single-colour blob into three authored sub-shapes without inventing the cut lines. The
authored sub-shape boundaries exist only in the vector source, not in the rendered pixels.

### Q3 — pupils over the navy eye region

Authored: `left-pupil`/`right-pupil` are r=5 `#182e4c` circles at (323,373)/(477,373); the
eye-mask quads (`left-eye-mask` etc.) are the **same** `#182e4c`, with a thin cream
`left-eye` lens between them.

- **Pupil fuses into the mask.** Strict navy (`≤14`) labelling: left-pupil (323,373) and
  left-eye-mask (300,345) are **the same component, label 6, 2 991 px**. The same holds on
  the right (label 7, 3 086 px with the looser tol). `pupil isolated from mask = False`.
- **The cream lens does not enclose the pupil.** Column x=323 reads navy y=355→364, a
  1-px cream/antialias notch at y=365–368 (single cream pixel at y=367), then navy again
  y=369→384. A radial ring probe at r=6/8/10/12 shows cream on the left and lower-right
  but navy on the top and right — the pupil is open to the mask on more than half its
  circumference. The ASCII navy/cream map of the left-eye region shows the pupil as a
  small navy lump embedded in the cream lens but bridged to the mask above.

So the pupil is **same-colour-on-same-colour** with only a partial, sub-pixel cream hint on
two sides. There is not enough signal for a classical pass to carve an r=5 disc out of a
~3 000 px navy region; any attempt would be guessing the circle, i.e. inventing geometry.

**Verdict: LIMIT.** (This is the clearest same-on-same case of the three.)

### Q4 — nose vs mouth (both navy)

Authored: `nose` is a filled triangle `#182e4c`; `mouth` is an **open** `#182e4c` stroke,
width 6, round caps. Geometrically very different primitives — which is why the question is
whether this is more separable than the cream merges.

- **One navy component.** In the nose+mouth bbox (y440–510, x360–440) there is a single
  connected navy region. Sampling the mouth band y480–505 returns **only label 10**, the
  same label as the nose centroid (400,456); component size 1 106 px. The round-cap mouth
  stroke physically **touches** the nose triangle in the raster (no cream gap on x=400:
  navy is continuous y=448→493, cream only from y=496).
- So at the **colour/segmentation** level this is the same information limit as the cream
  merges: one contiguous same-colour blob. The *distinctness* is only in the authored
  primitive type, which the raster does not preserve because the shapes abut.

**Verdict: LIMIT (colour).** It is *marginally* more structured than the cream case — a
shape-decomposition that recognised "triangle with a thin curved tail" could in principle
split it — but that is a bespoke heuristic with no reusable cue and high false-positive risk
on other artwork; it is **not** a clean classical signal. Treat as a limit, not a
tracing bug worth chasing. See the recommendation.

### Q5 — the 6 extra objects

Emitted from `pipeline.run(...)` and matched against the diff:

| extra id | emitted geometry | what it is |
|---|---|---|
| `Gold_rectangle_3` | rect x=200 y=476 24×6 `#e9bc59` | tail fragment of **left-laurel-stem** (`M400 650Q250 630 210 470`) |
| `Gold_ellipse` | ellipse cx=587 cy=483 ~4×6 | tail fragment of **right-laurel-stem** end |
| `Gold_ellipse_2` | ellipse cx=400 cy=650 ~3×6 | fragment at the **stem junction (400,650)** |
| `Navy_rounded_rectangle` | rect x=388 y=817 28×21 rx=6 | navy pocket inside the **name-ribbon**, framed by overlaid letters |
| `Navy_rounded_rectangle_2` | rect x=388 y=781 25×19 rx=4 | same — ribbon navy between letters |
| `Navy_rectangle` | rect x=550 y=781 26×19 | same — ribbon navy around the "R" |

These are **two over-segmentation families**:

1. **Gold laurel-stem fragments** — the thin 6-px gold stem strokes (`left/right-laurel-stem`)
   break into disconnected pieces; the main pieces already mis-match as `Gold_rectangle_2`
   / stroke-vs-path, and these three are leftover tails. This is the *same shape family* as
   the ORBIT interrupted-ring case that `order._merge_compound_siblings` was written for
   (commit 1390e5b) — same-colour fragments of one object split by crossing occluders.
2. **Name-ribbon navy pockets** — the navy ribbon (`#182e4c`, x=115 y=750 570×115) is cut
   by the overlaid cream letters into the main `Navy_shape_2` plus these small navy
   rectangles sitting in letter counters/gaps. This ties into the already-reported
   `shield-four-transparent-cutouts + name-ribbon → Navy_shape_2` merge: the ribbon's
   editable structure is lost to the letters, not to a colour limit.

Neither family is a *same-colour face-feature* merge; they are thin-stroke and
letter-interruption fragmentation.

---

## How the pipeline currently treats these (why they merge)

- `segment.py` builds the palette from flat (non-edge) pixels and assigns edge pixels to
  the nearest palette colour. Because the cheeks/muzzle, and the pupils/eye-masks, are
  **identical fills**, segmentation correctly produces **one region per colour-blob** —
  there is no colour difference to split on. This is working as designed; the limit is in
  the input, not the stage.
- `order.py::merge_fragments` and `_merge_compound_siblings` only ever *merge* same-colour
  siblings (parent-island redundancy, flat pools, and interrupted compound objects
  admitted by the relative T-junction test + exact-circle continuation). Nothing in the
  classical pipeline *splits* a single contiguous same-colour region into authored
  sub-shapes, and adding such a splitter would have no raster cue to key on.
- `complete.py` reconstructs *hidden* parts of a shape behind occluders using the relative
  T-junction test (`_occludes`, 15°) and exact primitive fits. It cannot manufacture an
  interior boundary inside a uniformly-coloured region.

So the merges are not a bug in any stage; they are the faithful consequence of the authored
artwork rendering adjacent/overlapping same-colour fills as single contiguous regions.

---

## Overall assessment: how much of EMBER's gap is a classical limit vs engine work?

EMBER's diff: `matched=45 missing=6 extra=6 merged=3` against 51 expected.

- **Information-limit (not addressable without inventing geometry or using the VLM for
  geometry — forbidden):** the two cream merges (cheeks+muzzle) and the two pupils, and the
  colour-level nose+mouth merge. These account for **5 of the 6 missing** (right-cheek,
  left-pupil, right-pupil, muzzle, mouth) and **2 of the 3 merged groups** directly, plus
  the nose match degradation. This is the bulk of the face-feature gap and is **genuine
  classical information loss**.
- **Addressable engine work (has a real cue, but out of this investigation's fix scope):**
  the gold laurel-stem fragmentation (3 of the 6 extras) is the ORBIT-style interrupted
  same-colour compound family that `_merge_compound_siblings` already targets; the
  name-ribbon/letter structure (`name-ribbon` missing, 3 navy-rect extras, the
  `shield cutouts + ribbon` merge) is a thin-feature/overlaid-glyph problem, not a
  same-colour face limit.

So of EMBER's structural deficit, the **face same-colour merges are a hard classical
limit**; the remaining gap (strokes, ribbon, laurel fragments) is ordinary thin-feature
engine work already reflected in the gap text ("4 of 7 strokes recovered").

---

## Recommendation

**Primary: document the face same-colour merges as information limits, with a pin-test.**
This mirrors the project's existing practice for demonstrated limits — the
`tests/test_robustness.py` "below-the-floor" stress cases
(`test_blur_1p2_marker_is_below_the_alpha128_silhouette_floor`,
`test_contrast_1_over_16_foreground_is_below_the_colour_merge_floor`) pin *known* losses so
a future regression or false "fix" is caught. A parallel pin for EMBER would assert the
measured contiguity directly from the raster (no renderer needed), e.g.:

- cheeks+muzzle at (315,440)/(485,440)/(400,500) share **one** 8-connected `#f5edda`
  component;
- left-pupil (323,373) and left-eye-mask (300,345) share **one** `#182e4c` component.

Such a test encodes "these are one region in the pixels" as the documented reason the
authored sub-shapes cannot be recovered classically. It does **not** weaken any gate, edit
the authored target, or touch the VLM. The strict-xfail `gap=` text in `tests/challenges.py`
already names these; the pin-test makes the *pixel* justification executable.

**Do NOT attempt a geometry fix for the face merges.** There is no reusable classical cue;
any splitter would be fabricating boundaries (exactly the VLM-geometry prohibition in
AGENTS.md, and it would be worse done heuristically). The nose/mouth split, though the
shapes differ in type, has no colour/alpha/concavity cue and a bespoke "triangle + tail"
decomposer would be high-risk and single-use — not worth it.

**Optional, narrowly-scoped, gate-preserving avenue (only if stroke recovery is pursued
later):** the 3 gold laurel-stem *extras* are the same interrupted-same-colour-compound
family that `order._merge_compound_siblings` (commit 1390e5b) already handles for ORBIT.
A future session working on strokes could investigate whether the stem fragments satisfy
the *existing* admission evidence (shared occluder via the relative T-junction test +
common-curve continuation) — reusing the current gates, not relaxing them. This is a
stroke/thin-feature improvement, independent of the same-colour face limit, and should be
scoped as its own measured change (move a `plate bench` number) rather than bundled with
the face merges. It is explicitly **not** required to resolve this investigation.

**Explicitly rejected (per brief and AGENTS.md):** weakening gates, editing the authored
target, or using the VLM to invent face-feature geometry.

---

## Reproduction (read-only)

- Diff: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python -m challenge_report logo_ember_crest`
- Pixel probes: throwaway scripts under `/tmp/ember_probe*.py` (not committed). Core
  measurements: 1:1 SVG↔PNG mapping (both 800×960); cream cheeks+muzzle = one 23 344 px
  component; left pupil+mask = one 2 991 px navy component (strict ≤14); nose+mouth = one
  1 106 px navy component; 6 extras = 3 gold laurel-stem fragments + 3 name-ribbon navy
  pockets.
