/**
 * Phase 1 spike measurement harness (task 3.2).
 *
 * This harness drives the task-3.1 Web Worker / Pyodide runtime across the
 * 24-scene seed-1 bake-off corpus and collects exactly the measurements the
 * design's Phase 1 spike requires:
 *
 *   - the `opencv-python` (and numpy/scipy) load result — the top unverified risk;
 *   - per-scene conversion time in seconds;
 *   - a byte-for-byte comparison of each browser SVG against the CLI SVG, falling
 *     back to the `bakeoff/score.py` composite difference and a
 *     byte-identical / within-tolerance / outside-tolerance classification when the
 *     two are not identical.
 *
 * It then writes every outcome (per-package load results, per-scene timings,
 * per-image SVG classification) into `STATUS.md`.
 *
 * SCOPE (task 3.2 only): this is the harness + its orchestration. It deliberately
 * does NOT implement task 3.3's decision-point halts, nor task 4's "record the
 * measurements" checkpoint sign-off — it produces the measurements those tasks act
 * on. The engine is never touched; the harness runs the UNCHANGED wheel in Pyodide.
 *
 * SPLIT OF LABOUR with the Python driver (`web/spike/driver.py`):
 *   1. `driver.py prepare` builds the corpus and the CLI reference manifest
 *      (image bytes + CLI SVG + CLI composite per scene).
 *   2. This harness converts each scene in the worker, times it, captures the
 *      browser SVG, and writes the browser SVGs out for scoring.
 *   3. `driver.py score` classifies the browser SVGs against the CLI SVGs with
 *      `bakeoff/score.py` (cairosvg / scikit-image are NOT in the browser, so the
 *      composite must be computed in CPython) and emits `classification.json`.
 *   4. This harness folds the classification + timings + package results into the
 *      single `STATUS.md` spike block.
 *
 * HOW THE NUMBERS ARE CAPTURED (task 4): the harness core (`runSpike`) is
 * environment-agnostic — it takes a `SpikeRuntime` (the worker behind a promise
 * API) and a `SpikeIO` (file access + the Python scorer). `run.ts` builds the
 * wheel and bundles, serves them, opens `page.ts` in headless Chromium, and there
 * calls `runSpike` with `workerRuntime(worker)` and a `SpikeIO` backed by
 * Playwright-exposed functions (filesystem, `driver.py score`, STATUS.md splice).
 * See `web/spike/README.md` for the commands.
 */

import type {
  ConvertResult,
  PackageLoadResults,
  RuntimeInfo,
  Stage,
  WorkerIn,
  WorkerOut,
} from "../src/protocol.js";
import type { SpikeVerdict } from "./decision.js";
import {
  appendDecisionToStatusBlock,
  evaluateVerdict,
  renderDecision,
} from "./decision.js";

/* -------------------------------------------------------------------------- */
/* Manifest + classification shapes (mirror web/spike/driver.py)              */
/* -------------------------------------------------------------------------- */

/** One corpus scene as emitted by `driver.py prepare`. */
export interface ManifestScene {
  /** Stable scene key (`scene00`, `scene03_jpg`). */
  name: string;
  /** Original filename; its extension drives the MEMFS `/input.<ext>` path. */
  filename: string;
  /** Base64 of the raw corpus image bytes (decoded to a Uint8Array to convert). */
  imageBytesB64: string;
  /** The CLI SVG from the unchanged `pipeline.run` — the source of truth. */
  cliSvg: string;
  /** The `bakeoff/score.py` composite of the CLI SVG (for the diff fallback). */
  cliComposite: number;
}

/** The manifest `driver.py prepare` writes to `<dir>/manifest.json`. */
export interface Manifest {
  corpusN: number;
  corpusSeed: number;
  bakeoffTolerance: number;
  scenes: ManifestScene[];
}

/** SVG-equivalence outcome for one scene (Requirement 2.3). */
export type SvgClassification =
  | "byte-identical"
  | "within-tolerance"
  | "outside-tolerance"
  | "missing-browser-svg";

/** One scene's classification as emitted by `driver.py score`. */
export interface SceneClassification {
  name: string;
  classification: SvgClassification;
  cliComposite: number;
  browserComposite?: number;
  compositeDiff?: number;
}

/** The classification `driver.py score` writes to `<dir>/classification.json`. */
export interface Classification {
  bakeoffTolerance: number;
  scenes: SceneClassification[];
}

/* -------------------------------------------------------------------------- */
/* Per-scene measurement + the full spike report                              */
/* -------------------------------------------------------------------------- */

/** A recorded package load outcome, including "the loader never got that far". */
export type PackageLoadRecord = "pass" | "fail" | "not attempted";

/** Everything the spike records for one scene. */
export interface SceneMeasurement {
  name: string;
  /**
   * Wall-clock conversion time in seconds (Requirement 2.2), measured around one
   * `convert` request on the already-warm worker, so it excludes the one-time
   * runtime bring-up. `NaN` means the scene was never converted (bring-up failed).
   */
  seconds: number;
  /** The engine's own `stats.t_total` for this conversion (seconds), when reported. */
  engineSeconds?: number;
  /** `pass` once converted (the engine ran); `fail` if conversion threw. */
  converted: "pass" | "fail";
  /**
   * The `opencv-python` load result in force for this conversion; `not attempted`
   * when bring-up stopped before the package loader ran.
   */
  opencvLoad: PackageLoadRecord;
  /** Filled in from the Python scorer; `missing-browser-svg` until scored. */
  classification: SvgClassification;
  /** Error message when `converted === "fail"`. */
  error?: string;
  cliComposite?: number;
  browserComposite?: number;
  compositeDiff?: number;
}

/** The one-time runtime bring-up (`runtime.init()`), timed separately. */
export interface BringUpMeasurement {
  /** Wall-clock seconds from `init` to `ready` (or to the bring-up error). */
  seconds: number;
  /** The bring-up error message when the runtime never became ready. */
  error?: string;
}

/**
 * How a run was set up, supplied by the runner and recorded verbatim so the
 * measurements can be reproduced: labelled facts (versions, host, environment
 * prefixes) and the exact commands, in order.
 */
export interface SpikeSetup {
  facts: Array<[label: string, value: string]>;
  commands: string[];
}

/** The full spike report the harness writes into STATUS.md. */
export interface SpikeReport {
  corpusN: number;
  corpusSeed: number;
  bakeoffTolerance: number;
  /**
   * Per-package load results from the worker's `ready` message (Req 2.1), or
   * from its bring-up error when a package failed. Partial when bring-up stopped
   * before every package was tried; empty when the worker reported none.
   */
  packages: Partial<PackageLoadResults>;
  /** The one-time runtime bring-up time, measured apart from the scenes. */
  bringUp: BringUpMeasurement;
  /** What the warm runtime reported about itself (Pyodide/Python/library versions). */
  runtime?: RuntimeInfo;
  /** How the run was set up (runner-supplied facts and reproduce commands). */
  setup?: SpikeSetup;
  /** One row per corpus scene (Req 2.2, 2.3). */
  scenes: SceneMeasurement[];
}

/* -------------------------------------------------------------------------- */
/* Ports the harness depends on (so its core is testable + environment-free)  */
/* -------------------------------------------------------------------------- */

/**
 * The warm Pyodide worker behind a promise API. `init` resolves with the
 * per-package load results (the worker's `ready` message); `convert` resolves
 * with the engine's result for one scene. A production adapter is `workerRuntime`
 * below; a test can supply a fake.
 */
export interface SpikeRuntime {
  /**
   * Bring the runtime up once. On failure, reject with a {@link SpikeInitError}
   * carrying the per-package results the worker recorded, when it has them.
   */
  init(): Promise<PackageLoadResults>;
  convert(imageBytes: Uint8Array, filename: string): Promise<ConvertResult>;
  /** What the ready runtime reported about itself, once `init` has resolved. */
  runtimeInfo?(): RuntimeInfo | undefined;
}

/**
 * A runtime bring-up failure. `packages` holds the per-package load results the
 * worker attached to its bring-up error (absent when it never reached the
 * package loader), so a package failure is still recorded (Requirement 2.4).
 */
export class SpikeInitError extends Error {
  readonly packages: Partial<PackageLoadResults> | undefined;

  constructor(message: string, packages?: Partial<PackageLoadResults>) {
    super(message);
    this.name = "SpikeInitError";
    this.packages = packages;
  }
}

/**
 * Filesystem + Python-scorer access. Kept abstract so the harness core carries no
 * Node imports (the web/ tsconfig builds with `types: []`); a real runner backs
 * this with `node:fs` and a child process that runs `driver.py score`.
 */
export interface SpikeIO {
  /** Read `<dir>/manifest.json`. */
  readManifest(): Promise<Manifest>;
  /** Write one browser SVG to `<dir>/browser/<name>.svg`. */
  writeBrowserSvg(name: string, svg: string): Promise<void>;
  /** Run `driver.py score -o <dir>` and read back `<dir>/classification.json`. */
  scoreBrowserSvgs(): Promise<Classification>;
  /** Append/replace the spike block in `STATUS.md` with the rendered report. */
  writeStatus(markdown: string): Promise<void>;
}

/* -------------------------------------------------------------------------- */
/* Worker adapter: wrap the task-3.1 Web Worker as a SpikeRuntime              */
/* -------------------------------------------------------------------------- */

/** Minimal view of the worker the harness needs (matches `Worker`/worker shim). */
export interface WorkerLike {
  postMessage(message: WorkerIn, transfer?: Transferable[]): void;
  addEventListener(
    type: "message",
    listener: (event: MessageEvent<WorkerOut>) => void,
  ): void;
  removeEventListener(
    type: "message",
    listener: (event: MessageEvent<WorkerOut>) => void,
  ): void;
}

/** A simple monotonic id source for correlating convert requests/responses. */
function makeIdSource(): () => string {
  let n = 0;
  return () => `spike-${++n}`;
}

/**
 * Adapt the task-3.1 Web Worker (the `WorkerIn`/`WorkerOut` protocol) into a
 * `SpikeRuntime`. `init` sends `{type:"init"}` and resolves on the `ready`
 * message's package results; `convert` sends `{type:"convert"}` and resolves on
 * the matching `result` (or rejects on the matching `error`). Progress events are
 * forwarded to the optional `onProgress` callback and otherwise ignored.
 */
export function workerRuntime(
  worker: WorkerLike,
  onProgress?: (stage: Stage, pct: number, id?: string) => void,
): SpikeRuntime {
  const nextId = makeIdSource();
  let info: RuntimeInfo | undefined;

  function waitFor<T>(
    predicate: (out: WorkerOut) => { done: true; value: T } | { done: false } | { fail: Error },
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const listener = (event: MessageEvent<WorkerOut>) => {
        const out = event.data;
        if (out.type === "progress") {
          onProgress?.(out.stage, out.pct, out.id);
          return;
        }
        const verdict = predicate(out);
        if ("fail" in verdict) {
          worker.removeEventListener("message", listener);
          reject(verdict.fail);
        } else if (verdict.done) {
          worker.removeEventListener("message", listener);
          resolve(verdict.value);
        }
      };
      worker.addEventListener("message", listener);
    });
  }

  return {
    init(): Promise<PackageLoadResults> {
      const ready = waitFor<PackageLoadResults>((out) => {
        if (out.type === "ready") {
          info = out.runtime;
          return { done: true, value: out.packages };
        }
        if (out.type === "error" && out.id === undefined) {
          return { fail: new SpikeInitError(out.message, out.packages) };
        }
        return { done: false };
      });
      worker.postMessage({ type: "init" });
      return ready;
    },

    runtimeInfo(): RuntimeInfo | undefined {
      return info;
    },

    convert(imageBytes: Uint8Array, filename: string): Promise<ConvertResult> {
      const id = nextId();
      const done = waitFor<ConvertResult>((out) => {
        if (out.type === "result" && out.id === id) return { done: true, value: out.result };
        if (out.type === "error" && out.id === id) return { fail: new Error(out.message) };
        return { done: false };
      });
      const request: WorkerIn = {
        type: "convert",
        id,
        // The spike runs the default config (no overrides) — Property-1 equivalence.
        request: { imageBytes, filename, config: {} },
      };
      // Transfer the bytes buffer (not copy) to the worker, matching the design.
      worker.postMessage(request, [imageBytes.buffer]);
      return done;
    },
  };
}

/* -------------------------------------------------------------------------- */
/* Base64 decode (no Node Buffer / browser atob dependency in the core)       */
/* -------------------------------------------------------------------------- */

const B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/** Decode a base64 string to bytes without relying on `atob`/`Buffer`. */
export function decodeBase64(b64: string): Uint8Array {
  const lookup = new Int16Array(256).fill(-1);
  for (let i = 0; i < B64_ALPHABET.length; i++) lookup[B64_ALPHABET.charCodeAt(i)] = i;
  const clean = b64.replace(/[^A-Za-z0-9+/]/g, "");
  const len = clean.length;
  const outLen = Math.floor((len * 3) / 4);
  const out = new Uint8Array(outLen);
  let acc = 0;
  let bits = 0;
  let o = 0;
  for (let i = 0; i < len; i++) {
    const v = lookup[clean.charCodeAt(i)];
    if (v < 0) continue;
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[o++] = (acc >> bits) & 0xff;
    }
  }
  return out.subarray(0, o);
}

/* -------------------------------------------------------------------------- */
/* STATUS.md rendering                                                         */
/* -------------------------------------------------------------------------- */

/** The marker lines the harness uses to find/replace its block in STATUS.md. */
export const STATUS_BLOCK_START = "<!-- SPIKE:browser-web-page:begin -->";
export const STATUS_BLOCK_END = "<!-- SPIKE:browser-web-page:end -->";

/** The packages Requirement 2.1 and the engine's module-load imports need. */
const REPORTED_PACKAGES: ReadonlyArray<keyof PackageLoadResults> = [
  "numpy",
  "scipy",
  "opencv-python",
  "pillow",
  "scikit-image",
];

/** Every classification, in the order the counts line reports them. */
const CLASSIFICATIONS: readonly SvgClassification[] = [
  "byte-identical",
  "within-tolerance",
  "outside-tolerance",
  "missing-browser-svg",
];

/** Make a value safe inside a single Markdown table cell. */
function cell(text: string): string {
  return text.replace(/\r?\n/g, " ").replace(/\|/g, "\\|");
}

/**
 * The informative part of an error message: Pyodide surfaces a whole Python
 * traceback, whose last non-empty line names the exception. Capped so a table
 * row stays readable; the runner's console log keeps the full text.
 */
function errorSummary(message: string): string {
  const lines = message.split(/\r?\n/).map((l) => l.trim()).filter((l) => l.length > 0);
  const last = lines.length > 0 ? lines[lines.length - 1]! : message;
  return last.length > 240 ? `${last.slice(0, 237)}...` : last;
}

/** Seconds with two decimals, or "not run" for a scene that never converted. */
function formatSeconds(seconds: number | undefined): string {
  if (seconds === undefined) return "—";
  return Number.isFinite(seconds) ? seconds.toFixed(2) : "not run";
}

/** The median of a non-empty list of numbers. */
function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2;
}

/** Render the run-setup section: runner facts, runtime versions, commands. */
function renderSetup(report: SpikeReport): string[] {
  const lines: string[] = [];
  if (!report.setup && !report.runtime) return lines;
  lines.push("### Run setup", "");
  if (report.setup && report.setup.facts.length > 0) {
    lines.push("| setting | value |", "|---|---|");
    for (const [label, value] of report.setup.facts) {
      lines.push(`| ${cell(label)} | ${cell(value)} |`);
    }
    lines.push("");
  }
  if (report.runtime) {
    lines.push(
      `Browser runtime as reported by the warm worker: Pyodide ${report.runtime.pyodide}, ` +
        `Python ${report.runtime.python}.`,
      "",
      "| distribution (in Pyodide) | version |",
      "|---|---|",
    );
    for (const [name, version] of Object.entries(report.runtime.versions)) {
      lines.push(`| \`${cell(name)}\` | ${cell(version)} |`);
    }
    lines.push("");
  }
  if (report.setup && report.setup.commands.length > 0) {
    lines.push("Reproduce (from the repository root):", "", "```bash", ...report.setup.commands, "```", "");
  }
  return lines;
}

/**
 * Render the spike report as the Markdown block written into STATUS.md. Records
 * every per-package load result, every per-scene timing, and every per-image SVG
 * classification (task 3.2's three outcome families), the one-time bring-up time,
 * how the run was set up, plus the slowest scene and the worst composite diff so
 * task 4/5 can read the done-definition at a glance. This records measurements
 * only; it does NOT assert the gate (that is task 5).
 */
export function renderStatus(report: SpikeReport): string {
  const pkgNames = [
    ...REPORTED_PACKAGES,
    ...(Object.keys(report.packages) as (keyof PackageLoadResults)[]).filter(
      (name) => !REPORTED_PACKAGES.includes(name),
    ),
  ];
  const pkgRows = pkgNames
    .map((name) => `| \`${name}\` | ${report.packages[name] ?? "not attempted"} |`)
    .join("\n");

  const sceneRows = report.scenes
    .map((s) => {
      const diff = s.compositeDiff === undefined ? "—" : s.compositeDiff.toFixed(4);
      const note = s.error ? ` (${cell(errorSummary(s.error))})` : "";
      return (
        `| ${s.name} | ${formatSeconds(s.seconds)} | ${formatSeconds(s.engineSeconds)} | ` +
        `${s.opencvLoad} | ${s.classification} | ${diff}${note} |`
      );
    })
    .join("\n");

  const timed = report.scenes.filter((s) => Number.isFinite(s.seconds));
  const timingLine =
    timed.length === 0
      ? "Per-scene conversion time: no scene was converted."
      : (() => {
          const seconds = timed.map((s) => s.seconds);
          const slowest = timed.reduce((m, s) => (s.seconds > m.seconds ? s : m));
          return (
            `Per-scene conversion time over ${timed.length} timed scene(s): ` +
            `min **${Math.min(...seconds).toFixed(2)}s**, ` +
            `median **${median(seconds).toFixed(2)}s**, ` +
            `max **${Math.max(...seconds).toFixed(2)}s**. ` +
            `Slowest scene: **${slowest.name}** at **${slowest.seconds.toFixed(2)}s**.`
          );
        })();

  const worst = report.scenes.reduce(
    (m, s) => ((s.compositeDiff ?? 0) > (m.compositeDiff ?? 0) ? s : m),
    { name: "—" } as SceneMeasurement,
  );
  const counts = CLASSIFICATIONS.map(
    (c) => `${c} ${report.scenes.filter((s) => s.classification === c).length}`,
  ).join(", ");
  const failed = report.scenes.filter((s) => s.converted === "fail").length;

  const bringUpLine =
    `Runtime bring-up (one-time \`init\`, timed apart from the scenes): ` +
    `**${report.bringUp.seconds.toFixed(2)}s**` +
    (report.bringUp.error
      ? `, **FAILED**: ${errorSummary(report.bringUp.error)}`
      : ", ready.");

  return [
    STATUS_BLOCK_START,
    "",
    `## Browser web page — Phase 1 spike measurements`,
    "",
    `Corpus: ${report.corpusN} scenes, seed ${report.corpusSeed}. ` +
      `Bakeoff_Tolerance (composite band): ${report.bakeoffTolerance}. ` +
      `These are the raw spike measurements; the done-definition is asserted by task 5.`,
    "",
    ...renderSetup(report),
    "### Package load results (Requirement 2.1)",
    "",
    "A package passes when Pyodide loaded it and its top-level module imported.",
    "",
    "| package | load |",
    "|---|---|",
    pkgRows,
    "",
    bringUpLine,
    "",
    "### Per-scene timings + SVG classification (Requirements 2.2, 2.3)",
    "",
    "`seconds` is the wall-clock time of one convert request on the warm worker " +
      "(`plate.web.convert_bytes`: noise pre-check plus `pipeline.run`); `engine s` " +
      "is the engine's own `stats.t_total` for the same call.",
    "",
    "| scene | seconds | engine s | opencv-python | svg vs CLI | composite diff |",
    "|---|---|---|---|---|---|",
    sceneRows,
    "",
    timingLine,
    "",
    `Classification counts: ${counts}. Scenes that failed to convert: **${failed}**. ` +
      `Largest composite diff: **${worst.name}** (${(worst.compositeDiff ?? 0).toFixed(4)}).`,
    "",
    STATUS_BLOCK_END,
  ].join("\n");
}

/* -------------------------------------------------------------------------- */
/* Harness core                                                                */
/* -------------------------------------------------------------------------- */

export interface RunSpikeArgs {
  runtime: SpikeRuntime;
  io: SpikeIO;
  /** Optional monotonic clock in ms; defaults to a wall clock when available. */
  now?: () => number;
  /** Optional progress log. */
  log?: (message: string) => void;
  /** How the run was set up, recorded verbatim in the STATUS.md block. */
  setup?: SpikeSetup;
}

/**
 * The spike result: the recorded measurements plus the task-3.3 go/no-go verdict.
 * `runSpike` returns this so a runner can halt before Phase 2 when `verdict.halt`
 * is set (the verdict is also recorded inside the STATUS.md spike block).
 */
export interface SpikeOutcome {
  report: SpikeReport;
  verdict: SpikeVerdict;
}

/** A monotonic-ish clock that works in both the browser and Node, with a
 * fallback so the core never depends on a global being present. */
function defaultNow(): number {
  const perf = (globalThis as { performance?: { now(): number } }).performance;
  if (perf && typeof perf.now === "function") return perf.now();
  return Date.now();
}

/**
 * Run the spike end to end against the injected runtime + IO and return the
 * recorded measurements plus the task-3.3 go/no-go verdict (both written into the
 * STATUS.md spike block via `io.writeStatus`).
 *
 * Steps:
 *   1. read the manifest `driver.py prepare` produced;
 *   2. `runtime.init()` once (warm runtime) and capture the package load results;
 *   3. for each of the 24 scenes: convert in the worker, time it in seconds, and
 *      capture the browser SVG (written via `io.writeBrowserSvg`);
 *   4. `io.scoreBrowserSvgs()` (runs `driver.py score`) to classify each SVG;
 *   5. evaluate the task-3.3 decision points (opencv load, per-scene time, SVG
 *      equivalence) and render the measurements + the decision verdict into the
 *      single STATUS.md spike block.
 *
 * A single scene failing to convert is recorded (converted="fail") and does not
 * sink the run, so the spike still records every other scene's numbers; that
 * failure is instead surfaced by the SVG-equivalence decision point as a halt.
 *
 * The one-time `runtime.init()` is timed separately (`report.bringUp`), so each
 * per-scene time covers one conversion on the warm worker only. If bring-up
 * fails, the run is still recorded: the per-package results the worker attached
 * to its error, the bring-up error, and every scene as not converted (no time),
 * which trips the decision points instead of losing the result.
 *
 * HALT behaviour (task 3.3): when any decision point trips, the returned
 * `verdict.halt` is `true` and the STATUS.md block records the spike as NOT MET
 * with the tripped reasons (and, for an opencv-load failure, a named alternative
 * approach). A runner MUST NOT begin any Phase 2 work while `verdict.halt` holds;
 * the formal done-definition gate that unlocks Phases 2/3/4 is task 5.
 */
export async function runSpike(args: RunSpikeArgs): Promise<SpikeOutcome> {
  const { runtime, io } = args;
  const now = args.now ?? defaultNow;
  const log = args.log ?? (() => {});

  const manifest = await io.readManifest();
  log(`loaded manifest: ${manifest.scenes.length} scenes, seed ${manifest.corpusSeed}`);

  // One-time bring-up, timed apart from the scenes so that every per-scene time
  // measures a conversion on the warm worker only.
  let packages: Partial<PackageLoadResults> = {};
  let bringUpError: string | undefined;
  const tInit = now();
  try {
    packages = await runtime.init();
  } catch (err) {
    bringUpError = err instanceof Error ? err.message : String(err);
    if (err instanceof SpikeInitError && err.packages !== undefined) packages = err.packages;
  }
  const bringUp: BringUpMeasurement = { seconds: (now() - tInit) / 1000 };
  if (bringUpError !== undefined) bringUp.error = bringUpError;
  const opencvLoad: PackageLoadRecord = packages["opencv-python"] ?? "not attempted";
  if (bringUpError === undefined) {
    log(`runtime ready in ${bringUp.seconds.toFixed(2)}s; opencv-python load=${opencvLoad}`);
  } else {
    log(`runtime bring-up FAILED after ${bringUp.seconds.toFixed(2)}s — ${bringUpError}`);
  }

  const measurements: SceneMeasurement[] = [];
  for (const scene of manifest.scenes) {
    if (bringUpError !== undefined) {
      // Never converted: no time was measured, so none is recorded.
      measurements.push({
        name: scene.name,
        seconds: Number.NaN,
        converted: "fail",
        opencvLoad,
        classification: "missing-browser-svg",
        error: "not converted: runtime bring-up failed",
        cliComposite: scene.cliComposite,
      });
      continue;
    }
    const bytes = decodeBase64(scene.imageBytesB64);
    const t0 = now();
    try {
      const result = await runtime.convert(bytes, scene.filename);
      const seconds = (now() - t0) / 1000;
      await io.writeBrowserSvg(scene.name, result.svg);
      const measurement: SceneMeasurement = {
        name: scene.name,
        seconds,
        converted: "pass",
        opencvLoad,
        classification: "missing-browser-svg", // replaced after scoring
        cliComposite: scene.cliComposite,
      };
      const engineSeconds = result.stats?.["t_total"];
      if (typeof engineSeconds === "number" && Number.isFinite(engineSeconds)) {
        measurement.engineSeconds = engineSeconds;
      }
      measurements.push(measurement);
      log(`${scene.name}: converted in ${seconds.toFixed(2)}s`);
    } catch (err) {
      const seconds = (now() - t0) / 1000;
      const message = err instanceof Error ? err.message : String(err);
      measurements.push({
        name: scene.name,
        seconds,
        converted: "fail",
        opencvLoad,
        classification: "missing-browser-svg",
        error: message,
        cliComposite: scene.cliComposite,
      });
      log(`${scene.name}: FAILED after ${seconds.toFixed(2)}s — ${message}`);
    }
  }

  // Classify in CPython (bakeoff/score.py); fold the result back per scene.
  const classification = await io.scoreBrowserSvgs();
  const byName = new Map(classification.scenes.map((c) => [c.name, c]));
  for (const m of measurements) {
    const c = byName.get(m.name);
    if (c) {
      m.classification = c.classification;
      if (c.browserComposite !== undefined) m.browserComposite = c.browserComposite;
      if (c.compositeDiff !== undefined) m.compositeDiff = c.compositeDiff;
    }
  }

  const report: SpikeReport = {
    corpusN: manifest.corpusN,
    corpusSeed: manifest.corpusSeed,
    bakeoffTolerance: classification.bakeoffTolerance,
    packages,
    bringUp,
    scenes: measurements,
  };
  const runtimeInfo = runtime.runtimeInfo?.();
  if (runtimeInfo !== undefined) report.runtime = runtimeInfo;
  if (args.setup !== undefined) report.setup = args.setup;

  // Task 3.3: evaluate the decision points and fold the verdict into the same
  // STATUS.md spike block as the measurements, so the halt is recorded alongside
  // the numbers it was derived from.
  const verdict = evaluateVerdict(report);
  const statusBlock = appendDecisionToStatusBlock(
    renderStatus(report),
    renderDecision(verdict),
  );
  await io.writeStatus(statusBlock);
  log("wrote spike measurements + decision verdict to STATUS.md");

  if (verdict.halt) {
    const points = verdict.reasons.map((r) => r.point).join(", ");
    log(`SPIKE NOT MET — HALT before Phase 2 (tripped: ${points})`);
  } else {
    log("spike decision points cleared (task 5 asserts the formal gate)");
  }

  return { report, verdict };
}
