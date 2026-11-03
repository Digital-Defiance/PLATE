/** Content-address the UI and worker so returning visitors receive a matching pair. */
import path from "node:path";
import fs from "node:fs/promises";
import { build, type Metafile } from "esbuild";

function entryFile(meta: Metafile, source: string): string {
  const output = Object.entries(meta.outputs).find(([, info]) =>
    info.entryPoint !== undefined && path.resolve(info.entryPoint) === path.resolve(source));
  if (!output) throw new Error(`No bundled entry for ${source}`);
  return path.basename(output[0]);
}

export async function buildBrowserBundles(srcDir: string, outDir: string, revision: string) {
  const sourceDir = await fs.realpath(srcDir);
  const common = {
    outdir: outDir, bundle: true, format: "esm" as const, platform: "browser" as const,
    target: "es2022", sourcemap: true, minify: true, logLevel: "warning" as const,
    entryNames: "[name]-[hash]", metafile: true as const,
  };
  const workerSource = path.join(sourceDir, "worker.ts");
  const worker = await build({
    ...common, entryPoints: { worker: workerSource },
    define: { __PLATE_ENGINE_REVISION__: JSON.stringify(revision) },
  });
  const workerFile = entryFile(worker.metafile, workerSource);
  const mainSource = path.join(sourceDir, "main.ts");
  const clientSource = path.join(sourceDir, "client.ts");
  const app = await build({
    ...common, entryPoints: { main: mainSource, client: clientSource },
    define: { __PLATE_WORKER_URL__: JSON.stringify(`./${workerFile}`) },
  });
  return { workerFile, mainFile: entryFile(app.metafile, mainSource),
    clientFile: entryFile(app.metafile, clientSource) };
}

export function injectMainBundle(html: string, mainFile: string): string {
  const entry = 'src="./main.js"';
  if (!html.includes(entry)) throw new Error("Missing main.js script entry in the shell HTML");
  return html.replace(entry, `src="./${mainFile}"`);
}
