/**
 * Tests for `PlateClient` (web/src/client.ts) with a fake Web Worker.
 *
 * These cover the worker message protocol from the main-thread side: init
 * resolves on `ready`, convert requests correlate to replies by `id`, progress
 * events fan out to listeners, a bring-up `error` (no id) rejects `init`, and a
 * per-request `error` rejects only that convert. The real worker/Pyodide is not
 * exercised — the fake worker stands in so these run under Node (task 6.2 adds
 * the full protocol suite; this is the client-wrapper coverage for task 6.1).
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type {
  ConvertRequest,
  ConvertResult,
  PackageLoadResults,
  ProgressUpdate,
  WorkerIn,
  WorkerOut,
} from "../src/protocol.js";
import { PlateClient, PlateClientError, type WorkerLike } from "../src/client.js";

const allPass: PackageLoadResults = {
  numpy: "pass",
  scipy: "pass",
  "opencv-python": "pass",
  pillow: "pass",
  "scikit-image": "pass",
};

/**
 * A scripted fake worker: it records every posted message (and transfer list)
 * and lets a test push `WorkerOut` messages / `error` events back as if the
 * worker produced them. `terminate` is recorded so dispose can be asserted.
 */
class FakeWorker implements WorkerLike {
  readonly posted: Array<{ message: WorkerIn; transfer?: Transferable[] }> = [];
  terminated = false;
  private messageListeners = new Set<(event: MessageEvent<WorkerOut>) => void>();
  private errorListeners = new Set<(event: ErrorEvent) => void>();

  postMessage(message: WorkerIn, transfer?: Transferable[]): void {
    this.posted.push(transfer !== undefined ? { message, transfer } : { message });
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

  removeEventListener(
    _type: "message",
    listener: (event: MessageEvent<WorkerOut>) => void,
  ): void {
    this.messageListeners.delete(listener);
  }

  terminate(): void {
    this.terminated = true;
  }

  /** Deliver a worker-out message to every registered listener. */
  emit(out: WorkerOut): void {
    const event = { data: out } as MessageEvent<WorkerOut>;
    for (const listener of this.messageListeners) listener(event);
  }

  /** Deliver a worker-level error (script load failure / top-level throw). */
  emitError(message: string): void {
    const event = { message } as ErrorEvent;
    for (const listener of this.errorListeners) listener(event);
  }

  /** The last convert request's correlation id, for driving replies. */
  lastConvertId(): string {
    for (let i = this.posted.length - 1; i >= 0; i--) {
      const m = this.posted[i]!.message;
      if (m.type === "convert") return m.id;
    }
    throw new Error("no convert message posted");
  }
}

/** Let queued microtasks run so an awaited `init()` settles before we assert. */
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function makeRequest(bytes = new Uint8Array([1, 2, 3])): ConvertRequest {
  return { imageBytes: bytes, filename: "logo.png", config: { preset: "logo" } };
}

function makeResult(tTotal = 0.5): ConvertResult {
  // The engine reports snake_case stats; ConvertStats mirrors them exactly.
  const stats = { t_total: tTotal } as unknown as ConvertResult["stats"];
  return { svg: "<svg/>", stats, layers: [], warnings: [] };
}

test("init posts {type:init} and resolves on ready with packages + runtime", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);

  const ready = client.init();
  assert.deepEqual(fake.posted[0]?.message, { type: "init" });

  fake.emit({
    type: "ready",
    packages: allPass,
    runtime: { pyodide: "314.0.7", python: "3.14.2", versions: { numpy: "2.4.6" } },
  });

  const result = await ready;
  assert.deepEqual(result.packages, allPass);
  assert.equal(result.runtime?.pyodide, "314.0.7");
});

test("init is idempotent: concurrent calls share one bring-up", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);

  const a = client.init();
  const b = client.init();
  // Only one init message is posted despite two calls.
  const initMessages = fake.posted.filter((p) => p.message.type === "init");
  assert.equal(initMessages.length, 1);

  fake.emit({ type: "ready", packages: allPass });
  const [ra, rb] = await Promise.all([a, b]);
  assert.deepEqual(ra, rb);
});

test("convert correlates the matching result by id and transfers the bytes buffer", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);

  const request = makeRequest();
  const pending = client.convert(request);

  // convert() warms the runtime first; answer the ready, then let the awaited
  // init() settle so the convert message is posted before we read its id.
  fake.emit({ type: "ready", packages: allPass });
  await flush();
  const id = fake.lastConvertId();

  // The request was posted with the image buffer in the transfer list.
  const convertPost = fake.posted.find((p) => p.message.type === "convert");
  assert.ok(convertPost);
  assert.deepEqual(convertPost?.transfer, [request.imageBytes.buffer]);

  fake.emit({ type: "result", id, result: makeResult(0.42) });
  const result = await pending;
  assert.equal(result.svg, "<svg/>");
  assert.equal(result.stats.t_total, 0.42);
});

test("two converts resolve to their own results, not each other's", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);
  await (async () => {
    const r = client.init();
    fake.emit({ type: "ready", packages: allPass });
    await r;
  })();

  const firstReq = makeRequest(new Uint8Array([1]));
  const secondReq = makeRequest(new Uint8Array([2]));
  const first = client.convert(firstReq);
  await flush();
  const firstId = fake.lastConvertId();
  const second = client.convert(secondReq);
  await flush();
  const secondId = fake.lastConvertId();
  assert.notEqual(firstId, secondId);

  // Reply to the second request first; the first must still be pending.
  fake.emit({ type: "result", id: secondId, result: makeResult(0.2) });
  fake.emit({ type: "result", id: firstId, result: makeResult(0.9) });

  assert.equal((await first).stats.t_total, 0.9);
  assert.equal((await second).stats.t_total, 0.2);
});

test("progress events fan out to listeners; unsubscribe stops them", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);
  const seen: ProgressUpdate[] = [];
  const unsubscribe = client.onProgress((p) => seen.push(p));

  client.init();
  fake.emit({ type: "progress", stage: "load-pyodide", pct: 0 });
  fake.emit({ type: "progress", stage: "load-packages", pct: 25 });
  fake.emit({ type: "ready", packages: allPass });

  const convert = client.convert(makeRequest());
  await flush();
  const id = fake.lastConvertId();
  fake.emit({ type: "progress", stage: "segment", pct: 50, id });
  unsubscribe();
  fake.emit({ type: "progress", stage: "emit", pct: 90, id });
  fake.emit({ type: "result", id, result: makeResult() });
  await convert;

  assert.deepEqual(
    seen.map((p) => [p.stage, p.pct, p.id]),
    [
      ["load-pyodide", 0, undefined],
      ["load-packages", 25, undefined],
      ["segment", 50, id],
    ],
  );
});

test("a bring-up error (no id) rejects init with a non-recoverable error carrying packages", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);

  const ready = client.init();
  const failed: PackageLoadResults = { ...allPass, "opencv-python": "fail" };
  fake.emit({
    type: "error",
    message: "required package(s) failed to load in Pyodide: opencv-python",
    recoverable: false,
    packages: failed,
  });

  await assert.rejects(ready, (err: unknown) => {
    assert.ok(err instanceof PlateClientError);
    assert.equal(err.recoverable, false);
    assert.deepEqual(err.packages, failed);
    assert.match(err.message, /opencv-python/);
    return true;
  });
});

test("a per-request error rejects only that convert and marks recoverable", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);
  const convert = client.convert(makeRequest());
  fake.emit({ type: "ready", packages: allPass });
  await flush();
  const id = fake.lastConvertId();

  fake.emit({ type: "error", id, message: "ImageLoadError: bad png", recoverable: true });

  await assert.rejects(convert, (err: unknown) => {
    assert.ok(err instanceof PlateClientError);
    assert.equal(err.recoverable, true);
    assert.match(err.message, /ImageLoadError/);
    return true;
  });
});

test("a worker-level error rejects the in-flight init rather than hanging", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);
  const ready = client.init();
  fake.emitError("script failed to load");
  await assert.rejects(ready, (err: unknown) => {
    assert.ok(err instanceof PlateClientError);
    assert.equal(err.recoverable, false);
    assert.match(err.message, /worker error/);
    return true;
  });
});

test("dispose terminates the worker and rejects outstanding requests", async () => {
  const fake = new FakeWorker();
  const client = new PlateClient(() => fake);
  const convert = client.convert(makeRequest());
  fake.emit({ type: "ready", packages: allPass });
  await flush(); // let the awaited init() settle so the convert is registered as pending

  client.dispose();
  assert.equal(fake.terminated, true);
  await assert.rejects(convert, (err: unknown) => err instanceof PlateClientError);
});
