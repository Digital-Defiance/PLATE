# PNG decoding and conversion coverage

This matrix tests sample interpretation separately from artwork reconstruction.
It does not certify arbitrary PNG metadata, all damaged files, or every intended
editable structure. Broader artwork limits remain in README and ROADMAP.

## Verified static formats

`tests/png_fixtures.py` writes PNG bytes directly from integer samples using
stdlib `struct`/`zlib`, including packed sub-byte rows, all five scanline filters,
Adam7 passes and CRCs. It does not use the Pillow/OpenCV encoders under test.
Expected RGBA pixels come from those source samples, not a second decoded image.

| PNG colour type | Depths tested | Transparency contract |
| --- | --- | --- |
| 0: grayscale | 1, 2, 4, 8, 16 | Opaque and exact tRNS colour keys |
| 2: RGB | 8, 16 | Opaque and exact RGB tRNS keys |
| 3: indexed palette | 1, 2, 4, 8 | Opaque, full/partial palette alpha and implicit opaque table tail |
| 4: grayscale + alpha | 8, 16 | Explicit alpha, including near-zero/partial/opaque samples |
| 6: RGBA | 8, 16 | Explicit alpha, including hidden RGB values |

All **15 legal colour/depth combinations** are checked with ordinary rows and
Adam7 interlacing. Additional cases cover empty Adam7 passes, single-pixel/narrow
images, partial packed bytes and split/empty IDAT chunks. Fifteen equivalent
encodings of an independently specified transparent cutout must produce the exact
same editable SVG as an 8-bit RGBA reference, including the hole.

Current module: **111 cases** in `tests/test_png_matrix.py`:

- 30 colour/depth/interlace pixel contracts; 22 keyed/palette-alpha contracts.
- 4 full-16-bit transparency comparisons; 6 tiny/interlaced packing cases.
- 15 equivalent-encoding tracing checks; 3 illegal type/depth cases.
- 6 PNG EXIF orientation cases; 12 gAMA/sRGB sample-policy checks and 4 valid
  embedded sRGB ICC cases. ICC test-profile generation uses Pillow LittleCMS;
  those four tests skip if that optional Pillow feature is unavailable.
- 2 hidden-RGB invariance checks (native/downsampled working sizes); 2 APNG
  first/default-image checks; 3 full-depth decoder failure checks and 2 damaged
  CRC/deflate cases.

Run from the repository root:

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/pytest -q tests/test_png_matrix.py
```

## Interpretation policy

- PNG input becomes straight **8-bit RGBA**. Integer channels are normalized using
  their declared range; all 16-bit channels, including alpha, use nearest-integer
  `sample / 257`. Original 16-bit precision is not retained in SVG output.
- tRNS matching happens at the original sample precision. For 2/4-bit grayscale,
  the key must match the expanded 8-bit pixels. For 16-bit gray/RGB, only a full
  exact sample match is transparent, even if a nearby opaque sample rounds to the
  same 8-bit RGB. This follows the [PNG specification](https://www.w3.org/TR/png/).
- Pillow already reduces multichannel 16-bit pixels when exposing RGB/RGBA. PLATE
  uses the existing OpenCV dependency's unchanged decoder to retain full samples
  through transparency comparison and rounding, then applies EXIF once. Decoder
  failures produce `ImageLoadError`; no silently lossy fallback is used.
- ICC, gAMA and sRGB metadata **do not trigger colour-space conversion**. PLATE
  traces the normalized encoded samples, implicitly using those values in SVG's
  sRGB space. Tagged non-sRGB artwork may differ from a colour-managed viewer.
  These tests document this limit; they do not establish ICC/gamma-correct display
  equivalence. Colour-managed normalization and wider profile fixtures remain open.
- APNG uses the default image when present, otherwise the first image. Animation,
  frame timing, disposal and animated SVG reconstruction are not preserved.
- Fully transparent RGB samples are retained by decoding but must not affect
  traced visible geometry or colour, including after working-size reduction.
- The matrix's invalid examples are robustness checks, not a complete PNG
  conformance/fuzzing or resource-exhaustion test suite. Decode limits and bounded
  worker memory/time remain separate hosted-service requirements.

## Measured fixes — 2026-10-30

The first 80-case matrix reproduced **21 failures** before the fix. It exposed
lost grayscale 2/4-bit and grayscale/RGB 16-bit tRNS transparency, plus inconsistent
16-bit multichannel rounding. Fixing these makes all 111 cases pass alongside the
existing input regressions.

Four independently specified transparent-cutout fixtures improve to **SSIM 1.0
on both backgrounds**:

| Case | White SSIM before → after | Dark SSIM before → after |
| --- | --- | --- |
| 2-bit grayscale key | .7192 → 1.0 | .6740 → 1.0 |
| 4-bit grayscale key | .8740 → 1.0 | .5691 → 1.0 |
| 16-bit grayscale key | .9173 → 1.0 | .5467 → 1.0 |
| 16-bit RGB key | .8100 → 1.0 | .5927 → 1.0 |

Artifacts: `/tmp/plate-png-matrix-review/` (PNGs, before/after SVGs, HTML reports,
`metrics.json`). Visual comparison: `plate-png-transparency-review.png` in this
chat's visualization directory. All **24 existing PLATE and 24 VTracer benchmark
SVGs remain byte-identical**: `/tmp/plate-png-benchmark-comparison.json` and
`/tmp/plate-png-{before,after}-{samples,challenges}/`.
