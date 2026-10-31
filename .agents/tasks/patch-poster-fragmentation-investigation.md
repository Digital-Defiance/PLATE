# Patch & Poster fragmentation investigation — addressable fix vs information limit

**Mode:** read-only. No engine, target, or test file was modified. All probes lived
under `/tmp`. Repo state: `main @ 7e7f3c3`, clean (`git status` empty). Both PNGs are
960×960 and both target viewBoxes are `0 0 960 960`, so **authored SVG coordinates map 1:1
to raster pixels** — every authored vertex is sampled directly.

Diagnostics reproduced with the trustworthy per-object report (commit 5692fa9):
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib PYTHONPATH=tests .venv/bin/python -m challenge_report <name>`.

---

## Summary answer

The single biggest, most concentrated remaining family is **the poster
`gradient-disc-behind-title` fragmentation: 26 of the 39 poster extras are flat bands of
one linear-gradient disc, sliced into 7 disconnected pieces by the opaque overlays painted
on top of it** (6 crossing-lines, the diagonal ribbon, the dot grid, the headline letters).
It is concentrated and would be the largest single-number win — but it is an **INFORMATION
LIMIT under the existing gates**, not an addressable one. The disc is a single authored
object that the raster faithfully renders as seven mutually-disconnected regions; reuniting
them requires completing a gradient fill *across* opaque occluders, which every existing
gradient gate deliberately refuses to do without a free, fittable silhouette boundary — and
this disc does not have enough free boundary.

Every one of the "interesting" splits/extras in both scenes turns out to be the same story
with different geometry:

| scene | family | verdict | why |
|---|---|---|---|
| patch | shaded-planet (3 frags) | **LIMIT** | one radial-gradient circle, split by overlays; `_grow_radial_bands` finds **0 free boundary points** (planet rim is 360/360 enclosed by the teal sky) so the circle fit can never run |
| patch | back-orbit / front-orbit (2 frags each) | **LIMIT under existing gate** | genuine interrupted same-colour **ellipse** rings sharing occluders — but `_merge_compound_siblings` admits only a **circle** fit, which fails hard (rms 35 vs gate 5.2). Reuniting needs an ellipse extension = new admission geometry, not gate reuse |
| patch | 28 extras | mostly **LIMIT/over-seg** | sky-disc slivers (teal), planet gradient debris (gray/purple), crossing-ribbon cut by title letters (orange) |
| patch | crater-3 missing | **LIMIT (low contrast)** | r=19×12 crater, contrast ≈17 against a shifting gradient background |
| poster | gradient-disc (26 frags) | **LIMIT under existing gates** | one linear-gradient disc fragmented into **7 four-connected components** by overlays; fails the `_single_object` pooling gate and has no clean radial silhouette to grow from |
| poster | ~13 other extras | **LIMIT/thin-feature** | navy footer-letter counters + crossing-line fragments, mint/cream slivers, letter-interrupted fills |

**Recommendation: no gate-preserving engine fix exists for the concentrated families. Pin
the two gradient-object fragmentations (patch shaded-planet, poster gradient-disc) and the
interrupted-ellipse orbits as documented information limits, mirroring the EMBER precedent.**
The honest outcome is that the remaining patch/poster gap is dominated by *opaque overlays
slicing single gradient objects* and *letter/stroke-interrupted fills* — classes with no
reusable classical cue that the current gates can key on without inventing geometry or
weakening a gate. Details and pixel evidence below.

---

## Evidence

### Q1 — the three mission_patch splits

Authored geometry (`complex_mission_patch.target.svg`):
- `shaded-planet` — `<circle cx=460 cy=400 r=182 fill=url(#planet-light)>`, a **radial**
  gradient `#ecd494 → #997698`.
- `back-orbit` — `<ellipse cx=465 cy=420 rx=280 ry=90 … stroke=#a9d1b5 stroke-width=8
  transform=rotate(-24 …)>`, a **stroke-only** ellipse ring.
- `front-orbit` — `<ellipse … rx=270 ry=73 … stroke=#f5edda stroke-width=5
  transform=rotate(24 …)>`, a **stroke-only** ellipse ring.

What PLATE emits for each split (`/tmp/probe_actual.py`):

| split | actual fragments | geometry |
|---|---|---|
| shaded-planet | `Light_gray_shape` radialGradient bbox(277,298)-(574,533); `Tan_shape` radialGradient bbox(315,219)-(573,375); `Gray_shape` **solid** `#997698` bbox(294,476)-(575,584) | the gradient body, an upper band, and the dark lower band (emitted flat) |
| back-orbit | `Beige_stroke_5` stroke `#a9d1b5` w8 bbox(203,424)-(355,564); `Beige_shape` **solid** `#a9d1b5` bbox(610,276)-(727,335) | left arc kept as a stroke, right-top arc emitted as a solid fill |
| front-orbit | `Cream_shape_13` solid `#f5edda` bbox(214,289)-(576,537); `Cream_stroke` stroke `#f5edda` w5 bbox(593,428)-(715,550) | two arc fragments of the thin ring |

**shaded-planet is ONE object split by overlaid occluders (not distinct in the raster).**
Scanning the raster column `x=460` top→bottom (`/tmp/probe_raster.py`) shows a continuous,
smooth radial ramp (e.g. `(205,177,149)` near the lit side decaying toward the purple
`#997698` rim) **interrupted only where opaque features are painted on top**: a navy block
(`left-solar-array #182e4c`, y≈325→437), a 1-px cream notch at y≈495 (the `front-orbit`
stroke), and the orange `crossing-ribbon #e88040` at y≥565. The three fragments are the
same gradient model: the `gradient.detect()` stage already recovers two of them as radial
gradients centred at ~(429,350) with residual 0.3–1.1 (`/tmp/probe_grow.py`), matching the
authored `planet-light` centre (430,350). So this is genuinely **one gradient object, split
by overlays** — ADDRESSABLE in principle.

**But it is a LIMIT under the existing gate.** The reunion path for a radial ramp split by
overlays is `gradient._grow_radial_bands`. Instrumenting it (`/tmp/probe_grow2.py`) shows
the band-grouping succeeds (seed gathers ids `{0,46,52,59,72}`, ≥3 required) and then dies
at exactly one gate:

```
free boundary pts=0 (need>=40)
```

The cause (`/tmp/probe_planet_boundary.py`): walking the authored circle rim at r+4, **all
360/360 sample points are adjacent to a "foreign" foreground region**, every one of them
the teal sky `#267d83` (id 2, 133 462 px). The planet is a disc painted entirely **inside**
the sky disc, so it has *no* boundary touching empty canvas or background. Compounding this,
the scene has **no background root ≥60 %** — the navy `patch-rim-nine-cutouts` covers
`552 781 / 921 600 = 0.5997`, just under the 0.6 threshold — so `excluded` is empty and the
sky counts as foreign. With zero free boundary points the `fit_circle` call that
`_grow_radial_bands` needs to assert the silhouette can never run. Reuniting the planet
would require **inventing** the occluded circle boundary from the gradient alone, which is
the behaviour the gate exists to forbid. **Verdict: LIMIT.** Stage/rule that *could* act:
`gradient._grow_radial_bands`; it does not admit this under its existing free-boundary +
≥270° arc gate, and relaxing that gate is a gate weakening (out of scope and dangerous — it
would let a gradient hallucinate a silhouette behind any surrounding fill).

**back-orbit / front-orbit are genuine interrupted same-colour ELLIPSE rings sharing
occluders — ADDRESSABLE in principle, LIMIT under the existing gate.** Both are single
stroke-ellipses whose same-colour fragments sit under shared overlays (the planet, the
spacecraft hull, the solar arrays, and `small-moon` all cross the rings). This is precisely
the compound-sibling family `order._merge_compound_siblings` (commit 1390e5b) was written
for. **However**, that routine admits a group only when the pooled convex hull fits a
**circle** (`fit_circle`, `rms ≤ 0.02·r ∧ arc ≥ 160°`). Testing the pooled orbit fragments
(`/tmp/probe_orbit.py`):

```
back-orbit  circle fit: r=260.5 rms=35.54 (gate rms<=5.21) cov=194deg  -> FAIL
            ellipse fit: rx=105 ry=283 cov=284deg rms=6.85
front-orbit circle fit: r=501.7 rms=41.86 (gate rms<=10.03) cov=65deg  -> FAIL
            ellipse fit: rx=112 ry=282 cov=272deg rms=9.67
```

The circle fit fails by ~7× the RMS gate because the shapes **are ellipses** (rx≈105,
ry≈283 — the authored rx=280 ry=90 rotated −24°). The fragments *do* share occluders and
*do* lie on one common ellipse, so the only thing standing between them and reunion is that
the existing admission geometry is circle-only. Extending it to an **ellipse** fit is new
admission geometry, not reuse of the current gate — and it is risky: the pooled hull here is
polluted by same-colour solar-panel-cell strokes and the cream stars, and OpenCV's ellipse
angle came back as garbage (3829°) in the probe. **Verdict: LIMIT under the existing gate.**
Stage/rule: `order._merge_compound_siblings`; the existing circle gate rejects it, and the
only way to admit it is to add ellipse admission geometry (gate change).

### Q2 — mission_patch's 28 extras and the crater-3 miss

Characterised from `/tmp/probe_actual.py` (all 28) by colour family:

- **Teal `#267d83` (≈9 extras: `Teal_shape_2` 155 369 px, `Teal_shape_2_2`, `Teal_polygon`,
  `Teal_polygon_2/3`, `Teal_shape_3`, `Teal_rectangle`, `Teal_rectangle_2`, `Teal_shape_4`)**
  — fragments of the **sky disc**. Sky matches cleanly as `Teal_circle_2` (IoU 0.9959); these
  are the sky's leftover pockets between everything painted on it (planet, orbits, spacecraft,
  porthole glass). Over-segmentation of one well-matched object, **not** an ORBIT-mergeable
  compound (they are not same-colour fragments of a *hidden* object — the sky is fully
  visible and already matched).
- **Gray/purple `#997698 #b18c9e #b39397 #bea096` (≈11 extras)** — debris from the
  **shaded-planet** gradient's dark end and from craters; same gradient-split limit as Q1.
- **Orange `#e88040` (4 extras: `Orange_rectangle_2_2/3`, `Orange_rounded_rectangle/_2`,
  bbox y601-649)** — fragments of the `crossing-ribbon` polygon cut by the overlaid
  `outlined-title` letters. Letter-interrupted fill (same class as EMBER's name-ribbon).
- **Small beige/gray slivers near (640,416) & the right solar array** — thin-feature debris
  around the small-moon / orbit / panel-cell crossings.

None of these is an ORBIT-style *hidden-compound* merge that the existing circle gate would
admit: the teal and orange families are over-segmentation of already-matched visible
objects, and the gray family is the planet-gradient limit.

**crater-3 missing** (`/tmp/probe_crater3.py`): authored `<ellipse cx=515 cy=470 rx=19
ry=12 fill=#b18c9e>`. Its fill `(177,140,158)` sits on a planet-gradient region of local
colour ≈`(181,150,151)` (surround mean `(182,142,141)`); peak contrast ≈ **16.8**, almost
all in the blue channel. crater-1 (rx=27) and crater-2 (rx=35) match because they are larger
and sit on lighter, higher-contrast gradient zones. crater-3 is a small, low-contrast detail
on a shifting gradient — a thin/low-contrast segmentation loss, **LIMIT-adjacent**, not an
ORBIT merge.

### Q3 — event_poster's 39 extras

Authored `gradient-disc-behind-title` = `<circle cx=480 cy=468 r=260 fill=url(#poster-wash)>`,
a **linear** gradient `#edba68 → #d17d79`. Classifying all 39 extras by family
(`/tmp/probe_poster2.py`):

| family | count | detail |
|---|---|---|
| **gradient-disc ramp fragments inside the disc** | **26** | `Tan_*` / `Pink_*` flat bands (`#e7ad6c #e09d70 #da9173 #d58577`), every one 100 % inside the r=260 disc |
| navy `#182e4c` | 6 | footer-letter counters (`Navy_rectangle_2_2/3`, y843-874) + crossing-line stroke fragments (`Navy_rectangle_11-14`, y558-561) |
| mint `#a9d1b5` | 2 | slivers straddling the disc edge in the crossing-line/dots region |
| cream `#f5edda` | 5 | background-colour fragments (headline-letter counters, top-rule gaps) |

The disc dominates: **26/39 extras are one object.** The disc matches as `Tan_shape_2`
(linearGradient) but at **IoU 0.2262** — only a small slice is recovered as the gradient.
Why (`/tmp/probe_poster3.py`): segmentation posterises the ramp into ~41 flat bands, and
`gradient.detect._find_components` requires the **filled union of a component to be a single
4-connected region** (`_single_object`). The union of the disc bands forms **7 disconnected
4-connected components**, because opaque overlays cut the disc:

- 6 `crossing-line` navy strokes (x510→865, y440-560) across the right half,
- the `diagonal-ribbon` polygon bisecting the disc,
- the 3×4 `dot` grid, and
- the four `headline` letters over the top.

So no single gradient component spans the disc; `detect()` emits just the largest
contiguous slice (area 46 818 of the ~212 000 px disc) and leaves the rest as 26 flat
bands. The radial-band grower cannot rescue it either: `_grow_radial_bands` only *seeds*
from a **radial** gradient (this disc is linear), and the disc rim is 247/360 occluded
(navy letters, mint-ellipse, ribbon, foreground-disc) so even a radial seed would struggle.
The pairwise `gradient.merge_occluded` path needs two *completed primitives* that agree;
only one gradient shape exists, so there is no pair.

**Verdict for the 26-fragment disc: LIMIT under the existing gates.** It is genuinely one
gradient object that the raster shows as 7 disconnected pieces because opaque art is painted
over it. Reuniting them means completing a gradient fill across the occluders with no
clean silhouette to anchor on — exactly what the `_single_object`, free-boundary and
completed-primitive gates each refuse. Stage/rule that *would* own it:
`gradient.detect` / `gradient._grow_radial_bands`; neither admits it without weakening a
gate (relaxing `_single_object` to pool disconnected components would let any two
same-ramp blobs anywhere fuse) or inventing the occluded silhouette.

The remaining 13 poster extras are thin-feature / letter-interruption fragmentation (navy
footer-letter counters and crossing-line slivers, cream letter counters, mint slivers) — the
same class EMBER documents, not a same-colour hidden-compound merge. The lone split
`crossing-line-5 → Beige_shape_2 + Navy_rectangle_10` is one navy stroke nicked by an overlay.

### Q4 — the single most concentrated, lowest-risk, gate-preserving win

There isn't one. Ranked by object-count concentration:

1. **poster gradient-disc (26 extras)** — biggest by far, but LIMIT under existing gates
   (7 disconnected components, no clean silhouette; see Q3).
2. **patch shaded-planet (3 frags)** — LIMIT; 0 free boundary points (see Q1).
3. **patch orbits (back + front, 4 frags)** — addressable *only* by adding ellipse admission
   geometry to `_merge_compound_siblings`; the existing circle gate rejects them (see Q1).

Every concentrated family needs either a gate relaxation or new geometry. There is **no**
family that the existing `_merge_compound_siblings` circle gate, the gradient
`_single_object` / free-boundary gates, or the completion T-junction test will admit as-is.
Contrast with ORBIT, where the fragments lay on one **circle** with a free arc — that is why
the existing machinery took ORBIT 44→38 and why it does **not** transfer here: patch/poster
break on *ellipses* and *fully-enclosed gradient discs*, which the current gates were
explicitly shaped to exclude.

---

## Conclusions and recommendation

**Pin the concentrated families as documented information limits** (mirroring the EMBER
precedent: `.agents/tasks/ember-separation-investigation.md` and the `test_robustness.py`
"below-the-floor" pins). The pins should assert the measured raster facts directly, with no
renderer:

1. **poster gradient-disc** — the disc ramp bands form **7** disconnected 4-connected
   components (fails `_single_object`); the authored circle rim is **247/360 occluded** by
   opaque overlays. Pin: "this disc is rendered as ≥2 mutually-disconnected regions, so it
   cannot be pooled into one gradient without crossing opaque occluders."
2. **patch shaded-planet** — the authored circle rim is **360/360 enclosed by the sky**
   (`#267d83`), giving `_grow_radial_bands` **0 free boundary points**. Pin: "the gradient
   disc has no free silhouette arc; its reunion would require inventing the occluded
   boundary."
3. **patch back-orbit / front-orbit** — same-colour interrupted **ellipse** rings whose
   pooled hull fails the circle gate (rms 35.5 / 41.9 vs gate 5.2 / 10.0) and fits an
   ellipse (rx≈105 ry≈283). Pin: "interrupted ellipse ring; the compound-sibling circle gate
   does not admit it, and the pooled hull is contaminated by same-colour panel-cell strokes."

**Explicitly rejected (per brief and AGENTS.md):** weakening the `_merge_compound_siblings`
circle gate, relaxing the gradient `_single_object`/free-boundary gates, editing the authored
targets or goldens, or using the VLM for geometry. None of these would be a measured,
gate-preserving win; each would risk false merges across unrelated same-colour or same-ramp
regions elsewhere in the suite.

**If a future session chooses to invest in new geometry (a separate, scoped change — not a
gate-preserving quick win):** the single highest-leverage *direction* is an **ellipse
extension of `order._merge_compound_siblings`** for the patch orbits. The fragments already
share occluders (the test the routine trusts) and lie on one common ellipse; adding a
`fit_ellipse` admission arm alongside the existing `fit_circle` one — with an equally tight
RMS/arc gate and the same shared-occluder requirement — would reunite back-orbit and
front-orbit (4 fragments → 2 objects, ~72→70 on the patch). This is a real geometry addition
with false-positive risk (the contaminated hull above), so it must be scoped as its own
measured change that moves a `plate bench` / `challenge_report` number and ships with its own
regression test — **not** bundled with the limit pins, and **not** represented as reuse of
the current gate. The two gradient-object fragmentations (planet, poster disc) have no such
avenue: they are faithful renderings of single objects genuinely broken by opaque overlays,
and are honest information limits.

---

## Reproduction (read-only)

- Diffs: `… -m challenge_report complex_mission_patch` / `complex_event_poster`.
- Probes (throwaway, under `/tmp`, not committed):
  `probe_actual.py` (emitted fragment geometry), `probe_raster.py` (planet column scan +
  orbit component counts), `probe_orbit.py` (circle-vs-ellipse fit on orbit hulls),
  `probe_grow.py` / `probe_grow2.py` (`_grow_radial_bands` gate trace → 0 free boundary pts),
  `probe_planet_boundary.py` (planet rim 360/360 enclosed by sky),
  `probe_crater3.py` (crater-3 contrast ≈16.8), `probe_poster.py` / `probe_poster2.py` /
  `probe_poster3.py` (poster disc: 1 gradient recovered, 26 ramp-band extras, 7 disconnected
  components).
- Core measurements: PNG↔SVG 1:1 (both 960×960); planet rim 360/360 foreign-occluded;
  patch background root frac 0.5997 (< 0.60, so sky is foreign not background); orbit circle
  fit rms 35.5/41.9 vs gate 5.2/10.0; poster disc = 7 four-connected components, 26/39 extras
  are disc-ramp bands inside r=260.
