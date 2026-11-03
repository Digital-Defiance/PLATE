# Headless-browser smoke test (task 18)

A **browser-only integration test** — NOT part of the pure-Python `pytest` suite
and NOT part of the Node `test:spike` unit suite (both stay fast and hermetic).
It is the automated form of the spike done-definition: it loads the **actual**
web page in headless Chromium, drops a fixed PNG sample onto the real drop zone,
lets the page run a conversion through the Web Worker + Pyodide, and asserts the
SVG the page produced equals the CLI SVG. It guards against the browser shell
drifting from the CLI (Requirements 1.2, 1.3). The engine is never modified; the
smoke test runs the unchanged wheel in Pyodide and the unchanged `pipeline.run`
on the CLI side.

| file | runtime | role |
|---|---|---|
| `oracle.py` | CPython (project venv) | runs the UNCHANGED engine (`pipeline.run`, default `Config`) on the fixed sample and writes the oracle manifest: the sample bytes (base64) + the CLI SVG + its `bakeoff/score.py` composite |
| `score.py` | CPython (project venv) | composite scorer used **only** on the non-byte-identical fallback path; reports the browser SVG's composite and its difference from the CLI composite |
| `run.ts` | Node (tsx) | builds the wheel (`uv build --wheel`), bundles the real page modules (`src/main.ts` + `client.ts` + `worker.ts`) with esbuild, serves the real `index.html` on 127.0.0.1, opens it in headless Chromium (Playwright), dispatches a real `drop` on `#drop-zone`, waits for the conversion, and asserts equivalence |

## Equivalence rule

- **PNG sample** → the page SVG must be **byte-identical** to the CLI SVG
  (Requirement 1.2). Using a PNG sidesteps the known browser-vs-CLI JPEG-decoder
  difference, so the result is deterministic and byte-exact.
- **Fallback band** → if (for a non-PNG, or a platform float drift) the SVG is
  not byte-identical, the runner falls back to the documented `Bakeoff_Tolerance`
  (0.01 composite difference, matching `web/spike/driver.py`) via `score.py`.

## Run it

From `web/`:

```sh
npm run smoke                                   # defaults: sample badge.png, dir /tmp/plate-smoke
npm run smoke -- --sample badge.png --dir /tmp/plate-smoke
npm run smoke -- --headful                      # watch it in a visible browser
```

Prerequisites: the project venv at `.venv` (so `oracle.py`/`score.py` can import
`plate`), `uv` at `~/.local/bin/uv` (overridable with `--uv` or `$UV`), and
Playwright's Chromium cached (it is a pinned devDependency; `npx playwright
install chromium` if missing). The Python steps are invoked with
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` so cairosvg's cairo loads for the
composite fallback.

All build outputs (wheel, bundles, served page, any saved browser SVG) land under
the `--dir` working directory (default `/tmp/plate-smoke`), **outside** the repo —
nothing is written into the tree, exactly like `web/spike/run.ts`.

Exit status is `0` when the page SVG matches the CLI oracle (byte-identical, or
within `Bakeoff_Tolerance` on the fallback), `1` on any mismatch or harness
failure.

## Why `src/main.ts` exists

The static shell (`web/index.html`) references `./main.js` as its module entry
seam. `src/main.ts` is the minimal composition of the already-finished shell
modules — `PlateClient` + `intake` + `settings` + `preview` + `download` +
`warnings` + `errors` + `links` — that wires the shell DOM end-to-end so there is
a working page to smoke-test. It adds no conversion logic (Property 1: thin
shell); all heavy work stays in the Web Worker. The deploy build (`build.ts`)
bundles it as `main.js` alongside `client.js` and `worker.js`.
