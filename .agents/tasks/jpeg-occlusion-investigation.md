# JPEG occlusion-recovery investigation (read-only)

Repo: `/Volumes/Code/PLATE` @ `425fa19` (clean). Corpus: `plate corpus -o /tmp/jpeg-bo -n 24 --seed 1`
(default `noisy_every=4` → JPEG variants are scenes **03, 07, 11, 15, 19, 23**; q=55). All numbers below
are measured on that corpus with the shipped default `Config` (no code changed).

---

## Summary answer

**Root cause is a two-link failure, classification (a) + (d): the auto-denoiser never fires on
JPEG-q55 damage (a), and the un-denoised, JPEG-roughened region boundary then defeats the
primitive-fit tolerance gate inside `complete.try_complete` (d).** The T-junction occlusion test
that `docs/BAKEOFF.md` names as the prime suspect is **exonerated** — it still finds the junctions
and scores the occluder correctly on JPEG input. The break happens one step later, when
`fit_rect`/`fit_circle`/`fit_ellipse` are applied to the free (unoccluded) contour points: JPEG
ringing displaces the segmentation boundary, so the free-point fit RMS jumps past the acceptance
tolerance and completion returns `None`.

Secondary mode, classification (c): on one scene (scene23) JPEG blocking adds a palette colour and
**shatters** segmentation (4 → 65 regions), so no clean contour exists at all.

**Verdict: ADDRESSABLE-needs-measured-tradeoff, with a hard partial-LIMIT floor.** The only link
that recovers JPEG occlusion is denoising *pixels before segmentation* (contour smoothing after
tracing does not work — see §4). But **no global denoise-gate change is safe**: clean, edge-dense
shipped art has a higher `noise_fraction` than the JPEG scenes, so any threshold that catches JPEG
also re-denoises ≥10 shipped SVGs and breaks their byte-identical guarantee. A safe fix therefore
needs a *JPEG-specific* trigger (not the existing noise estimators) or an explicit opt-in, and even
then the ceiling is ~0.6 because 3 of the 10 occluded objects are unrecoverable **even on the clean
render**.

**Headline correction:** on this corpus PLATE recovers **3/10** occluded JPEG objects at the shipped
default, not 0/10. The "0/10" in `docs/BAKEOFF.md` came from a different corpus configuration; the
*mechanism* it describes is real but the attribution (T-junction test) is wrong.

---

## Evidence

### The bake-off result reproduced

`plate bakeoff /tmp/jpeg-bo/images --truth /tmp/jpeg-bo/truth` → PLATE composite 0.843, first overall.
Per-scene `hidden_completion` / `obj_complete_f1` from `/tmp/jpeg-bo/out/results.csv` (JPEG scenes):

| scene | hidden_completion | obj_complete_f1 | n_elements | anchors/shape |
|---|---|---|---|---|
| scene03_jpg | **0.0** | 0.25 | 6 | 19.5 |
| scene07_jpg | 1.0 | 1.00 | 5 | 4.0 |
| scene11_jpg | 0.5 | 0.67 | 8 | 5.75 |
| scene15_jpg | **0.0** | 0.29 | 4 | 7.0 |
| scene19_jpg | 0.5 | 0.73 | 7 | 19.9 |
| scene23_jpg | **0.0** | 0.06 | **65** | 4.2 |

JPEG damage does *not* uniformly break completion — 07/11/19 recover fine. The failures cluster in
two shapes: contour roughening (03) and segmentation shatter (23); 15 is a false attribution (below).

### Link-by-link divergence on the representative scene (scene03_jpg)

I rendered the **clean** PNG from the shared ground-truth SVG (`truth/scene03_jpg.svg`) and ran PLATE
on clean vs the q55 JPEG. First divergence walks down the chain:

Pipeline stats (`pipeline.run`, default cfg):

| metric | CLEAN | JPG |
|---|---|---|
| `imageio.noise_fraction` | 0.0002 | **0.0171** |
| `imageio.interior_noise_fraction` | 0.0000 | 0.0003 |
| auto-denoise fires? (`>0.04` OR `>0.002`) | No | **No** |
| segmentation palette size | 4 | 4 |
| shapes | 5 | 6 |
| anchors | 37 | **117** |
| completed (hidden recovered) | **1** | **0** |
| structure `hidden_completion` | **1.0** | **0.0** |

- **Link 1 — denoise (`imageio.load_image`):** `noise_fraction`=0.0171 < 0.04 and
  `interior_noise_fraction`=0.0003 < `cfg.interior_noise`=0.002, so the auto-denoise branch does
  **not fire**. JPEG ringing is edge-localized and structured, so it slips under both estimators —
  the global one is confounded by (and here diluted by the scene's sparse edges), the interior one
  reads ~0 because ringing does not reach flat interiors. **This is classification (a), and it holds
  for every JPEG scene** (all `noise_fraction` 0.0106–0.0264, all interior ≤0.0007; none fire).
- **Link 2 — segmentation (`stages/segment.py`):** palette is unchanged (4 vs 4) and object count is
  near-right (5 → 6). Segmentation is **not** the first divergence for scene03. (It *is* for scene23 —
  see below.)
- **Link 3 — occlusion test (`complete._junctions` / `_occludes`):** instrumented the relative
  T-junction score for the occluded rect (shape3) against its occluder. The test **still fires** on
  JPEG: `_occludes` identifies the correct occluder set `real occluders=[5]` (clean: `[2,4]`), and the
  free/occluded point split is healthy (JPG: `n_occl=139`, `n_free=462`; gate needs occl≥4,
  free≥120 — passes). The 15° angle test is **not** the break. (`_occludes` angle for shape3↔its big
  neighbour did collapse to +0.5 on JPG vs +108 clean, but a *different* neighbour still provides a
  passing occluder, so the occluded-point set is recovered either way.)
- **Link 4 — primitive fit (`complete.try_complete`, `geometry.fit_rect`): THIS is the first
  divergence.** On the free contour points:

  | fit (scene03 shape3) | CLEAN RMS | JPG RMS | tol |
  |---|---|---|---|
  | `fit_rect` | **1.52 ✓** | **6.22 ✗** | ~2.3 |
  | `fit_circle` | 11.96 | 11.56 | — |
  | `fit_ellipse` | 6.93 | 7.02 | — |

  Clean: `fit_rect` RMS 1.52 ≤ tol 2.32 → `try_complete` returns a completion. JPG: RMS **6.22** > tol
  2.31 → all three primitive fits fail, no `len(contours)==1` Bézier bridge (the shape has holes/
  multiple contours), so `try_complete` returns `None`. **The occluded rect is emitted as its raw
  visible cut-out instead of completed.** The anchor explosion (37 → 117) is the same roughened
  boundary showing up in the traced paths.

So the first point that diverges is the **mean-deviation primitive-fit gate in `try_complete`**, fed a
boundary that JPEG ringing has displaced (not merely jittered).

### scene23_jpg — the (c) shatter mode

| metric | CLEAN | JPG |
|---|---|---|
| palette | 4 | **5** |
| shapes | 4 | **65** |
| completed | 1 | **0** |
| `obj_complete_f1` | 0.571 | **0.059** |

Here the first divergence is **segmentation** (`stages/segment.py`): JPEG blocking introduces an 8×8
artifact colour that enters the palette (4 → 5) and fractures the regions into 65 pieces, so the
occluded object has no coherent contour to complete. This matches the `real_jpeg_artifacts → 269
objects` finding in `docs/REAL-CORPUS.md`. Forcing `denoise=3` de-shatters it (65 → 9 shapes,
`obj_complete_f1` 0.06 → 0.5) but still does not recover the specific occluded object (see ceiling).

### scene15_jpg — a FALSE attribution (not JPEG at all)

| denoise | CLEAN recovered | JPG recovered |
|---|---|---|
| 0 / 2 / 4 / 6 | **0/2** | **0/2** |

scene15 recovers **0/2 occluded objects on the CLEAN render at every denoise level**. Its `_occludes`
score actually *passes* on JPG (+121 vs +98 clean) and `fit_rect` RMS is fine on both (0.45 vs 0.57) —
one object completes but below the IoU≥0.9 truth match, and a second occluded object never completes.
This is a **pre-existing completion/matching limit, independent of JPEG.** Counting it against "JPEG
robustness" is a misattribution.

### Why no global denoise gate is safe (`noise_fraction` overlap)

`noise_fraction` on clean shipped art vs the JPEG scenes (measured at the working resolution):

| clean shipped image | noise_fraction |  | JPEG scene | noise_fraction |
|---|---|---|---|---|
| badge.png | 0.0241 |  | scene23_jpg | **0.0106** (min) |
| donut_alpha.png | 0.0225 |  | scene11_jpg | 0.0145 |
| logo_ember_crest.png | 0.0286 |  | scene07_jpg | 0.0151 |
| logo_orbit_wordmark.png | 0.0399 |  | scene03_jpg | 0.0171 |
| logo_root_seal.png | **0.0423** |  | scene15_jpg | 0.0231 |
| complex_mission_patch.png | 0.0158 |  | scene19_jpg | 0.0264 (max) |

The ranges **overlap completely**: the cleanest shipped logos score *higher* than every JPEG scene,
because `noise_fraction` is confounded by edge density (the code comment in `imageio.py` already says
so) and the synthetic scenes are edge-sparse. Lowering the global gate to 0.012 (needed to catch the
JPEG minimum 0.0106) would newly denoise **10 shipped images** — badge, donut_alpha, poster, panel,
patch, ember, orbit, root, dial, noisy_badge — breaking the byte-identical SVG guarantee and almost
certainly the 70/78 sweep. The `interior_noise_fraction` estimator does not help either: JPEG interior
values (0.0001–0.0007) sit at the clean-art floor, below the 0.002 lever, because ringing is an edge
phenomenon. (Note `logo_root_seal.png` at 0.0423 already trips today's 0.04 gate, so its shipped SVG is
already a denoised output — fine, but it shows how close clean art sits to the gate.)

A naive 8×8-block-boundary roughness metric also fails to separate (clean `scene04.png`=1.73 and
`shaded.png`=1.26 land inside the JPEG range 1.10–1.64), so a cheap spatial JPEG detector is not
robust on this flat-art corpus.

---

## Why the "smooth the contour harder" idea does NOT work

`docs/BAKEOFF.md` and ROADMAP suggest "smooth contours harder before junction analysis." Measured on
scene03's roughened free contour, Gaussian-smoothing the resampled contour (σ=1, 2) before the fit
leaves the `fit_rect` RMS essentially unchanged: **6.22 → 6.21**, still far above tol 2.31. The JPEG
damage is not high-frequency jitter on a correct boundary — ringing **systematically displaces the
region boundary** (colour bleed shifts where segmentation draws the edge), so the free points are
*biased*, not noisy. Smoothing a biased contour cannot remove the bias. The fix must restore correct
pixels **before** segmentation (denoise), which is exactly why `denoise≥1` helps and post-trace
smoothing does not.

---

## The realistic ceiling

Total occluded objects across the 6 JPEG scenes = **10**. Aggregate `hidden_completion`
(total recovered / total occluded) by denoise level:

| denoise | scene03 | scene07 | scene11 | scene15 | scene19 | scene23 | total |
|---|---|---|---|---|---|---|---|
| auto (shipped) | 0/2 | 1/1 | 1/2 | 0/2 | 1/2 | 0/1 | **3/10 = 0.30** |
| 1 | 1/2 | 1/1 | 1/2 | 0/2 | 1/2 | 0/1 | 4/10 = 0.40 |
| 3 | 0/2 | 1/1 | 1/2 | 0/2 | 2/2 | 0/1 | 4/10 = 0.40 |
| per-scene oracle | 1/2 | 1/1 | 2/2 | 0/2 | 2/2 | 0/1 | **6/10 = 0.60** |

- No *single* denoise level clears 0.6; the effect is non-monotonic (denoise=2 over-rounds scene03's
  rect corners and loses what denoise=1 recovered).
- **3 of the 10 objects are a hard floor**: scene15 (2) and scene23 (1) recover 0 **even on the clean
  render at every denoise level** — pre-existing completion limits, not JPEG damage.
- The JPEG-*addressable* universe is the **7 objects in scenes 03/07/11/19** that all complete on
  clean. A good denoise fix recovers ~6 of those 7, i.e. aggregate ≈ 0.60.

So **`hidden_completion` ≥ 0.6 on the JPEG variants is achievable but sits exactly at the ceiling**,
and only if (a) the denoise trigger is tuned per-image well enough to pick a helpful level and
(b) the 3-object floor is accepted as an honest limit (or attacked separately via the rect/polygon
completion P1 item, which is not JPEG-specific).

---

## Recommendation (single most promising, lowest-risk fix)

**Add a JPEG-class-damage trigger to the auto-denoise branch in `imageio.load_image`, independent of
the existing `noise_fraction`/`interior_noise_fraction` estimators, and keep it off the clean path.**
The mechanism (denoise fixes the region boundary so `try_complete`'s primitive fit re-passes) is
proven; the risk is entirely in the *trigger*, because the global estimators cannot separate JPEG from
clean edge-dense art.

Concrete, in rough order of safety:

1. **Safest / recommended:** make the denoise decision aware of the decoded source format. When the
   input is actually JPEG-encoded (PIL `im.format == "JPEG"`, already available in `open_rgba`), run a
   small, fixed denoise (measured best: **1 bilateral pass**, which took scene03 0→1 and did not lose
   any already-recovered scene). This touches **zero clean PNG inputs** — every shipped sample and
   challenge is PNG, so all 24 SVGs stay byte-identical by construction, and the 70/78 sweep (PNG) is
   untouched. It directly targets the corpus damage (the variants are literally `.jpg`). Add a
   regression test in `tests/test_bakeoff.py` asserting JPEG-variant aggregate `hidden_completion`
   rises (target ≥0.4, honest-stretch ≥0.6) and a `tests` assertion that the 24 shipped SVGs are
   unchanged.
   - *Caveat to record:* this keys on container format, so a clean photo-sourced JPEG would also get
     one bilateral pass. One pass of bilateral(9,40,5) is gentle and the existing `denoise=2` path
     already ships; measure SSIM on a clean JPEG before committing. If that is unacceptable, gate the
     format trigger behind a *DCT-domain* JPEG-artifact estimate (quantization-grid energy) rather
     than the spatial block metric, which §evidence showed is not separable.

2. **If a format-agnostic signal is required:** add a DCT-grid estimator (8×8 block-boundary energy in
   the DCT domain, or quantization-table presence) as a third OR-term in the auto gate. Do **not**
   lower the existing `noise_fraction` gate — measured to regress ≥10 shipped SVGs.

**Do NOT** (per the brief and the measurements): lower the 0.04 `noise_fraction` gate (regresses
shipped SVGs), loosen the 15° `_occludes` threshold (it is not the failure and loosening invites false
positives), loosen the `try_complete` primitive-fit tolerance (it would admit drifted silhouettes on
clean input too), or touch targets/goldens/VLM geometry.

### Expected effect, with regression evidence already gathered
- **Recovers JPEG occlusion:** denoise=1 on JPEG scenes takes aggregate `hidden_completion` 0.30→0.40
  immediately (scene03 0→1); reaching ~0.60 needs per-image level selection, which is a tuning
  follow-up, not a blocker.
- **Does not regress clean inputs:** the format-keyed trigger fires on no PNG, so the 24 shipped
  sample/challenge SVGs stay byte-identical and the 70/78 PNG sweep is untouched — *by construction*,
  not by luck. Clean bakeoff scenes are PNG (max `noise_fraction` 0.0004) and are likewise untouched.

### Honest limit to document alongside the fix
scene15 (2 objects) and scene23 (1 object) recover 0 even on clean input; they belong to the separate
"rect/polygon amodal completion" P1 weakness, not JPEG robustness. Pin them with a test asserting the
clean-render floor so a future reader does not re-chase them as JPEG bugs.

---

## Reproduction (read-only probes used)

- `/tmp/probe1.py`, `/tmp/probe_complete.py`, `/tmp/probe_tc.py` — pipeline + `_occludes` + `try_complete` trace, clean vs jpg.
- `/tmp/probe_score.py`, `/tmp/probe_fix.py`, `/tmp/probe_ceiling.py`, `/tmp/probe_ceiling2.py` — structure scoring and denoise sweep.
- `/tmp/probe_clean_noise.py`, `/tmp/probe_jpegdetect.py`, `/tmp/probe_regress.py`, `/tmp/probe_smooth.py` — safety/separability checks.

All probes import `plate` from `src/`, render with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`, and
only read the repo; no repo file was modified (git clean at `425fa19`).
