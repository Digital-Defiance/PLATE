/**
 * Unit tests for the worker MESSAGE PROTOCOL (task 6.2).
 *
 * Scope: the typed `WorkerIn`/`WorkerOut` contract (web/src/protocol.ts) and the
 * staged `convert` handler's wire behaviour (web/src/worker.ts, task 8.1), driven
 * through the real `PlateClient` (web/src/client.ts) against a MOCKED worker. This
 * complements — and deliberately does NOT duplicate — the client-wrapper tests in
 * `client.test.ts` (task 6.1), which already cover bare init/convert/dispose,
 * single-stage progress fan-out, and the two error paths.
 *
 * What is NEW here, matched to task 6.2's three sub-bullets:
 *   - request-id correlation UNDER the full task-8.1 staged sequence, including
 *     interleaved conversions and out-of-order replies (id must thread through
 *     the whole segment→order→trace→emit→result run, never crossing requests);
 *   - progress callback dispatch for the WHOLE ordered stage sequence a real
 *     worker emits (cold start load-pyodide…import tagged with the request id,
 *     then segment→order→trace→emit, with the engine timing `note`s preserved),
 *     plus the warm-runtime re-emit=none contract;
 *   - message serialization: every `WorkerIn`/`WorkerOut` variant is
 *     structured-clone-safe, `ConvertRequest.imageBytes` survives as a
 *     transferred `Uint8Array` (source buffer detached, no copy), and no
 *     function/proxy leaks into a posted message.
 *
 * WHY a mocked worker and not the real one: `worker.ts` boots Pyodide via a
 * runtime `import()` of `pyodide.mjs` and references `self` at module top level,
 * so it cannot be imported under plain Node. Rather than refactor task 8.1's
 * worker (the engine and sibling-task files stay untouched), these tests pin the
 * protocol CONTRACT: a `ProtocolWorker` fake replays the exact message sequence a
 * task-8.1 worker produces (the `handleConvert` ordering is encoded in
 * `STAGED_CONVERT_SEQUENCE` below from reading worker.ts), and the structured
 * clone checks prove the shapes actually cross a worker boundary intact. The
 * end-to-end guarantee that the LIVE worker emits exactly this sequence from a
 * real Pyodide run is the job of the headless-browser smoke test (task 18); these
 * unit tests fix the contract that both sides of the boundary agree on.
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
  ProgressUpdate,
  RuntimeInfo,
  Stage,
  WorkerIn,
  WorkerOut,
} from "../src/protocol.js";
import { PlateClient, PlateClientError, type WorkerLike } from "../src/client.js";

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

/** A full engine-shaped stats dict (snake_case keys, as the glue returns). */
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

/**
 * The bring-up stage ladder a cold start emits, mirroring worker.ts
 * `ensureRuntime`: load-pyodide(0) → load-packages(25) → install-plate(70) →
 * import(90). On a conversion's cold start these carry the request id and NO
 * `done` is injected (the sequence continues into the pipeline stages).
 */
const BRINGUP_STAGES: ReadonlyArray<{ stage: Stage; pct: number }> = [
  { stage: "load-pyodide", pct: 0 },
  { stage: "load-packages", pct: 25 },
  { stage: "install-plate", pct: 70 },
  { stage: "import", pct: 90 },
];

/**
 * The pipeline stage ladder `handleConvert` emits around the single
 * `convert_bytes` call: `segment` fires BEFORE the call, then
 * `order`/`trace`/`emit` fire after, each carrying the engine's real per-stage
 * timing from `stats` as a `"0.123s"` note (segment's own timing is in stats but
 * worker.ts annotates only order/trace — STAGE_TIMING maps segment→t_segment,
 * order→t_order, trace→t_trace; `emit` carries no timing note).
 */
const PIPELINE_STAGES: ReadonlyArray<{ stage: Stage; pct: number }> = [
  { stage: "segment", pct: 92 },
  { stage: "order", pct: 95 },
  { stage: "trace", pct: 98 },
  { stage: "emit", pct: 100 },
];

/* -------------------------------------------------------------------------- */
/* ProtocolWorker — a mock worker that replays a task-8.1 message sequence      */
/* -------------------------------------------------------------------------- */

/**
 * A mocked worker that, unlike `client.test.ts`'s bare FakeWorker, knows how to
 * replay the EXACT staged sequence a task-8.1 worker produces for a `convert`,
 * so the protocol contract (stage order + ids + timing notes + single
 * result/error) is exercised end-to-end through the real `PlateClient`. It also
 * records posted messages (and transfer lists) so serialization/transfer can be
 * asserted. Messages are delivered synchronously in `postMessage` order, exactly
 * as a dedicated worker's message channel preserves order.
 */
class ProtocolWorker implements WorkerLike {
  readonly posted: Array<{ message: WorkerIn; transfer?: Transferable[] }> = [];
  terminated = false;
  /** Whether the runtime has already been brought up (warm after first convert/init). */
  warm = false;
  private messageListeners = new Set<(event: MessageEvent<WorkerOut>) => void>();
  private errorListeners = new Set<(event: ErrorEvent) => void>();

  postMessage(message: WorkerIn, transfer?: Transferable[]): void {
    // Record the message as it would actually cross the boundary: a structured
    // clone, honouring any transfer list, so the recorded payload reflects what
    // the worker would receive (and the source buffer is detached on transfer).
    const cloned = transfer !== undefined
      ? (structuredClone(message, { transfer }) as WorkerIn)
      : (structuredClone(message) as WorkerIn);
    this.posted.push(transfer !== undefined ? { message: cloned, transfer } : { message: cloned });
  }

  addEventListener(type: "message", listener: (event: MessageEvent<WorkerOut>) => void): void;
  addEventListener(type: "error", listener: (event: ErrorEvent) => void): void;
  addEventListener(type: "message" | "error", listener: unknown): void {
    if (type === "message") {
      this.messageListeners.add(listener as (event: MessageEvent<WorkerOut>) => void);
    } else {
      this.errorListeners.add(listener as (event: ErrorEvent) => void);
    }
  }

  removeEventListener(_type: "message", listener: (event: MessageEvent<WorkerOut>) => void): void {
    this.messageListeners.delete(listener);
  }

  terminate(): void {
    this.terminated = true;
  }

  /** Deliver one `WorkerOut`, round-tripped through structured clone (as the real channel would). */
  emit(out: WorkerOut): void {
    const event = { data: structuredClone(out) as WorkerOut } as MessageEvent<WorkerOut>;
    for (const listener of this.messageListeners) listener(event);
  }

  emitError(message: string): void {
    const event = { message } as ErrorEvent;
    for (const listener of this.errorListeners) listener(event);
  }

  /** The id of the Nth (default: last) convert message posted. */
  convertIdAt(n = -1): string {
    const converts = this.posted.filter((p) => p.message.type === "convert");
    const picked = n < 0 ? converts[converts.length + n] : converts[n];
    if (!picked || picked.message.type !== "convert") throw new Error("no convert message posted");
    return picked.message.id;
  }

  /**
   * Replay the worker's `ready` for an `init()` bring-up: id-less bring-up
   * progress (load-pyodide…import, then `done`) followed by `ready`.
   */
  replayInit(): void {
    for (const { stage, pct } of BRINGUP_STAGES) this.emit({ type: "progress", stage, pct });
    this.emit({ type: "progress", stage: "done", pct: 100 });
    this.warm = true;
    this.emit({ type: "ready", packages: allPass, runtime: runtimeInfo });
  }

  /**
   * Replay a successful `handleConvert` for `id`, exactly as worker.ts orders it:
   *   - cold start (runtime not yet warm): bring-up stages tagged with `id`
   *     (load-pyodide…import), NO `done`, then straight into the pipeline;
   *   - warm start: NONE of the bring-up stages re-emitted (Requirement 5.5);
   *   - pipeline: `segment` (no note) then `order`/`trace` (timing notes) then
   *     `emit` (no note), each tagged with `id`;
   *   - exactly one `result` carrying `id`.
   */
  replayConvertSuccess(id: string, result: ConvertResult): void {
    if (!this.warm) {
      for (const { stage, pct } of BRINGUP_STAGES) this.emit({ type: "progress", stage, pct, id });
      this.warm = true;
    }
    const timing: Partial<Record<Stage, keyof ConvertStats>> = {
      order: "t_order",
      trace: "t_trace",
    };
    for (const { stage, pct } of PIPELINE_STAGES) {
      const key = timing[stage];
      const seconds = key !== undefined ? result.stats[key] : undefined;
      if (typeof seconds === "number") {
        this.emit({ type: "progress", stage, pct, id, note: `${seconds.toFixed(3)}s` });
      } else {
        this.emit({ type: "progress", stage, pct, id });
      }
    }
    this.emit({ type: "result", id, result });
  }
}

/** Let the client's awaited `init()` settle before the next assertion. */
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

/* -------------------------------------------------------------------------- */
/* 1. Request-id correlation under the full staged-convert sequence            */
/* -------------------------------------------------------------------------- */

test("id threads through a convert's pipeline stages: every pipeline event carries the request id and one result resolves it", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  const seen: ProgressUpdate[] = [];
  client.onProgress((p) => seen.push(p));

  // Through PlateClient a convert first awaits init() (which carries the id-less
  // bring-up ladder), then posts the convert whose pipeline stages carry the id.
  // (The worker's alternative "cold convert tags bring-up with the id" ordering
  // is only reachable by posting a convert with NO prior init — a path the
  // client never takes; its wire SHAPE is asserted in the serialization tests
  // and its live ordering is covered by the headless smoke test, task 18.)
  const init = client.init();
  worker.replayInit();
  await init;
  const bringupCount = seen.length;

  const pending = client.convert(makeRequest());
  await flush(); // let the awaited init() settle so the convert message is posted
  const id = worker.convertIdAt();
  const result = makeResult();
  worker.replayConvertSuccess(id, result);

  const got = await pending;
  assert.equal(got.svg, result.svg);

  // Every pipeline progress event for this conversion carries the SAME request
  // id (Requirement 5.2) and they arrive in order.
  const pipeline = seen.slice(bringupCount);
  assert.deepEqual(
    pipeline.map((p) => p.stage),
    ["segment", "order", "trace", "emit"],
  );
  assert.ok(pipeline.every((p) => p.id === id), "every pipeline event carries the request id");
});

test("interleaved conversions never cross ids; out-of-order replies route to the right promise", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  // Warm the runtime first so both converts are warm-start (no bring-up noise).
  const init = client.init();
  worker.replayInit();
  await init;

  const first = client.convert(makeRequest(new Uint8Array([0xa]))); // distinct bytes
  await flush();
  const firstId = worker.convertIdAt();
  const second = client.convert(makeRequest(new Uint8Array([0xb])));
  await flush();
  const secondId = worker.convertIdAt();
  assert.notEqual(firstId, secondId);

  // Reply to the SECOND request first (out of order) — correlation is by id,
  // not arrival order, so each promise still gets its own result.
  worker.replayConvertSuccess(secondId, makeResult({ svg: "<svg id='second'/>" }));
  worker.replayConvertSuccess(firstId, makeResult({ svg: "<svg id='first'/>" }));

  assert.equal((await first).svg, "<svg id='first'/>");
  assert.equal((await second).svg, "<svg id='second'/>");
});

test("a per-request error carrying the id rejects only that convert and leaves no result for it", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  const init = client.init();
  worker.replayInit();
  await init;

  const bad = client.convert(makeRequest());
  await flush();
  const badId = worker.convertIdAt();
  const good = client.convert(makeRequest());
  await flush();
  const goodId = worker.convertIdAt();

  // A recoverable decode failure for the first id (segment was already emitted
  // before convert_bytes threw, so progress may precede the error — id-correlated).
  worker.emit({ type: "progress", stage: "segment", pct: 92, id: badId });
  worker.emit({
    type: "error",
    id: badId,
    message: "ImageLoadError: cannot identify image file",
    recoverable: true,
  });
  worker.replayConvertSuccess(goodId, makeResult({ svg: "<svg ok/>" }));

  await assert.rejects(bad, (err: unknown) => {
    assert.ok(err instanceof PlateClientError);
    assert.equal(err.recoverable, true);
    assert.match(err.message, /ImageLoadError/);
    return true;
  });
  assert.equal((await good).svg, "<svg ok/>");
});

/* -------------------------------------------------------------------------- */
/* 2. Progress callback dispatch for the whole ordered stage sequence          */
/* -------------------------------------------------------------------------- */

test("warm-runtime convert re-emits NO bring-up stages, only the pipeline stages (Requirement 5.5)", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  const seen: ProgressUpdate[] = [];
  client.onProgress((p) => seen.push(p));

  const init = client.init();
  worker.replayInit(); // id-less bring-up + ready warms the runtime
  await init;
  const bringupCount = seen.length;

  const pending = client.convert(makeRequest());
  await flush();
  const id = worker.convertIdAt();
  worker.replayConvertSuccess(id, makeResult());
  await pending;

  // The bring-up stages (id-less) came only from init; the convert added ONLY
  // the four pipeline stages, all tagged with the request id.
  const afterInit = seen.slice(bringupCount);
  assert.deepEqual(
    afterInit.map((p) => p.stage),
    ["segment", "order", "trace", "emit"],
  );
  assert.ok(afterInit.every((p) => p.id === id), "warm pipeline stages all carry the convert id");

  // And the id-less bring-up ladder was delivered exactly once, in order.
  assert.deepEqual(
    seen.slice(0, bringupCount).map((p) => [p.stage, p.id]),
    [
      ["load-pyodide", undefined],
      ["load-packages", undefined],
      ["install-plate", undefined],
      ["import", undefined],
      ["done", undefined],
    ],
  );
});

test("pipeline progress carries the engine's real per-stage timing notes from stats", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  const seen: ProgressUpdate[] = [];
  client.onProgress((p) => seen.push(p));

  const init = client.init();
  worker.replayInit();
  await init;

  const pending = client.convert(makeRequest());
  await flush();
  const id = worker.convertIdAt();
  // Distinctive timings so we can assert the note reflects THIS run's stats.
  const result = makeResult({ stats: makeStats({ t_order: 0.0, t_trace: 1.25 }) });
  worker.replayConvertSuccess(id, result);
  await pending;

  const byStage = new Map(seen.filter((p) => p.id === id).map((p) => [p.stage, p]));
  // segment and emit carry no timing note (worker.ts STAGE_TIMING omits them).
  assert.equal(byStage.get("segment")?.note, undefined);
  assert.equal(byStage.get("emit")?.note, undefined);
  // order/trace carry the engine's own seconds, formatted "0.000s".
  assert.equal(byStage.get("order")?.note, "0.000s");
  assert.equal(byStage.get("trace")?.note, "1.250s");
});

test("unsubscribing mid-run stops further dispatch but the convert still resolves", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  const seen: ProgressUpdate[] = [];
  const unsubscribe = client.onProgress((p) => seen.push(p));

  const init = client.init();
  worker.replayInit();
  await init;
  const bringupCount = seen.length;

  const pending = client.convert(makeRequest());
  await flush();
  const id = worker.convertIdAt();
  // Deliver the first two pipeline stages, then unsubscribe before the rest.
  worker.emit({ type: "progress", stage: "segment", pct: 92, id });
  worker.emit({ type: "progress", stage: "order", pct: 95, id, note: "0.022s" });
  unsubscribe();
  worker.emit({ type: "progress", stage: "trace", pct: 98, id, note: "0.333s" });
  worker.emit({ type: "progress", stage: "emit", pct: 100, id });
  worker.emit({ type: "result", id, result: makeResult() });
  await pending;

  assert.deepEqual(
    seen.slice(bringupCount).map((p) => p.stage),
    ["segment", "order"],
  );
});

/* -------------------------------------------------------------------------- */
/* 3. Message serialization (structured-clone safety + transfer semantics)     */
/* -------------------------------------------------------------------------- */

test("every WorkerIn variant is structured-clone-safe and survives the round trip", () => {
  const ins: WorkerIn[] = [
    { type: "init" },
    { type: "convert", id: "convert-1", request: makeRequest() },
  ];
  for (const message of ins) {
    const clone = structuredClone(message);
    assert.deepEqual(clone, message, `WorkerIn ${message.type} clones intact`);
  }
});

test("every WorkerOut variant is structured-clone-safe and survives the round trip", () => {
  const outs: WorkerOut[] = [
    { type: "ready", packages: allPass, runtime: runtimeInfo },
    { type: "ready", packages: allPass }, // runtime optional
    { type: "progress", stage: "load-pyodide", pct: 0 }, // id-less bring-up
    { type: "progress", stage: "trace", pct: 98, id: "convert-1", note: "0.333s" },
    { type: "result", id: "convert-1", result: makeResult() },
    { type: "error", id: "convert-1", message: "ImageLoadError: bad", recoverable: true },
    {
      type: "error",
      message: "required package(s) failed to load in Pyodide: opencv-python",
      recoverable: false,
      packages: { ...allPass, "opencv-python": "fail" },
    },
  ];
  for (const message of outs) {
    const clone = structuredClone(message);
    assert.deepEqual(clone, message, `WorkerOut ${message.type} clones intact`);
  }
});

test("a convert message transfers imageBytes as a Uint8Array: receiver keeps the data, sender's buffer is detached (no copy)", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  // Warm first so the convert posts promptly (keeps the sequencing clean).
  const init = client.init();
  worker.replayInit();
  await init;

  const bytes = new Uint8Array([9, 8, 7, 6, 5]);
  const original = Array.from(bytes);
  const pending = client.convert(makeRequest(bytes));
  await flush(); // let the awaited init() settle so the convert message is posted
  const id = worker.convertIdAt();
  worker.replayConvertSuccess(id, makeResult());
  await pending;

  // The worker RECEIVED the bytes intact (structuredClone with transfer copies
  // the data into the receiver's heap)...
  const convertPost = worker.posted.find((p) => p.message.type === "convert");
  assert.ok(convertPost && convertPost.message.type === "convert");
  assert.ok(convertPost.message.request.imageBytes instanceof Uint8Array);
  assert.deepEqual(Array.from(convertPost.message.request.imageBytes), original);
  // ...and the client listed the underlying buffer in the transfer list.
  assert.equal(convertPost.transfer?.length, 1);
  assert.ok(convertPost.transfer?.[0] instanceof ArrayBuffer);
  // The sender's view is detached after transfer — proving no copy was made on
  // the main thread (Property 5 / Requirement 3.6: bytes are transferred).
  assert.equal(bytes.byteLength, 0, "sender's buffer is detached after transfer");
});

test("no function or proxy leaks into a posted message (posted payload is pure data)", async () => {
  const worker = new ProtocolWorker();
  const client = new PlateClient(() => worker);
  const init = client.init();
  worker.replayInit();
  await init;
  const pending = client.convert(makeRequest());
  await flush();
  const id = worker.convertIdAt();
  worker.replayConvertSuccess(id, makeResult());
  await pending;

  // Walk every posted message; a structured clone of pure data must equal
  // itself, and nothing in the tree may be a function (functions are not
  // clonable and would throw crossing a real worker boundary).
  const assertNoFunctions = (value: unknown, path: string): void => {
    assert.notEqual(typeof value, "function", `function leaked at ${path}`);
    if (value && typeof value === "object") {
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        assertNoFunctions(v, `${path}.${k}`);
      }
    }
  };
  for (const [i, { message }] of worker.posted.entries()) {
    assertNoFunctions(message, `posted[${i}]`);
    // Round-trips cleanly (would throw on a non-clonable member).
    assert.doesNotThrow(() => structuredClone(message));
  }
});
