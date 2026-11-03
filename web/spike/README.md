# Phase 1 spike measurement harness (tasks 3.2–4)

This directory holds the spike harness that checks whether the **unchanged** PLATE
engine runs in Pyodide and produces the same SVG in the browser as on the CLI,
across the 24-scene seed-1 bake-off corpus, within acceptable per-scene time. It
records every outcome into `STATUS.md`. The engine is never modified; the spike
runs the unchanged wheel in Pyodide.

| file | runtime | role |
|---|---|---|
| `driver.py` | CPython (project venv) | builds the corpus + CLI reference manifest (`prepare`); classifies browser SVGs against the CLI SVGs with `bakeoff/score.py` (`score`) |
| `measure.ts` | browser page (any JS runtime) | `runSpike`: drives the worker over all scenes, times each conversion and the one-time bring-up separately, captures the browser SVGs, and renders the `STATUS.md` block |
| `decision.ts` | pure TS | task 3.3: evaluates the spike decision points over a recorded report and produces the go/no-go HALT verdict folded into the same block |
| `page.ts` | browser page | wires `runSpike` to the real worker (`workerRuntime`) and to the functions `run.ts` exposes |
| `run.ts` | Node (tsx) | task 4 runner: builds the wheel and bundles, serves them on 127.0.0.1, runs `page.ts` in headless Chromium (Playwright), backs `SpikeIO` with the filesystem and `driver.py score`, and writes `STATUS.md` |
| `status-file.ts` | pure TS | replaces the marker-delimited spike block in `STATUS.md` in place, appends it when absent, and refuses to edit malformed markers |
| `diagnose.py` | CPython + Pyodide | attributes each outside-tolerance scene to library versions or to Pyodide (see below) |

The scoring split is deliberate: `bakeoff/score.py`'s composite needs `cairosvg`,
which stays **out** of the browser runtime. The harness records raw browser SVGs
and timings in the browser, and `driver.py score` computes the composite
difference and classification in CPython.

## Runtime notes

- Pyodide is pinned to **314.0.7** in both `web/src/worker.ts` and the `pyodide`
  devDependency in `web/package.json`; keep them equal (Requirement 11.3).
- Pyodide 314 refuses classic workers, so the worker is an ES module worker:
  create it with `new Worker(url, { type: "module" })`. It loads `pyodide.mjs`
  with a dynamic `import()`.
- The worker loads numpy, scipy, opencv-python, pillow and scikit-image
  explicitly (the engine imports Pillow and scikit-image at module load) and
  records pass/fail for each; a package passes only when its module imports,
  because `loadPackage` does not reject on a failed download.
- The PLATE wheel is installed with `micropip` `deps=False`: its declared
  `opencv-python-headless` and `vtracer` have no Pyodide builds.

## Running the spike (task 4)

Python commands need `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` so cairocffi
finds Homebrew's cairo. All working data stays in the spike directory, outside
the repository.

```bash
# 1. corpus + CLI reference manifest
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/driver.py prepare -o /tmp/plate-spike

# 2. optional: a venv with Pyodide 314.0.7's library versions, for the diagnostic
~/.local/bin/uv venv --python 3.14.2 /tmp/plate-pyodide-venv
~/.local/bin/uv pip install --python /tmp/plate-pyodide-venv/bin/python \
  numpy==2.4.6 scipy==1.18.0 opencv-python-headless==4.11.0.86 scikit-image==0.26.0 pillow==12.2.0

# 3. the spike itself (writes the STATUS.md block)
cd web && npm ci
npx tsx spike/run.ts --dir /tmp/plate-spike --diag-python /tmp/plate-pyodide-venv/bin/python
```

`run.ts` exits 0 when no decision point tripped, 3 when the recorded verdict
halts the spike, and 1 when the runner itself failed. Other options: `--status`
(a different STATUS file, for dry runs), `--python`, `--uv`, `--dyld`,
`--timeout-minutes`.

The recorded block holds every per-package load result, the bring-up time, every
per-scene timing, every per-image SVG classification, the decision verdict, how
the run was set up (versions, prefixes, reproduce commands) and, with
`--diag-python`, the diagnostic section.

## Diagnostic for outside-tolerance scenes

With `--diag-python`, after scoring and only when a scene is outside tolerance,
`run.ts`:

1. reinstalls the freshly built wheel into the diagnostic venv (`--no-deps`);
2. runs `diagnose.py convert` there: reruns those scenes natively with Pyodide's
   library versions;
3. runs `diagnose.py decode` inside Pyodide under Node (npm `pyodide` 314.0.7,
   the same WebAssembly package builds the browser loads) to record the pixels
   the engine's decoder produces there;
4. runs `diagnose.py compare` in the CLI venv: a gap comes from **library
   versions** when the native rerun reproduces the browser SVG, and from
   **Pyodide** when it reproduces the CLI SVG instead (composites decide when the
   rerun matches neither byte for byte).

## Tests

```bash
cd web && npm run typecheck && npm run test:spike
```

`test:spike` runs the `STATUS.md` splice tests (`status-file.test.ts`) and the
`runSpike` tests with fake ports (`measure.test.ts`: bring-up timed apart from the
scenes, bring-up failures recorded and halting) with Node's built-in test runner.
