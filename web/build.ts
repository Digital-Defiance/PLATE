/**
 * Static shell bundler for the PLATE web page (deploy build).
 *
 * The deploy workflow (`.github/workflows/deploy-web.yml`, task 15.1) runs this
 * via `npm run build` to produce the publishable static shell. It bundles the
 * two shell entry points with esbuild — the UI app (`src/client.ts`, task 6.1)
 * and the Pyodide Web Worker (`src/worker.ts`, task 3.1) — into `dist/`, copies
 * `index.html` beside them, and leaves room for the workflow to drop the built
 * PLATE wheel next to the worker so the worker's same-origin relative wheel URL
 * (`PLATE_WHEEL_URL` in `src/worker.ts`) resolves on GitHub Pages.
 *
 * This mirrors the spike runner's esbuild call (`spike/run.ts`) so the deployed
 * worker is bundled exactly as the measured spike worker was. esbuild and tsx
 * are pinned in `package.json`; Pyodide itself is loaded from the pinned CDN by
 * the worker and is NOT bundled or vendored here.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import { engineRevision } from "./build-revision.js";

const WEB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
const SRC_DIR = path.join(WEB_DIR, "src");
const OUT_DIR = path.join(WEB_DIR, "dist");

/** Shell entry points: the page module, the UI app, and the Pyodide Worker. */
const ENTRY_POINTS = {
  // The page's module entry point (index.html loads ./main.js): composes the
  // finished shell modules (PlateClient + intake + settings + preview +
  // download + warnings + errors + links) and wires the DOM end-to-end.
  main: path.join(SRC_DIR, "main.ts"),
  // Task 6.1: the main-thread UI app wrapper (PlateClient + protocol).
  client: path.join(SRC_DIR, "client.ts"),
  // Task 3.1: the Pyodide runtime worker that runs the unchanged engine.
  worker: path.join(SRC_DIR, "worker.ts"),
};

async function main(): Promise<void> {
  // Fail clearly if a shell entry point is missing rather than emitting a
  // half-built site (e.g. if run before task 6.1's client.ts lands).
  for (const [name, entry] of Object.entries(ENTRY_POINTS)) {
    try {
      await fs.access(entry);
    } catch {
      throw new Error(`missing shell entry point "${name}": ${path.relative(WEB_DIR, entry)}`);
    }
  }

  await fs.rm(OUT_DIR, { recursive: true, force: true });
  await fs.mkdir(OUT_DIR, { recursive: true });

  const revision = await engineRevision(path.resolve(WEB_DIR, ".."));
  await build({
    define: { __PLATE_ENGINE_REVISION__: JSON.stringify(revision) },
    entryPoints: ENTRY_POINTS,
    outdir: OUT_DIR,
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    sourcemap: true,
    minify: true,
    logLevel: "warning",
  });

  // Copy the static shell page beside the bundled JS.
  await fs.copyFile(path.join(WEB_DIR, "index.html"), path.join(OUT_DIR, "index.html"));

  // A same-origin sample makes the product usable before a visitor brings a file.
  await fs.mkdir(path.join(OUT_DIR, "examples"), { recursive: true });
  await fs.copyFile(path.join(WEB_DIR, "..", "samples", "badge.png"),
    path.join(OUT_DIR, "examples", "badge.png"));

  // Ship the Pages custom-domain file so every artifact deploy re-asserts the
  // domain (this workflow publishes only the artifact; without CNAME in it a
  // deploy would drop the custom domain and revert to the github.io URL).
  await fs.copyFile(path.join(WEB_DIR, "CNAME"), path.join(OUT_DIR, "CNAME"));

  console.log(
    `[build] wrote shell bundle to ${path.relative(WEB_DIR, OUT_DIR)}/ ` +
      `(main.js, client.js, worker.js, index.html)`,
  );
}

main().catch((err: unknown) => {
  console.error(`[build] FAILED: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}`);
  process.exitCode = 1;
});
