/**
 * Unit tests for the WORKER HANDLER's staging + result/error exclusivity
 * contract (task 8.2).
 *
 * Scope: the REAL `handleConvert` / `ensureRuntime` in web/src/worker.ts, driven
 * through the exported `createWorkerHandlers({ post, bootstrap })` factory with a
 * FAKE Pyodide runtime (stubbed `toPy`/`toBytes`/`convert_bytes` + a captured
 * `post`). This exercises the worker's own code path — the order it emits stages,
 * the single result-xor-error it posts, and how it classifies failures — rather
 * than a re-encoded mock of that behaviour.
 *
 * WHY this is NOT a duplicate of task 6.2 (spike/protocol.test.ts): that suite
 * drives the real `PlateClient` against a `ProtocolWorker` MOCK that *replays* a
 * hand-encoded copy of the worker's sequence, so it pins the id-correlation /
 * progress-dispatch / serialization CONTRACT the two boundary sides agree on. It
 * cannot catch a bug in the worker's actual staging/exclusivity logic because
 * that logic is the thing it re-encodes. Task 8.2's distinct angle is the worker
 * HANDLER itself: here the sequence and the "exactly one result OR one error,
 * never both, per id" invariant are *observed outputs* of the real
 * `handleConvert`, and the recoverable-vs-non-recoverable classification is
 * exercised exhaustively across the failure kinds. Together: 6.2 fixes the wire
 * contract; 8.2 proves the worker produces it.
 *
 * To make worker.ts importable under plain Node (it references `self` and does a
 * runtime `import()` of `pyodide.mjs` only inside the browser-only bootstrap and
 * the `self`-guarded shell), task 8.2 made a minimal, additive refactor: the
 * handlers live in the pure `createWorkerHandlers` factory with the Pyodide I/O
 * injected as a `RuntimeBootstrap`. No engine code changed; all prior web tests
 * stay green.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type {
  ConvertRequest,
  ConvertResult,
  ConvertStats,
  LayerInfo,
  PackageLoadResults,
  RuntimeInfo,
  WorkerOut,
} from "../src/protocol.js";
import {
  createWorkerHandlers,
  type Runtime,
  type RuntimeBootstrap,
} from "../src/worker.js";

/* -------------------------------------------------------------------------- */
/* Fixtures                                                                    */
/* -------------------------------------------------------------------------- */

const allPass: PackageLoadResults = {
  numpy: "pass",
  scipy: "pass",
  "opencv-python": "pass",
  pillow: "pass",
  "scikit-image": "pass",
};

const runtimeInfo: RuntimeInfo = {
  pyodide: "314.0.7",
  python: "3.14.2",
  versions: { numpy: "2.4.6", "opencv-python": "4.11.0.86", "plate-svg": "0.1.0" },
};

function makeStats(over: Partial<ConvertStats> = {}): ConvertStats {
  return {
    shapes: 3,
    completed: 1,
    anchors: 42,
    primitives: 2,
    gradients: 0,
    strokes: 0,
    t_segment: 0.111,
    t_order: 0.022,
    t_trace: 0.333,
    t_total: 0.5,
    vlm_names: 0,
    ...over,
  };
}

function makeResult(over: Partial<ConvertResult> = {}): ConvertResult {
  const layers: LayerInfo[] = [
    { name: "background", kind: "layer", order: 0 },
    { name: "red circle", kind: "shape", order: 1 },
  ];
  return { svg: "<svg/>", stats: makeStats(), layers, warnings: [], ...over };
}

function makeRequest(bytes = new Uint8Array([1, 2, 3, 4])): ConvertRequest {
  return { imageBytes: bytes, filename: "logo.png", config: { preset: "logo", maxColors: 8 } };
}

/* -------------------------------------------------------------------------- */
/* Fake Pyodide runtime + bootstrap                                            */
/* -------------------------------------------------------------------------- */

/** A disposable proxy that records whether the worker released it. */
class FakeProxy {
  destroyed = false;
  destroy(): void {
    this.destroyed = true;
  }
}

/** A result proxy whose `toJs` yields a plain JS result (or throws). */
class FakeResultProxy extends FakeProxy {
  constructor(private readonly value: ConvertResult) {
    super();
  }
  toJs(): unknown {
    return this.value;
  }
}

/**
 * A fake `Runtime`: `convert_bytes` is scripted to either return a result proxy
 * or throw (with a chosen message), and every proxy it hands out is tracked so
 * the test can assert the worker released its Python objects.
 */
class FakeRuntime implements Runtime {
  readonly proxies: FakeProxy[] = [];
  convertCalls = 0;
  /** Set to make the NEXT convert_bytes throw this message instead of returning. */
  throwMessage: string | null = null;
  /** The result the next successful convert_bytes yields. */
  nextResult: ConvertResult = makeResult();

  packages = allPass;
  info = runtimeInfo;

  toPy(value: unknown): unknown {
    const p = new FakeProxy();
    this.proxies.push(p);
    // Return a disposable proxy standing in for the Python dict `overrides`.
    return Object.assign(p, { _value: value });
  }

  toBytes(_buffer: Uint8Array): FakeProxy {
    const p = new FakeProxy();
    this.proxies.push(p);
    return p;
  }

  plateWeb = {
    convert_bytes: (_data: unknown, _filename: string, _overrides: unknown): FakeResultProxy => {
      this.convertCalls += 1;
      if (this.throwMessage !== null) {
        const message = this.throwMessage;
        this.throwMessage = null;
        throw new Error(message);
      }
      const proxy = new FakeResultProxy(this.nextResult);
      this.proxies.push(proxy);
      return proxy;
    },
  };
}

/**
 * A fake `RuntimeBootstrap` that records which staged steps ran and can fail a
 * chosen step. `loadPackages` returns `allPass` unless `packageFailures` is set.
 * It hands back a provided `FakeRuntime` from `importGlue`.
 */
class FakeBootstrap implements RuntimeBootstrap {
  readonly steps: string[] = [];
  packageFailures: string[] = [];
  packages: PackageLoadResults = allPass;
  /** Set to throw from `importGlue` (simulating an engine import failure). */
  importError: string | null = null;

  constructor(private readonly runtime: FakeRuntime) {}

  async loadPyodide(): Promise<void> {
    this.steps.push("loadPyodide");
  }

  async loadPackages(): Promise<{ packages: PackageLoadResults; failures: string[] }> {
    this.steps.push("loadPackages");
    return { packages: this.packages, failures: this.packageFailures };
  }

  async installPlate(): Promise<void> {
    this.steps.push("installPlate");
  }

  async importGlue(): Promise<Runtime> {
    this.steps.push("importGlue");
    if (this.importError !== null) throw new Error(this.importError);
    return this.runtime;
  }
}

/** Build a wired-up harness: real handlers over a captured `post` + fakes. */
function harness(runtime = new FakeRuntime()): {
  posts: WorkerOut[];
  runtime: FakeRuntime;
  bootstrap: FakeBootstrap;
  handlers: ReturnType<typeof createWorkerHandlers>;
} {
  const posts: WorkerOut[] = [];
  const bootstrap = new FakeBootstrap(runtime);
  const handlers = createWorkerHandlers({ post: (m) => posts.push(m), bootstrap });
  return { posts, runtime, bootstrap, handlers };
}

/** The ordered (stage, id) pairs of every `progress` message posted. */
function stageSeq(posts: WorkerOut[]): Array<[string, string | undefined]> {
  return posts
    .filter((m): m is Extract<WorkerOut, { type: "progress" }> => m.type === "progress")
    .map((m) => [m.stage, m.id]);
}

/* -------------------------------------------------------------------------- */
/* (a) Staged progress ordering as the worker produces it                      */
/* -------------------------------------------------------------------------- */

test("cold-start convert emits the full ladder in order, all tagged with the request id, then one result", async () => {
  const { posts, handlers } = harness();

  await handlers.handleConvert("convert-1", makeRequest());

  // load-pyodide → load-packages → install-plate → import (bring-up ladder,
  // NO `done` mid-sequence) then segment → order → trace → emit — the exact
  // order Requirement 5.2 names, every event carrying the request id.
  assert.deepEqual(stageSeq(posts), [
    ["load-pyodide", "convert-1"],
    ["load-packages", "convert-1"],
    ["install-plate", "convert-1"],
    ["import", "convert-1"],
    ["segment", "convert-1"],
    ["order", "convert-1"],
    ["trace", "convert-1"],
    ["emit", "convert-1"],
  ]);
  // No `done` is injected on a conversion cold start (it would break the order).
  assert.ok(!posts.some((m) => m.type === "progress" && m.stage === "done"));
  // Exactly one result, carrying the id.
  const results = posts.filter((m) => m.type === "result");
  assert.equal(results.length, 1);
  assert.equal(results[0]!.type === "result" && results[0]!.id, "convert-1");
});

test("warm-runtime convert re-emits NONE of the bring-up stages, only segment→order→trace→emit (Requirement 5.5)", async () => {
  const { posts, bootstrap, handlers } = harness();

  // First convert warms the runtime (and runs the bring-up steps once).
  await handlers.handleConvert("convert-1", makeRequest());
  const afterFirst = posts.length;
  assert.deepEqual(bootstrap.steps, ["loadPyodide", "loadPackages", "installPlate", "importGlue"]);

  // Second convert on the warm runtime.
  await handlers.handleConvert("convert-2", makeRequest());

  // The bootstrap steps did NOT run again — the runtime is reused.
  assert.deepEqual(bootstrap.steps, ["loadPyodide", "loadPackages", "installPlate", "importGlue"]);
  // The second convert emitted only the four pipeline stages, all under its id.
  assert.deepEqual(stageSeq(posts.slice(afterFirst)), [
    ["segment", "convert-2"],
    ["order", "convert-2"],
    ["trace", "convert-2"],
    ["emit", "convert-2"],
  ]);
});

test("standalone init emits the id-less ladder ending in `done`, then ready — and warms the runtime for a later convert", async () => {
  const { posts, bootstrap, handlers } = harness();

  await handlers.handleInit();

  // init's ladder is id-less and DOES terminate with `done` (no conversion
  // follows), then `ready`.
  assert.deepEqual(stageSeq(posts), [
    ["load-pyodide", undefined],
    ["load-packages", undefined],
    ["install-plate", undefined],
    ["import", undefined],
    ["done", undefined],
  ]);
  const ready = posts.filter((m) => m.type === "ready");
  assert.equal(ready.length, 1);
  assert.equal(ready[0]!.type === "ready" && ready[0]!.runtime?.pyodide, "314.0.7");

  // A convert after init reuses the warm runtime: no bring-up steps re-run and
  // no bring-up stages re-emit (Requirement 5.5).
  const afterInit = posts.length;
  await handlers.handleConvert("convert-1", makeRequest());
  assert.deepEqual(bootstrap.steps, ["loadPyodide", "loadPackages", "installPlate", "importGlue"]);
  assert.deepEqual(stageSeq(posts.slice(afterInit)), [
    ["segment", "convert-1"],
    ["order", "convert-1"],
    ["trace", "convert-1"],
    ["emit", "convert-1"],
  ]);
});

/* -------------------------------------------------------------------------- */
/* (b) Exactly ONE result OR ONE error per request id — never both             */
/* -------------------------------------------------------------------------- */

/** Count the result/error terminal messages the worker posted for `id`. */
function terminals(posts: WorkerOut[], id: string): { results: number; errors: number } {
  let results = 0;
  let errors = 0;
  for (const m of posts) {
    if (m.type === "result" && m.id === id) results += 1;
    if (m.type === "error" && m.id === id) errors += 1;
  }
  return { results, errors };
}

test("a successful convert posts exactly one result and zero errors for its id", async () => {
  const { posts, handlers } = harness();
  await handlers.handleConvert("convert-1", makeRequest());
  assert.deepEqual(terminals(posts, "convert-1"), { results: 1, errors: 0 });
});

test("a convert whose convert_bytes throws posts exactly one error and ZERO results for its id", async () => {
  const runtime = new FakeRuntime();
  runtime.throwMessage = "ImageLoadError: cannot identify image file";
  const { posts, handlers } = harness(runtime);

  await handlers.handleConvert("convert-1", makeRequest());

  // The `segment` marker fired before the throw, but no `result` follows — only
  // one `error`. This is the result-xor-error invariant: never both.
  assert.deepEqual(terminals(posts, "convert-1"), { results: 0, errors: 1 });
  assert.ok(
    posts.some((m) => m.type === "progress" && m.stage === "segment"),
    "segment marker was emitted before convert_bytes threw",
  );
  // The post-segment pipeline markers (order/trace/emit) are NOT emitted on
  // failure — they only replay after a successful return.
  const emittedStages = stageSeq(posts).map(([s]) => s);
  assert.ok(!emittedStages.includes("order"));
  assert.ok(!emittedStages.includes("emit"));
});

test("a bring-up failure posts exactly one error and ZERO results for its id, and no pipeline stages", async () => {
  const { posts, bootstrap, handlers } = harness();
  bootstrap.packageFailures = ["opencv-python (import cv2 failed)"];
  bootstrap.packages = { ...allPass, "opencv-python": "fail" };

  await handlers.handleConvert("convert-1", makeRequest());

  assert.deepEqual(terminals(posts, "convert-1"), { results: 0, errors: 1 });
  // Bring-up stopped at load-packages; segment/order/trace/emit never emit.
  const emittedStages = stageSeq(posts).map(([s]) => s);
  assert.deepEqual(emittedStages, ["load-pyodide", "load-packages"]);
  assert.ok(!emittedStages.includes("segment"));
});

test("exclusivity holds across MANY ids and mixed outcomes: every id sees exactly one terminal, never both", async () => {
  const { posts, handlers, runtime } = harness();

  // Warm the runtime so each convert's own outcome drives its terminal.
  await handlers.handleConvert("warm", makeRequest());

  const cases: Array<{ id: string; fail: string | null }> = [
    { id: "ok-1", fail: null },
    { id: "bad-decode", fail: "ImageLoadError: bad png" },
    { id: "ok-2", fail: null },
    { id: "bad-convert", fail: "ConvertError: empty palette" },
    { id: "bad-empty", fail: "empty file: /input.png" },
    { id: "ok-3", fail: null },
  ];
  for (const { id, fail } of cases) {
    runtime.throwMessage = fail;
    await handlers.handleConvert(id, makeRequest());
  }

  for (const { id, fail } of [{ id: "warm", fail: null }, ...cases]) {
    const t = terminals(posts, id);
    assert.equal(t.results + t.errors, 1, `${id} has exactly one terminal`);
    if (fail === null) {
      assert.deepEqual(t, { results: 1, errors: 0 }, `${id} succeeded`);
    } else {
      assert.deepEqual(t, { results: 0, errors: 1 }, `${id} errored`);
    }
  }
});

/* -------------------------------------------------------------------------- */
/* (c) Recoverable vs non-recoverable classification (exhaustive)              */
/* -------------------------------------------------------------------------- */

/** Pull the single error message posted for `id`. */
function errorFor(posts: WorkerOut[], id: string): Extract<WorkerOut, { type: "error" }> {
  const err = posts.find((m) => m.type === "error" && m.id === id);
  assert.ok(err && err.type === "error", `expected an error for ${id}`);
  return err;
}

test("decode/input failures from convert_bytes are classified RECOVERABLE", async () => {
  // Each distinct message the glue can raise for a bad input (ImageLoadError /
  // ConvertError / unsupported extension / empty file) must come back as a
  // recoverable error so the user can pick another file without reloading
  // (Requirements 3.6, 9.5).
  const recoverableMessages = [
    "ImageLoadError: cannot identify image file '/input.png'",
    "ConvertError: palette collapsed to a single colour",
    "unsupported file extension: .gif (expected .png/.jpg/.jpeg)",
    "empty file: refusing to convert zero bytes",
  ];
  for (const [i, message] of recoverableMessages.entries()) {
    const runtime = new FakeRuntime();
    runtime.throwMessage = message;
    const { posts, handlers } = harness(runtime);
    const id = `rec-${i}`;
    await handlers.handleConvert(id, makeRequest());
    const err = errorFor(posts, id);
    assert.equal(err.recoverable, true, `"${message}" is recoverable`);
    assert.equal(err.message, message, "the engine message is surfaced verbatim");
  }
});

test("a runtime bring-up / package-load failure is classified NON-recoverable and carries the package results", async () => {
  const { posts, bootstrap, handlers } = harness();
  bootstrap.packageFailures = ["opencv-python (Failed to load opencv-python)"];
  bootstrap.packages = { ...allPass, "opencv-python": "fail" };

  await handlers.handleConvert("convert-1", makeRequest());

  const err = errorFor(posts, "convert-1");
  assert.equal(err.recoverable, false);
  assert.match(err.message, /opencv-python/);
  // The per-package results ride along so the shell can name the failed wheel.
  assert.deepEqual(err.packages, { ...allPass, "opencv-python": "fail" });
});

test("an engine IMPORT failure during bring-up is NON-recoverable (not a decode error)", async () => {
  const { posts, bootstrap, handlers } = harness();
  // Even though the message is about importing, bring-up failures are never
  // reclassified as recoverable: the page cannot run the engine at all.
  bootstrap.importError = "ModuleNotFoundError: No module named 'plate.web'";

  await handlers.handleConvert("convert-1", makeRequest());

  const err = errorFor(posts, "convert-1");
  assert.equal(err.recoverable, false);
  assert.equal(terminals(posts, "convert-1").results, 0);
});

test("a non-decode conversion failure (unknown message) is classified NON-recoverable", async () => {
  const runtime = new FakeRuntime();
  runtime.throwMessage = "RuntimeError: something unexpected inside the pipeline";
  const { posts, handlers } = harness(runtime);

  await handlers.handleConvert("convert-1", makeRequest());

  const err = errorFor(posts, "convert-1");
  assert.equal(err.recoverable, false, "an unrecognised failure is not treated as recoverable");
});

/* -------------------------------------------------------------------------- */
/* (d) Per-stage timing notes come from stats; segment/emit carry none         */
/* -------------------------------------------------------------------------- */

test("order/trace carry the engine's real per-stage seconds from stats; segment and emit carry none", async () => {
  const runtime = new FakeRuntime();
  runtime.nextResult = makeResult({ stats: makeStats({ t_order: 0.0, t_trace: 1.25 }) });
  const { posts, handlers } = harness(runtime);

  await handlers.handleConvert("convert-1", makeRequest());

  const notes = new Map(
    posts
      .filter((m): m is Extract<WorkerOut, { type: "progress" }> => m.type === "progress")
      .map((m) => [m.stage, m.note]),
  );
  // order/trace: the engine's own seconds, formatted "0.000s".
  assert.equal(notes.get("order"), "0.000s");
  assert.equal(notes.get("trace"), "1.250s");
  // segment/emit: no timing note (STAGE_TIMING omits them).
  assert.equal(notes.get("segment"), undefined);
  assert.equal(notes.get("emit"), undefined);
  // Bring-up stages carry no note either.
  assert.equal(notes.get("load-pyodide"), undefined);
});

test("a stage whose stats timing is missing or non-finite carries no note", async () => {
  const runtime = new FakeRuntime();
  // t_order present and finite, t_trace NaN → only order gets a note.
  runtime.nextResult = makeResult({ stats: makeStats({ t_order: 0.5, t_trace: Number.NaN }) });
  const { posts, handlers } = harness(runtime);

  await handlers.handleConvert("convert-1", makeRequest());

  const notes = new Map(
    posts
      .filter((m): m is Extract<WorkerOut, { type: "progress" }> => m.type === "progress")
      .map((m) => [m.stage, m.note]),
  );
  assert.equal(notes.get("order"), "0.500s");
  assert.equal(notes.get("trace"), undefined, "a non-finite timing produces no note");
});

/* -------------------------------------------------------------------------- */
/* Resource hygiene: the worker releases the Python proxies it created          */
/* -------------------------------------------------------------------------- */

test("the worker releases every Python proxy it created on BOTH success and failure", async () => {
  // Success: toBytes + toPy + result proxy all destroyed in the finally block.
  const okRuntime = new FakeRuntime();
  const ok = harness(okRuntime);
  await ok.handlers.handleConvert("convert-1", makeRequest());
  assert.ok(okRuntime.proxies.length >= 2, "proxies were created");
  assert.ok(okRuntime.proxies.every((p) => p.destroyed), "all proxies released on success");

  // Failure: the input proxies are still released even though convert_bytes threw.
  const failRuntime = new FakeRuntime();
  failRuntime.throwMessage = "ImageLoadError: bad";
  const bad = harness(failRuntime);
  await bad.handlers.handleConvert("convert-2", makeRequest());
  assert.ok(failRuntime.proxies.every((p) => p.destroyed), "input proxies released on failure");
});
