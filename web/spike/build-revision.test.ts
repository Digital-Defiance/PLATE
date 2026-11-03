import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { engineRevision } from "../build-revision.js";
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
