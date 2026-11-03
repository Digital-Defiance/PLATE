/** Stable engine cache key: source changes invalidate the same-version wheel URL. */
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

export async function engineRevision(repoRoot: string): Promise<string> {
  const engineDir = path.join(repoRoot, "src", "plate");
  const files = (await fs.readdir(engineDir, { recursive: true }))
    .filter(file => file.endsWith(".py"))
    .map(file => `src/plate/${file.split(path.sep).join("/")}`);
  const hash = createHash("sha256");
  for (const file of ["pyproject.toml", ...files].sort()) {
    hash.update(`${file}\0`);
    hash.update(await fs.readFile(path.join(repoRoot, file)));
    hash.update("\0");
  }
  return hash.digest("hex");
}
