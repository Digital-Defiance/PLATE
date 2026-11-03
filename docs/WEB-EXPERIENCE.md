# PLATE website: first result, useful objects, repeat use

Product review: 2026-11-03. The public site is https://plate.digitaldefiance.org/.
The owner approved publishing this checkpoint on 2026-11-03; see STATUS for deployment
verification. No analytics, outreach,
accounts, payment system or new export formats are introduced.

## Positioning

**Turn a PNG or JPG into editable SVG objects. Free, private, on your device.**

Explain the payoff before the implementation: resize without pixelation, recolor
individual shapes, and edit named layers in Illustrator/Inkscape. "Object oriented"
means PLATE looks for whole shapes and strokes and organizes the result; do not
promise that every semantic object or hidden boundary can be recovered. Lettering
becomes paths, not editable font text. Flat artwork is the first target; photo
vectorization and soft transparency are not an across-the-board quality claim.

The local-compute model is a benefit (no image upload, no conversion queue on our
servers), with an understandable tradeoff (first-use download and device-dependent
runtime). Do not promise a duration or offline support before measuring/testing it.
Optional LM Studio naming must remain explicit about the configured endpoint.

## Implemented in this iteration

- Visible welcome heading, PNG/JPG input and layered-SVG output, object/layer
  explanation, three short steps and optional inline SVG help. No blocking modal,
  mandatory tour or account gate. A direct Choose your image action is available
  in the welcome section.
- Try this example performs a real conversion of the existing badge fixture.
  The sample image is bundled by the normal build and served from the same origin.
- Presets are visible; technical sliders/toggles move under Fine-tune. They remain
  keyboard accessible, with their original labels and ranges. Choosing a preset
  now updates displayed slider positions to its effective values.
- Settings changes reuse the selected image and debounce for 350ms. Run one
  conversion at a time, keep only the latest pending settings/image, suppress
  superseded results/errors, and disable downloads immediately while updating.
  Preserve source bytes because sending request bytes to the worker detaches them.
- Runtime warm-up no longer leaves a Done / 100% result before a file is selected.
- Existing engine presets smooth/max are exposed. The small-text recipe maps to
  `smooth` plus `upscale=2`, matching the Research Force CLI configuration. The
  browser glue bounds the new upscale override to 1–2; engine defaults/algorithms
  are unchanged. 2× is explicitly slower and uses more memory.

| Visible choice | Engine recipe | Purpose |
|---|---|---|
| Balanced — start here | Defaults | First attempt without technical decisions |
| Flat logo | logo | Simple limited-palette logo |
| Clean JPEG logo | smooth | Clean curves/corners and JPEG-edge treatment |
| Logo with small text (2×, slower) | smooth + upscale=2 | Research Force-style fine lettering and strokes |
| Illustration | illustration | Richer flat artwork |
| Line art | lineart | Two-color drawing |
| Compact | compact | Fewer anchors and a smaller output |
| Maximum detail (slower) | max | Larger work size and tighter curve fitting |

These are starting points, not guaranteed quality rankings. Keep the existing
fixture and regression metrics; do not label synthetic benchmark scores as user
success rates.

## Next product improvements, in order

1. **Make objects tangible.** Add synchronized pan/zoom and a comparison slider.
   Let users click a shape to highlight its path/layer, recolor it or hide it,
   with undo. This demonstrates editability better than the phrase "object oriented."
2. **Resolve the measured browser/native JPEG discrepancy before using Research Force
   as a quality showcase.** The actual local browser run with smooth + 2× completes,
   but measures SSIM .975083, edge F1 .996153, topology 1 extra / 3 missing, versus
   native SSIM .977355, topology 0/0. Recipe resolution is tested equal; the cause
   of the runtime output difference is not established. Compare decoded pixels and
   pinned numerical libraries rather than weaken the topology checks. Evidence:
   `out/web-review/{research-force.browser.svg,research-force.native.svg,*validation.json}`.
3. **Keep returning users close to the editor.** Compact the introduction after
   image selection, with an easy How it works expansion. Persist preferences
   locally, keep an explicit reset, and never retain image data without a choice.
4. **Build a small, honest example gallery.** Research Force plus a flat logo,
   diagram and line drawing. Show source, real output, recipe and downloadable
   SVG. Include a limitation example. Obtain permission for each contributed asset.
5. **Guide recovery.** Explain which preset helps with small text, JPEG edges or
   excessive detail. Offer retry from the cached source rather than a new upload.
   Base device warnings on measurements; do not automatically launch several
   expensive full-resolution conversions just to choose a preset.
6. **Polish the output handoff.** Keep Download SVG prominent beside the preview.
   Provide a short Open in Illustrator/Inkscape guide. Do not offer a renamed PDF
   as AI; native AI and PDF export are not in this iteration.

## Acquisition: win a specific job first

Start with people converting logos, icons and diagrams: independent designers,
research/nonprofit teams, educators and open-source maintainers. Lead with a real
example and editable output, not an unqualified "better than AI" claim.

- Publish a Research Force case study showing the actual JPEG, preset and SVG,
  including the detail that still needs cleanup. Make the SVG available before
  visitors commit their own file.
- Create useful search pages for free PNG-to-SVG, JPG-logo-to-SVG, private image
  vectorization and layered SVG for Illustrator. Each should have its own real
  example and guidance; avoid a directory of near-identical keyword pages.
- Publish a factual Vectorizer.AI alternative comparison: processing location,
  account requirement, payment to download, output structure and observed quality
  on identical inputs. Date the comparison and include cases PLATE handles poorly.
- Share short, useful demos in relevant Inkscape, Illustrator, open-source and
  nonprofit-design communities, respecting each community's rules. This document
  authorizes no posting or messaging; outreach remains an owner action.
- Add optional Share PLATE links after a successful download. Never share a user's
  image or add branding/watermarks inside their SVG. A small tip/support link can
  fund hosting without blocking conversion or download.

Free alone is insufficient differentiation: Autotracer is also free/no-registration.
Vectorizer.AI allows free previews but requires a subscription for production
web downloads. PLATE's combined proposition is a usable free download, local
processing, open source and editable objects/layers. Do not imply these establish
superior tracing quality for all inputs.

## Measure success before spending on promotion

The activation event is **a completed conversion followed by an SVG download**,
not a page view. Separate example runs from personal-file runs. Measure runtime
ready → first result → download, setting-change → updated result, recoverable
error categories, and coarse cold/warm timings. Establish a baseline before setting
a conversion-rate target or buying ads.

If analytics are added, use an explicit privacy decision and coarse aggregate
product events. Do not send images, filenames, SVG contents, layer names, LM Studio
URLs or persistent identifiers by default. No such instrumentation is added here.

## Sources checked 2026-11-03

- Live PLATE page and local `web/` implementation; `src/plate/config.py` and
  `src/plate/web.py` for exact preset/config behavior.
- https://vectorizer.ai/ and https://vectorizer.ai/pricing — free previews,
  subscription downloads and competing editing features. Recheck before publishing
  a comparison or quoting a localized price.
- https://www.autotracer.org/ — free conversion without registration.
