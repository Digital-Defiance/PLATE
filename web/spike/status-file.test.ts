/**
 * Tests for the STATUS.md block splice (`replaceStatusBlock`).
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { STATUS_BLOCK_END, STATUS_BLOCK_START } from "./measure.js";
import { replaceStatusBlock } from "./status-file.js";

const block = (body: string): string => `${STATUS_BLOCK_START}\n\n${body}\n\n${STATUS_BLOCK_END}`;

test("appends the block after a blank line when STATUS.md has no spike block", () => {
  const existing = "# STATUS\n\n## Older entry\n- detail\n";
  const out = replaceStatusBlock(existing, block("first run"));
  assert.ok(out.startsWith(existing), "existing text must be kept as the prefix");
  assert.equal(out, `${existing}\n${block("first run")}\n`);
});

test("appends with a separator when the file does not end in a newline", () => {
  const out = replaceStatusBlock("# STATUS", block("x"));
  assert.equal(out, `# STATUS\n\n${block("x")}\n`);
});

test("replaces an existing block in place and keeps the text around it", () => {
  const before = "# STATUS\n\nintro\n\n";
  const after = "\n\n## Later section\n- keep me\n";
  const existing = `${before}${block("old numbers")}${after}`;
  const out = replaceStatusBlock(existing, block("new numbers"));
  assert.equal(out, `${before}${block("new numbers")}${after}`);
  assert.ok(!out.includes("old numbers"));
});

test("is idempotent: appending then replacing with the same block is stable", () => {
  const existing = "# STATUS\n- a\n";
  const once = replaceStatusBlock(existing, block("same"));
  assert.equal(replaceStatusBlock(once, block("same")), once);
  assert.equal(replaceStatusBlock(once, `${block("same")}\n\n`), once);
});

test("keeps the decision sub-block markers distinct from the outer markers", () => {
  const inner =
    "<!-- SPIKE:browser-web-page:decision:begin -->\nverdict\n<!-- SPIKE:browser-web-page:decision:end -->";
  const existing = `# STATUS\n\n${block(`v1\n${inner}`)}\ntrailer\n`;
  const out = replaceStatusBlock(existing, block(`v2\n${inner}`));
  assert.equal(out, `# STATUS\n\n${block(`v2\n${inner}`)}\ntrailer\n`);
});

test("refuses to edit when the markers are malformed", () => {
  const good = block("x");
  assert.throws(() => replaceStatusBlock(`a\n${STATUS_BLOCK_START}\nb\n`, good), /malformed/);
  assert.throws(() => replaceStatusBlock(`a\n${STATUS_BLOCK_END}\nb\n`, good), /malformed/);
  assert.throws(
    () => replaceStatusBlock(`${STATUS_BLOCK_END}\nmid\n${STATUS_BLOCK_START}\n`, good),
    /malformed/,
  );
  assert.throws(() => replaceStatusBlock(`${good}\n${good}\n`, good), /malformed/);
});

test("rejects a block that is not delimited by exactly one pair of markers", () => {
  assert.throws(() => replaceStatusBlock("# STATUS\n", "no markers"), /must start/);
  assert.throws(() => replaceStatusBlock("# STATUS\n", `${block("a")}\n${block("b")}`), /must start/);
});

test("never changes text outside the block (randomised prefixes and suffixes)", () => {
  // Deterministic LCG so a failure is reproducible.
  let seed = 12345;
  const rand = (n: number): number => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed % n;
  };
  const alphabet = "ab#|- \n<>!*`";
  const text = (): string =>
    Array.from({ length: rand(40) }, () => alphabet[rand(alphabet.length)]).join("");

  for (let i = 0; i < 300; i++) {
    const prefix = text();
    const suffix = text();
    const existing = `${prefix}${block(`old ${i}`)}${suffix}`;
    const out = replaceStatusBlock(existing, block(`new ${i}`));
    assert.equal(out, `${prefix}${block(`new ${i}`)}${suffix}`);

    const plain = `${prefix}${suffix}`;
    const appended = replaceStatusBlock(plain, block(`new ${i}`));
    assert.ok(appended.startsWith(plain));
    assert.ok(appended.endsWith(`${block(`new ${i}`)}\n`));
  }
});
