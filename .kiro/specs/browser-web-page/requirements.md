# Requirements Document

## Introduction

This feature wraps PLATE's unchanged Python conversion engine (`pipeline.run(path, cfg, labels) -> Result`) in a free, static web page that runs the engine in the visitor's browser via Pyodide (CPython compiled to WebAssembly). A visitor drops in a PNG or JPG, chooses a preset or adjusts a few sliders, and downloads a named, layered, Illustrator-friendly SVG. The image never leaves the device, GitHub Pages serves the static shell for free, and the browser renders the SVG preview natively.

The CLI remains the source of truth. The web page is a thin shell around `pipeline.run`; it adds no new conversion logic. Delivery is spike-gated: Phase 1 is a measurement spike that must prove the engine imports and runs in Pyodide, that OpenCV loads, and that the browser produces the same SVG as the CLI within the bake-off scoring tolerance. Phases 2-4 (minimal page, automatic deploy, polish) do not begin until the spike answers whether PLATE runs acceptably in the browser.

These requirements are derived from the approved design document and are structured so each of the design's six Correctness Properties maps to at least one requirement. The property-to-requirement mapping is recorded at the end of this document for back-reference into the design.

## Glossary

- **Browser_Shell**: The static HTML/CSS/JS UI running on the main thread; owns the DOM, intake, settings, preview, layer list, and download, and never performs CPU-heavy work.
- **Conversion_Worker**: The Web Worker that hosts the Pyodide runtime, loads packages, installs the PLATE wheel, calls the glue module, and streams progress.
- **Pyodide_Runtime**: The CPython-on-WebAssembly runtime loaded inside the Conversion_Worker, together with the in-memory virtual filesystem (MEMFS).
- **Glue_Module**: The `plate.web` Python module (`convert_bytes`, `check_noise`, `build_config`) shipped inside the PLATE wheel and version-locked to the engine.
- **Engine**: The unchanged PLATE pipeline reached through `pipeline.run(path, cfg, labels) -> Result`.
- **CLI**: The existing PLATE command-line tool, treated as the source of truth for conversion output.
- **Settings_Panel**: The Browser_Shell component that maps presets and sliders onto a subset of `Config` levers.
- **Deploy_Action**: The GitHub Action that rebuilds the PLATE wheel and publishes the web shell to GitHub Pages.
- **Bakeoff_Tolerance**: The composite-score tolerance used as the documented fallback when SVG output is not byte-identical. `bakeoff/score.py` defines no such named constant; the tolerance is a 0.01 composite-score difference, set by the owner and recorded as `BAKEOFF_TOLERANCE` in `web/spike/driver.py`, measured with the `bakeoff/score.py` composite.
- **Noise_Check**: The `check_noise` glue function that estimates whether the Engine's auto-denoise would fire.
- **Config**: The frozen `Config` dataclass of engine levers, with `PRESETS` and `load()` / `merged()` resolution.
- **Work_Size_Cap**: The `Config.work_size` lever (default 1536) bounding the internal longest side.
- **Upload_Cap**: The hard byte/dimension limit applied before decode to reject oversized files.
- **LM_Studio_Naming**: The optional, off-by-default call to a local LM Studio OpenAI-compatible endpoint for layer naming.

## Requirements

### Requirement 1: In-browser conversion equals CLI output

**User Story:** As a visitor, I want the browser to convert my PNG or JPG into a layered SVG using the same engine as the CLI, so that I get the same trusted result without installing anything.

#### Acceptance Criteria

1. WHEN image bytes with a filename ending in a recognised image extension (`.png`, `.jpg`, or `.jpeg`, case-insensitive) and a resolved config are supplied to the Glue_Module, THE Glue_Module SHALL invoke the unchanged `pipeline.run` entry point and SHALL add no conversion transformation of its own beyond writing the input, building the config, and summarising the result.
2. WHEN the Glue_Module converts a PNG with a given config, THE Glue_Module SHALL produce SVG text byte-identical to the SVG that the CLI produces from `pipeline.run` for the same image bytes and same config.
3. WHEN the Glue_Module converts a JPEG with a given config, THE Glue_Module SHALL produce SVG text that differs from the CLI SVG only because the browser's JPEG decoder produces different pixels than the CLI's; specifically, the Engine run on the exact pixels the browser decoder produced SHALL reproduce the browser SVG, byte-identical or within Bakeoff_Tolerance of it as measured by `bakeoff/score.py`, and any difference that is not attributable to the decoder SHALL be treated as a failure.
4. WHEN the Glue_Module returns a result on the success path, THE Glue_Module SHALL return a single JSON-serialisable object containing exactly these top-level entries: the SVG text, conversion statistics, a top-level layer summary, and a warnings list.
5. WHERE the uploaded filename carries a recognised image extension, THE Glue_Module SHALL write the uploaded bytes to the virtual filesystem path `/input.<ext>` using that extension so the Engine decoder selects the correct format.
6. IF the supplied bytes cannot be decoded by the Engine (`ImageLoadError`) or the filename carries no recognised image extension, THEN THE Glue_Module SHALL raise a message-bearing error identifying the decode or extension failure, SHALL NOT bypass the Engine's own validation, and SHALL remove any temporary virtual filesystem input entry so no uploaded image persists after the call.

### Requirement 2: Phase 1 spike validation gate

**User Story:** As the project owner, I want a measurement spike that proves PLATE runs acceptably in Pyodide before any UI work, so that I can decide whether to proceed or choose an alternative approach.

#### Acceptance Criteria

1. WHEN the spike runs, THE Conversion_Worker SHALL import the Engine inside the Pyodide_Runtime and record, in STATUS.md, a pass or fail result for the load of each of `numpy`, `scipy`, and `opencv-python`.
2. WHEN the spike runs against all 24 scenes of the bake-off corpus, THE spike SHALL record in STATUS.md, for every scene, the per-scene conversion time in seconds and the `opencv-python` load result (pass or fail).
3. WHEN the spike converts a corpus image in the browser, THE spike SHALL compare the browser SVG against the CLI SVG byte for byte and, when the two are not byte-identical, compute the Bakeoff_Tolerance composite-score difference, and record in STATUS.md one of the outcomes byte-identical, within Bakeoff_Tolerance, or outside Bakeoff_Tolerance for that image; for a PNG the outcome must be byte-identical or within Bakeoff_Tolerance, while for a JPEG an outside-tolerance outcome is acceptable only when the spike also records that the Engine run on the exact pixels the browser decoder produced reproduces the browser SVG (byte-identical or within Bakeoff_Tolerance), establishing the difference as decoder-only.
4. IF the `opencv-python` load result recorded in STATUS.md is fail, THEN THE spike SHALL halt before any Phase 2 work and record in STATUS.md a decision-point entry marking the spike as not met and naming an alternative approach.
5. IF the per-scene conversion time recorded for any of the 24 scenes exceeds 60 seconds, THEN THE spike SHALL halt before any Phase 2 work and record in STATUS.md a decision-point entry marking the spike as not met.
6. THE spike done-definition SHALL be met only when STATUS.md records all three of: every required package load result as pass, every per-scene conversion time at or below 60 seconds, and every converted corpus image as either byte-identical, within Bakeoff_Tolerance, or (for a JPEG) differing from the CLI only because of the browser's JPEG decoder, where that decoder-only attribution is proven by the Engine run on the exact browser-decoded pixels reproducing the browser SVG (byte-identical or within Bakeoff_Tolerance).
7. WHILE STATUS.md does not record the spike done-definition as met, THE project SHALL NOT begin any of Phases 2, 3, or 4.

### Requirement 3: Image intake with type and size validation

**User Story:** As a visitor, I want to drag in or pick an image file and be told immediately if it is the wrong type or too large, so that I do not wait on a conversion that cannot work.

#### Acceptance Criteria

1. WHEN a visitor drops a file on the drop zone or selects one with the file picker, THE Browser_Shell SHALL read the file bytes for conversion within 2 seconds for a file up to the Upload_Cap byte limit.
2. IF the selected file is not a PNG or JPG, THEN THE Browser_Shell SHALL reject the file before reading its bytes, display a message naming PNG and JPG as the only accepted types, and keep the drop zone ready for another file.
3. IF the selected file exceeds the Upload_Cap byte limit of 20 megabytes, THEN THE Browser_Shell SHALL reject the file before decode, display an error indication that the file is too large, and prompt the visitor to downsize and retry.
4. IF the selected file exceeds 8192 pixels on either axis, THEN THE Browser_Shell SHALL reject the file before decode and display an error indication that the image dimensions are too large.
5. IF the selected file is empty, zero-byte, or cannot be decoded as an image, THEN THE Browser_Shell SHALL reject the file, display an error indication that the image could not be read, and keep the drop zone ready for another file.
6. WHEN the Browser_Shell accepts a file, THE Browser_Shell SHALL transfer the image bytes to the Conversion_Worker together with the filename and the serialised config.

### Requirement 4: JPEG and noise pre-check with beta warning

**User Story:** As a visitor converting a compressed or noisy JPEG, I want a warning before conversion that matches what the engine will actually do, so that I understand the beta limitations on such images.

#### Acceptance Criteria

1. WHEN an accepted image is received, THE Noise_Check SHALL estimate `noise_fraction` and `interior_noise_fraction` by decoding the image and resizing it to the configured `work_size` before estimation.
2. THE Noise_Check SHALL report an image as noisy when `noise_fraction` exceeds 0.04 or `interior_noise_fraction` exceeds `Config.interior_noise`, matching the Engine's auto-denoise trigger in `imageio.load_image`.
3. IF the image cannot be decoded or resized, THEN THE Noise_Check SHALL abort the estimation, retain the original uploaded image unchanged, and return an error indication that the image could not be analyzed.
4. IF the Noise_Check reports an image as both JPEG and noisy, THEN THE Browser_Shell SHALL display a beta warning before or at conversion stating that hidden-object recovery is limited on compressed JPEGs.
5. WHEN the Noise_Check runs, THE Noise_Check SHALL complete within 5 seconds for an accepted image, without persisting any file to disk, and without performing any network I/O.

### Requirement 5: Non-blocking conversion with staged progress

**User Story:** As a visitor, I want the page to stay responsive and show progress while my image converts, so that the WebAssembly conversion time does not feel like a freeze.

#### Acceptance Criteria

1. WHILE a conversion is running, THE Conversion_Worker SHALL perform all image-conversion computation off the main thread, and THE Browser_Shell SHALL perform only message passing such that the main thread remains able to process user input events within 100 milliseconds.
2. WHEN a conversion progresses, THE Conversion_Worker SHALL post a staged progress event for each of the stages load-pyodide, load-packages, install-plate, import, segment, order, trace, and emit, in that order, with each event identifying the stage name and the associated request identifier.
3. WHEN the Conversion_Worker completes a conversion request successfully, THE Conversion_Worker SHALL post exactly one result message carrying that request identifier.
4. IF the Conversion_Worker fails to complete a conversion request, THEN THE Conversion_Worker SHALL post exactly one error message carrying that request identifier and an error indication describing the failure cause, and SHALL post no result message for that request identifier.
5. WHEN a conversion finishes, THE Conversion_Worker SHALL retain the initialized Pyodide_Runtime in memory so that a subsequent conversion request does not repeat the load-pyodide, load-packages, or install-plate stages.

### Requirement 6: Settings panel mapping presets and sliders to Config levers

**User Story:** As a visitor, I want presets and a few sliders that control the conversion, so that I can tune the output without learning the full engine.

#### Acceptance Criteria

1. THE Settings_Panel SHALL offer the presets `logo`, `illustration`, `lineart`, and `compact` as the primary control.
2. THE Settings_Panel SHALL expose controls that map one-to-one onto the `Config` levers `max_colors`, `simplify`, `smooth`, and `work_size` as numeric inputs and `snap_primitives`, `strokes`, `gradients`, and `remove_background` as boolean toggles.
3. WHEN the Settings_Panel produces a config object, THE Glue_Module SHALL build a `Config` equal to `load(preset).merged(**clamped_levers)`, applying the resolution order built-in defaults then preset then explicit overrides.
4. WHEN the Glue_Module builds a config, THE Glue_Module SHALL clamp each numeric lever to its engine-sane range before calling `Config.merged`.
5. IF a numeric lever value falls outside its engine-sane range, THEN THE Glue_Module SHALL clamp it to the nearest range bound rather than rejecting the config.
6. IF the config object contains an unknown preset or an unknown lever key, THEN THE Glue_Module SHALL reject it with a descriptive, message-bearing error rather than ignoring it.

### Requirement 7: Preview, layer list, and SVG download

**User Story:** As a visitor, I want to see my source image next to the converted SVG with its layers and download the result, so that I can confirm and keep the output.

#### Acceptance Criteria

1. WHEN a conversion result is received, THE Browser_Shell SHALL display the source image and the SVG preview side by side within 1 second, each rendered at its native aspect ratio without distortion.
2. WHEN a conversion result is received, THE Browser_Shell SHALL render the top-level layer list from the result's layer summary ordered from bottom to top paint order, displaying the layer name for each entry.
3. IF the result's layer summary contains zero layers, THEN THE Browser_Shell SHALL display an empty-state message indicating that no layers are present and SHALL render no layer list entries.
4. WHEN a conversion result is available, THE Browser_Shell SHALL enable a download control that saves the SVG text to a file named from the source base name with a `.svg` extension.
5. IF the source base name is empty or unavailable when the download control is activated, THEN THE Browser_Shell SHALL save the SVG text to a file with a default base name and the `.svg` extension.
6. WHEN the result includes one or more warnings, THE Browser_Shell SHALL display each warning text as a separate visible entry to the visitor.

### Requirement 8: Privacy by construction

**User Story:** As a privacy-conscious visitor, I want my image to stay on my device, so that I can convert sensitive artwork without it being uploaded anywhere.

#### Acceptance Criteria

1. WHILE the Glue_Module executes the core conversion path for an image, THE Glue_Module SHALL perform zero network I/O operations (no outbound or inbound socket, fetch, or HTTP connections).
2. WHEN a conversion completes successfully, THE Glue_Module SHALL remove the temporary virtual filesystem input entry for that image within 1 second of returning the result, such that no image bytes remain readable from the virtual filesystem after the call returns.
3. IF a conversion fails or raises an error, THEN THE Glue_Module SHALL remove the temporary virtual filesystem input entry for that image before returning control to the caller, and SHALL surface an error indication identifying the failure while retaining no image bytes in the virtual filesystem.
4. WHEN the Browser_Shell executes the core conversion path, THE Browser_Shell SHALL make no outbound request that transmits any portion of the image bytes.
5. WHERE the LM_Studio_Naming feature is explicitly enabled by the user, THE Browser_Shell SHALL permit exactly one category of outbound request transmitting image bytes, limited to the LM_Studio_Naming call, and SHALL transmit no image bytes on any other outbound request.

### Requirement 9: Memory and size bounds

**User Story:** As a visitor on a memory-limited browser, I want oversized images rejected early and internal resolution capped, so that the page does not crash on large uploads.

#### Acceptance Criteria

1. WHEN an accepted image is converted, THE Engine SHALL apply the Work_Size_Cap (`Config.work_size`, default 1536 pixels) to the internal longest side, producing working-image dimensions identical to those the CLI produces for identical input and config.
2. IF an uploaded image exceeds the Upload_Cap byte or pixel-dimension limit, THEN THE Browser_Shell SHALL reject it before decode, retain any prior result unchanged, and display an error indication that the file is too large.
3. WHEN an accepted image is converted, THE internal working image longest side SHALL be less than or equal to the configured `work_size` in pixels.
4. WHERE an accepted image's longest side is less than or equal to the configured `work_size`, THE Engine SHALL NOT upscale the image and SHALL process it at its original dimensions.
5. IF an accepted image cannot be decoded after passing intake validation, THEN THE Conversion_Worker SHALL abort the conversion, retain any prior result unchanged, and return an error indication that the image could not be decoded.

### Requirement 10: Optional LM Studio naming

**User Story:** As a power user, I want to optionally enable LM Studio naming, so that I can get refined layer names while keeping it off by default.

#### Acceptance Criteria

1. THE Settings_Panel SHALL keep LM_Studio_Naming disabled by default and expose it only through an advanced toggle that displays a note stating that LM Studio requires CORS to be enabled for the browser origin.
2. WHERE the advanced `vlmUrl` field is empty or contains only whitespace, THE Glue_Module SHALL leave LM_Studio_Naming disabled.
3. WHERE the advanced `vlmUrl` field contains a non-empty, non-whitespace string, THE Glue_Module SHALL enable LM_Studio_Naming against the endpoint identified by that string.
4. IF the LM Studio server rejects the browser origin because CORS is not enabled, THEN THE Browser_Shell SHALL fall back to the Engine's classical color-and-shape names, retain all previously generated layer output unchanged, and display a note explaining how to enable CORS in LM Studio.
5. IF a request to the configured LM Studio endpoint does not return a naming response within 30 seconds, THEN THE Browser_Shell SHALL cancel the request, fall back to the Engine's classical color-and-shape names, and display a note indicating that LM Studio naming was unavailable.

### Requirement 11: Automatic GitHub Pages deployment

**User Story:** As the project owner, I want the web page rebuilt and redeployed automatically on every engine change, so that the browser version cannot lag the CLI.

#### Acceptance Criteria

1. WHEN code changes are pushed to the repository's default branch, THE Deploy_Action SHALL build the PLATE wheel, copy the built wheel into the deploy artifact alongside the static web shell, and publish the deploy artifact to GitHub Pages.
2. IF the wheel build fails or the publish step fails, THEN THE Deploy_Action SHALL abort without updating the live GitHub Pages site, preserve the previously deployed version, and surface a failure status on the triggering workflow run.
3. THE Deploy_Action SHALL pin the Pyodide version and every scientific-package version to exact versions so that a CDN change cannot alter the page content without a corresponding repository change.
4. WHEN the Deploy_Action runs, THE Deploy_Action SHALL complete the build-and-publish workflow within 15 minutes, and SHALL report a timeout failure if the limit is exceeded.
5. THE web shell SHALL be deployed from the `/web` folder inside the PLATE repository unless the owner configures a separate repository as the deployment source.

### Requirement 12: Error handling for runtime, input, and platform failures

**User Story:** As a visitor, I want clear, recoverable messages when something goes wrong, so that I know whether to retry, change file, or use a different browser.

#### Acceptance Criteria

1. IF a required package cannot be resolved or installed in the Pyodide_Runtime within 60 seconds, THEN THE Conversion_Worker SHALL post a non-recoverable error identifying the failed package, and THE Browser_Shell SHALL display a "not supported in this browser yet" notice that remains visible until the visitor dismisses it or reloads the page.
2. WHILE the Pyodide_Runtime and scientific wheels load on first visit, THE Browser_Shell SHALL display a progress bar that advances through at least 3 named stages and reports a percentage from 0 to 100.
3. WHEN the Pyodide_Runtime and scientific wheels have been loaded once, THE Browser_Shell SHALL serve them from browser cache on subsequent visits without re-displaying the staged progress bar.
4. IF the Engine raises `ImageLoadError` on an unreadable or unsupported file, THEN THE Conversion_Worker SHALL post a recoverable error carrying the Engine's own message verbatim without bypassing Engine validation, and THE Browser_Shell SHALL allow the visitor to select a different file without reloading the page.
5. WHERE the browser is Safari and Safari support has not been verified, THE Browser_Shell SHALL feature-detect on load and display a compatibility notice that degrades to a "best in Chrome, Edge, Firefox" message.
6. WHILE a conversion is running in WebAssembly, THE Browser_Shell SHALL keep the progress bar visible and the Web Worker active so that the main page thread remains responsive to visitor interaction.
7. IF a conversion runs for more than 120 seconds without completing, THEN THE Browser_Shell SHALL display a recoverable notice offering the visitor the option to continue waiting or cancel the conversion.

### Requirement 13: Owner launch and placement decisions

**User Story:** As the project owner, I want the open launch and placement decisions captured as explicit requirements, so that the beta scope and deployment home are agreed before build.

#### Acceptance Criteria

1. WHILE the owner has not decided to wait for the v0.2 JPEG-robustness work, THE web page SHALL be labelled "beta" in a visible page element and SHALL be launched before the v0.2 JPEG-robustness work begins.
2. IF the owner decides to wait for the v0.2 JPEG-robustness work, THEN THE web page launch SHALL be deferred until after the v0.2 JPEG-robustness work is recorded as complete.
3. WHERE the owner approves the spike, THE project SHALL record the web page in both the README and the ROADMAP as a goal positioned after the v0.2 milestone and before the v0.3 milestone.
4. WHERE the owner decides to show power-user links, THE Browser_Shell SHALL display a link to the CLI for batch work and a link to LM Studio naming.
5. WHERE the owner has not decided to show power-user links, THE Browser_Shell SHALL omit the CLI batch-work link and the LM Studio naming link.

## Correctness Property Mapping

The design document's six Correctness Properties map to these requirements. The design should be updated with "Validates: Requirements X.Y" back-references accordingly:

- **Property 1 (Thin shell / source of truth)** — Validates: Requirements 1.1, 1.2, 1.3
- **Property 2 (Privacy by construction)** — Validates: Requirements 8.1, 8.2, 8.3
- **Property 3 (Config fidelity)** — Validates: Requirements 6.3, 6.6
- **Property 4 (Warning matches behaviour)** — Validates: Requirements 4.2
- **Property 5 (Non-blocking main thread)** — Validates: Requirements 5.1
- **Property 6 (Memory bounded)** — Validates: Requirements 9.1, 9.2, 9.3
