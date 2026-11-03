/**
 * Headless-browser smoke test (task 18) — a BROWSER-ONLY integration test.
 *
 * This is NOT part of the pure-Python `pytest` suite and NOT part of the Node
 * `test:spike` unit suite (both stay fast and hermetic). It is the automated
 * form of the spike done-definition: it loads the ACTUAL web page in headless
 * Chromium, drops a fixed PNG sample onto the real drop zone, lets the page run
 * a conversion through the Web Worker + Pyodide, and asserts the SVG the page
 * produced equals the CLI SVG — byte-identical for a PNG (Requirement 1.2),
 * with the documented Bakeoff_Tolerance (0.01 composite) as the fallback band
 * (Requirement 1.3). It guards against the shell drifting from the CLI.
 *
 * Built on the Phase 1 harness (`web/spike/run.ts`): same `uv build --wheel` →
 * esbuild-bundle (now including `web/src/main.ts`, the page module) → serve on
 * 127.0.0.1 → Playwright headless Chromium pattern. The difference is it serves
 * the REAL `web/index.html` + its bundled modules and drives the conversion the
 * way a user does — a drop event on `#drop-zone` — then reads the result the
 * page computed (off `window.__plateApp`, which is exactly the SVG the page
 * injected into `#svg-preview`).
 *
 * Oracle: the CLI SVG from the UNCHANGED engine for the same sample + default
 * config, produced by `web/smoke/oracle.py` (which uses `pipeline.run` and
 * `bakeoff/score.py`). Prefix its Python with DYLD_FALLBACK_LIBRARY_PATH so
 * cairosvg's cairo is found for the composite fallback.
 *
 * Run (from web/):
 *   npm run smoke            # defaults: sample badge.png, dir /tmp/plate-smoke
 *   npm run smoke -- --sample badge.png --dir /tmp/plate-smoke
 *
 * Exit status: 0 when the page SVG matches the CLI oracle (byte-identical for a
 * PNG, or within Bakeoff_Tolerance as the fallback); 1 on any mismatch or
 * harness failure. All build outputs stay under `<dir>`, outside the repo.
 */

import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import http from "node:http";
import type { AddressInfo } from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import { chromium } from "playwright";

const WEB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_DIR, "..");

/** Must match `PLATE_WHEEL_URL` in `web/src/worker.ts` (and pyproject's version). */
const EXPECTED_WHEEL = "plate_svg-0.1.0-py3-none-any.whl";

/**
 * Bakeoff_Tolerance: the documented composite-score fallback band when the page
 * SVG is not byte-identical to the CLI (Requirement 1.3 / the glossary). 0.01,
 * matching `BAKEOFF_TOLERANCE` in `web/spike/driver.py`. For a PNG the real gate
 * is byte-identity; this band only applies on the non-identical fallback path.
 */
const BAKEOFF_TOLERANCE = 0.01;

interface Options {
  sample: string;
  dir: string;
  python: string;
  uv: string;
  dyld: string;
  timeoutMinutes: number;
  headful: boolean;
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    sample: "badge.png",
    dir: "/tmp/plate-smoke",
    python: path.join(REPO_ROOT, ".venv", "bin", "python"),
    uv: process.env["UV"] ?? path.join(os.homedir(), ".local", "bin", "uv"),
    dyld: "/opt/homebrew/lib",
    timeoutMinutes: 10,
    headful: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === "--headful") {
      opts.headful = true;
      continue;
    }
    const value = argv[i + 1];
    if (value === undefined) throw new Error(`missing value for ${flag}`);
    switch (flag) {
      case "--sample":
        opts.sample = value;
        break;
      case "--dir":
        opts.dir = value;
        break;
      case "--python":
        opts.python = value;
        break;
      case "--uv":
        opts.uv = value;
        break;
      case "--dyld":
        opts.dyld = value;
        break;
      case "--timeout-minutes":
        opts.timeoutMinutes = Number(value);
        break;
      default:
        throw new Error(`unknown option ${flag}`);
    }
    i++;
  }
  opts.dir = path.resolve(opts.dir);
  return opts;
}

interface Manifest {
  sample: string;
  filename: string;
  imageBytesB64: string;
  cliSvg: string;
  cliComposite: number;
}

/** The result the page exposes on `window.__plateApp` after a conversion. */
interface PageResult {
  svg: string;
  layers: Array<{ name: string; kind: string; order: number }>;
  warnings: string[];
}

/** Run a command to completion; resolve stdout, reject stderr on failure. */
function runCommand(
  cmd: string,
  args: string[],
  options: { cwd: string; env?: NodeJS.ProcessEnv; echoStderr?: boolean },
): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      cwd: options.cwd,
      env: options.env ?? process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => (stdout += chunk.toString("utf8")));
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
      if (options.echoStderr) process.stderr.write(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve(stdout);
      else reject(new Error(`${cmd} ${args.join(" ")} exited with ${code}\n${stderr}`));
    });
  });
}

/** Serve `root` read-only on 127.0.0.1 (random port), never outside `root`. */
function serveDirectory(root: string): Promise<{ server: http.Server; origin: string }> {
  const types: Record<string, string> = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".whl": "application/zip",
  };
  const server = http.createServer((req, res) => {
    void (async () => {
      try {
        const url = new URL(req.url ?? "/", "http://127.0.0.1");
        const rel = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
        const file = path.resolve(root, rel);
        if (!file.startsWith(root + path.sep)) {
          res.writeHead(403).end();
          return;
        }
        const body = await fs.readFile(file);
        res.writeHead(200, {
          "content-type": types[path.extname(file)] ?? "application/octet-stream",
          "cache-control": "no-store",
        });
        res.end(body);
      } catch {
        res.writeHead(404).end();
      }
    })();
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address() as AddressInfo;
      resolve({ server, origin: `http://127.0.0.1:${port}` });
    });
  });
}

function withTimeout<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${what} timed out after ${ms / 60000} minutes`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

async function main(): Promise<number> {
  const opts = parseArgs(process.argv.slice(2));
  const dir = opts.dir;
  const serveDir = path.join(dir, "serve");
  const manifestPath = path.join(dir, "manifest.json");

  // Fresh outputs for this run.
  await fs.rm(serveDir, { recursive: true, force: true });
  await fs.mkdir(serveDir, { recursive: true });

  // 1. CLI oracle: run the unchanged engine on the fixed sample.
  console.log(`[smoke] building the CLI oracle for ${opts.sample}`);
  await runCommand(
    opts.python,
    [path.join(WEB_DIR, "smoke", "oracle.py"), "--sample", opts.sample, "-o", manifestPath],
    { cwd: REPO_ROOT, env: { ...process.env, DYLD_FALLBACK_LIBRARY_PATH: opts.dyld }, echoStderr: true },
  );
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8")) as Manifest;

  // 2. Build the PLATE wheel exactly as the deploy build + spike do.
  console.log(`[smoke] building ${EXPECTED_WHEEL} with ${opts.uv}`);
  await runCommand(opts.uv, ["build", "--wheel", "--out-dir", serveDir], { cwd: REPO_ROOT, echoStderr: true });
  const wheels = (await fs.readdir(serveDir)).filter((f) => f.endsWith(".whl"));
  if (wheels.length !== 1 || wheels[0] !== EXPECTED_WHEEL) {
    throw new Error(`expected exactly ${EXPECTED_WHEEL}, got ${JSON.stringify(wheels)}`);
  }

  // 3. Bundle the REAL page modules (main + client + worker) and serve the real
  //    index.html — this is the actual deployed page, not a spike stub.
  console.log("[smoke] bundling main + client + worker with esbuild");
  await build({
    entryPoints: {
      main: path.join(WEB_DIR, "src", "main.ts"),
      client: path.join(WEB_DIR, "src", "client.ts"),
      worker: path.join(WEB_DIR, "src", "worker.ts"),
    },
    outdir: serveDir,
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    sourcemap: true,
    logLevel: "warning",
  });
  await fs.copyFile(path.join(WEB_DIR, "index.html"), path.join(serveDir, "index.html"));

  const { server, origin } = await serveDirectory(serveDir);
  console.log(`[smoke] serving ${serveDir} at ${origin}`);
  const browser = await chromium.launch({ headless: !opts.headful });
  try {
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("console", (msg) => {
      const source = msg.worker() ? "worker" : "page";
      console.log(`[${source}:${msg.type()}] ${msg.text()}`);
    });
    page.on("pageerror", (err) => console.error(`[pageerror] ${err.message}`));

    await page.goto(`${origin}/index.html`);

    // Wait for the page module to mount (main.ts sets window.__plateApp).
    await page.waitForFunction(() => Boolean((window as Window & { __plateApp?: unknown }).__plateApp));
    console.log("[smoke] page mounted; dropping the sample onto #drop-zone");

    const run = page.evaluate(
      async ({ filename, bytesB64 }) => {
        // Decode the sample bytes in-page (base64 → Uint8Array → File).
        const binary = atob(bytesB64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        const file = new File([bytes], filename, { type: "image/png" });

        const dropZone = document.getElementById("drop-zone");
        if (!dropZone) throw new Error("#drop-zone not found");

        // Dispatch a real drop event carrying the file, exactly as a user drop.
        const dt = new DataTransfer();
        dt.items.add(file);
        const drop = new DragEvent("drop", { bubbles: true, cancelable: true });
        Object.defineProperty(drop, "dataTransfer", { value: dt });
        dropZone.dispatchEvent(drop);

        // Wait for the conversion to finish: the result pane flips data-ready
        // and the app records the result. Poll both so we fail fast on an error.
        const appWin = window as Window & {
          __plateApp?: { lastResult(): unknown };
        };
        const deadline = Date.now() + 9 * 60 * 1000;
        for (;;) {
          const result = appWin.__plateApp?.lastResult();
          if (result) return result;
          const errorEl = document.querySelector(
            '#messages .message[data-kind="error"]',
          );
          if (errorEl) {
            throw new Error(`page surfaced an error: ${errorEl.textContent ?? ""}`);
          }
          if (Date.now() > deadline) throw new Error("conversion did not finish in time");
          await new Promise((r) => setTimeout(r, 250));
        }
      },
      { filename: manifest.filename, bytesB64: manifest.imageBytesB64 },
    );

    const started = Date.now();
    const pageResult = (await withTimeout(
      run,
      opts.timeoutMinutes * 60_000,
      "page conversion",
    )) as PageResult;
    const elapsed = ((Date.now() - started) / 1000).toFixed(1);
    console.log(`[smoke] conversion finished in ${elapsed}s (page loaded + Pyodide cold start + convert)`);

    // Sanity: the SVG the app holds is exactly what the preview pane shows.
    const previewSvg = await page.evaluate(
      () => document.getElementById("svg-preview")?.innerHTML ?? "",
    );
    if (!previewSvg.includes("<svg")) {
      throw new Error("the #svg-preview pane did not render an SVG");
    }

    // 4. Assert equivalence against the CLI oracle.
    const byteIdentical = pageResult.svg === manifest.cliSvg;
    if (byteIdentical) {
      console.log(
        `\n[smoke] PASS — page SVG is BYTE-IDENTICAL to the CLI output ` +
          `(sample=${manifest.sample}, ${manifest.cliSvg.length} chars, ` +
          `${pageResult.layers.length} layers).`,
      );
      return 0;
    }

    // Not byte-identical: fall back to the documented Bakeoff_Tolerance band
    // (Requirement 1.3). For a PNG this should not happen; score to report why.
    console.error("[smoke] page SVG was NOT byte-identical to the CLI SVG; scoring the difference");
    const browserSvgPath = path.join(dir, "browser.svg");
    await fs.writeFile(browserSvgPath, pageResult.svg, "utf8");
    const scoreOut = await runCommand(
      opts.python,
      [
        path.join(WEB_DIR, "smoke", "score.py"),
        "--sample",
        opts.sample,
        "--svg",
        browserSvgPath,
        "--cli-composite",
        String(manifest.cliComposite),
      ],
      { cwd: REPO_ROOT, env: { ...process.env, DYLD_FALLBACK_LIBRARY_PATH: opts.dyld }, echoStderr: true },
    );
    const { browserComposite, diff } = JSON.parse(scoreOut) as {
      browserComposite: number;
      diff: number;
    };
    const within = diff <= BAKEOFF_TOLERANCE;
    console.error(
      `[smoke] composite: cli=${manifest.cliComposite.toFixed(4)}, ` +
        `browser=${browserComposite.toFixed(4)}, diff=${diff.toFixed(4)}, ` +
        `tolerance=${BAKEOFF_TOLERANCE}`,
    );
    if (within) {
      console.log(
        `\n[smoke] PASS (fallback) — page SVG within Bakeoff_Tolerance of the CLI ` +
          `(diff ${diff.toFixed(4)} ≤ ${BAKEOFF_TOLERANCE}). A PNG was expected to be ` +
          `byte-identical; the browser SVG was saved to ${browserSvgPath}.`,
      );
      return 0;
    }
    console.error(
      `\n[smoke] FAIL — page SVG differs from the CLI beyond Bakeoff_Tolerance ` +
        `(diff ${diff.toFixed(4)} > ${BAKEOFF_TOLERANCE}). Browser SVG saved to ${browserSvgPath}.`,
    );
    return 1;
  } finally {
    await browser.close();
    server.close();
  }
}

main().then(
  (code) => {
    process.exitCode = code;
  },
  (err: unknown) => {
    console.error(`[smoke] FAILED: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}`);
    process.exitCode = 1;
  },
);
