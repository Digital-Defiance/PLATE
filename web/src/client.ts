/**
 * PlateClient — the main-thread wrapper around the PLATE Conversion_Worker.
 *
 * This is the Browser_Shell's only door to the engine. The main thread never
 * runs CPU-heavy work (Property 5: non-blocking main thread); PlateClient only
 * posts messages to the Web Worker and resolves promises off the worker's
 * replies. The worker (web/src/worker.ts) boots Pyodide, installs the unchanged
 * PLATE wheel and calls `plate.web.convert_bytes`; this class knows nothing
 * about Pyodide — it speaks only the typed message protocol in `./protocol.ts`.
 *
 * Protocol (imported, never redefined — see `./protocol.ts`):
 *   - `init()` posts `{type:"init"}` and resolves on the worker's `ready`
 *     message (which carries the per-package load results + runtime info). A
 *     bring-up `error` (no `id`) rejects it.
 *   - `convert()` posts `{type:"convert", id, request}` with a fresh id and
 *     resolves on the matching `result` (same id) or rejects on the matching
 *     `error` (same id). Request/response correlation is by that `id` field.
 *   - `onProgress()` registers a callback fed every `progress` event (stage +
 *     pct, with the optional request id so the UI can attribute per-conversion
 *     progress vs one-time bring-up).
 *
 * MODULE WORKER: Pyodide 314 refuses classic workers, so the default worker
 * factory creates an ES-module worker (`new Worker(url, { type: "module" })`).
 * The factory is injectable so tests can supply a fake worker (task 6.2) and so
 * the bundler can hand in a built worker URL without this file hard-coding it.
 */

import type {
  ConvertRequest,
  ConvertResult,
  PackageLoadResults,
  ProgressUpdate,
  RuntimeInfo,
  WorkerIn,
  WorkerOut,
} from "./protocol.js";

/**
 * The slice of the DOM `Worker` API PlateClient uses. Narrowing to this keeps
 * the client testable: task 6.2 supplies a fake implementing exactly these
 * members, and the production default (a real module `Worker`) satisfies it.
 */
export interface WorkerLike {
  postMessage(message: WorkerIn, transfer?: Transferable[]): void;
  addEventListener(
    type: "message",
    listener: (event: MessageEvent<WorkerOut>) => void,
  ): void;
  addEventListener(type: "error", listener: (event: ErrorEvent) => void): void;
  removeEventListener(
    type: "message",
    listener: (event: MessageEvent<WorkerOut>) => void,
  ): void;
  terminate(): void;
}

/** A listener fed every `progress` event the worker posts. */
export type ProgressListener = (event: ProgressUpdate) => void;

/** How `PlateClient` makes its worker; injectable for tests and bundlers. */
export type WorkerFactory = () => WorkerLike;

/** What `init()` resolves with: the ready runtime's package + version report. */
export interface PlateReady {
  packages: PackageLoadResults;
  runtime?: RuntimeInfo;
}

/**
 * A conversion (or bring-up) failure surfaced to the caller. `recoverable`
 * marks a decode/input error the user can retry with a different file without a
 * reload (vs a non-recoverable runtime/package failure); `packages` carries the
 * per-package load results when a bring-up failure recorded them.
 */
export class PlateClientError extends Error {
  readonly recoverable: boolean;
  readonly packages: PackageLoadResults | undefined;

  constructor(
    message: string,
    options: { recoverable?: boolean; packages?: PackageLoadResults } = {},
  ) {
    super(message);
    this.name = "PlateClientError";
    this.recoverable = options.recoverable ?? false;
    this.packages = options.packages;
  }
}

/**
 * The default module-worker factory. Resolves the worker bundle relative to
 * this module's own URL so it works wherever GitHub Pages serves the shell. The
 * deploy build emits the worker next to this module as `worker.js`.
 */
declare const __PLATE_WORKER_URL__: string | undefined;

function defaultWorkerFactory(): WorkerLike {
  // `import.meta.url` resolves against the served module, not the page, so the
  // worker URL is correct under any Pages sub-path.
  const workerFile = typeof __PLATE_WORKER_URL__ === "undefined" ? "./worker.js" : __PLATE_WORKER_URL__;
  const url = new URL(workerFile, import.meta.url);
  // { type: "module" } is required — Pyodide 314 refuses classic workers.
  return new Worker(url, { type: "module" }) as unknown as WorkerLike;
}

/** A monotonic id source correlating convert requests with their replies. */
function makeIdSource(): () => string {
  let n = 0;
  return () => `convert-${++n}`;
}

/**
 * Main-thread wrapper around the Conversion_Worker. Construct it, register a
 * progress listener, `await init()` once to warm the runtime, then `convert()`
 * each accepted image. The worker stays warm, so a second `convert` skips
 * load/install (Requirement 5.5).
 */
export class PlateClient {
  private readonly factory: WorkerFactory;
  private worker: WorkerLike | null = null;
  private readonly nextId = makeIdSource();
  private readonly progressListeners = new Set<ProgressListener>();

  /** One-time bring-up, shared so concurrent callers don't double-init. */
  private initPromise: Promise<PlateReady> | null = null;

  /**
   * Pending convert requests keyed by id, so the single message listener can
   * route each `result`/`error` back to the right promise.
   */
  private readonly pending = new Map<
    string,
    { resolve: (r: ConvertResult) => void; reject: (e: PlateClientError) => void }
  >();

  /** Resolver for the in-flight `init()` (settled by `ready` or a bring-up error). */
  private initResolve: ((r: PlateReady) => void) | null = null;
  private initReject: ((e: PlateClientError) => void) | null = null;

  constructor(factory: WorkerFactory = defaultWorkerFactory) {
    this.factory = factory;
  }

  /**
   * Register a progress listener. Returns an unsubscribe function. Progress
   * events carry the pipeline `stage`, a 0–100 `pct`, and — for a conversion —
   * the request `id` (absent for one-time bring-up), so the UI can show a
   * first-load staged bar separately from per-conversion progress.
   */
  onProgress(listener: ProgressListener): () => void {
    this.progressListeners.add(listener);
    return () => {
      this.progressListeners.delete(listener);
    };
  }

  /**
   * Spin up the worker (if not already) and warm the Pyodide runtime. Resolves
   * once the worker posts `ready` (carrying package load results + runtime
   * info); rejects if bring-up fails. Idempotent: concurrent or repeated calls
   * share the one bring-up instead of racing to load Pyodide twice.
   */
  init(): Promise<PlateReady> {
    if (this.initPromise) return this.initPromise;

    const worker = this.ensureWorker();
    this.initPromise = new Promise<PlateReady>((resolve, reject) => {
      this.initResolve = resolve;
      this.initReject = reject;
      worker.postMessage({ type: "init" });
    });

    // A failed bring-up clears the cached promise so a later init() can retry
    // rather than permanently resolving to the rejected attempt.
    this.initPromise.catch(() => {
      this.initPromise = null;
    });

    return this.initPromise;
  }

  /**
   * Convert one accepted image. Ensures the runtime is warm (calling `init()`
   * if the caller did not), posts the request with a fresh correlation id,
   * transfers the image bytes to the worker (not copied — the main thread does
   * no heavy work), and resolves on the matching `result` or rejects on the
   * matching `error`.
   */
  async convert(request: ConvertRequest): Promise<ConvertResult> {
    // Warm the runtime first; a bring-up failure surfaces here as a rejection.
    await this.init();
    const worker = this.ensureWorker();

    const id = this.nextId();
    const done = new Promise<ConvertResult>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });

    const message: WorkerIn = { type: "convert", id, request };
    // Transfer the underlying buffer so no copy crosses the worker boundary.
    worker.postMessage(message, [request.imageBytes.buffer]);
    return done;
  }

  /**
   * Terminate the worker and reject every outstanding request. After this the
   * client can be re-`init()`ed (a fresh worker is created on demand).
   */
  dispose(): void {
    const worker = this.worker;
    this.worker = null;
    this.initPromise = null;

    const err = new PlateClientError("PlateClient disposed", { recoverable: false });
    this.rejectInit(err);
    for (const [, waiter] of this.pending) waiter.reject(err);
    this.pending.clear();

    if (worker) worker.terminate();
  }

  /* ---------------------------------------------------------------------- */
  /* Internals                                                               */
  /* ---------------------------------------------------------------------- */

  private ensureWorker(): WorkerLike {
    if (this.worker) return this.worker;
    const worker = this.factory();
    worker.addEventListener("message", this.onMessage);
    worker.addEventListener("error", this.onWorkerError);
    this.worker = worker;
    return worker;
  }

  /**
   * The single `message` handler. Routes each `WorkerOut` by type: `progress`
   * fans out to listeners; `ready` settles `init()`; `result`/`error` settle
   * the pending request their `id` names (or, for an id-less bring-up `error`,
   * settle `init()`).
   */
  private readonly onMessage = (event: MessageEvent<WorkerOut>): void => {
    const out = event.data;
    switch (out.type) {
      case "progress": {
        const progress: ProgressUpdate =
          out.id !== undefined
            ? out.note !== undefined
              ? { stage: out.stage, pct: out.pct, id: out.id, note: out.note }
              : { stage: out.stage, pct: out.pct, id: out.id }
            : out.note !== undefined
              ? { stage: out.stage, pct: out.pct, note: out.note }
              : { stage: out.stage, pct: out.pct };
        for (const listener of this.progressListeners) listener(progress);
        break;
      }
      case "ready": {
        const ready: PlateReady =
          out.runtime !== undefined
            ? { packages: out.packages, runtime: out.runtime }
            : { packages: out.packages };
        this.resolveInit(ready);
        break;
      }
      case "result": {
        const waiter = this.pending.get(out.id);
        if (waiter) {
          this.pending.delete(out.id);
          waiter.resolve(out.result);
        }
        break;
      }
      case "error": {
        const err = new PlateClientError(out.message, {
          recoverable: out.recoverable,
          ...(out.packages !== undefined ? { packages: out.packages } : {}),
        });
        if (out.id === undefined) {
          // An id-less error is a one-time bring-up failure.
          this.rejectInit(err);
        } else {
          const waiter = this.pending.get(out.id);
          if (waiter) {
            this.pending.delete(out.id);
            waiter.reject(err);
          }
        }
        break;
      }
      default: {
        // Exhaustiveness guard: a new WorkerOut variant must be handled here.
        const _never: never = out;
        void _never;
      }
    }
  };

  /**
   * A worker-level `error` (the module script failing to load, or an uncaught
   * throw at top level) never produces a protocol message, so it would hang
   * every pending promise. Convert it into a non-recoverable rejection of the
   * in-flight bring-up and of all pending conversions.
   */
  private readonly onWorkerError = (event: ErrorEvent): void => {
    const err = new PlateClientError(
      `worker error: ${event.message || "script failed to load"}`,
      { recoverable: false },
    );
    this.rejectInit(err);
    for (const [, waiter] of this.pending) waiter.reject(err);
    this.pending.clear();
  };

  private resolveInit(ready: PlateReady): void {
    const resolve = this.initResolve;
    this.initResolve = null;
    this.initReject = null;
    if (resolve) resolve(ready);
  }

  private rejectInit(err: PlateClientError): void {
    const reject = this.initReject;
    this.initResolve = null;
    this.initReject = null;
    if (reject) reject(err);
  }
}
