/**
 * Browser-page side of the spike runner (`run.ts`).
 *
 * `run.ts` serves this bundle with the worker and the PLATE wheel, opens it in
 * headless Chromium, and exposes the filesystem/scorer operations as page
 * functions (Playwright `exposeFunction`). This module wires them into the
 * unchanged harness: the task-3.1 worker behind `workerRuntime`, a `SpikeIO`
 * backed by those page functions, and `runSpike`, so every timing is taken in
 * the page around a request to the warm worker.
 */

import type { Classification, Manifest, SpikeIO, SpikeOutcome, SpikeRuntime, SpikeSetup } from "./measure.js";
import { runSpike, workerRuntime } from "./measure.js";

/** The functions `run.ts` exposes on `window`, plus the entry point it calls. */
export interface SpikePageBridge {
  __spikeReadManifest(): Promise<Manifest>;
  __spikeWriteBrowserSvg(name: string, svg: string): Promise<void>;
  __spikeScore(): Promise<Classification>;
  __spikeWriteStatus(markdown: string): Promise<void>;
  __spikeLog(message: string): Promise<void>;
  __plateRunSpike?: (setup: SpikeSetup) => Promise<SpikeOutcome>;
}

const bridge = window as unknown as SpikePageBridge;

/**
 * Wrap a runtime so a worker-level failure (the module script failing to load
 * or throwing at top level) rejects the pending request instead of hanging.
 */
function failOnWorkerError(base: SpikeRuntime, worker: Worker): SpikeRuntime {
  const failed = new Promise<never>((_, reject) => {
    worker.addEventListener("error", (event) => {
      reject(new Error(`worker error: ${event.message || "script failed to load"}`));
    });
  });
  failed.catch(() => {}); // observed via the races below
  const wrapped: SpikeRuntime = {
    init: () => Promise.race([base.init(), failed]),
    convert: (bytes, filename) => Promise.race([base.convert(bytes, filename), failed]),
  };
  if (base.runtimeInfo) {
    const info = base.runtimeInfo.bind(base);
    wrapped.runtimeInfo = () => info();
  }
  return wrapped;
}

bridge.__plateRunSpike = async (setup: SpikeSetup): Promise<SpikeOutcome> => {
  const log = (message: string): void => {
    void bridge.__spikeLog(message);
  };
  // Pyodide 314 only runs in module workers.
  const worker = new Worker(new URL("./worker.js", location.href), { type: "module" });
  const runtime = failOnWorkerError(
    workerRuntime(worker, (stage, pct, id) => {
      if (id === undefined) log(`bring-up: ${stage} ${pct}%`);
    }),
    worker,
  );
  const io: SpikeIO = {
    readManifest: () => bridge.__spikeReadManifest(),
    writeBrowserSvg: (name, svg) => bridge.__spikeWriteBrowserSvg(name, svg),
    scoreBrowserSvgs: () => bridge.__spikeScore(),
    writeStatus: (markdown) => bridge.__spikeWriteStatus(markdown),
  };
  try {
    return await runSpike({ runtime, io, setup, log });
  } finally {
    worker.terminate();
  }
};
