/**
 * PLATE Conversion_Worker — Pyodide runtime bootstrap + staged convert handling.
 *
 * This is the first web/ frontend file. It runs the *unchanged* PLATE engine in
 * the visitor's browser off the main thread: it boots Pyodide, loads the
 * scientific wheels, installs the PLATE wheel served from GitHub Pages and
 * imports the `plate.web` glue module. The engine is never modified; the worker
 * only calls `plate_web.convert_bytes` / `check_noise`, which write the uploaded
 * bytes to Pyodide's in-memory filesystem and call `pipeline.run` exactly as the
 * CLI does.
 *
 * MODULE WORKER: Pyodide 314 refuses to run in classic workers ("Classic web
 * workers are not supported"), so this script must be started as an ES module
 * worker — `new Worker(url, { type: "module" })` — and it loads Pyodide with a
 * dynamic `import()` of the pinned `pyodide.mjs` instead of `importScripts`.
 *
 * Scope note: the runtime bootstrap (`ensureRuntime`), per-package load
 * tracking, readiness signalling and warm-runtime reuse came in with task 3.1;
 * task 8.1 fleshed out the staged `convert` handling — `handleConvert` emits the
 * ordered staged progress (load-pyodide … import → segment/order/trace/emit),
 * posts exactly one `result` or one `error` per request id, and classifies a
 * decode failure after intake as recoverable. Because the engine runs the whole
 * pipeline in one synchronous `convert_bytes` call with no mid-pipeline hooks,
 * the segment/order/trace/emit markers are coarse (emitted around that call) and
 * carry the engine's real per-stage timings from `stats` rather than fabricated
 * sub-progress.
 *
 * TESTABILITY (task 8.2): the message handlers live in a pure
 * `createWorkerHandlers({ post, bootstrap })` factory — the warm-runtime state
 * is closure-held (not a module singleton), the `post` sink and the low-level
 * Pyodide `bootstrap` steps are injected. This lets the unit suite drive the
 * REAL `handleConvert`/`ensureRuntime` against a fake runtime, asserting the
 * staged ordering, the result-xor-error exclusivity and the recoverable
 * classification directly. The `self`/`postMessage` wiring at the bottom is a
 * thin shell: in a worker it builds the real Pyodide bootstrap and dispatches
 * messages; under plain Node (no `self`) it is skipped, so importing this module
 * for tests touches nothing browser-only.
 */

import type {
  ConvertRequest,
  ConvertResult,
  ConvertStats,
  PackageLoadResult,
  PackageLoadResults,
  RuntimeInfo,
  Stage,
  WorkerIn,
  WorkerOut,
} from "./protocol.js";

// Pyodide's loader is fetched from the CDN at runtime via a dynamic import (it is
// not bundled). We only need its types at compile time.
import type { PyodideInterface, loadPyodide as LoadPyodide } from "pyodide";

/* -------------------------------------------------------------------------- */
/* Pinned versions (a CDN change must not alter page behaviour without a repo  */
/* change — Requirement 11.3). Keep PYODIDE_VERSION equal to the `pyodide`     */
/* devDependency in web/package.json; the deploy workflow (task 15.1) pins the */
/* same version.                                                               */
/* -------------------------------------------------------------------------- */

/**
 * Pinned Pyodide release. 314.0.7 ships Python 3.14.2 and, per its
 * `pyodide-lock.json`: numpy 2.4.6, scipy 1.18.0, opencv-python 4.11.0.86,
 * pillow 12.2.0, scikit-image 0.26.0, micropip 0.11.1.
 */
const PYODIDE_VERSION = "314.0.7";
const PYODIDE_CDN_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
/** The ES-module loader (Pyodide 314 has no classic-worker loader). */
const PYODIDE_MODULE_URL = `${PYODIDE_CDN_BASE}pyodide.mjs`;

/**
 * The PLATE wheel served from GitHub Pages alongside this shell (package name
 * `plate-svg`). The deploy workflow (task 15.1) copies the built wheel next to
 * the worker, so a relative URL resolves against the page origin — no network
 * call leaves the user's machine except fetching this same-origin wheel.
 *
 * Resolved lazily (inside the real bootstrap) rather than at module top level so
 * importing this module outside a worker — the unit tests run under plain Node,
 * where `self` is undefined — does not touch `self.location`.
 */
function plateWheelUrl(): string {
  return new URL("./plate_svg-0.1.0-py3-none-any.whl", self.location.href).href;
}

/**
 * Scientific packages the engine imports at module load, loaded explicitly via
 * Pyodide's package loader, each paired with the top-level module the load check
 * imports. numpy/scipy/opencv-python are the packages Requirement 2.1 names; the
 * engine also imports Pillow (`imageio.py`) and scikit-image (`geometry.py`) at
 * module load. The wheel is installed with `deps=False` because its declared
 * dependencies (`opencv-python-headless`, `vtracer`) have no Pyodide builds;
 * vtracer is only used by the CLI's baseline comparison and is not loaded here.
 */
const REQUIRED_PACKAGES = [
  { name: "numpy", module: "numpy" },
  { name: "scipy", module: "scipy" },
  { name: "opencv-python", module: "cv2" },
  { name: "pillow", module: "PIL" },
  { name: "scikit-image", module: "skimage" },
] as const satisfies ReadonlyArray<{ name: keyof PackageLoadResults; module: string }>;
type RequiredPackage = (typeof REQUIRED_PACKAGES)[number];

/** Distributions whose installed versions are reported on `ready`. */
const REPORTED_DISTRIBUTIONS = [
  "numpy",
  "scipy",
  "opencv-python",
  "pillow",
  "scikit-image",
  "micropip",
  "plate-svg",
] as const;

/* -------------------------------------------------------------------------- */
/* Runtime types                                                               */
/* -------------------------------------------------------------------------- */

/** The slice of `plate.web` the worker calls, as a Pyodide module proxy. */
interface PlateWebModule {
  convert_bytes: (
    data: unknown,
    filename: string,
    overrides: unknown,
  ) => PyResultProxy;
}

/** A Python object proxy the worker converts to JS and then releases. */
interface PyResultProxy {
  toJs: (opts: { dict_converter: typeof Object.fromEntries }) => unknown;
  destroy: () => void;
}

/** A disposable Python object proxy (for example converted input bytes). */
interface PyDisposable {
  destroy: () => void;
}

/**
 * The warm runtime the handlers operate against. It is deliberately described in
 * terms of the handful of operations `handleConvert` performs, not the full
 * Pyodide surface, so the unit suite (task 8.2) can supply a fake implementing
 * exactly these members while the production bootstrap returns a real one.
 */
export interface Runtime {
  /** Copy a JS object into a Python-friendly mapping (Pyodide `toPy`). */
  toPy: (value: unknown) => unknown;
  /** Copy a JS typed array into real Python `bytes`. */
  toBytes: (buffer: Uint8Array) => PyDisposable;
  /** `plate.web` imported as a Python module proxy for direct calls. */
  plateWeb: PlateWebModule;
  packages: PackageLoadResults;
  info: RuntimeInfo;
}

/**
 * The low-level Pyodide bring-up, split into the four staged steps so the
 * progress ladder (load-pyodide → load-packages → install-plate → import) stays
 * in the testable `ensureRuntime` while the browser-only Pyodide I/O is injected.
 * The real implementation lives in `realBootstrap`; the unit suite supplies a
 * fake that records which steps ran and can fail a chosen step.
 */
export interface RuntimeBootstrap {
  /** load-pyodide: fetch + initialise the pinned Pyodide runtime. */
  loadPyodide(): Promise<void>;
  /** load-packages: load each required wheel, returning its pass/fail result. */
  loadPackages(): Promise<{ packages: PackageLoadResults; failures: string[] }>;
  /** install-plate: micropip-install the PLATE wheel (deps already loaded). */
  installPlate(): Promise<void>;
  /** import: import the engine + glue and build the callable `Runtime`. */
  importGlue(): Promise<Runtime>;
}

/**
 * A bring-up failure that still carries the per-package load results recorded
 * so far, so the spike can record which package failed (Requirement 2.4) and
 * the `error` message can surface them to the client.
 */
export class RuntimeBringUpError extends Error {
  readonly packages: PackageLoadResults | undefined;

  constructor(message: string, packages?: PackageLoadResults) {
    super(message);
    this.name = "RuntimeBringUpError";
    this.packages = packages;
  }
}

/* -------------------------------------------------------------------------- */
/* Messaging helpers (pure)                                                    */
/* -------------------------------------------------------------------------- */

/** A sink for messages the worker posts back to the main thread. */
export type Post = (message: WorkerOut) => void;

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

/**
 * A decode failure (`ImageLoadError` / bad extension / empty bytes) is a
 * recoverable error: the user can pick another file without reloading. Runtime
 * or package failures are non-recoverable. The glue raises distinct Python
 * error types; we classify on the message text Pyodide surfaces.
 */
export function isRecoverable(message: string): boolean {
  return (
    /ImageLoadError/.test(message) ||
    /ConvertError/.test(message) ||
    /unsupported file extension/.test(message) ||
    /empty file/.test(message)
  );
}

/** Release a Python proxy if the value is one (plain JS values pass through). */
function release(value: unknown): void {
  const proxy = value as Partial<PyDisposable> | null | undefined;
  if (proxy && typeof proxy.destroy === "function") proxy.destroy();
}

/* -------------------------------------------------------------------------- */
/* Pipeline stage tables (pure)                                                */
/* -------------------------------------------------------------------------- */

/**
 * The four engine pipeline stages the conversion reports, in paint order. They
 * follow the bring-up stages (load-pyodide → … → import) so one conversion's
 * full staged sequence is load-pyodide, load-packages, install-plate, import,
 * segment, order, trace, emit — the exact order Requirement 5.2 names. The
 * `pct` values span the post-bring-up band 92→100 so a cold conversion's bar
 * advances monotonically from `import` (90) through to the result.
 */
const PIPELINE_STAGES: ReadonlyArray<{ stage: Stage; pct: number }> = [
  { stage: "segment", pct: 92 },
  { stage: "order", pct: 95 },
  { stage: "trace", pct: 98 },
  { stage: "emit", pct: 100 },
] as const;

/** The `stats` key whose engine timing corresponds to each pipeline stage. */
const STAGE_TIMING: Partial<Record<Stage, keyof ConvertStats>> = {
  segment: "t_segment",
  order: "t_order",
  trace: "t_trace",
};

/** A `"0.123s"` note for a stage when `stats` carries its engine timing. */
function stageTimingNote(stats: ConvertStats | undefined, stage: Stage): string | undefined {
  if (stats === undefined) return undefined;
  const key = STAGE_TIMING[stage];
  if (key === undefined) return undefined;
  const seconds = stats[key];
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return undefined;
  return `${seconds.toFixed(3)}s`;
}

/* -------------------------------------------------------------------------- */
/* Worker handlers (pure factory — injected post + bootstrap)                  */
/* -------------------------------------------------------------------------- */

/** The message handlers a running worker (or a test) drives. */
export interface WorkerHandlers {
  ensureRuntime(id?: string): Promise<Runtime>;
  handleInit(): Promise<void>;
  handleConvert(id: string, request: ConvertRequest): Promise<void>;
}

/**
 * Build the worker's message handlers over an injected `post` sink and Pyodide
 * `bootstrap`. The warm runtime is held in this closure (not a module
 * singleton), so each worker — and each unit test — gets independent warm state.
 */
export function createWorkerHandlers(deps: {
  post: Post;
  bootstrap: RuntimeBootstrap;
}): WorkerHandlers {
  const { post, bootstrap } = deps;

  function emitProgress(stage: Stage, pct: number, id?: string, note?: string): void {
    const message: Extract<WorkerOut, { type: "progress" }> = { type: "progress", stage, pct };
    if (id !== undefined) message.id = id;
    if (note !== undefined) message.note = note;
    post(message);
  }

  /** Post a non-recoverable bring-up error, attaching package results when known. */
  function postBringUpError(err: unknown, id?: string): void {
    const message: Extract<WorkerOut, { type: "error" }> = {
      type: "error",
      message: errorMessage(err),
      recoverable: false,
    };
    if (id !== undefined) message.id = id;
    if (err instanceof RuntimeBringUpError && err.packages !== undefined) {
      message.packages = err.packages;
    }
    post(message);
  }

  /**
   * The single warm runtime. Held as a promise so concurrent `init`/`convert`
   * messages share one bring-up instead of racing to load Pyodide twice.
   */
  let runtimePromise: Promise<Runtime> | null = null;

  /**
   * Boot the Python runtime once and keep it warm. Subsequent calls return the
   * same instance so a second conversion skips load/install (Requirement 5.5).
   *
   * Steps mirror the design's `ensureRuntime` pseudocode:
   *   load-pyodide → load-packages → install-plate → import → done.
   * Each required package's load result is recorded (pass/fail) for the spike and
   * returned on the `ready` message; `opencv-python` is the top unverified risk.
   * The import stage imports the engine itself (`plate.pipeline`) as well as the
   * `plate.web` glue, so engine import failures surface during bring-up and the
   * one-time import cost is not charged to the first conversion.
   *
   * `id` tags the bring-up progress events with a conversion request id when the
   * runtime is brought up *as part of* a conversion (the cold-start path). This
   * is what lets a first conversion report the full staged sequence
   * load-pyodide → … → emit all under one request id (Requirement 5.2). A warm
   * runtime returns the cached handle without re-emitting these stages, so a
   * subsequent conversion skips them (Requirement 5.5). Runtime bring-up from
   * `init` (no conversion) passes no id, matching the id-less bring-up progress
   * the `PlateClient` attributes to the one-time first load.
   */
  function ensureRuntime(id?: string): Promise<Runtime> {
    if (runtimePromise) return runtimePromise;

    runtimePromise = (async (): Promise<Runtime> => {
      emitProgress("load-pyodide", 0, id);
      await bootstrap.loadPyodide();

      emitProgress("load-packages", 25, id);
      const { packages, failures } = await bootstrap.loadPackages();
      if (failures.length > 0) {
        // Non-recoverable: the page cannot run the engine without these wheels.
        throw new RuntimeBringUpError(
          `required package(s) failed to load in Pyodide: ${failures.join("; ")}`,
          packages,
        );
      }

      try {
        emitProgress("install-plate", 70, id);
        await bootstrap.installPlate();

        emitProgress("import", 90, id);
        const runtime = await bootstrap.importGlue();
        // The per-package results came from `loadPackages`; stamp them onto the
        // runtime the handlers report on `ready`. (Assign rather than spread so a
        // class-instance runtime keeps its prototype methods — the real bootstrap
        // returns a plain object, but tests may hand back a class instance.)
        runtime.packages = packages;

        // `done` terminates a *standalone* bring-up (an `init` with no conversion).
        // When bring-up is the cold start of a conversion (`id` present), the
        // sequence continues into the pipeline stages segment → … → emit, so we
        // must NOT inject `done` here — it would land mid-sequence and break the
        // ordered staged progress Requirement 5.2 specifies for a conversion.
        if (id === undefined) emitProgress("done", 100);
        return runtime;
      } catch (err) {
        throw new RuntimeBringUpError(errorMessage(err), packages);
      }
    })();

    // If bring-up fails, clear the cached promise so a later attempt can retry
    // rather than permanently resolving to a rejected runtime.
    runtimePromise.catch(() => {
      runtimePromise = null;
    });

    return runtimePromise;
  }

  async function handleInit(): Promise<void> {
    try {
      const rt = await ensureRuntime();
      post({ type: "ready", packages: rt.packages, runtime: rt.info });
    } catch (err) {
      postBringUpError(err);
    }
  }

  /**
   * Emit the post-`segment` pipeline stage markers (`order`, `trace`, `emit`) in
   * order after `convert_bytes` returns, each carrying the request id and —
   * where the engine measured it — the real per-stage timing from `stats` as a
   * note. The engine runs the whole pipeline in one call, so these are honest
   * coarse markers of completed phases, not fabricated sub-progress.
   */
  function emitStageTimings(stats: ConvertStats | undefined, id: string): void {
    for (const { stage, pct } of PIPELINE_STAGES) {
      if (stage === "segment") continue; // already emitted before the convert call
      const note = stageTimingNote(stats, stage);
      emitProgress(stage, pct, id, note);
    }
  }

  /**
   * Convert one image on the warm runtime, reporting staged progress and posting
   * exactly one `result` OR one `error` for the request id (Requirements 5.2–5.5,
   * 3.6, 9.5).
   *
   * STAGED PROGRESS — what the engine allows: `plate.web.convert_bytes` runs the
   * whole segment→order→trace→emit pipeline in one synchronous call and exposes
   * no mid-pipeline callbacks to JS, so the worker cannot interleave fine-grained
   * sub-progress with real engine state. Instead it emits coarse per-stage
   * markers around that single call, exactly as the design specifies ("coarse
   * progress events … segment → order → trace → emit"): a `segment` marker before
   * the call announces the pipeline has begun, then after the call completes the
   * remaining `order`/`trace`/`emit` markers fire in order, carrying the *real*
   * per-stage timings the engine reported in `stats` (`t_order`/`t_trace`) as a
   * human `note` rather than any fabricated percentage. Each event carries the
   * request `id`.
   *
   * RESULT/ERROR EXCLUSIVITY: on success exactly one `result` is posted; on any
   * failure exactly one `error` is posted and no `result`. Decode/input failures
   * (ImageLoadError / ConvertError / empty / unsupported extension) are
   * recoverable — the user can pick another file without reloading (Requirement
   * 9.5); bring-up failures are non-recoverable. The runtime stays warm so a
   * subsequent request skips the load/install stages (Requirement 5.5).
   */
  async function handleConvert(id: string, request: ConvertRequest): Promise<void> {
    let rt: Runtime;
    try {
      // Cold start: bring-up emits load-pyodide → … → import tagged with this
      // request id (Requirement 5.2). Warm start: returns immediately, emitting
      // none of those stages (Requirement 5.5).
      rt = await ensureRuntime(id);
    } catch (err) {
      // Bring-up failure is non-recoverable; still tagged with the request id,
      // and no `result` is posted for it (Requirement 5.4).
      postBringUpError(err, id);
      return;
    }

    let data: PyDisposable | undefined;
    let overrides: unknown;
    let resultProxy: PyResultProxy | undefined;
    try {
      // A JS Uint8Array crosses into Python as a JsProxy, which is not bytes-like;
      // copy it into real Python bytes (the glue's documented input type).
      data = rt.toBytes(request.imageBytes);
      // overrides must cross as a Python-friendly mapping; pass the plain config
      // object (Pyodide converts a JS object to a dict). Keys are the UI lever
      // names the glue's build_config maps onto Config fields.
      overrides = rt.toPy(request.config);

      // Announce the pipeline has started. The whole segment→emit pipeline runs
      // inside the single synchronous `convert_bytes` call below (the engine
      // exposes no mid-pipeline hooks), so this marker fires before the call.
      emitProgress("segment", PIPELINE_STAGES[0]!.pct, id);

      resultProxy = rt.plateWeb.convert_bytes(data, request.filename, overrides);
      // Convert the returned Python dict to a plain JS object (structured-clonable).
      const result = resultProxy.toJs({ dict_converter: Object.fromEntries }) as ConvertResult;

      // The pipeline finished; replay the remaining stage markers in order,
      // annotating each with the engine's real per-stage timing from `stats`.
      emitStageTimings(result.stats, id);

      post({ type: "result", id, result });
    } catch (err) {
      // Any failure in decode/config/convert surfaces as exactly one `error`
      // with no `result`. A decode failure after intake (ImageLoadError / bad
      // extension / empty bytes) is recoverable so the user can retry with a
      // different file, keeping any prior result unchanged (Requirements 3.6,
      // 9.5); other conversion failures classify the same way on their message.
      const message = errorMessage(err);
      post({ type: "error", id, message, recoverable: isRecoverable(message) });
    } finally {
      release(resultProxy);
      release(overrides);
      release(data);
    }
  }

  return { ensureRuntime, handleInit, handleConvert };
}

/* -------------------------------------------------------------------------- */
/* Real Pyodide bootstrap (browser-only; not exercised under Node)             */
/* -------------------------------------------------------------------------- */

/**
 * Load one Pyodide package and confirm its top-level module imports, returning
 * pass/fail instead of throwing so the spike (tasks 3.2/3.3) can record every
 * package's outcome even when one fails.
 *
 * `loadPackage` resolves even when a download or install fails (Pyodide logs
 * "Failed to load …" rather than rejecting), so the import is the real check.
 */
async function loadOnePackage(
  pyodide: PyodideInterface,
  pkg: RequiredPackage,
): Promise<{ result: PackageLoadResult; detail?: string }> {
  const errors: string[] = [];
  try {
    await pyodide.loadPackage(pkg.name, { errorCallback: (msg) => errors.push(msg) });
    release(pyodide.pyimport(pkg.module));
    return { result: "pass" };
  } catch (err) {
    errors.push(errorMessage(err));
    return { result: "fail", detail: errors.join(" | ") };
  }
}

/** Collect the runtime's Pyodide/Python versions and installed distributions. */
function describeRuntime(pyodide: PyodideInterface, version: string): RuntimeInfo {
  const describe = pyodide.runPython(`
def _plate_describe(names):
    import importlib.metadata as md
    import sys
    versions = {}
    for name in names:
        try:
            versions[name] = md.version(name)
        except md.PackageNotFoundError:
            versions[name] = "not installed"
    return {"python": sys.version.split()[0], "versions": versions}
_plate_describe
`) as (names: readonly string[]) => PyResultProxy;
  let proxy: PyResultProxy | undefined;
  try {
    proxy = describe([...REPORTED_DISTRIBUTIONS]);
    const out = proxy.toJs({ dict_converter: Object.fromEntries }) as {
      python: string;
      versions: Record<string, string>;
    };
    return { pyodide: version, python: out.python, versions: out.versions };
  } finally {
    release(proxy);
    release(describe);
  }
}

/**
 * The production `RuntimeBootstrap`: it holds the Pyodide handle across its four
 * steps so `ensureRuntime` can drive them with the staged progress ladder. The
 * `load-pyodide` step fetches the pinned ES-module loader (the browser caches it
 * after the first visit); the remaining steps load the scientific wheels, install
 * the same-origin PLATE wheel and import the engine + glue.
 */
function realBootstrap(): RuntimeBootstrap {
  let pyodide: PyodideInterface | undefined;
  let loaderVersion = PYODIDE_VERSION;

  return {
    async loadPyodide(): Promise<void> {
      const loader = (await import(/* @vite-ignore */ PYODIDE_MODULE_URL)) as {
        loadPyodide: typeof LoadPyodide;
        version: string;
      };
      pyodide = await loader.loadPyodide({ indexURL: PYODIDE_CDN_BASE });
      loaderVersion = loader.version;
    },

    async loadPackages(): Promise<{ packages: PackageLoadResults; failures: string[] }> {
      const py = pyodide!;
      const packages = {} as PackageLoadResults;
      const failures: string[] = [];
      for (const pkg of REQUIRED_PACKAGES) {
        const { result, detail } = await loadOnePackage(py, pkg);
        packages[pkg.name] = result;
        if (result === "fail") failures.push(`${pkg.name}${detail ? ` (${detail})` : ""}`);
      }
      return { packages, failures };
    },

    async installPlate(): Promise<void> {
      const py = pyodide!;
      await py.loadPackage("micropip");
      const micropip = py.pyimport("micropip") as {
        install: { callKwargs: (...args: unknown[]) => Promise<unknown> };
      };
      // deps=False: the scientific packages are loaded above; the wheel's
      // declared opencv-python-headless/vtracer have no Pyodide builds.
      await micropip.install.callKwargs(plateWheelUrl(), { deps: false });
    },

    async importGlue(): Promise<Runtime> {
      const py = pyodide!;
      release(py.pyimport("plate.pipeline"));
      const plateWeb = py.pyimport("plate.web") as PlateWebModule;
      const toBytesHelper = py.runPython(
        "lambda buffer: buffer.to_bytes()",
      ) as (buffer: Uint8Array) => PyDisposable;
      const info = describeRuntime(py, loaderVersion);
      return {
        toPy: (value: unknown) => py.toPy(value),
        toBytes: (buffer: Uint8Array) => toBytesHelper(buffer),
        plateWeb,
        // `packages` is filled in by ensureRuntime from loadPackages(); this
        // placeholder keeps the shape total until then.
        packages: {} as PackageLoadResults,
        info,
      };
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Worker entry point (thin shell — browser only)                              */
/* -------------------------------------------------------------------------- */

/**
 * Wire the handlers onto the worker's message channel. Guarded by the presence
 * of `self.addEventListener` so importing this module under plain Node (the unit
 * tests) is a no-op: the tests construct `createWorkerHandlers` with a fake
 * bootstrap directly instead of going through the channel.
 */
function startWorker(): void {
  const handlers = createWorkerHandlers({
    post: (message) =>
      (self as unknown as { postMessage: (m: WorkerOut) => void }).postMessage(message),
    bootstrap: realBootstrap(),
  });

  self.addEventListener("message", (event: MessageEvent<WorkerIn>) => {
    const message = event.data;
    switch (message.type) {
      case "init":
        void handlers.handleInit();
        break;
      case "convert":
        void handlers.handleConvert(message.id, message.request);
        break;
      default: {
        // Exhaustiveness guard: a new WorkerIn variant must be handled here.
        const _never: never = message;
        void _never;
      }
    }
  });
}

if (typeof self !== "undefined" && typeof self.addEventListener === "function") {
  startWorker();
}
