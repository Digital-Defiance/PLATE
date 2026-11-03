/**
 * Property 5 — Non-blocking main thread (task 12).
 *
 * Design (`.kiro/specs/browser-web-page/design.md`, Correctness Properties):
 *
 *   Property 5: Non-blocking main thread
 *   "No conversion runs on the main thread; the UI thread only posts/receives
 *    messages, so the page stays responsive."
 *   ∀ conversion : runs_on(conversion) == WebWorker
 *                  ∧ main_thread_work(conversion) == message_passing_only
 *   Validates: Requirements 5.1
 *
 * This is a PROPERTY test over randomised sequences of worker traffic, not a
 * worked example — it deliberately does NOT re-cover the single-case wiring in
 * `client.test.ts` (6.1) or `protocol.test.ts` (6.2). It drives the real
 * `PlateClient` (web/src/client.ts) with a fake `WorkerLike` and, across a
 * seeded family of randomised init/convert/progress/result/error sequences,
 * asserts the invariants that together ENCODE "the main thread only passes
 * messages and never does heavy/synchronous conversion work":
 *
 *   (A) TRANSFER-NOT-COPY. Every `convert` posts the image bytes with
 *       `imageBytes.buffer` in the postMessage transfer list, so the pixel data
 *       is moved to the worker, never copied on the main thread. We also assert
 *       the source buffer is DETACHED after the post (byteLength 0) — the
 *       structured-clone transfer actually happened — across randomised byte
 *       lengths. This is the concrete Property-5 signal hinted in client.test.ts.
 *
 *   (B) NO SYNCHRONOUS CONVERSION. Posting a convert does not, by itself,
 *       produce a result: the returned Promise stays unsettled until the worker
 *       posts the reply whose `id` matches. Between post and reply the main
 *       thread holds no busy loop — it is free to run other microtasks — which
 *       we observe by interleaving unrelated work and confirming the convert is
 *       still pending. "runs_on(conversion) == WebWorker": the only thing that
 *       settles a convert is a worker message.
 *
 *   (C) PER-REQUEST ISOLATION UNDER CONCURRENCY. N concurrent converts each post
 *       exactly one `convert` message with a distinct id, and each settles only
 *       when ITS id is answered — regardless of the (randomised) reply order.
 *       No convert resolves early, none cross-talk. The main thread is pure
 *       message routing by id.
 *
 *   (D) O(1) MAIN-THREAD BOOKKEEPING. Under a randomised flood of `progress`
 *       events the client's per-message cost is constant-size: its pending-
 *       request table is bounded by the number of in-flight converts and is
 *       unaffected by how many progress events arrive. A flood of worker chatter
 *       cannot make the main thread accumulate unbounded state (no heavy work).
 *
 * Together: conversion never runs or blocks on the main thread; the client only
 * posts messages (transferring, not copying, pixel data) and resolves promises
 * off worker replies.
 *
 * Hermetic: Node + tsx, no real browser and no Pyodide. The fake worker never
 * runs the engine; it only lets the test replay the worker side of the protocol,
 * which is all Property 5 is about (the main-thread contract). The guarantee
 * that the LIVE worker actually does the CPU work is the headless smoke test
 * (task 18).
 *
 * Randomisation uses a seeded, deterministic PRNG (no external dependency) so a
 * failure is reproducible from the printed seed.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type {
  ConvertRequest,
  ConvertResult,
  PackageLoadResults,
  Stage,
  WorkerIn,
  WorkerOut,
} from "../src/protocol.js";
import { PlateClient, type WorkerLike } from "../src/client.js";

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

/** Progress stages a real worker emits per conversion; used to flood (D). */
const CONVERT_STAGES: Stage[] = ["segment", "order", "trace", "emit"];

/**
 * A scripted fake worker. It records every posted message and, to prove the
 * transfer actually happened (invariant A), it ACTUALLY detaches each
 * transferred ArrayBuffer the way a real `postMessage(msg, [buffer])` does — by
 * transferring it out via `structuredClone`'s transfer list. That leaves the
 * source buffer's `byteLength` at 0, exactly as the browser would, so the test
 * observes real move-not-copy semantics rather than trusting the client.
 */
class FakeWorker implements WorkerLike {
  readonly posted: Array<{ message: WorkerIn; transfer?: Transferable[] }> = [];
  terminated = false;
  private messageListeners = new Set<(event: MessageEvent<WorkerOut>) => void>();
  private errorListeners = new Set<(event: ErrorEvent) => void>();

  postMessage(message: WorkerIn, transfer?: Transferable[]): void {
    this.posted.push(transfer !== undefined ? { message, transfer } : { message });
    // Emulate the browser's move semantics: everything in the transfer list is
    // detached from the sender. This is what makes the pixel data NOT a
    // main-thread copy — after this the source buffer is unusable here.
    if (transfer) {
      for (const t of transfer) {
        if (t instanceof ArrayBuffer) {
          structuredClone(t, { transfer: [t] });
        }
      }
    }
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

  emit(out: WorkerOut): void {
    const event = { data: out } as MessageEvent<WorkerOut>;
    for (const listener of this.messageListeners) listener(event);
  }

  /** Correlation ids of every convert posted so far, in order. */
  convertIds(): string[] {
    const ids: string[] = [];
    for (const p of this.posted) {
      if (p.message.type === "convert") ids.push(p.message.id);
    }
    return ids;
  }
}

/** Let queued microtasks run so an awaited `init()`/convert post settles. */
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function makeResult(tTotal: number): ConvertResult {
  const stats = { t_total: tTotal } as unknown as ConvertResult["stats"];
  return { svg: "<svg/>", stats, layers: [], warnings: [] };
}

function makeRequest(byteLen: number): ConvertRequest {
  const bytes = new Uint8Array(byteLen);
  for (let i = 0; i < byteLen; i++) bytes[i] = i & 0xff;
  return { imageBytes: bytes, filename: "img.png", config: { preset: "logo" } };
}

/**
 * A tiny deterministic PRNG (mulberry32) so each randomised property run is
 * reproducible from its seed. No external dependency: the design's property
 * stack is Python/hypothesis; for this TS-side shell property a seeded loop is
 * the faithful equivalent and keeps devDependencies untouched.
 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Random integer in [lo, hi] inclusive, from the seeded PRNG. */
function randInt(rng: () => number, lo: number, hi: number): number {
  return lo + Math.floor(rng() * (hi - lo + 1));
}

/** Fisher–Yates shuffle driven by the seeded PRNG (randomised reply order). */
function shuffle<T>(items: T[], rng: () => number): T[] {
  const out = items.slice();
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = out[i]!;
    out[i] = out[j]!;
    out[j] = tmp;
  }
  return out;
}

/** Warm the client so `convert()` posts immediately (init resolved). */
async function warm(fake: FakeWorker, client: PlateClient): Promise<void> {
  const ready = client.init();
  fake.emit({ type: "ready", packages: allPass });
  await ready;
}

/** How many randomised cases each property explores. */
const CASES = 200;

/* -------------------------------------------------------------------------- */
/* Property 5                                                                  */
/* -------------------------------------------------------------------------- */

test("P5(A): every convert TRANSFERS imageBytes.buffer (no main-thread copy) across randomised byte lengths", async () => {
  // Validates: Requirements 5.1 — the main thread moves pixel data to the worker
  // via the transfer list; it never copies it. A copy would be heavy main-thread
  // work scaling with image size, which Property 5 forbids.
  for (let c = 0; c < CASES; c++) {
    const seed = 0xa0000 + c;
    const rng = mulberry32(seed);
    const fake = new FakeWorker();
    const client = new PlateClient(() => fake);
    await warm(fake, client);

    const byteLen = randInt(rng, 0, 65536);
    const request = makeRequest(byteLen);
    const buffer = request.imageBytes.buffer;

    const pending = client.convert(request);
    await flush(); // let the awaited init() settle so the convert is posted

    const convertPost = fake.posted.find((p) => p.message.type === "convert");
    assert.ok(convertPost, `seed ${seed}: a convert message must be posted`);
    // The buffer is in the transfer list — moved, not structured-cloned.
    assert.deepEqual(
      convertPost!.transfer,
      [buffer],
      `seed ${seed}: imageBytes.buffer must be the sole transfer entry`,
    );
    // And the transfer truly happened: the source buffer is detached (0 bytes),
    // so no pixel-data copy remains on the main thread.
    assert.equal(
      request.imageBytes.buffer.byteLength,
      0,
      `seed ${seed}: source buffer must be detached after transfer (byteLen=${byteLen})`,
    );

    const id = fake.convertIds().at(-1)!;
    fake.emit({ type: "result", id, result: makeResult(rng()) });
    await pending;
    client.dispose();
  }
});

test("P5(B): a convert never settles synchronously — only the matching worker reply resolves it", async () => {
  // Validates: Requirements 5.1 — runs_on(conversion) == WebWorker. The main
  // thread does no synchronous conversion: posting a convert yields no result by
  // itself, and the main thread stays free (unrelated microtasks run) while the
  // conversion is "in the worker".
  for (let c = 0; c < CASES; c++) {
    const seed = 0xb0000 + c;
    const rng = mulberry32(seed);
    const fake = new FakeWorker();
    const client = new PlateClient(() => fake);
    await warm(fake, client);

    let settled = false;
    const pending = client
      .convert(makeRequest(randInt(rng, 1, 4096)))
      .then((r) => {
        settled = true;
        return r;
      });
    await flush();

    // No worker reply yet -> the convert must still be pending. If the main
    // thread had run the conversion itself, it would have resolved by now.
    assert.equal(settled, false, `seed ${seed}: convert settled with no worker reply`);

    // The main thread is free: unrelated work interleaves while the conversion
    // is outstanding. Run a randomised number of unrelated microtasks.
    const spins = randInt(rng, 1, 8);
    for (let s = 0; s < spins; s++) {
      await Promise.resolve();
      assert.equal(settled, false, `seed ${seed}: convert settled during idle main-thread work`);
    }

    // Exactly one result message, matching id, settles it.
    const id = fake.convertIds().at(-1)!;
    const tTotal = rng();
    fake.emit({ type: "result", id, result: makeResult(tTotal) });
    const result = await pending;
    assert.equal(settled, true, `seed ${seed}: convert should resolve after its reply`);
    assert.equal(result.stats.t_total, tTotal, `seed ${seed}: wrong result threaded back`);

    client.dispose();
  }
});

test("P5(C): N concurrent converts post one message each and settle only on their own id, in randomised reply order", async () => {
  // Validates: Requirements 5.1 — the main thread is pure message routing by id.
  // Many conversions can be in flight at once (the worker does the work); each
  // resolves to its own result no matter the reply order, and none resolve early.
  for (let c = 0; c < CASES; c++) {
    const seed = 0xc0000 + c;
    const rng = mulberry32(seed);
    const fake = new FakeWorker();
    const client = new PlateClient(() => fake);
    await warm(fake, client);

    const n = randInt(rng, 1, 6);
    // Distinct t_total per request so we can prove no cross-talk.
    const expected = new Map<string, number>();
    const settledIds = new Set<string>();
    const promises: Array<Promise<void>> = [];

    for (let i = 0; i < n; i++) {
      const want = i + 1; // unique, non-zero
      const p = client.convert(makeRequest(randInt(rng, 1, 2048))).then((res) => {
        // Resolve the id from the posted order: the i-th convert posted is this one.
        const id = fake.convertIds()[i]!;
        settledIds.add(id);
        assert.equal(
          res.stats.t_total,
          expected.get(id),
          `seed ${seed}: convert ${id} resolved with another request's result`,
        );
      });
      promises.push(p);
      await flush(); // ensure each convert is posted (one message) before the next
      const id = fake.convertIds()[i]!;
      expected.set(id, want);
    }

    const ids = fake.convertIds();
    assert.equal(ids.length, n, `seed ${seed}: exactly one convert message per request`);
    assert.equal(new Set(ids).size, n, `seed ${seed}: correlation ids must be distinct`);

    // Reply in a randomised order; after each reply only the answered ids are
    // settled (no early/eager resolution of the not-yet-answered ones).
    const replyOrder = shuffle(
      ids.map((id, i) => ({ id, want: i + 1 })),
      rng,
    );
    for (let k = 0; k < replyOrder.length; k++) {
      const { id, want } = replyOrder[k]!;
      fake.emit({ type: "result", id, result: makeResult(want) });
      await flush();
      // Every id replied so far is settled; none beyond that.
      const answered = new Set(replyOrder.slice(0, k + 1).map((e) => e.id));
      for (const otherId of ids) {
        if (!answered.has(otherId)) {
          assert.ok(
            !settledIds.has(otherId),
            `seed ${seed}: ${otherId} settled before its reply`,
          );
        }
      }
    }

    await Promise.all(promises);
    assert.equal(settledIds.size, n, `seed ${seed}: all converts should settle exactly once`);
    client.dispose();
  }
});

test("P5(D): a randomised flood of progress events keeps main-thread bookkeeping O(1) in in-flight converts", async () => {
  // Validates: Requirements 5.1 — the page stays responsive. A storm of worker
  // chatter (progress) must cost the main thread constant-size work: the client
  // only ever tracks the in-flight converts, never accumulating per-progress
  // state. We assert the pending table size equals the number of unanswered
  // converts throughout, independent of how many progress events arrive.
  const pendingSize = (client: PlateClient): number => {
    // The pending table is private; read it via the documented field for the
    // test only. It is a Map keyed by correlation id.
    const map = (client as unknown as { pending: Map<string, unknown> }).pending;
    return map.size;
  };

  for (let c = 0; c < CASES; c++) {
    const seed = 0xd0000 + c;
    const rng = mulberry32(seed);
    const fake = new FakeWorker();
    const client = new PlateClient(() => fake);
    await warm(fake, client);

    const n = randInt(rng, 1, 5);
    const promises: Array<Promise<ConvertResult>> = [];
    for (let i = 0; i < n; i++) {
      promises.push(client.convert(makeRequest(randInt(rng, 1, 1024))));
      await flush();
    }
    const ids = fake.convertIds();
    assert.equal(pendingSize(client), n, `seed ${seed}: pending must equal in-flight converts`);

    // Flood randomised progress events (with and without ids) — these must not
    // change the pending table at all.
    const floods = randInt(rng, 10, 200);
    for (let f = 0; f < floods; f++) {
      const stage = CONVERT_STAGES[randInt(rng, 0, CONVERT_STAGES.length - 1)]!;
      const taggedId = rng() < 0.5 ? ids[randInt(rng, 0, ids.length - 1)]! : undefined;
      fake.emit(
        taggedId !== undefined
          ? { type: "progress", stage, pct: randInt(rng, 0, 100), id: taggedId }
          : { type: "progress", stage, pct: randInt(rng, 0, 100) },
      );
      assert.equal(
        pendingSize(client),
        n,
        `seed ${seed}: progress flood must not grow/shrink pending bookkeeping`,
      );
    }

    // Draining results shrinks the table one-per-reply, back to zero.
    const order = shuffle(ids.slice(), rng);
    for (let k = 0; k < order.length; k++) {
      fake.emit({ type: "result", id: order[k]!, result: makeResult(rng()) });
      assert.equal(
        pendingSize(client),
        n - (k + 1),
        `seed ${seed}: each reply must clear exactly one pending entry`,
      );
    }
    await Promise.all(promises);
    assert.equal(pendingSize(client), 0, `seed ${seed}: pending must be empty after all replies`);
    client.dispose();
  }
});
