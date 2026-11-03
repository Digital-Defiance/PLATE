/**
 * Phase 1 spike runner (task 4): runs the spike harness for real.
 *
 * 1. Builds the PLATE wheel (`uv build --wheel`) and bundles the task-3.1 worker
 *    plus the page glue (`page.ts`) with esbuild, into `<dir>/serve/`.
 * 2. Serves that directory on 127.0.0.1 and opens it in headless Chromium
 *    (Playwright, fresh profile, so the first bring-up is a cold-cache load).
 * 3. In the page, `runSpike` drives every corpus scene through the worker; the
 *    page reaches the filesystem and the CPython scorer (`driver.py score`) via
 *    functions this runner exposes.
 * 4. STATUS.md is updated by replacing only the marker-delimited spike block
 *    (appended when absent); a copy of the previous file is kept in `<dir>`.
 *
 * Prerequisite, the CLI reference manifest:
 *   DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib .venv/bin/python web/spike/driver.py prepare -o /tmp/plate-spike
 * Run (from web/):
 *   npx tsx spike/run.ts --dir /tmp/plate-spike
 *
 * Exit status: 0 when no decision point tripped; 3 when the recorded verdict
 * halts the spike (a valid, recorded result); 1 when the runner itself failed.
 * All build outputs stay under `<dir>`, outside the repository.
 */

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import http from "node:http";
import type { AddressInfo } from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import { chromium } from "playwright";

import { appendDecisionToStatusBlock } from "./decision.js";
import type { Classification, Manifest, SpikeOutcome, SpikeSetup } from "./measure.js";
import type { SpikePageBridge } from "./page.js";
import { replaceStatusBlock } from "./status-file.js";

const WEB_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(WEB_DIR, "..");

/** Must match `PLATE_WHEEL_URL` in `web/src/worker.ts` (and pyproject's version). */
const EXPECTED_WHEEL = "plate_svg-0.1.0-py3-none-any.whl";

/** Scene names become file names; keep them to a safe alphabet. */
const SAFE_SCENE_NAME = /^[A-Za-z0-9_-]+$/;

const INDEX_HTML = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>PLATE spike</title></head>
<body>
<p>PLATE Phase 1 spike harness. Driven by web/spike/run.ts.</p>
<script type="module" src="./spike-page.js"></script>
</body>
</html>
`;

interface Options {
  dir: string;
  status: string;
  python: string;
  uv: string;
  dyld: string;
  timeoutMinutes: number;
  /** Python of a venv with Pyodide's library versions; enables the diagnostic. */
  diagPython: string | undefined;
}

function parseArgs(argv: string[]): Options {
  const opts: Options = {
    dir: "/tmp/plate-spike",
    status: path.join(REPO_ROOT, "STATUS.md"),
    python: path.join(REPO_ROOT, ".venv", "bin", "python"),
    uv: process.env["UV"] ?? path.join(os.homedir(), ".local", "bin", "uv"),
    dyld: "/opt/homebrew/lib",
    timeoutMinutes: 120,
    diagPython: undefined,
  };
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    const value = argv[i + 1];
    if (value === undefined) throw new Error(`missing value for ${flag}`);
    switch (flag) {
      case "--dir":
        opts.dir = value;
        break;
      case "--status":
        opts.status = value;
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
      case "--diag-python":
        opts.diagPython = value;
        break;
      default:
        throw new Error(`unknown option ${flag}`);
    }
    i++;
  }
  opts.dir = path.resolve(opts.dir);
  opts.status = path.resolve(opts.status);
  return opts;
}

/** Run a command to completion; resolve with stdout, reject with stderr on failure. */
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
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
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

/**
 * Replace (or append) the spike block in STATUS.md, keeping every other byte.
 * The previous file is copied into the spike dir first; the new file is written
 * to a temp file and renamed over STATUS.md so a crash cannot leave it truncated.
 */
async function writeStatus(statusPath: string, markdown: string, backupDir: string): Promise<void> {
  const before = await fs.readFile(statusPath, "utf8");
  const after = replaceStatusBlock(before, markdown);
  await fs.writeFile(path.join(backupDir, "STATUS.md.before-spike"), before, "utf8");
  const tmp = `${statusPath}.spike-${process.pid}.tmp`;
  try {
    await fs.writeFile(tmp, after, "utf8");
    await fs.rename(tmp, statusPath);
  } finally {
    await fs.rm(tmp, { force: true });
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number, what: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${what} timed out after ${ms / 60000} minutes`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/** Library versions in the CLI reference venv (the one `driver.py prepare` used). */
async function cliVersions(python: string, dyld: string): Promise<string> {
  const script = [
    "import importlib.metadata as md, json, sys",
    "import cv2, plate",
    "names = ['numpy', 'scipy', 'opencv-python-headless', 'opencv-python', 'pillow', 'scikit-image', 'cairosvg', 'plate-svg']",
    "v = {}",
    "for n in names:",
    "    try:",
    "        v[n] = md.version(n)",
    "    except md.PackageNotFoundError:",
    "        v[n] = None",
    "print(json.dumps({'python': sys.version.split()[0], 'cv2': cv2.__version__,",
    "                  'plate': plate.__file__, 'versions': v}))",
  ].join("\n");
  const out = await runCommand(python, ["-c", script], {
    cwd: REPO_ROOT,
    env: { ...process.env, DYLD_FALLBACK_LIBRARY_PATH: dyld },
  });
  const info = JSON.parse(out) as {
    python: string;
    cv2: string;
    plate: string;
    versions: Record<string, string | null>;
  };
  const installed = Object.entries(info.versions)
    .filter(([, version]) => version !== null)
    .map(([name, version]) => `${name} ${version}`)
    .join(", ");
  const plateDir = path.dirname(info.plate);
  const editable = plateDir.startsWith(REPO_ROOT + path.sep) ? " (editable install of this working tree)" : "";
  return (
    `Python ${info.python}; ${installed} (cv2.__version__ ${info.cv2}); ` +
    `plate imported from ${rel(plateDir)}${editable}`
  );
}

/** Pyodide's package names for the engine's module-load imports (as in worker.ts). */
const PYODIDE_PACKAGES = ["numpy", "scipy", "opencv-python", "pillow", "scikit-image"];

/**
 * Run `diagnose.py decode` inside Pyodide under Node (the pinned npm `pyodide`,
 * the same WebAssembly package builds the browser loads from the CDN), so the
 * diagnostic sees the decoder output the browser conversion started from.
 */
async function pyodideDecode(dir: string, wheelPath: string): Promise<void> {
  const { loadPyodide } = await import("pyodide");
  const pyodide = await loadPyodide({
    packageCacheDir: path.join(dir, "pyodide-node-cache") + path.sep,
    stdout: (msg: string) => console.log(`[pyodide-node] ${msg}`),
    stderr: (msg: string) => console.error(`[pyodide-node] ${msg}`),
  });
  await pyodide.loadPackage(PYODIDE_PACKAGES);
  await pyodide.loadPackage(wheelPath);
  const { FS } = pyodide;
  FS.mkdirTree("/spike");
  FS.mount(FS.filesystems.NODEFS, { root: dir }, "/spike");
  FS.mkdirTree("/tools");
  FS.mount(FS.filesystems.NODEFS, { root: path.join(WEB_DIR, "spike") }, "/tools");
  pyodide.runPython('import runpy\nrunpy.run_path("/tools/diagnose.py")["main"](["decode", "-o", "/spike"])');
}

/**
 * The agreed diagnostic for outside-tolerance scenes: rerun them natively in a
 * venv with Pyodide's library versions (after reinstalling the freshly built
 * browser wheel there), record the decoder output inside Pyodide, then attribute
 * each gap. Returns the Markdown section, or undefined when no scene is outside.
 */
async function runDiagnostic(opts: Options, diagPython: string, wheelPath: string): Promise<string | undefined> {
  const classification = JSON.parse(
    await fs.readFile(path.join(opts.dir, "classification.json"), "utf8"),
  ) as Classification;
  if (!classification.scenes.some((s) => s.classification === "outside-tolerance")) return undefined;
  const diagnose = path.join(WEB_DIR, "spike", "diagnose.py");
  const pyEnv = { ...process.env, DYLD_FALLBACK_LIBRARY_PATH: opts.dyld };
  console.log("[run] diagnostic: installing the browser wheel into the rerun venv");
  await runCommand(
    opts.uv,
    ["pip", "install", "--python", diagPython, "--no-deps", "--reinstall", wheelPath],
    { cwd: os.tmpdir(), echoStderr: true },
  );
  console.log("[run] diagnostic: rerunning the outside-tolerance scenes natively");
  await runCommand(diagPython, [diagnose, "convert", "-o", opts.dir], { cwd: os.tmpdir(), echoStderr: true });
  console.log("[run] diagnostic: recording decoder output inside Pyodide (Node)");
  await pyodideDecode(opts.dir, wheelPath);
  console.log("[run] diagnostic: attributing each gap");
  const markdown = await runCommand(opts.python, [diagnose, "compare", "-o", opts.dir], {
    cwd: REPO_ROOT,
    env: pyEnv,
    echoStderr: true,
  });
  return markdown.trim();
}

async function gitState(): Promise<string> {
  const head = (await runCommand("git", ["rev-parse", "--short", "HEAD"], { cwd: REPO_ROOT })).trim();
  const dirty = (await runCommand("git", ["status", "--porcelain"], { cwd: REPO_ROOT })).trim();
  return dirty ? `${head} plus uncommitted working-tree changes` : head;
}

/** A path as a reproduce command should show it: repo-relative, else `~`-relative. */
function rel(p: string): string {
  const r = path.relative(REPO_ROOT, p);
  if (!r.startsWith("..")) return r;
  const home = os.homedir();
  return p.startsWith(home + path.sep) ? `~${p.slice(home.length)}` : p;
}

function summarise(outcome: SpikeOutcome): string {
  const { report, verdict } = outcome;
  const lines: string[] = [];
  lines.push(`packages: ${JSON.stringify(report.packages)}`);
  lines.push(
    `bring-up: ${report.bringUp.seconds.toFixed(2)}s${report.bringUp.error ? ` FAILED: ${report.bringUp.error}` : ""}`,
  );
  const timed = report.scenes.filter((s) => Number.isFinite(s.seconds));
  if (timed.length > 0) {
    const sorted = [...timed].sort((a, b) => a.seconds - b.seconds);
    const mid = Math.floor(sorted.length / 2);
    const median =
      sorted.length % 2 === 1 ? sorted[mid]!.seconds : (sorted[mid - 1]!.seconds + sorted[mid]!.seconds) / 2;
    const slowest = sorted[sorted.length - 1]!;
    lines.push(
      `per-scene seconds: min ${sorted[0]!.seconds.toFixed(2)}, median ${median.toFixed(2)}, ` +
        `max ${slowest.seconds.toFixed(2)} (slowest: ${slowest.name})`,
    );
  }
  const counts = new Map<string, number>();
  for (const s of report.scenes) counts.set(s.classification, (counts.get(s.classification) ?? 0) + 1);
  lines.push(`classification: ${JSON.stringify(Object.fromEntries(counts))}`);
  lines.push(`verdict: ${verdict.status}${verdict.halt ? " (HALT)" : ""}`);
  for (const r of verdict.reasons) lines.push(`  - ${r.point}: ${r.message} [${r.scenes.join(", ")}]`);
  return lines.join("\n");
}

async function main(): Promise<number> {
  const opts = parseArgs(process.argv.slice(2));
  const dir = opts.dir;
  const manifestPath = path.join(dir, "manifest.json");
  const prepareCmd =
    `DYLD_FALLBACK_LIBRARY_PATH=${opts.dyld} ${rel(opts.python)} web/spike/driver.py prepare -o ${dir}`;
  try {
    await fs.access(manifestPath);
  } catch {
    throw new Error(`missing ${manifestPath}; build it first (from the repo root):\n  ${prepareCmd}`);
  }
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8")) as Manifest;
  for (const scene of manifest.scenes) {
    if (!SAFE_SCENE_NAME.test(scene.name)) throw new Error(`unsafe scene name in manifest: ${scene.name}`);
  }

  // Fresh outputs for this run: a stale browser SVG must never be scored.
  const browserDir = path.join(dir, "browser");
  const serveDir = path.join(dir, "serve");
  await fs.rm(browserDir, { recursive: true, force: true });
  await fs.rm(path.join(dir, "classification.json"), { force: true });
  await fs.rm(path.join(dir, "diag"), { recursive: true, force: true });
  await fs.rm(serveDir, { recursive: true, force: true });
  await fs.mkdir(browserDir, { recursive: true });
  await fs.mkdir(serveDir, { recursive: true });

  console.log(`[run] building ${EXPECTED_WHEEL} with ${opts.uv}`);
  await runCommand(opts.uv, ["build", "--wheel", "--out-dir", serveDir], { cwd: REPO_ROOT, echoStderr: true });
  const wheels = (await fs.readdir(serveDir)).filter((f) => f.endsWith(".whl"));
  if (wheels.length !== 1 || wheels[0] !== EXPECTED_WHEEL) {
    throw new Error(
      `expected exactly ${EXPECTED_WHEEL} (the name worker.ts fetches), got ${JSON.stringify(wheels)}`,
    );
  }
  const wheelSha = createHash("sha256")
    .update(await fs.readFile(path.join(serveDir, EXPECTED_WHEEL)))
    .digest("hex");

  console.log("[run] bundling worker + page with esbuild");
  await build({
    entryPoints: {
      worker: path.join(WEB_DIR, "src", "worker.ts"),
      "spike-page": path.join(WEB_DIR, "spike", "page.ts"),
    },
    outdir: serveDir,
    bundle: true,
    format: "esm",
    platform: "browser",
    target: "es2022",
    sourcemap: true,
    logLevel: "warning",
  });
  await fs.writeFile(path.join(serveDir, "index.html"), INDEX_HTML, "utf8");

  const pkg = JSON.parse(await fs.readFile(path.join(WEB_DIR, "package.json"), "utf8")) as {
    devDependencies: Record<string, string>;
  };
  const playwrightVersion = pkg.devDependencies["playwright"] ?? "unknown";
  const pyodidePin = pkg.devDependencies["pyodide"] ?? "unknown";
  const cliLibs = await cliVersions(opts.python, opts.dyld);
  const git = await gitState();

  const { server, origin } = await serveDirectory(serveDir);
  console.log(`[run] serving ${serveDir} at ${origin}`);
  const browser = await chromium.launch({ headless: true });
  try {
    const chromiumVersion = browser.version();
    const context = await browser.newContext();
    const page = await context.newPage();
    page.on("console", (msg) => {
      const source = msg.worker() ? "worker" : "page";
      console.log(`[${source}:${msg.type()}] ${msg.text()}`);
    });
    page.on("pageerror", (err) => console.error(`[pageerror] ${err.message}`));

    await page.exposeFunction("__spikeReadManifest", async (): Promise<Manifest> => manifest);
    await page.exposeFunction("__spikeWriteBrowserSvg", async (name: string, svg: string): Promise<void> => {
      if (!SAFE_SCENE_NAME.test(name)) throw new Error(`unsafe scene name: ${name}`);
      await fs.writeFile(path.join(browserDir, `${name}.svg`), svg, "utf8");
    });
    await page.exposeFunction("__spikeScore", async (): Promise<Classification> => {
      console.log("[run] scoring browser SVGs with driver.py score");
      await runCommand(opts.python, [path.join(WEB_DIR, "spike", "driver.py"), "score", "-o", dir], {
        cwd: REPO_ROOT,
        env: { ...process.env, DYLD_FALLBACK_LIBRARY_PATH: opts.dyld },
        echoStderr: true,
      });
      return JSON.parse(await fs.readFile(path.join(dir, "classification.json"), "utf8")) as Classification;
    });
    await page.exposeFunction("__spikeWriteStatus", async (markdown: string): Promise<void> => {
      let block = markdown;
      if (opts.diagPython !== undefined) {
        let section: string | undefined;
        try {
          section = await runDiagnostic(opts, opts.diagPython, path.join(serveDir, EXPECTED_WHEEL));
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          console.error(`[run] diagnostic FAILED: ${message}`);
          section = `### Diagnostic\n\nThe diagnostic failed and recorded nothing: ${message.split("\n")[0]}`;
        }
        if (section !== undefined) block = appendDecisionToStatusBlock(block, section);
      }
      await writeStatus(opts.status, block, dir);
      console.log(`[run] wrote the spike block to ${opts.status}`);
    });
    await page.exposeFunction("__spikeLog", (message: string): void => {
      console.log(`[spike] ${message}`);
    });

    const setup: SpikeSetup = {
      facts: [
        ["Run date (UTC)", new Date().toISOString()],
        ["Host", `${os.type()} ${os.release()} ${os.arch()}, ${os.cpus()[0]?.model ?? "unknown CPU"}`],
        [
          "Browser",
          `Chromium ${chromiumVersion} via Playwright ${playwrightVersion}, headless, fresh profile ` +
            "(cold cache: bring-up includes fetching Pyodide and the packages from the CDN)",
        ],
        ["Node", process.version],
        [
          "Pyodide",
          `${pyodidePin} pinned in web/src/worker.ts and web/package.json, loaded as an ES module ` +
            `in a module worker from https://cdn.jsdelivr.net/pyodide/v${pyodidePin}/full/`,
        ],
        [
          "PLATE wheel",
          `${EXPECTED_WHEEL} (sha256 ${wheelSha.slice(0, 16)}…), built with \`uv build --wheel\` from ` +
            `${git}; installed in Pyodide with micropip deps=False`,
        ],
        ["CLI reference venv (.venv)", cliLibs],
        [
          "Python command prefix",
          `DYLD_FALLBACK_LIBRARY_PATH=${opts.dyld} (cairocffi does not search Homebrew's lib dir; ` +
            "cairosvg needs it for driver.py prepare/score)",
        ],
        ["Spike working dir", `${dir} (manifest, corpus, browser SVGs, serve/ build outputs)`],
        ...(opts.diagPython !== undefined
          ? ([["Diagnostic rerun venv", `${opts.diagPython} (see the diagnostic section)`]] as Array<
              [string, string]
            >)
          : []),
      ],
      commands: [
        prepareCmd,
        ...(opts.diagPython !== undefined
          ? [
              "# diagnostic venv with Pyodide 314.0.7's library versions (outside the repo):",
              `${rel(opts.uv)} venv --python 3.14.2 ${path.dirname(path.dirname(opts.diagPython))}`,
              `${rel(opts.uv)} pip install --python ${opts.diagPython} numpy==2.4.6 scipy==1.18.0 ` +
                "opencv-python-headless==4.11.0.86 scikit-image==0.26.0 pillow==12.2.0",
            ]
          : []),
        `(cd web && npm ci && npx tsx spike/run.ts --dir ${dir}` +
          (opts.diagPython !== undefined ? ` --diag-python ${opts.diagPython})` : ")"),
        "# run.ts itself runs, in order:",
        `#   ${rel(opts.uv)} build --wheel --out-dir ${serveDir}`,
        "#   esbuild bundles web/src/worker.ts and web/spike/page.ts into the same dir",
        `#   DYLD_FALLBACK_LIBRARY_PATH=${opts.dyld} ${rel(opts.python)} web/spike/driver.py score -o ${dir}`,
        ...(opts.diagPython !== undefined
          ? [
              "#   then, only when a scene is outside tolerance:",
              `#   ${rel(opts.uv)} pip install --python ${opts.diagPython} --no-deps --reinstall <the built wheel>`,
              `#   ${opts.diagPython} web/spike/diagnose.py convert -o ${dir}`,
              "#   diagnose.py decode inside Pyodide under Node (npm pyodide 314.0.7)",
              `#   DYLD_FALLBACK_LIBRARY_PATH=${opts.dyld} ${rel(opts.python)} web/spike/diagnose.py compare -o ${dir}`,
            ]
          : []),
      ],
    };

    await page.goto(`${origin}/index.html`);
    await page.waitForFunction(
      () => typeof (window as unknown as SpikePageBridge).__plateRunSpike === "function",
    );
    console.log(`[run] Chromium ${chromiumVersion}; starting the spike (${manifest.scenes.length} scenes)`);
    const evaluation = page.evaluate(
      (s) => (window as unknown as SpikePageBridge).__plateRunSpike!(s),
      setup,
    );
    evaluation.catch(() => {}); // a timeout below closes the browser under it
    const outcome = await withTimeout(evaluation, opts.timeoutMinutes * 60_000, "spike run");
    console.log(`\n[run] summary\n${summarise(outcome)}`);
    return outcome.verdict.halt ? 3 : 0;
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
    console.error(`[run] FAILED: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}`);
    process.exitCode = 1;
  },
);
