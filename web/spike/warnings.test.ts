/**
 * Unit tests for the `#messages` renderer and the pre-conversion noise/JPEG beta
 * warning (web/src/warnings.ts, task 10.1).
 *
 * These cover every Requirement-4.4 / 7.6 / 8.4 path this module owns:
 *   - 4.4 the beta JPEG/noise warning surfaces when a result carries it (the
 *         `check_noise`-reports-both-jpeg-and-noisy signal that `convert_bytes`
 *         encodes as `BETA_JPEG_WARNING` in `result.warnings`), and is tagged so
 *         the shell can single it out.
 *   - 7.6 every result warning renders as its own `.message[data-kind="warning"]`
 *         entry; blank warnings are dropped; duplicates never stack.
 *   - 8.4 the privacy guard rejects cross-origin image egress and permits
 *         same-origin/worker targets.
 *
 * A tiny fake DOM stands in for the browser so everything runs under Node via
 * tsx (mirrors how `settings.ts` / `links.ts` keep `document` injectable). The
 * fake implements only the handful of `document`/element members warnings.ts
 * touches; it is cast to the DOM types at the boundary.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { ConvertResult } from "../src/protocol.js";
import {
  BETA_JPEG_WARNING,
  MESSAGES_CONTAINER_ID,
  assertNoImageEgress,
  clearMessages,
  isBetaJpegWarning,
  mountMessageArea,
  renderMessages,
  resultHasBetaJpegWarning,
  warningsToEntries,
  type MessageEntry,
} from "../src/warnings.js";

/* -------------------------------------------------------------------------- */
/* Minimal fake DOM                                                            */
/* -------------------------------------------------------------------------- */

/** The slice of an element warnings.ts uses; enough to assert rendered output. */
class FakeElement {
  id = "";
  className = "";
  textContent = "";
  readonly children: FakeElement[] = [];
  private readonly attrs = new Map<string, string>();

  constructor(readonly tagName: string) {}

  setAttribute(name: string, value: string): void {
    this.attrs.set(name, value);
  }

  getAttribute(name: string): string | null {
    return this.attrs.has(name) ? (this.attrs.get(name) as string) : null;
  }

  appendChild(child: FakeElement): FakeElement {
    this.children.push(child);
    return child;
  }

  replaceChildren(): void {
    this.children.length = 0;
  }
}

/** A fake `document` resolving elements by id and minting fake elements. */
class FakeDocument {
  readonly body = new FakeElement("body");
  private readonly byId = new Map<string, FakeElement>();

  register(el: FakeElement): FakeElement {
    if (el.id) this.byId.set(el.id, el);
    return el;
  }

  getElementById(id: string): FakeElement | null {
    return this.byId.get(id) ?? null;
  }

  createElement(tag: string): FakeElement {
    return new FakeElement(tag);
  }
}

/** Build a fake document plus a registered `#messages` container. */
function withMessagesContainer(): { doc: FakeDocument; container: FakeElement } {
  const doc = new FakeDocument();
  const container = new FakeElement("div");
  container.id = MESSAGES_CONTAINER_ID;
  container.className = "messages";
  doc.register(container);
  return { doc, container };
}

/** Cast helpers: the fake implements only what warnings.ts touches. */
function asDocument(doc: FakeDocument): Document {
  return doc as unknown as Document;
}
function asElement(el: FakeElement): HTMLElement {
  return el as unknown as HTMLElement;
}

function makeResult(warnings: string[]): Pick<ConvertResult, "warnings"> {
  return { warnings };
}

/* -------------------------------------------------------------------------- */
/* Beta JPEG warning recognition (Requirement 4.4)                             */
/* -------------------------------------------------------------------------- */

test("isBetaJpegWarning recognises the engine's exact beta text (and trims transport whitespace)", () => {
  assert.equal(isBetaJpegWarning(BETA_JPEG_WARNING), true);
  assert.equal(isBetaJpegWarning(`  ${BETA_JPEG_WARNING}\n`), true);
  assert.equal(isBetaJpegWarning("some other warning"), false);
  assert.equal(isBetaJpegWarning(""), false);
});

test("the pinned beta text matches the engine's wording (jpeg + noisy signal)", () => {
  // Guards against drift from src/plate/web.py BETA_JPEG_WARNING.
  assert.match(BETA_JPEG_WARNING, /^beta: compressed JPEG detected;/);
  assert.match(BETA_JPEG_WARNING, /hidden-object recovery is limited on noisy JPEGs today/);
});

test("resultHasBetaJpegWarning fires iff the result carries the beta warning", () => {
  assert.equal(resultHasBetaJpegWarning(makeResult([BETA_JPEG_WARNING])), true);
  assert.equal(
    resultHasBetaJpegWarning(makeResult(["unrelated", BETA_JPEG_WARNING])),
    true,
  );
  assert.equal(resultHasBetaJpegWarning(makeResult([])), false);
  assert.equal(resultHasBetaJpegWarning(makeResult(["unrelated only"])), false);
});

/* -------------------------------------------------------------------------- */
/* Rendering into #messages (Requirements 7.6 / 4.4)                           */
/* -------------------------------------------------------------------------- */

test("renderMessages writes one .message[data-kind] per entry, in order", () => {
  const { doc, container } = withMessagesContainer();
  const entries: MessageEntry[] = [
    { text: "first", kind: "warning" },
    { text: "second", kind: "error" },
    { text: "third", kind: "info" },
  ];
  const rendered = renderMessages(asElement(container), entries, {
    document: asDocument(doc),
  });

  assert.equal(rendered.length, 3);
  assert.equal(container.children.length, 3);
  const kinds = container.children.map((c) => c.getAttribute("data-kind"));
  assert.deepEqual(kinds, ["warning", "error", "info"]);
  const texts = container.children.map((c) => c.textContent);
  assert.deepEqual(texts, ["first", "second", "third"]);
  for (const child of container.children) {
    assert.equal(child.className, "message");
  }
});

test("renderMessages de-duplicates identical entries within one render", () => {
  const { doc, container } = withMessagesContainer();
  const rendered = renderMessages(
    asElement(container),
    [
      { text: "dup", kind: "warning" },
      { text: "dup", kind: "warning" },
      { text: "dup", kind: "error" }, // different kind -> not a duplicate
    ],
    { document: asDocument(doc) },
  );
  assert.equal(rendered.length, 2);
  assert.equal(container.children.length, 2);
});

test("renderMessages replaces previous content (clears between conversions)", () => {
  const { doc, container } = withMessagesContainer();
  const d = asDocument(doc);
  renderMessages(asElement(container), [{ text: "old", kind: "warning" }], { document: d });
  renderMessages(asElement(container), [{ text: "new", kind: "info" }], { document: d });
  assert.equal(container.children.length, 1);
  assert.equal(container.children[0]!.textContent, "new");
});

test("the beta JPEG warning renders tagged with data-beta='jpeg'", () => {
  const { doc, container } = withMessagesContainer();
  const rendered = renderMessages(
    asElement(container),
    [{ text: BETA_JPEG_WARNING, kind: "warning" }],
    { document: asDocument(doc) },
  );
  assert.equal(rendered.length, 1);
  assert.equal(rendered[0]!.getAttribute("data-kind"), "warning");
  assert.equal(rendered[0]!.getAttribute("data-beta"), "jpeg");
});

test("a non-beta warning is NOT tagged data-beta", () => {
  const { doc, container } = withMessagesContainer();
  const rendered = renderMessages(
    asElement(container),
    [{ text: "ordinary warning", kind: "warning" }],
    { document: asDocument(doc) },
  );
  assert.equal(rendered[0]!.getAttribute("data-beta"), null);
});

test("warningsToEntries maps every warning to a warning entry and drops blanks", () => {
  const entries = warningsToEntries([BETA_JPEG_WARNING, "", "   ", "another"]);
  assert.equal(entries.length, 2);
  assert.deepEqual(
    entries.map((e) => e.kind),
    ["warning", "warning"],
  );
  assert.equal(entries[0]!.text, BETA_JPEG_WARNING);
  assert.equal(entries[1]!.text, "another");
});

test("clearMessages empties the container", () => {
  const { doc, container } = withMessagesContainer();
  renderMessages(asElement(container), [{ text: "x", kind: "warning" }], {
    document: asDocument(doc),
  });
  assert.equal(container.children.length, 1);
  clearMessages(asElement(container));
  assert.equal(container.children.length, 0);
});

/* -------------------------------------------------------------------------- */
/* MessageArea handle                                                          */
/* -------------------------------------------------------------------------- */

test("mountMessageArea resolves the shell's #messages container", () => {
  const { doc, container } = withMessagesContainer();
  const area = mountMessageArea({ document: asDocument(doc) });
  assert.equal(area.container, asElement(container));
});

test("mountMessageArea creates a fallback container when the shell lacks one", () => {
  const doc = new FakeDocument();
  const area = mountMessageArea({ document: asDocument(doc) });
  assert.equal((area.container as unknown as FakeElement).id, MESSAGES_CONTAINER_ID);
  // attached to the fallback host (body)
  assert.equal(doc.body.children.length, 1);
});

test("showResultWarnings surfaces the beta JPEG warning among result warnings (4.4/7.6)", () => {
  const { doc } = withMessagesContainer();
  const area = mountMessageArea({ document: asDocument(doc) });
  const result = makeResult(["palette reduced", BETA_JPEG_WARNING]);

  const rendered = area.showResultWarnings(result);
  assert.equal(rendered.length, 2);

  const betaEl = rendered.find((el) => el.getAttribute("data-beta") === "jpeg");
  assert.ok(betaEl, "the beta JPEG warning must render as a tagged entry");
  assert.equal(betaEl!.textContent, BETA_JPEG_WARNING);
  assert.equal(area.hasBetaJpegWarning(result), true);
});

test("showResultWarnings renders nothing for a clean result", () => {
  const { doc } = withMessagesContainer();
  const area = mountMessageArea({ document: asDocument(doc) });
  const rendered = area.showResultWarnings(makeResult([]));
  assert.equal(rendered.length, 0);
  assert.equal(area.hasBetaJpegWarning(makeResult([])), false);
});

test("showWarning/showError/showInfo render a single kind-tagged entry", () => {
  const { doc } = withMessagesContainer();
  const area = mountMessageArea({ document: asDocument(doc) });

  assert.equal(area.showWarning("w")[0]!.getAttribute("data-kind"), "warning");
  assert.equal(area.showError("e")[0]!.getAttribute("data-kind"), "error");
  assert.equal(area.showInfo("i")[0]!.getAttribute("data-kind"), "info");
  // each call replaces the last -> exactly one entry remains
  assert.equal((area.container as unknown as FakeElement).children.length, 1);
});

/* -------------------------------------------------------------------------- */
/* Privacy guard (Requirement 8.4)                                             */
/* -------------------------------------------------------------------------- */

test("assertNoImageEgress permits same-origin / worker / blob targets", () => {
  const origin = "https://example.github.io";
  assert.doesNotThrow(() =>
    assertNoImageEgress(
      [
        "https://example.github.io/web/worker.js",
        "https://example.github.io/web/plate_svg-0.1.0-py3-none-any.whl",
        "./worker.js",
        "blob:https://example.github.io/abc-123",
      ],
      origin,
    ),
  );
  // No outbound targets at all is trivially fine.
  assert.doesNotThrow(() => assertNoImageEgress([], origin));
});

test("assertNoImageEgress rejects a cross-origin outbound target", () => {
  const origin = "https://example.github.io";
  assert.throws(
    () =>
      assertNoImageEgress(
        ["https://example.github.io/web/worker.js", "https://evil.example.com/upload"],
        origin,
      ),
    /image egress on the conversion path is forbidden/,
  );
});
