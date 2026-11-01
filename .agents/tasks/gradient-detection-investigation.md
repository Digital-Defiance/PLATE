# Gradient under-detection on realistic shading — read-only investigation

Repo: `/Volumes/Code/PLATE` (clean, main @ af219c8). CPU-only classical converter.
All numbers below are measured with `.venv/bin/python` against the real corpus and the
synthetic/control gradient fixtures. No repo files were modified.

---

## Summary answer (read this first)

**The realistic radial orb is not lost in a gradient gate at all — it is lost one stage
earlier, in `segment()`.** For `real_radial_orb.png`, `segment()` returns **1 shape**: the
palette collapses to a single colour `(239,234,224)`, the whole ramp is nearest-assigned to
it, and `gradient.detect()` therefore receives **zero band candidates**. The gradient gates
(`grad_min_bands`, `grad_max_residual`, `_single_object`, `grad_band_max_frac`,
`grad_min_frac`, `grad_step_de`) never even run on a ramp region, because no ramp region
exists. The failing stage is **`segment._build_palette`**, specifically its flat-art count
floor (`counts >= 0.0004·len(px)`) combined with the `color_merge = 8.0` Lab dedup.

`real_sunset_gradient.png` is a different, harder failure: `segment()` *does* posterize it
(101 bands), a 94-band component forms, it passes the residual gate (radial RMS 0.0577 ≤
0.06), but it **fails the `_monotone_ok` gate** — the component pools foreground objects into
the sky via dE-adjacency, so the fitted axis reverses by 149–363 (per channel) against a
backstep budget of 15.3. That rejection is *correct*: the 94-band blob is not one clean ramp.

**Verdict:**
- `real_radial_orb`: **ADDRESSABLE — new segmentation geometry** (a smooth-ramp region
  detector / ramp-aware palette path). It is NOT a safe gradient-gate tune: the gate chain is
  never reached, and the naive upstream fix (letting ramps posterize) shatters the orb into
  **2666 regions / 27 fragmented mini-gradients** (measured), which is worse, not better.
- `real_sunset_gradient`: **genuine LIMIT at current band-grouping geometry.** The monotone
  gate is doing its job; recovering it needs ramp-vs-foreground separation the stage does not
  model, not a threshold change.
- There is **no safe, gate-preserving threshold tune** that recovers either image without
  regression. Loosening the palette count floor or `color_merge` to admit ramp colours
  directly regresses flat art (see §4). Recommended next step is the scoped new work in §5.

---

## 1. `real_radial_orb.png` — exact failing stage, measured

Probe: `/tmp/probe_grad.py`, `/tmp/probe_seg.py`, `/tmp/probe_pal.py`, `/tmp/probe_pal2.py`
(all read-only; import `plate` from `src/`).

### 1a. It never reaches the gradient gates

```
IMAGE: samples/real/real_radial_orb.png   work 700x700 (490000 px) scale 1.0
  segment() -> 1 shapes (1 non-empty)
  thin bands (area <= 73500px): 0 of 1
  OVERSIZE shapes (area > band_max): 1   frac = [1.0]
  _find_components ACCEPTED 0 gradient component(s)
  --- component growth report ---   (empty: no thin bands to seed from)
```

`gradient._find_components` (src/plate/stages/gradient.py:70) builds its thin-band set from
`seg.shapes`. With one full-canvas shape there are **no thin bands**, so the adjacency graph
is empty and the loop produces nothing. Full pipeline confirms: `real_radial_orb` →
`shapes=1, gradients=0, primitives=1, anchors=4` (one filled circle). This matches
`docs/REAL-CORPUS.md` (1 object, 4 anchors, 0 gradients, SSIM 0.83).

So for the orb the "failing gate" is upstream: **`segment()` emits a single region.** None of
`grad_min_bands` / `grad_max_residual` / `_single_object` / `grad_band_max_frac` /
`grad_min_frac` / `grad_step_de` is the cause — they are never consulted.

### 1b. Why `segment()` collapses it — `_build_palette`

Measured in `segment()` (src/plate/stages/segment.py:148) on the orb:

```
opaque = 490000   edge = 291758   flat(before fallback) = 198242   flat/opaque = 0.405
fallback-to-all-opaque? False
palette size = 1          # colours: [(239,234,224)]  (the near-white background)
source opaque RGB range: min [0,10,38]  max [255,255,255]   luma span 244.8
source Lab range: L 3.3..100.0   a -5.0..10.5   b -34.8..10.2
unique source RGB colours in opaque = 29617
```

The orb is a wide, smooth blue→near-black ramp on a near-white field (Lab L spans the full
3.3..100). But `_build_palette` (src/plate/stages/segment.py:40) keeps only colours that
*repeat often enough*:

```
flat px = 198242
count floor = max(2, int(0.0004 * 198242)) = 79
unique flat colours = 12645
colours surviving the count floor = 267
   ... all 267 are the background cluster: Lab L 91.5..93.5,
       within 0.35..2.86 dE of the heaviest colour (267 of 267 inside color_merge=8.0)
after color_merge(8.0) dedup -> palette = 1 colour
```

The smooth ramp spreads its luminance over **29617 unique colours**, so no individual ramp
colour repeats ≥79 times; only the flat background survives the floor, and the 267 survivors
are all one near-white cluster that `color_merge` collapses to a single swatch. Raising
`max_colors` to 32 and dropping `color_merge` to 3.0 **still yields 1 colour** (the ramp
colours never reach the merge step — they are filtered by the count floor first).

The ramp pixels are then assigned to that one palette entry by `_fill_unknown` / the nearest
-colour edge logic, producing one region. **This is the root cause for the orb.**

Note (rules out an alternative hypothesis): the ramp is *not* mostly killed by the edge mask.
At `edge_threshold = 10` only **16.1%** of the orb body is classed as edge (measured in
`/tmp/probe_edge.py`); 84% is "flat". The collapse is the palette count floor, not edge
dilation.

---

## 2. Why synthetic `shaded.png` succeeds where the realistic orb fails

Measured side by side (`/tmp/probe_grad.py`, `/tmp/probe_seg.py`, `/tmp/probe_edge.py`):

| metric | `shaded.png` (synthetic) | `real_radial_orb.png` (realistic) |
|---|---|---|
| canvas | 400×400 (160000 px) | 700×700 (490000 px) |
| unique opaque RGB colours | **357** | **29617** |
| interior Lab-grad median | **2.16** (90pct 5.69) | 6.64 (90pct 11.26) |
| `_build_palette` result | **11 colours** | **1 colour** |
| `segment()` shapes | **12 bands** | **1 region** |
| band fractions (top) | 0.227, 0.173, 0.113, 0.106, 0.074, … | [1.0] |
| gradient component | **1 radial, 8 bands, 70661 px** | none |
| chosen fit residual | **0.0104** (lin 0.1187 / rad 0.0104) | n/a |
| full-pipeline gradients | **1** (5 shapes, SSIM ~0.956) | **0** |

The difference is **not** the gradient fit and **not** any gradient gate. It is how coarsely
each image posterizes:

- `shaded.png` is **synthetically chunky** — 357 unique colours, each ramp step repeats on
  thousands of pixels, so 11 palette entries survive the count floor and `segment()` cuts it
  into 12 fat bands. Those bands pass `grad_min_bands` (8 ≥ 6), fit a radial ramp at residual
  **0.0104** (far under 0.06), and are accepted.
- `real_radial_orb.png` is **realistically smooth** — 29617 unique colours, no repeated ramp
  step, so the ramp is invisible to a count-floor palette and the whole disc becomes one
  region. The affine-radial model is *not* the blocker (see §2a); the input never gets far
  enough to be fit.

### 2a. The radial model itself is adequate for the orb

To isolate whether the ramp is "outside what the affine radial fit admits", I fed `segment()`
a fixed 16-step palette sampled along the orb's own radius (`/tmp/probe_orb_forced.py`). With
bands present, `gradient._find_components` **does** find radial components — proving the fit
accepts the orb's falloff. But forced posterization is not a fix: it shatters the orb into
**2666 regions** and **27 small fragmented gradient components** (members 6–25, ≤1533 px
each), because the anti-aliased transitions between 16 bands become thousands of sliver
regions. So the orb's failure is "too smooth for a count-floor palette", and the obvious
counter (force bands) trades one bad output for a worse one.

---

## 3. `real_sunset_gradient.png` — which gate loses it

Measured (`/tmp/probe_grad.py`, `/tmp/probe_sunset2.py`):

```
segment() -> 101 bands (all thin; none oversize)
largest dE-adjacent component: 94 members, 414607 px (69% of canvas)
  fit: linear RMS 0.0598   radial RMS 0.0577  -> chooses radial, residual 0.0577
  residual gate (<= 0.06): PASS
  monotone check (budget 15.3 per channel):
     ch0 endpoint delta  -68.4   backstep 149.5   FAIL
     ch1 endpoint delta  -96.4   backstep 363.6   FAIL
     ch2 endpoint delta  -23.9   backstep 200.1   FAIL
  _monotone_ok = False  -> component REJECTED
```

**Failing gate: `gradient._monotone_ok`** (src/plate/stages/gradient.py:52). The component
clears residual but its per-channel colour sequence along the fitted axis reverses by
149–363 against a 15.3 budget. That is the gate working correctly: the 94-band component is
not one ramp — `grad_step_de = 14.0` dE-adjacency has chained the sky ramp together with
foreground elements (sun/horizon objects of similar neighbour-dE), so there is no single
monotone axis. Smaller components (5 and 1 members) fail `grad_min_bands`. Net: 0 gradients,
78 flat objects in the full pipeline, matching the corpus table.

A secondary signal: the fit picks **radial** (0.0577) over **linear** (0.0598) by 0.0021 on
what is a linear-ish sunset, because the pooled blob is not clean enough for linear to win.
Even forcing linear still fails monotone (measured), so the fit-kind tie is not the blocker —
the blob composition is.

---

## 4. Is there a safe, gate-preserving or evidence-backed tunable change? (measured)

**Baseline full-pipeline gradient counts (default `Config`), the regression surface:**

```
case                     shapes  grads  (must hold)
orb                          1      0
sunset                      78      0
shaded                       5      1    <- must stay 1 radial
t3_linear_grad               2      1    <- control, must stay 1
t3_radial_grad               2      1    <- control, must stay 1
t4_grad_behind_circle        3      1    <- control, must stay 1 (+linearGradient in SVG)
discrete_palette             9      0    <- must stay 0
twin_gradients              (challenges/)  2 linear  (component level)
gradient_badge              (challenges/)  2 radial  (component level)
```

`tests/test_gradient_bands.py` passes (9/9) and the gradient controls assert exact gradient
counts and kinds (`tests/test_controls.py`, e.g. `t4_grad_behind_circle` requires
`<linearGradient>` and the circle on top). Any change has to preserve all of the above.

Candidates considered and why each is unsafe or insufficient:

- **Lower / remove the palette count floor (`0.0004·len(px)`)** so ramp colours survive.
  Measured effect on the orb: with `counts >= 2` the merged palette is 11 colours — but this
  floor is exactly the flat-art guard. Dropping it admits photo/JPEG noise colours across the
  corpus; `discrete_palette` and the swatch/mosaic fixtures rely on the heavy-colour floor to
  stay flat. It also does not cleanly fix the orb: the AA transitions still fragment it (§2a).
  **Regresses flat art; rejected.**
- **Lower `color_merge`** — does not help the orb at all (the 267 survivors are all the
  background; ramp colours are filtered *before* the merge by the count floor). **No effect on
  the target; rejected.**
- **Loosen a gradient gate (`grad_min_bands`, `grad_max_residual`, `_monotone_ok`,
  `grad_step_de`).** None is reached for the orb (0 candidates). For the sunset, loosening
  `_monotone_ok` would accept a 69%-of-canvas non-ramp blob (backstep 149–363) as a single
  gradient — a clear false positive that would also start admitting multi-object blobs
  elsewhere. **Weakens a validated gate without evidence it is safe; rejected per the brief.**
- **Raise `grad_band_max_frac` / lower `grad_min_frac`.** Irrelevant to both failures (orb has
  no bands; sunset's blocker is monotonicity, not size). **No effect; rejected.**

**Conclusion: no safe quick-tune exists.** The orb needs segmentation to recognise a smooth
ramp as a ramp *before* palette quantisation destroys it; the sunset needs the band grouping
to separate the sky ramp from foreground objects. Both are new geometry, not lever changes.

---

## 5. Recommendation — the single most promising, lowest-risk next fix

**Scope it as ADDRESSABLE new segmentation geometry, and start with the orb (the cleanest,
highest-value case): add a "smooth single-ramp region" detector that runs in `segment()` /
as a pre-pass to `gradient.detect()`, and feeds the existing affine radial/linear fitters
directly from the raw region pixels instead of requiring posterized bands.**

Why this one:

- It attacks the *actual* failing stage for the orb (palette collapse in `_build_palette`),
  which `docs/REAL-CORPUS.md` + `STATUS.md` flag as the top realistic-gradient target.
- It reuses machinery that is already proven on the orb's geometry: `fit_radial_gradient` /
  `fit_linear_gradient` accept the orb's falloff when given its pixels (§2a). The missing
  piece is only *candidate formation without bands*.
- It is **gate-preserving by construction**: it adds a new acceptance path for regions that
  (a) cover one 4-connected opaque blob, (b) have high within-region luma variance but low
  local Lab gradient (smooth, not textured/noisy — orb median 6.64 vs noise), and (c) fit the
  affine radial/linear model at RMS ≤ `grad_max_residual`. Flat art fails (b)+(c); the
  existing band path, `grad_min_bands`, and all control fixtures are untouched because their
  inputs still posterize and flow through the unchanged path. The new path only *adds*
  gradients where today there are zero.

Concrete shape of the change (for the implementer; not implemented here):
1. In `segment()`, before per-region emission, detect candidate ramp blobs: a 4-connected
   opaque component whose interior Lab-gradient is smooth (median below a small threshold,
   e.g. ~8, measured: orb 6.64) but whose luma span is large (orb 244.8), and whose unique
   -colour count is high relative to repeated-colour mass (orb 29617 uniques, ~0 repeated).
   This is exactly the signature that defeats the count-floor palette.
2. Fit `fit_radial_gradient` / `fit_linear_gradient` on the blob's raw pixels; accept only if
   residual ≤ `grad_max_residual` (orb radial fit is well under 0.06 per §2a). On accept, emit
   **one** `Shape` carrying the `GradientFill` (bypassing posterization) and skip adding its
   colours to the flat palette.
3. Verification gate for the PR: `shaded.png` still → 1 radial gradient / SSIM ≥ 0.95;
   `t3_linear_grad`, `t3_radial_grad`, `t4_grad_behind_circle` unchanged (exact counts +
   `<linearGradient>`); `discrete_palette` stays 0; `twin_gradients`/`gradient_badge`
   unchanged; `real_radial_orb` → 1 radial-gradient disc with SSIM measurably above 0.83.
   Run `tests/test_gradient_bands.py` + `tests/test_controls.py` (both currently green) and
   `plate bench samples/real`.

**`real_sunset_gradient` is lower priority and genuinely harder.** Its blocker is
ramp-vs-foreground separation inside the dE-adjacency grouping, not a threshold. Recommend
pinning it as a documented limit (like the existing mission_patch/event_poster gradient pins
in `STATUS.md`) unless/until the ramp-region detector above can also claim large smooth
background ramps and exclude the foreground objects that currently poison its 94-band
component.

### Honest classification recap
- `real_radial_orb`: **ADDRESSABLE — new segmentation geometry** (ramp-region detector).
  Not a safe lever tune; the gate chain is never reached and forcing bands regresses to 2666
  fragments.
- `real_sunset_gradient`: **LIMIT at current band-grouping geometry** — the monotone gate is
  correctly rejecting a non-ramp blob; needs ramp/foreground separation, not a tune.
- Across the corpus, "only 2/14 emit a gradient" is the same root signature: realistic smooth
  shading does not survive the flat-art palette as bands, so the band-only gradient stage has
  nothing to work with.

---

## Evidence index (read-only probes under /tmp, repo untouched)
- `/tmp/probe_grad.py` — per-image band count, sizes, component growth, gate that fails, fit
  residuals (orb / shaded / sunset).
- `/tmp/probe_seg.py` — `segment()` internals: palette size, colour/Lab ranges, unique counts.
- `/tmp/probe_pal.py`, `/tmp/probe_pal2.py` — `_build_palette` count-floor + `color_merge`
  collapse on the orb (267 survivors → 1 colour; all within 2.86 dE of background).
- `/tmp/probe_edge.py` — orb body is only 16% edge at `edge_threshold=10` (rules out edge-mask
  as the cause); orb vs shaded interior Lab-gradient.
- `/tmp/probe_orb_forced.py` — forced ramp palette proves the radial fit accepts the orb but
  posterization shatters it (2666 regions / 27 fragmented components).
- `/tmp/probe_sunset2.py` — the 94-band component residual PASS / monotone FAIL detail.
- `/tmp/probe_fullrun.py` — full-pipeline gradient baseline (the regression surface in §4).
- Code read: `src/plate/stages/gradient.py` (detect / _find_components / _single_object /
  _monotone_ok / _grow_radial_bands / merge_occluded), `src/plate/stages/segment.py`
  (_build_palette + edge/flat logic), `src/plate/geometry.py` (fit_linear_gradient /
  fit_radial_gradient / _binned_stops), `src/plate/config.py` (grad_* levers + inline
  rationale), `src/plate/pipeline.py` (gradient runs between segment and order.build),
  `STATUS.md` / `HANDOFF.md` / `ROADMAP.md` gradient history, `docs/REAL-CORPUS.md`.
- Tests confirmed green: `tests/test_gradient_bands.py` 9/9.

Content was rephrased for compliance with licensing restrictions where repo docs were
summarized.
