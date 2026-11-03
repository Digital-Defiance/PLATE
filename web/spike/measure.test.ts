/**
 * Tests for `runSpike` with fake runtime/IO ports: bring-up is timed apart from
 * the scenes, and a bring-up failure is still recorded and halts the spike.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { ConvertResult, PackageLoadResults } from "../src/protocol.js";
import type { Classification, Manifest, SpikeIO, SpikeRuntime } from "./measure.js";
import { SpikeInitError, runSpike } from "./measure.js";

const manifest: Manifest = {
  corpusN: 2,
  corpusSeed: 1,
  bakeoffTolerance: 0.01,
  scenes: [
    { name: "scene00", filename: "scene00.png", imageBytesB64: "iVBORw==", cliSvg: "<svg/>", cliComposite: 0.9 },
    { name: "scene01_jpg", filename: "scene01_jpg.jpg", imageBytesB64: "/9j/", cliSvg: "<svg/>", cliComposite: 0.8 },
  ],
};

const allPass: PackageLoadResults = {
  numpy: "pass",
  scipy: "pass",
  "opencv-python": "pass",
  pillow: "pass",
  "scikit-image": "pass",
};

/** IO that records writes and scores every written SVG byte-identical. */
function fakeIO(): SpikeIO & { status: string[]; svgs: Map<string, string> } {
  const svgs = new Map<string, string>();
  const status: string[] = [];
  return {
    svgs,
    status,
    readManifest: async () => manifest,
    writeBrowserSvg: async (name, svg) => {
      svgs.set(name, svg);
    },
    scoreBrowserSvgs: async (): Promise<Classification> => ({
      bakeoffTolerance: 0.01,
      scenes: manifest.scenes.map((s) =>
        svgs.has(s.name)
          ? { name: s.name, classification: "byte-identical", cliComposite: s.cliComposite, compositeDiff: 0 }
          : { name: s.name, classification: "missing-browser-svg", cliComposite: s.cliComposite },
      ),
    }),
    writeStatus: async (markdown) => {
      status.push(markdown);
    },
  };
}

test("bring-up is timed separately and each scene time covers only its conversion", async () => {
  let clock = 0;
  const runtime: SpikeRuntime = {
    init: async () => {
      clock += 7000; // 7 s of one-time bring-up
      return allPass;
    },
    convert: async (): Promise<ConvertResult> => {
      clock += 500; // 0.5 s per conversion
      // The engine reports snake_case stat keys (`t_total`), not ConvertStats' camelCase.
      const stats = { t_total: 0.4 } as unknown as ConvertResult["stats"];
      return { svg: "<svg/>", stats, layers: [], warnings: [] };
    },
    runtimeInfo: () => ({ pyodide: "314.0.7", python: "3.14.2", versions: { numpy: "2.4.6" } }),
  };
  const io = fakeIO();
  const { report, verdict } = await runSpike({ runtime, io, now: () => clock });

  assert.equal(report.bringUp.seconds, 7);
  assert.equal(report.bringUp.error, undefined);
  assert.deepEqual(report.scenes.map((s) => s.seconds), [0.5, 0.5]);
  assert.deepEqual(report.scenes.map((s) => s.engineSeconds), [0.4, 0.4]);
  assert.equal(report.runtime?.pyodide, "314.0.7");
  assert.equal(verdict.status, "met");
  assert.equal(io.status.length, 1);
  assert.match(io.status[0]!, /Runtime bring-up .*\*\*7\.00s\*\*, ready\./);
});

test("a package failure at bring-up is recorded and halts with the opencv alternative", async () => {
  const packages: PackageLoadResults = { ...allPass, "opencv-python": "fail" };
  let converts = 0;
  const runtime: SpikeRuntime = {
    init: async () => {
      throw new SpikeInitError("required package(s) failed to load in Pyodide: opencv-python", packages);
    },
    convert: async () => {
      converts++;
      throw new Error("must not be called");
    },
  };
  const io = fakeIO();
  const { report, verdict } = await runSpike({ runtime, io, now: () => 0 });

  assert.equal(converts, 0);
  assert.deepEqual(report.packages, packages);
  assert.match(report.bringUp.error ?? "", /opencv-python/);
  assert.ok(report.scenes.every((s) => s.converted === "fail" && Number.isNaN(s.seconds)));
  assert.ok(report.scenes.every((s) => s.opencvLoad === "fail"));
  assert.equal(verdict.halt, true);
  assert.deepEqual(verdict.reasons.map((r) => r.point), ["opencv-load", "svg-equivalence"]);

  const block = io.status[0]!;
  assert.match(block, /\| `opencv-python` \| fail \|/);
  assert.match(block, /\| scene00 \| not run \|/);
  assert.match(block, /alternative approach:/);
});

test("a bring-up failure before the package loader records packages as not attempted", async () => {
  const runtime: SpikeRuntime = {
    init: async () => {
      throw new Error("worker error: script failed to load");
    },
    convert: async () => {
      throw new Error("must not be called");
    },
  };
  const io = fakeIO();
  const { report, verdict } = await runSpike({ runtime, io, now: () => 0 });

  assert.deepEqual(report.packages, {});
  assert.ok(report.scenes.every((s) => s.opencvLoad === "not attempted"));
  assert.deepEqual(verdict.reasons.map((r) => r.point), ["svg-equivalence"]);
  assert.match(io.status[0]!, /\| `numpy` \| not attempted \|/);
});
