# Real-artwork corpus — provenance and CC0 / public-domain drop-ins

This corpus is **primarily generated-realistic**. Every image prefixed `real_`
is authored in this repository (MIT) by
[`scripts/make_real_corpus.py`](../../scripts/make_real_corpus.py): an authored
SVG is rendered at 4x and Lanczos-downsampled, then a deterministic per-image
post-raster effect (gaussian noise, JPEG-like block quantization, blur, or
paper-grain texture) is applied with a fixed RNG seed. The images are therefore
fully reproducible and redistributable. No artwork was scraped or downloaded and
**no provenance is fabricated**.

The corpus is a diagnostic for `plate bench samples/real`; it is not a quality
gate and carries no structural oracle. See
[`docs/REAL-CORPUS.md`](../../docs/REAL-CORPUS.md) for the per-image bench
numbers and run instructions.

## Generated images (MIT, this repo)

| filename | description | stress axes |
|---|---|---|
| `real_sunset_gradient.png` | Wide sunset sky over sea with a glowing sun. | multi-stop linear gradient, soft radial glow, wide 5:3 aspect |
| `real_radial_orb.png` | Shaded sphere with a soft highlight on off-white. | soft radial shading, feathered highlight, off-white background |
| `real_soft_shadow_card.png` | White UI card floating above a blurred drop shadow. | soft drop shadow, feathered edges, blur |
| `real_sensor_noise_badge.png` | Gold star badge under heavy gaussian grain. | mild sensor-style noise over flat + gradient fills |
| `real_jpeg_artifacts.png` | Hard-edged colour blocks with JPEG-like block artifacts. | JPEG-like 8x8 blockiness / ringing around hard edges |
| `real_thin_strokes_type.png` | Hairline rules, ticks, and small anti-aliased type. | anti-aliased small text, thin (<2px) strokes, 2:1 aspect |
| `real_busy_palette.png` | 30-tile colour grid from a 20-colour palette. | busy palette (>16 colours), near-duplicate colours |
| `real_near_duplicate_swatches.png` | Grid of swatches that differ by a few code points. | many near-duplicate (small delta-E) colours |
| `real_panorama_banner.png` | Repeated sun/hill motifs across an extreme-wide banner. | extreme 4:1 aspect, gradient sky, repeated motifs |
| `real_tall_poster.png` | Tall poster with a gradient wash, disc, and type. | extreme tall aspect, gradient wash, type |
| `real_translucent_overlaps.png` | Overlapping translucent CMY blobs and a panel. | overlapping semi-transparent shapes, alpha blending |
| `real_textured_bg.png` | Logo panel over an off-white paper-grain background. | off-white textured background, soft grain |
| `real_glow_logo.png` | Glowing star mark with gradient core and fine type on dark. | soft glow / blur, gradient core, fine anti-aliased type |
| `real_mixed_mess.png` | Gradient wash + chip strip + shadowed card + noise + type. | combined: gradient, soft shadow, noise, >16 colours, thin type |

## Dropped-in CC0 / public-domain images

**None yet.** Zero genuine CC0 / public-domain images are currently included —
fetching real artwork is unreliable in this environment, so the slot is left
ready rather than populated with fabricated provenance.

To add a genuine redistributable image in a future session:

1. Confirm the license is **CC0 or public domain** (nothing else is acceptable).
2. Save the PNG directly in `samples/real/` (the bench reads this folder
   non-recursively, so it must not live in a subfolder). Use a distinct prefix
   such as `cc0_` so drop-ins are easy to tell apart from the generated `real_`
   images.
3. Add a row to the manifest table below with every column filled in. Do **not**
   fabricate any field — if you cannot verify the source URL, license, and
   author, do not add the image.
4. Re-run the bench and rebuild the diagnostic table:

   ```
   PYTHONPATH=src DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
     .venv/bin/python -m plate bench samples/real -o out/real_bench
   PYTHONPATH=src DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib \
     .venv/bin/python scripts/real_corpus_report.py
   ```

   (The report builder currently tabulates the generated `real_*.png` set;
   extend its glob to include the new prefix if you want drop-ins in the table.)

### Manifest

| filename | source URL | license (CC0 or public domain) | author / attribution | notes |
|---|---|---|---|---|
| _(none yet)_ | | | | |
