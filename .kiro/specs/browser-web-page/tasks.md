# Implementation Plan: Browser Web Page (PLATE in the Browser)

## Overview

This plan implements PLATE's browser shell around the **unchanged** conversion engine. The engine
is never edited; all new engine-side code is a small `plate.web` glue module that ships in the same
wheel and stays version-locked to `pipeline.run`. The browser writes uploaded bytes to Pyodide's
in-memory filesystem at `/input.<ext>` and calls `pipeline.run` so the engine runs exactly as on
the CLI.

**Languages (from the design, no pseudocode-only sections):** the glue module is Python
(`src/plate/web.py`, unit-testable under the existing `pytest -q` suite); the Web Worker and UI
shell are TypeScript/JavaScript; the deploy pipeline is a GitHub Actions YAML workflow.

**This plan is SPIKE-GATED.** Phase 1 is a measurement spike that must prove the engine imports and
runs in Pyodide, that OpenCV loads, that per-scene corpus timings are acceptable, and that the
browser SVG equals the CLI SVG (byte-identical or within bake-off tolerance), recording every
outcome in `STATUS.md`. Task **5** is the explicit, checkable spike done-definition gate
(Requirements 2.6, 2.7). **No Phase 2, 3, or 4 task may start until task 5 is checked.**

Testing notes:
- Pure-Python glue tests run under the existing `pytest -q` suite and must keep it green.
- The headless-browser smoke test (task 18) is a browser-only integration test, marked distinctly
  from the pytest tasks; it is the automated form of the spike done-definition for Phase 2+.
- Property-based tests use `hypothesis` (matches the existing Python stack).

## Tasks

- [x] 1. Phase 1 — Build the `plate.web` glue module as pure CPython (spike foundation)
  - [x] 1.1 Create `src/plate/web.py` with `build_config(overrides)`
    - Implement defaults → preset → explicit-override resolution returning `config.load(preset).merged(**clamped_levers)`
    - Map UI lever names (`maxColors`/`max_colors`, `simplify`, `smooth`, `workSize`/`work_size`, `snapPrimitives`, `strokes`, `gradients`, `removeBackground`, `vlmUrl`, `vlmModel`) onto `Config` fields
    - Clamp each numeric lever to its engine-sane range before calling `Config.merged`; clamp out-of-range values to the nearest bound rather than rejecting
    - Reject unknown preset or unknown lever key with a descriptive, message-bearing error
    - Leave LM Studio naming disabled unless `vlmUrl` is a non-empty, non-whitespace string
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 10.2, 10.3_

  - [x] 1.2 Write property test for config fidelity
    - **Property 3: Config fidelity**
    - **Validates: Requirements 6.3, 6.6**
    - For arbitrary valid override maps, assert `build_config(overrides) == load(preset).merged(**levers)`; for arbitrary invalid keys, assert it raises

  - [x] 1.3 Implement `check_noise(data, filename)` in `src/plate/web.py`
    - Decode and resize to the configured `work_size` before estimation, reusing the engine's `noise_fraction` / `interior_noise_fraction` estimators
    - Return `{"noisy", "jpeg", "noise_fraction", "interior_noise"}`; set `noisy` true iff `noise_fraction > 0.04` or `interior_noise_fraction > Config.interior_noise`, matching `imageio.load_image`'s auto-denoise trigger
    - On decode/resize failure, abort estimation, leave the uploaded image unchanged, and return a message-bearing error indication; no persisted file, no network I/O
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 1.4 Write property test for warning-matches-behaviour
    - **Property 4: Warning matches behaviour**
    - **Validates: Requirements 4.2**
    - Assert `check_noise(image).noisy ⟺ (noise_fraction > 0.04 ∨ interior_noise_fraction > interior_noise)` on clean art and the suite's noisy samples

  - [x] 1.5 Implement `convert_bytes(data, filename, overrides)` in `src/plate/web.py`
    - Reject empty bytes; resolve the recognised extension (`.png`/`.jpg`/`.jpeg`, case-insensitive) and write bytes to the MEMFS path `/input.<ext>`
    - Call the unchanged `pipeline.run(path, cfg)` with the config from `build_config`; add no conversion transformation beyond writing input, building config, and summarising the result
    - Build and return a single JSON-serialisable dict with exactly `{"svg", "stats", "layers", "warnings"}`; summarise top-level layers bottom→top paint order; append the beta JPEG warning when `check_noise` reports both jpeg and noisy
    - Remove the temporary MEMFS input entry in a `finally` on both success and failure; on decode failure (`ImageLoadError`) or missing recognised extension, raise a message-bearing error without bypassing engine validation
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 4.4, 8.1, 8.2, 8.3_

  - [x] 1.6 Write CLI-equivalence unit tests for `convert_bytes`
    - For each `samples/*.png`, read the file bytes and assert `convert_bytes(bytes, name).svg == pipeline.run(path).svg` (byte-identical contract)
    - Assert the returned dict has exactly the four top-level keys and a non-empty stats/layers summary
    - _Requirements: 1.2, 1.4_

  - [x] 1.7 Write property test for in-browser/CLI SVG equivalence
    - **Property 1: Thin shell / source of truth**
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - For images from the sample/corpus set and configs from valid preset+lever combinations, assert `convert_bytes(...).svg == pipeline.run(...).svg`

  - [x] 1.8 Write property test for no-persist privacy
    - **Property 2: Privacy by construction**
    - **Validates: Requirements 8.1, 8.2, 8.3**
    - After any `convert_bytes` call (success or `ImageLoadError`), assert no MEMFS/temp input file remains, using a fake/temp filesystem in the CPython test

- [x] 2. Phase 1 — Checkpoint: glue green under pytest
  - Ensure all tests pass (`pytest -q` stays green), ask the user if questions arise.

- [x] 3. Phase 1 — Pyodide bring-up in a Web Worker with OpenCV load check
  - [x] 3.1 Create the Web Worker runtime bootstrap (`web/src/worker.ts`)
    - Implement `ensureRuntime()`: load a pinned Pyodide from CDN, `loadPackages(["numpy","scipy","opencv-python"])`, `micropip.install` the PLATE wheel, then `import plate.web as plate_web`
    - Record a pass/fail load result for each of `numpy`, `scipy`, and `opencv-python`, and keep the initialized runtime warm for reuse
    - _Requirements: 2.1, 5.5_

  - [x] 3.2 Build the spike measurement harness (`web/spike/measure.ts` + Python driver)
    - For all 24 bake-off corpus scenes, convert in the worker and record per-scene conversion time (seconds) and the `opencv-python` load result
    - Compare each browser SVG against the CLI SVG byte-for-byte; when not byte-identical, compute the `bakeoff/score.py` composite difference and classify as byte-identical, within Bakeoff_Tolerance, or outside Bakeoff_Tolerance
    - Write all outcomes (per-package load results, per-scene timings, per-image SVG classification) into `STATUS.md`
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Implement spike decision-point halts
    - If the `opencv-python` load result is fail, halt before any Phase 2 work and record a decision-point entry in `STATUS.md` marking the spike not met and naming an alternative approach
    - If any of the 24 per-scene times exceeds 60 seconds, halt before any Phase 2 work and record a decision-point entry in `STATUS.md` marking the spike not met
    - _Requirements: 2.4, 2.5_

- [x] 4. Phase 1 — Checkpoint: spike measurements recorded
  - Ensure the spike harness ran and `STATUS.md` holds every per-package load result, every per-scene timing, and every per-image SVG classification. Ask the user if questions arise.

- [x] 5. Phase 1 GATE — Verify and record the spike done-definition (blocks all of Phase 2, 3, 4)
  - Assert and record in `STATUS.md` that ALL THREE hold: every required package load result is pass; every per-scene conversion time is at or below 60 seconds; every converted corpus image is byte-identical, within Bakeoff_Tolerance, or (for a JPEG) differs from the CLI only because of the browser's JPEG decoder, proven by the engine run on the exact browser-decoded pixels reproducing the browser SVG (byte-identical or within Bakeoff_Tolerance)
  - Only when all three are recorded as met may any Phase 2/3/4 task begin; while `STATUS.md` does not record the done-definition as met, do not start Phases 2, 3, or 4
  - _Requirements: 2.6, 2.7_

- [x] 6. Phase 2 — UI shell scaffold and worker client (GATED on task 5)
  - [x] 6.1 Create the static shell and `PlateClient` worker wrapper (`web/index.html`, `web/src/client.ts`)
    - Build the DOM skeleton (drop zone, status area, preview panes, layer list, download control) with no CPU-heavy work on the main thread
    - Implement `PlateClient.init()`, `convert()`, and `onProgress()` wrapping the Web Worker; define the typed worker message protocol (`WorkerIn`/`WorkerOut`/`Stage`)
    - _Requirements: 5.1_

  - [x] 6.2 Write unit tests for the worker message protocol
    - Test request-id correlation, progress callback dispatch, and message serialization with a mocked worker
    - _Requirements: 5.2, 5.3, 5.4_

- [x] 7. Phase 2 — Image intake with type and size validation (GATED on task 5)
  - [x] 7.1 Implement drag-drop and file-picker intake with pre-decode validation (`web/src/intake.ts`)
    - Read accepted file bytes for conversion within 2 seconds up to the Upload_Cap
    - Reject non-PNG/JPG before reading bytes with a message naming PNG and JPG as the only accepted types, keeping the drop zone ready
    - Reject files above the 20 MB Upload_Cap and above 8192 px on either axis before decode, with a too-large indication and a downsize prompt
    - Reject empty/zero-byte/undecodable files with a could-not-read indication, keeping the drop zone ready
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 9.2_

  - [x] 7.2 Write unit tests for intake validation
    - Cover wrong type, oversized bytes, oversized dimensions, zero-byte, and valid-file acceptance paths
    - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [x] 8. Phase 2 — Worker conversion protocol with staged progress (GATED on task 5)
  - [x] 8.1 Implement staged `convert` handling in the worker (`web/src/worker.ts`)
    - On an accepted file, transfer image bytes with filename and serialised config to the worker and call `plate_web.convert_bytes`
    - Post staged progress events for load-pyodide, load-packages, install-plate, import, segment, order, trace, emit in order, each carrying the stage name and request id
    - Post exactly one `result` message carrying the request id on success; on failure post exactly one `error` message with the request id and a cause indication and no result; keep the runtime warm so a subsequent request skips load/install
    - On a decode failure after intake, abort and return a could-not-decode error while retaining any prior result unchanged
    - _Requirements: 3.6, 5.2, 5.3, 5.4, 5.5, 9.5_

  - [x] 8.2 Write unit tests for staged progress and result/error exclusivity
    - Assert stage order, single result-or-error per request id, and warm-runtime reuse with a mocked Pyodide handle
    - _Requirements: 5.2, 5.3, 5.4, 5.5_

- [x] 9. Phase 2 — Preview, layer list, warnings, and download (GATED on task 5)
  - [x] 9.1 Render source/SVG preview, layer list, and warnings (`web/src/preview.ts`)
    - Show source image and SVG preview side by side within 1 second, each at native aspect ratio without distortion
    - Render the top-level layer list from the result's layer summary ordered bottom→top, showing each layer name; show an empty-state message and no entries when the summary has zero layers
    - Display each result warning as a separate visible entry
    - _Requirements: 7.1, 7.2, 7.3, 7.6_

  - [x] 9.2 Implement the SVG download control (`web/src/download.ts`)
    - Enable a download that saves the SVG text to `<source-base-name>.svg`; when the base name is empty/unavailable, use a default base name with the `.svg` extension
    - _Requirements: 7.4, 7.5_

  - [x] 9.3 Write unit tests for layer list, empty-state, and download naming
    - Cover ordering, zero-layer empty state, and base-name/default-name download filenames
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [x] 10. Phase 2 — JPEG/noise beta warning and privacy wiring (GATED on task 5)
  - [x] 10.1 Wire the pre-conversion noise/JPEG warning into the shell (`web/src/warnings.ts`)
    - Call `check_noise` on an accepted image and, when it reports both JPEG and noisy, display the beta warning (hidden-object recovery limited on compressed JPEGs) before or at conversion
    - Ensure the core conversion path makes no outbound request transmitting any portion of the image bytes
    - _Requirements: 4.4, 8.4_

- [x] 11. Phase 2 — Error handling for runtime, input, and platform failures (GATED on task 5)
  - [x] 11.1 Implement runtime/input/platform error surfaces (`web/src/errors.ts`)
    - On a package resolve/install failure within 60 s, surface a non-recoverable "not supported in this browser yet" notice that stays until dismissed or reload
    - Show a first-load progress bar advancing through at least 3 named stages reporting 0–100%; serve cached runtime on later visits without re-showing the staged bar
    - On `ImageLoadError`, surface the engine's verbatim message as a recoverable error and allow picking a different file without reload
    - Feature-detect on load; on unverified Safari show a "best in Chrome, Edge, Firefox" compatibility notice; keep the progress bar and worker active during conversion so the main thread stays responsive
    - On a conversion exceeding 120 s, show a recoverable notice offering continue-waiting or cancel
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 11.2 Write unit tests for error-surface behaviour
    - Cover package-load failure notice, decode-error recovery, Safari compatibility notice, and the 120 s long-run notice
    - _Requirements: 12.1, 12.4, 12.5, 12.7_

- [x] 12. Phase 2 — Property test for non-blocking main thread (GATED on task 5)
  - **Property 5: Non-blocking main thread**
  - **Validates: Requirements 5.1**
  - Assert conversion runs in the Web Worker and the main thread performs message passing only, remaining responsive to input within 100 ms

- [x] 13. Phase 2 — Property test for memory bounded (GATED on task 5)
  - **Property 6: Memory bounded**
  - **Validates: Requirements 9.1, 9.2, 9.3**
  - Assert the internal working-image longest side ≤ `work_size`, no upscale when the source longest side ≤ `work_size`, and that over-cap files are rejected before decode (glue/CPython side for the size bounds; shell side for the pre-decode rejection)
  - _Requirements: 9.1, 9.3, 9.4_

- [x] 14. Phase 2 — Checkpoint: minimal page end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Phase 3 — Automatic GitHub Pages deployment (GATED on task 5)
  - [x] 15.1 Author the deploy workflow (`.github/workflows/deploy-web.yml`)
    - On push to the default branch, build the PLATE wheel (`python -m build`), copy the wheel into the deploy artifact alongside the static `/web` shell, and publish to GitHub Pages from `/web`
    - Pin the Pyodide version and every scientific-package version to exact versions so a CDN change cannot alter page content without a repo change
    - Abort without updating the live site and preserve the previous deploy and surface a failure status if the wheel build or publish fails; report a timeout failure if the build-and-publish exceeds 15 minutes
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 15.2 Write a workflow validation/lint check for the deploy action
    - Assert the workflow references pinned versions and the `/web` source, and that build-failure aborts publish (lint/dry-run assertions)
    - _Requirements: 11.2, 11.3_

- [x] 16. Phase 4 — Settings panel: presets and sliders (GATED on task 5)
  - [x] 16.1 Build the settings panel mapping presets and levers (`web/src/settings.ts`)
    - Offer presets `logo`, `illustration`, `lineart`, `compact` as the primary control
    - Expose numeric inputs for `max_colors`, `simplify`, `smooth`, `work_size` and boolean toggles for `snap_primitives`, `strokes`, `gradients`, `remove_background`, each mapping 1:1 to a `Config` lever
    - Serialise the panel to the plain config object passed to the worker; defaults → preset → overrides resolution is handled by `build_config`
    - _Requirements: 6.1, 6.2_

  - [x] 16.2 Write unit tests for the settings-to-config serialisation
    - Cover preset selection, each slider/toggle mapping, and that the serialised object round-trips through `build_config`
    - _Requirements: 6.1, 6.2_

- [x] 17. Phase 4 — Optional LM Studio naming, off by default (GATED on task 5)
  - [x] 17.1 Add the advanced LM Studio naming toggle and fallback (`web/src/settings.ts`, `web/src/naming.ts`)
    - Keep LM Studio naming disabled by default behind an advanced toggle displaying a note that LM Studio requires CORS enabled for the browser origin
    - Treat an empty/whitespace `vlmUrl` as disabled; a non-empty `vlmUrl` enables naming against that endpoint (glue honours this via `build_config`)
    - On CORS rejection, fall back to the engine's classical color-and-shape names, retain prior layer output unchanged, and show a note on enabling CORS; on no response within 30 s, cancel, fall back to classical names, and show an unavailable note
    - Restrict image-byte transmission to the single LM Studio request category when enabled; no other outbound request transmits image bytes
    - _Requirements: 10.1, 10.4, 10.5, 8.5_

  - [x] 17.2 Write unit tests for LM Studio enable/disable and fallback
    - Cover default-off, empty-vs-nonempty `vlmUrl`, CORS-rejection fallback, and 30 s timeout fallback with a mocked endpoint
    - _Requirements: 10.1, 10.4, 10.5_

- [x] 18. Phase 4 — Headless-browser smoke test (BROWSER-ONLY integration test, GATED on task 5)
  - Load the deployed page in a headless browser, drop a fixed sample, trigger conversion, and assert the downloaded SVG matches the CLI output under the equivalence rule: byte-identical for a PNG sample; for a JPEG sample, differing from the CLI only because of the browser's JPEG decoder (the engine run on the browser-decoded pixels reproduces the browser SVG, byte-identical or within Bakeoff_Tolerance)
  - This is a browser-only integration test (NOT part of the pure-Python `pytest` suite); it is the automated form of the spike done-definition guarding against the shell drifting from the CLI
  - _Requirements: 1.2, 1.3_

- [x] 19. Phase 4 — Owner launch and placement items (GATED on task 5)
  - [x] 19.1 Add the beta label and power-user links to the shell (`web/index.html`, `web/src/links.ts`)
    - Render a visible "beta" page element; when power-user links are enabled, show a link to the CLI for batch work and a link to LM Studio naming; when not enabled, omit both links
    - _Requirements: 13.1, 13.4, 13.5_

  - [x] 19.2 Record the web page in README and ROADMAP
    - Add the web page to both `README.md` and `ROADMAP.md` as a goal positioned after the v0.2 milestone and before the v0.3 milestone
    - _Requirements: 13.3_

- [x] 20. Phase 4 — Final checkpoint: full suite green
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (unit, property, and integration tests) and can be skipped for a faster MVP; core implementation tasks are never optional.
- Every Phase 2, 3, and 4 task is gated on task 5 (the spike done-definition). Do not start any of them until `STATUS.md` records the spike as met (Requirements 2.6, 2.7).
- The engine is never modified; all new engine-side code is the `plate.web` glue in the existing wheel.
- Pure-Python glue tests run under `pytest -q` and must keep the suite green; the headless-browser smoke test (task 18) is a distinct browser-only integration test.
- Property tests use `hypothesis` and validate the design's six Correctness Properties; each property is its own sub-task annotated with its property number and the requirement clauses it checks.
- Owner-decision requirements (13.1/13.2 launch timing, 13.4/13.5 power-user links, deploy home) are reflected as explicit, togglable behaviour rather than open questions.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4", "1.5"] },
    { "id": 2, "tasks": ["1.6", "1.7", "1.8"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3"] },
    { "id": 6, "tasks": ["6.1", "7.1", "15.1"] },
    { "id": 7, "tasks": ["6.2", "7.2", "8.1", "16.1", "19.1", "19.2", "15.2"] },
    { "id": 8, "tasks": ["8.2", "9.1", "9.2", "10.1", "11.1", "16.2", "17.1"] },
    { "id": 9, "tasks": ["9.3", "11.2", "12", "13", "17.2"] },
    { "id": 10, "tasks": ["18"] }
  ]
}
```
