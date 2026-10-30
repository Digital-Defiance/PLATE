# PLATE audit — 2026-10-30

The classical converter is a substantial, working engine. The hosted service is
still a design. The next milestone is a safe, deployable conversion service;
closing every authored-logo reconstruction gap is deferred under the direction
recorded in [SERVICE.md](SERVICE.md).

## Resolution update — 2026-10-30

The later native-layer checkpoint adds **352 passing tests/7 structural xfails**
and **24/24 Illustrator 30.8.2 workflows, 636/636 checks**. Real layers now import
through Adobe namespace markers and explicit standalone-object containers;
geometry and both-background pixels are unchanged. The original audit tables
below retain their historical measurements. README/ROADMAP now explicitly separate
PNG decoding, appearance, structural recovery and SVG interchange: PLATE does not
cover every meaningful PNG. See STATUS.md and `docs/illustrator-checklist.md`.

Both reliability findings below are **fixed** (release `dceaae2` plus the loader
fix in the requested checkpoint). Declared-depth
normalization now maps the dark 16-bit sample to the correct value; batch reports
counts and exits 1 on any conversion failure while preserving valid outputs.
**19 regression cases** were added: final full suite **326 passed/7 xfailed**
(baseline 307/7, including the separate output-error/packaging edits). All 24
fixture SVGs remain byte-identical to this audit; the independent dark-16 reference
improves from MAE 199/SSIM .0102 to MAE 0/SSIM 1.0. See STATUS.md and
`/tmp/plate-bugfix-final-tests.txt`. A concurrent release commit included the batch
fix; Jessica requested the loader, regressions and audit docs be committed with
the native Illustrator checkpoint. Use `git log -1` for the resulting commit.

## Original verified audit snapshot

- Engine HEAD: `101b63d` (translucent opacity), after `a4ade05` (input hardening),
  `e9d66af` (circular holes) and `1f54ffe` (adaptive stroke fitting).
- Full suite: **303 passed, 7 strict expected failures**, no skips, in 128.95s.
  Log: `/tmp/plate-audit-tests.txt`. An output-permission CLI regression was added
  concurrently after collection; its current input-test module was checked
  separately: **23 input tests passed** in `/tmp/plate-audit-input-tests.txt`.
- Fresh benches: **8 original samples + 16 challenges**, with plain VTracer retained.
  Outputs: `/tmp/plate-audit-{samples,challenges}`. The 16 challenge SVGs were
  independently checked against their authored targets: **9 pass structurally;
  7 remain expected gaps; all 16 meet fidelity floors on white and dark**.
- Measurements: `/tmp/plate-audit-results.json`; rendered overview:
  `plate-audit-overview.png` in this chat's visualization directory.
- No service implementation, Dockerfile or CI workflow is present. No real-image
  corpus exists in `samples/real/`. Illustrator's checklist remains unchecked.
- At the audit snapshot, `src/plate/cli.py` and `tests/test_inputs.py` contained
  concurrent, uncommitted output-error handling work. Those edits were preserved.
  The local `origin/main` ref equalled HEAD; this was not a remote fetch audit.

## Current structural gaps

Counts below are **actual / desired**, measured from SVGs. Matching counts do not
imply correct editable geometry. All seven full contracts remain strict xfails.

| Challenge | Objects | Strokes | Anchors | SSIM white / dark | Remaining issue |
| --- | --- | --- | --- | --- | --- |
| ORBIT | 44 / 34 | 7 / 7 | 345 | .9846 / .9925 | Compound navy geometry and ambiguous ramp patches; all intended strokes/core already pass |
| EMBER | 51 / 51 | 3 / 7 | 455 | .9665 / .9685 | Shield full silhouette, merged same-colour details, missing strokes |
| ROOT | 51 / 56 | 9 / 32 | 526 | .9834 / .9871 | Touching organic/ring shapes and missing strokes |
| PLATE identity | 11 / 11 | 1 / 3 | 121 | .9907 / .9956 | Hidden rear-P geometry is not uniquely observable; back-P IoU .1387 |
| Mission patch | 72 / 45 | 8 / 10 | 807 | .9817 / .9831 | Fragmented planet, missing linear hull ramp and compound/completion work |
| Storefront | 73 / 64 | 3 / 4 | 571 | .9738 / .9752 | Object merging/fragmentation and curve/corner decisions |
| Event poster | 83 / 44 | 0 / 6 | 639 | .9715 / .9715 | Crossing lettering/ribbon and underlying shapes |

The instrument panel remains **59 objects / 27 strokes / 249 anchors** and passes.
The perforated plate now uses **20 anchors** and reaches **.9961 white SSIM**.
The earlier ROOT 3/32 and EMBER 2/7 status claims are stale: adaptive refitting
raised them to 9/32 and 3/7 without lowering the stroke-acceptance gate.

## Confirmed reliability findings (now resolved)

### 1. Dark 16-bit PNGs can decode far too brightly

[`imageio._to_8bit`](../src/plate/imageio.py) scales an integer image only when its
observed maximum exceeds 255. A valid 16-bit image whose samples are all below
256 therefore bypasses scaling.

Reproduction: a 16×16 `uint16` PNG filled with **200** opens as mode `I;16` and
PLATE returns **200** in 8-bit RGB; full-range 16→8-bit mapping should return **1**.
Samples 257 and 32768 return the expected 1 and 128, confirming the low-range
branch is the problem. Probe files: `/tmp/plate-audit-probes/dark16_*.png`.

Resolution: normalization now uses declared 16-bit mode/depth, including legacy
Pillow integer PNGs whose format context is retained before EXIF copying. Tests
cover zero/dark/full range and both byte orders. General integer/float policy is
unchanged; the independent dark-16 trace exactly matches its 8-bit reference.

### 2. Batch failure is reported as a successful process

[`cli._batch`](../src/plate/cli.py) catches every per-file exception, prints
`FAILED`, then always returns 0. A folder containing only a corrupt `.png`
prints an input error and exits **0** with no output SVG.

Reproduction input: `/tmp/plate-audit-probes/batch/broken.png`; command:
`plate batch /tmp/plate-audit-probes/batch -o /tmp/plate-audit-probes/batch-out`.
Resolution: valid files continue to convert, a success/failure summary is printed,
and any per-file failure yields exit 1. All-success exits 0; empty input retains
exit 2. Successful, all-failed and mixed batches have regressions. The separate
top-level `OSError` handler was preserved.

## Hosted-service readiness

[SERVICE.md](SERVICE.md) records the product direction: free daily quota, an
anonymous demo, supporter entitlements through Stripe, and classical conversion
at launch. AI naming is later. None of the following service components exists yet:

1. Upload/job/download API with a small preview interface.
2. Isolated conversion worker, queue/backpressure, job states and time/memory limits.
3. Pre-decode byte/dimension limits, validated formats, separate abuse rate limits,
   per-user result isolation and upload/result expiry.
4. Accounts, daily quota accounting and race-safe quota enforcement.
5. Verified, idempotent Stripe webhooks and supporter entitlement lifecycle.
6. Container/deployment configuration, CI, monitoring and operational failure paths.

The engine loader currently decodes the image before working-size reduction;
`work_size` is **not** an upload/decode memory limit. Existing Pillow protections
are useful but do not implement the service's explicit resource limits.

Do not use the design's “well under a second” claim as a capacity guarantee.
Indicative local timings during this audit: face **.191s**, ORBIT **3.630s**, mission
patch **5.220s**. Tests were also running, so these are neither isolated production
benchmarks nor hosting estimates. Measure worker throughput, peak memory and tail
latency on the chosen deployment platform before setting concurrency limits.

Unresolved launch choices remain hosting and auth provider; the design records
advisor review for funding/receipt wording. Its open-questions section redundantly
asks to confirm quota/demo details already listed as decided—reconcile those when
implementation begins.

## Next work, in order

1. Completed in the working tree: both reproduced reliability fixes and their
   regressions, with geometry/fidelity contracts preserved. Separate output-error
   and packaging work is now included in concurrent release commit `dceaae2`.
2. Build a minimal classical upload → queued worker → preview/download slice with
   explicit job/resource limits. Keep the engine separable and CPU-only.
3. Add account/quota enforcement, anonymous abuse limits, ownership and expiry.
4. Add Stripe entitlement handling, deploy/CI/monitoring and end-to-end failure tests.
5. Complete Illustrator import checks and a representative 10–20-image real-artwork
   corpus before describing the product as broadly validated.

Defer the seven hard geometry gaps and optional AI until product evidence calls
for them. Smooth opacity/shadows and scale consistency remain partial, not fully
solved by flat-region opacity support.
