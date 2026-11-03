import assert from "node:assert/strict";
import { test, type TestContext } from "node:test";
import { LiveConversion, SETTINGS_DEBOUNCE_MS } from "../src/live-conversion.js";
import type { IntakeAccepted } from "../src/intake.js";
import type { ConvertRequest, ConvertResult, PlateConfig } from "../src/protocol.js";

const flush = async (): Promise<void> => { await Promise.resolve(); await Promise.resolve(); };
const source = (filename = "logo.png"): IntakeAccepted => ({
  ok: true, filename, imageBytes: new Uint8Array([1, 2, 3]), width: 10, height: 10,
});
const result = (svg: string): ConvertResult => ({ svg, stats: { shapes: 1, completed: 0, anchors: 4, primitives: 1, gradients: 0, strokes: 0, t_segment: 0, t_order: 0, t_trace: 0, t_total: 0, vlm_names: 0 }, layers: [], warnings: [] });

function harness(t: TestContext) {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let config: PlateConfig = {};
  let invalidations = 0;
  let starts = 0;
  let settlements = 0;
  const requests: Array<{ request: ConvertRequest; resolve: (r: ConvertResult) => void;
    reject: (e: Error) => void }> = [];
  const rendered: Array<{ svg: string; filename: string }> = [];
  const errors: unknown[] = [];
  const live = new LiveConversion({
    convert: (request) => new Promise((resolve, reject) => {
      // Model the real Worker transfer, including detachment on the main thread.
      const received = structuredClone(request, { transfer: [request.imageBytes.buffer] });
      requests.push({ request: received, resolve, reject });
    }),
    getConfig: () => config,
    onInvalidate: () => { invalidations++; },
    onStart: () => { starts++; },
    onResult: (r, image) => { rendered.push({ svg: r.svg, filename: image.filename }); },
    onError: (e) => { errors.push(e); },
    onSettled: () => { settlements++; },
  });
  t.after(() => live.dispose());
  return { live, requests, rendered, errors, config: (c: PlateConfig) => { config = c; },
    invalidations: () => invalidations, starts: () => starts, settlements: () => settlements,
    tick: () => t.mock.timers.tick(SETTINGS_DEBOUNCE_MS) };
}

test("settings alone never start a conversion before an image is selected", (t) => {
  const h = harness(t);
  h.live.settingsChanged(); h.tick();
  assert.equal(h.requests.length, 0);
  assert.equal(h.invalidations(), 0);
});

test("preset changes, toggles and reset reconvert retained bytes after worker transfer", async (t) => {
  const h = harness(t); const image = source();
  h.live.setImage(image);
  h.requests[0]!.resolve(result("original")); await flush();
  for (const config of [{ preset: "logo" }, { removeBackground: true }, {}] as PlateConfig[]) {
    const n = h.requests.length;
    h.config(config); h.live.settingsChanged();
    assert.equal(h.requests.length, n);
    h.tick();
    assert.deepEqual(h.requests[n]!.request.config, config);
    assert.deepEqual([...h.requests[n]!.request.imageBytes], [1, 2, 3]);
    h.requests[n]!.resolve(result(`updated-${n}`)); await flush();
  }
  assert.equal(h.rendered.length, 4);
  assert.deepEqual([...image.imageBytes], [1, 2, 3]);
  assert.equal(h.invalidations(), 4);
});

test("rapid slider changes debounce to one conversion with the latest settings", async (t) => {
  const h = harness(t);
  h.live.setImage(source()); h.requests[0]!.resolve(result("first")); await flush();
  h.config({ smooth: 1 }); h.live.settingsChanged();
  t.mock.timers.tick(200);
  h.config({ smooth: 2 }); h.live.settingsChanged();
  t.mock.timers.tick(200);
  assert.equal(h.requests.length, 1);
  h.tick();
  assert.equal(h.requests.length, 2);
  assert.deepEqual(h.requests[1]!.request.config, { smooth: 2 });
});

test("changes during conversion queue only the latest and discard the stale result", async (t) => {
  const h = harness(t);
  h.live.setImage(source());
  h.config({ simplify: 1 }); h.live.settingsChanged(); h.tick();
  h.config({ simplify: 2 }); h.live.settingsChanged(); h.tick();
  assert.equal(h.requests.length, 1, "never overlap worker requests");
  h.requests[0]!.resolve(result("stale")); await flush();
  assert.equal(h.rendered.length, 0);
  assert.equal(h.requests.length, 2);
  assert.deepEqual(h.requests[1]!.request.config, { simplify: 2 });
  h.requests[1]!.resolve(result("latest")); await flush();
  assert.deepEqual(h.rendered.map(r => r.svg), ["latest"]);
});

test("finishing an old run does not bypass an unfinished slider debounce", async (t) => {
  const h = harness(t);
  h.live.setImage(source()); h.live.settingsChanged();
  h.requests[0]!.resolve(result("stale")); await flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.rendered.length, 0);
  h.tick();
  assert.equal(h.requests.length, 2);
});

test("a replacement image supersedes active and queued work without mixing filenames", async (t) => {
  const h = harness(t);
  h.live.setImage(source("old.png"));
  h.live.settingsChanged();
  h.live.setImage(source("new.jpg"));
  h.requests[0]!.resolve(result("old")); await flush();
  assert.equal(h.requests.length, 2);
  assert.equal(h.requests[1]!.request.filename, "new.jpg");
  h.tick();
  assert.equal(h.requests.length, 2);
  h.requests[1]!.resolve(result("new")); await flush();
  assert.deepEqual(h.rendered, [{ svg: "new", filename: "new.jpg" }]);
});

test("stale errors are ignored and current errors allow another settings attempt", async (t) => {
  const h = harness(t);
  h.live.setImage(source()); h.live.settingsChanged(); h.tick();
  h.requests[0]!.reject(new Error("old")); await flush();
  assert.equal(h.errors.length, 0);
  h.requests[1]!.reject(new Error("current")); await flush();
  assert.equal(h.errors.length, 1);
  h.live.settingsChanged(); h.tick();
  assert.equal(h.requests.length, 3);
  h.requests[2]!.resolve(result("recovered")); await flush();
  assert.equal(h.rendered[0]!.svg, "recovered");
});

test("dispose clears pending work and ignores late results", async (t) => {
  const h = harness(t);
  h.live.setImage(source()); h.live.settingsChanged(); h.tick();
  h.live.dispose();
  h.requests[0]!.resolve(result("late")); await flush();
  h.tick(); h.live.setImage(source()); h.live.settingsChanged(); h.tick();
  assert.equal(h.requests.length, 1);
  assert.equal(h.rendered.length, 0);
  assert.equal(h.settlements(), 0);
});


test("cancel clears queued work but keeps the image available for a later retry", async (t) => {
  const h = harness(t);
  h.live.setImage(source()); h.live.settingsChanged(); h.tick();
  h.live.cancel(); h.requests[0]!.reject(new Error("cancelled")); await flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.errors.length, 0);
  h.live.settingsChanged(); h.tick();
  assert.equal(h.requests.length, 2);
});
