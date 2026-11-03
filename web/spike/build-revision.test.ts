import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { engineRevision } from "../build-revision.js";
import { buildBrowserBundles, injectMainBundle } from "../build-bundles.js";
import { fileURLToPath } from "node:url";
import { plateWheelUrl } from "../src/worker.js";

test("engine edits and packaging changes invalidate the wheel URL even at the same package version", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "plate-revision-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  await fs.mkdir(path.join(root, "src/plate/stages"), { recursive: true });
  await fs.writeFile(path.join(root, "pyproject.toml"), 'version = "0.1.0"');
  await fs.writeFile(path.join(root, "src/plate/web.py"), 'summary = "flat"');
  await fs.writeFile(path.join(root, "src/plate/stages/trace.py"), "trace = 1");
  const first = await engineRevision(root);
  assert.equal(first, await engineRevision(root), "unchanged content has a stable key");
  await fs.writeFile(path.join(root, "src/plate/web.py"), 'summary = "nested"');
  const glue = await engineRevision(root);
  assert.notEqual(first, glue);
  await fs.writeFile(path.join(root, "src/plate/stages/trace.py"), "trace = 2");
  const core = await engineRevision(root);
  assert.notEqual(glue, core);
  await fs.writeFile(path.join(root, "pyproject.toml"), 'version = "0.1.0"\nextra = true');
  assert.notEqual(core, await engineRevision(root));
  assert.notEqual(plateWheelUrl("https://example.org/worker.js", first),
    plateWheelUrl("https://example.org/worker.js", glue));
});

test("wheel revisions ignore timestamps and non-Python assets but include new source files", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "plate-revision-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  await fs.mkdir(path.join(root, "src/plate"), { recursive: true });
  await fs.writeFile(path.join(root, "pyproject.toml"), "version = 1");
  const source = path.join(root, "src/plate/web.py");
  await fs.writeFile(source, "same");
  const first = await engineRevision(root);
  await fs.utimes(source, new Date(0), new Date(0));
  await fs.writeFile(path.join(root, "src/plate/web.pyc"), "cache");
  assert.equal(first, await engineRevision(root));
  await fs.writeFile(path.join(root, "src/plate/new.py"), "new");
  assert.notEqual(first, await engineRevision(root));
});

test("versioned wheel URLs preserve the deployment path and the valid wheel filename", () => {
  const url = new URL(plateWheelUrl("https://example.org/PLATE/worker.js", "new-engine"));
  assert.equal(url.pathname, "/PLATE/plate_svg-0.1.0-py3-none-any.whl");
  assert.equal(url.searchParams.get("v"), "new-engine");
  assert.equal(plateWheelUrl("https://example.org/worker.js"),
    "https://example.org/plate_svg-0.1.0-py3-none-any.whl");
});


test("real UI and worker bundles get matching content URLs across engine, UI and worker updates", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "plate-bundles-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const src = path.join(root, "src"), out = path.join(root, "dist");
  await fs.cp(fileURLToPath(new URL("../src", import.meta.url)), src, { recursive: true });
  const first = await buildBrowserBundles(src, out, "engine-a");
  assert.match(first.mainFile, /^main-[A-Z0-9]+\.js$/);
  assert.match(first.workerFile, /^worker-[A-Z0-9]+\.js$/);
  assert.ok((await fs.readFile(path.join(out, first.mainFile), "utf8")).includes(first.workerFile));
  assert.equal(injectMainBundle('<script src="./main.js"></script>', first.mainFile),
    `<script src="./${first.mainFile}"></script>`);
  assert.deepEqual(await buildBrowserBundles(src, out, "engine-a"), first);

  const engineUpdate = await buildBrowserBundles(src, out, "engine-b");
  assert.notEqual(engineUpdate.workerFile, first.workerFile);
  assert.notEqual(engineUpdate.mainFile, first.mainFile);
  await fs.appendFile(path.join(src, "main.ts"), '\nconsole.info("UI cache regression");');
  const uiUpdate = await buildBrowserBundles(src, out, "engine-b");
  assert.equal(uiUpdate.workerFile, engineUpdate.workerFile);
  assert.notEqual(uiUpdate.mainFile, engineUpdate.mainFile);
  await fs.appendFile(path.join(src, "worker.ts"), '\nconsole.info("Worker cache regression");');
  const workerUpdate = await buildBrowserBundles(src, out, "engine-b");
  assert.notEqual(workerUpdate.workerFile, uiUpdate.workerFile);
  assert.notEqual(workerUpdate.mainFile, uiUpdate.mainFile);
  assert.ok((await fs.readFile(path.join(out, workerUpdate.mainFile), "utf8")).includes(workerUpdate.workerFile));
});

test("a missing shell entry fails the build instead of silently publishing stale script links", () => {
  assert.throws(() => injectMainBundle("<html></html>", "main-NEW.js"), /Missing main.js/);
});
