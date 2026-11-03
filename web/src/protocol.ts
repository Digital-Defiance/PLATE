/**
 * Shared worker message protocol for PLATE in the browser.
 *
 * The UI shell (main thread) and the Conversion_Worker exchange exactly these
 * messages. This module is the single source of truth for the protocol so the
 * worker (this task), the `PlateClient` wrapper (task 6.1) and the staged
 * `convert` handler (task 8.1) all agree on the shapes.
 *
 * The engine itself is never touched: the worker boots Pyodide, installs the
 * unchanged PLATE wheel and calls `plate.web.convert_bytes` / `check_noise`,
 * which return the JSON-serialisable dicts defined in `src/plate/web.py`.
 */

/**
 * Coarse pipeline stages the worker reports progress through, in order.
 *
 * The first four cover one-time runtime bring-up (`ensureRuntime`); the middle
 * four mirror the engine's pipeline phases (`pipeline.run`); `done` marks the
 * end of a stage sequence. Progress for `segment`/`order`/`trace`/`emit` is
 * emitted by the staged `convert` handler (task 8.1); this task (3.1) emits the
 * bring-up stages from `ensureRuntime`.
 */
export type Stage =
  | "load-pyodide"
  | "load-packages"
  | "install-plate"
  | "import"
  | "segment"
  | "order"
  | "trace"
  | "emit"
  | "done";

/**
 * Mirror of `plate.web.convert_bytes`'s `stats` dict, which is `Result.stats`
 * returned verbatim (`src/plate/web.py` copies it key-for-key; see
 * `pipeline.run` in `src/plate/pipeline.py` for where it is built).
 *
 * KEYS ARE snake_case, matching the engine exactly. The worker converts the
 * Python dict straight to a JS object, so the runtime keys are the engine's own
 * `shapes`/`t_total`/`vlm_names` (snake_case), NOT camelCase. Property 1 (thin
 * shell / source of truth) requires the shell to mirror the engine faithfully,
 * so the protocol names what the glue actually returns rather than renaming it.
 * `rescued`/`absorbed`/`reconnected` are present only when `cfg.rescue_detail`
 * is on (optional here), so every lever combination type-checks.
 */
export interface ConvertStats {
  shapes: number;
  completed: number;
  anchors: number;
  primitives: number;
  gradients: number;
  strokes: number;
  t_segment: number;
  t_order: number;
  t_trace: number;
  t_total: number;
  vlm_names: number;
  /** Present only when `cfg.rescue_detail` is enabled. */
  rescued?: number;
  absorbed?: number;
  reconnected?: number;
  /** Allow extra engine-reported stat keys without losing type-safety on the known ones. */
  [key: string]: number | undefined;
}

/** A layer/group/object in the output hierarchy; order is local to its siblings. */
export interface LayerInfo {
  name: string;
  kind: "layer" | "group" | "shape";
  order: number;
  /** Actual group contents; optional for leaves and older flat summaries. */
  children?: LayerInfo[];
}

/** The JSON-serialisable result dict `plate.web.convert_bytes` returns. */
export interface ConvertResult {
  svg: string;
  stats: ConvertStats;
  layers: LayerInfo[];
  warnings: string[];
}

/**
 * The UI settings subset the shell sends and the glue maps onto `Config` levers
 * (see `PlateConfig` in the design and `LEVER_MAP` in `src/plate/web.py`). Only
 * this curated subset is user-facing; everything else keeps engine defaults.
 */
export interface PlateConfig {
  preset?: "logo" | "illustration" | "lineart" | "compact" | "smooth" | "max";
  /** Source-detail analysis scale, bounded to 1–2 by the browser glue. */
  upscale?: number;
  maxColors?: number;
  simplify?: number;
  smooth?: number;
  workSize?: number;
  snapPrimitives?: boolean;
  strokes?: boolean;
  gradients?: boolean;
  removeBackground?: boolean;
  /** Advanced, off by default: empty/whitespace leaves LM Studio naming disabled. */
  vlmUrl?: string;
  vlmModel?: string;
}

/** A single conversion request's payload (image bytes + filename + settings). */
export interface ConvertRequest {
  /** Raw file bytes, transferred (not copied) to the worker. */
  imageBytes: Uint8Array;
  /** Original filename; its extension selects the MEMFS `/input.<ext>` path. */
  filename: string;
  /** UI settings mapped to a subset of engine `Config` levers. */
  config: PlateConfig;
}

/**
 * A progress update the `PlateClient` hands to an `onProgress` listener: the
 * payload of a `progress` message without the `type` tag. It carries the
 * pipeline `stage`, a 0–100 `pct`, the optional request `id` (present for a
 * conversion, absent for one-time runtime bring-up) and an optional human note.
 *
 * Named `ProgressUpdate` (not `ProgressEvent`) deliberately: `ProgressEvent` is
 * a DOM lib global, and shadowing it invites confusion. The design's
 * `onProgress(cb: (p: ProgressEvent) => void)` maps onto this payload type.
 */
export interface ProgressUpdate {
  stage: Stage;
  pct: number;
  id?: string;
  note?: string;
}

/** Messages the main thread posts *to* the worker. */
export type WorkerIn =
  | { type: "init" }
  | { type: "convert"; id: string; request: ConvertRequest };

/** Messages the worker posts *back* to the main thread. */
export type WorkerOut =
  | { type: "ready"; packages: PackageLoadResults; runtime?: RuntimeInfo }
  | { type: "progress"; id?: string; stage: Stage; pct: number; note?: string }
  | { type: "result"; id: string; result: ConvertResult }
  | {
      type: "error";
      id?: string;
      message: string;
      recoverable: boolean;
      /**
       * Set on a runtime bring-up failure: the per-package load results recorded
       * before bring-up stopped, so a package failure can still be recorded.
       */
      packages?: PackageLoadResults;
    };

/** Per-package load outcome recorded during `ensureRuntime` (spike needs this). */
export type PackageLoadResult = "pass" | "fail";

/**
 * Load result for each scientific package the engine imports at module load.
 * `numpy`, `scipy` and `opencv-python` are the packages Requirement 2.1 names
 * (`opencv-python` is the top unverified risk and the spike's first gate). The
 * engine also imports Pillow (`imageio.py`) and scikit-image (`geometry.py`) at
 * module load, so those are required too. A result is `pass` only when the
 * package loaded and its top-level module imported.
 */
export interface PackageLoadResults {
  numpy: PackageLoadResult;
  scipy: PackageLoadResult;
  "opencv-python": PackageLoadResult;
  pillow: PackageLoadResult;
  "scikit-image": PackageLoadResult;
}

/**
 * What the warm runtime actually is, reported once on `ready`: the Pyodide and
 * Python versions plus the installed distribution versions (for example
 * `numpy`, `opencv-python`, `plate-svg`). The spike records this next to its
 * measurements so a CLI/browser difference can be traced to library versions.
 */
export interface RuntimeInfo {
  pyodide: string;
  python: string;
  /** Distribution name -> installed version, as `importlib.metadata` reports it. */
  versions: Record<string, string>;
}
