/**
 * Unit tests for the error-surface behaviour of web/src/errors.ts (task 11.2;
 * Requirement 12). errors.ts (task 11.1) is NOT modified here — these tests pin
 * the behaviour it already implements:
 *
 *   - 12.1 a non-recoverable runtime/package failure surfaces the fixed
 *          "not supported in this browser yet" notice, carries a per-package
 *          breakdown when the worker recorded one, and is dismissible (stays
 *          until dismissed/reload).
 *   - 12.4 an `ImageLoadError` surfaces as a RECOVERABLE input error that shows
 *          the engine's own message verbatim with the recovery-hint lead.
 *   - 12.5 the on-load platform pre-check: a missing capability -> hard
 *          "unsupported" error; a capable unverified Safari -> soft "best in
 *          Chrome, Edge, Firefox" info notice; a capable non-Safari -> nothing.
 *          `detectPlatform` reads the probe booleans from a fake scope and must
 *          NOT flag a Chrome UA (which also contains "Safari") as Safari.
 *   - 12.7 the long-run notice offers keep-waiting / cancel, each wired to its
 *          handler and each removing the notice.
 *
 * Composability (design "Error Handling"): the error surfaces share `#messages`
 * with the preview/noise warnings (tasks 9.1/10.1). These tests prove a foreign
 * warning (`data-kind="warning"`, no `data-surface`) survives this module's
 * clearing and re-rendering, and that clearing only removes this module's own
 * `data-surface`-tagged entries.
 *
 * A tiny fake DOM stands in for the browser so everything runs under Node via
 * tsx (mirrors warnings.test.ts / settings.test.ts). Unlike those, errors.ts
 * clears via `container.querySelectorAll('.message[data-surface="…"]')` and
 * `node.remove()`, so the fake element implements both — a minimal selector
 * parser that understands `.message` and `[data-surface="…"]`.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { PackageLoadResults } from "../src/protocol.js";
import { PlateClientError } from "../src/client.js";
import {
  BRING_UP_TIMEOUT_MS,
  INPUT_RECOVERY_HINT,
  LONG_RUN_MESSAGE,
  LONG_RUN_THRESHOLD_MS,
  MESSAGES_CONTAINER_ID,
  PLATFORM_UNSUPPORTED_MESSAGE,
  RUNTIME_UNSUPPORTED_MESSAGE,
  SAFARI_COMPAT_MESSAGE,
  checkPlatformSupport,
  clearAllErrorSurfaces,
  clearSurface,
  describePackages,
  detectPlatform,
  entryFromClientError,
  renderClientError,
  renderErrorEntry,
  renderLongRunNotice,
  renderPlatformSupport,
  surfacePlatformCheck,
  type ErrorEntry,
  type PlatformProbe,
} from "../src/errors.js";

/* -------------------------------------------------------------------------- */
/* Minimal fake DOM (with querySelectorAll + remove, which errors.ts needs)    */
/* -------------------------------------------------------------------------- */

/**
 * The slice of an element errors.ts touches. Beyond the warnings.test.ts fake,
 * this adds: a parent pointer + `remove()` (the dismiss/clear paths detach a
 * node), `addEventListener`/`dispatch` (dismiss/keep/cancel buttons), and a
 * `querySelectorAll` that understands the two selectors errors.ts uses:
 *   `.message[data-surface="<surface>"]`
 */
class FakeElement {
  id = "";
  className = "";
  textContent = "";
  type = "";
  parent: FakeElement | null = null;
  readonly children: FakeElement[] = [];
  private readonly attrs = new Map<string, string>();
  private readonly handlers = new Map<string, Array<() => void>>();

  constructor(readonly tagName: string) {}

  setAttribute(name: string, value: string): void {
    this.attrs.set(name, value);
  }

  getAttribute(name: string): string | null {
    return this.attrs.has(name) ? (this.attrs.get(name) as string) : null;
  }

  appendChild(child: FakeElement): FakeElement {
    child.parent = this;
    this.children.push(child);
    return child;
  }

  remove(): void {
    const p = this.parent;
    if (!p) return;
    const i = p.children.indexOf(this);
    if (i >= 0) p.children.splice(i, 1);
    this.parent = null;
  }

  addEventListener(event: string, handler: () => void): void {
    const list = this.handlers.get(event) ?? [];
    list.push(handler);
    this.handlers.set(event, list);
  }

  /** Fire the registered handlers for an event, mimicking a user click. */
  dispatch(event: string): void {
    for (const handler of this.handlers.get(event) ?? []) handler();
  }

  /**
   * A deliberately tiny selector engine covering exactly what errors.ts asks
   * for: `.message[data-surface="<surface>"]`. Walks the direct children (the
   * container holds `.message` nodes as direct children, which is how the
   * renderers append them) and matches class + the data-surface attribute.
   */
  querySelectorAll(selector: string): FakeElement[] {
    const m = /^\.message\[data-surface="([^"]+)"\]$/.exec(selector);
    if (!m) throw new Error(`fake querySelectorAll: unsupported selector ${selector}`);
    const surface = m[1];
    return this.children.filter(
      (c) =>
        c.className.split(/\s+/).includes("message") &&
        c.getAttribute("data-surface") === surface,
    );
  }

  /** Find a descendant by class (test helper, not used by errors.ts). */
  findByClass(cls: string): FakeElement | undefined {
    const stack: FakeElement[] = [...this.children];
    while (stack.length > 0) {
      const el = stack.pop() as FakeElement;
      if (el.className.split(/\s+/).includes(cls)) return el;
      stack.push(...el.children);
    }
    return undefined;
  }
}

/** A fake `document` resolving elements by id and minting fake elements. */
class FakeDocument {
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

/** Cast helpers: the fake implements only what errors.ts touches. */
function asDocument(doc: FakeDocument): Document {
  return doc as unknown as Document;
}
function asElement(el: FakeElement): HTMLElement {
  return el as unknown as HTMLElement;
}

/** Seed a foreign warning (as tasks 9.1/10.1 render: no data-surface tag). */
function seedForeignWarning(container: FakeElement, text = "palette reduced"): FakeElement {
  const el = new FakeElement("div");
  el.className = "message";
  el.setAttribute("data-kind", "warning");
  el.textContent = text;
  container.appendChild(el);
  return el;
}

function allPass(): PackageLoadResults {
  return {
    numpy: "pass",
    scipy: "pass",
    "opencv-python": "pass",
    pillow: "pass",
    "scikit-image": "pass",
  };
}

/* -------------------------------------------------------------------------- */
/* checkPlatformSupport — pure classification (Requirement 12.5)               */
/* -------------------------------------------------------------------------- */

function probe(overrides: Partial<PlatformProbe> = {}): PlatformProbe {
  return {
    hasWorker: true,
    hasWebAssembly: true,
    hasModuleWorker: true,
    isSafari: false,
    ...overrides,
  };
}

test("checkPlatformSupport: a capable non-Safari browser is ok with no message", () => {
  const support = checkPlatformSupport(probe());
  assert.equal(support.supported, true);
  assert.equal(support.kind, "ok");
  assert.deepEqual(support.missing, []);
  assert.equal(support.message, undefined);
});

test("checkPlatformSupport: missing Worker -> unsupported, lists Worker", () => {
  const support = checkPlatformSupport(probe({ hasWorker: false }));
  assert.equal(support.supported, false);
  assert.equal(support.kind, "unsupported");
  assert.ok(support.missing.includes("Worker"));
  assert.equal(support.message, PLATFORM_UNSUPPORTED_MESSAGE);
});

test("checkPlatformSupport: missing WebAssembly -> unsupported, lists WebAssembly", () => {
  const support = checkPlatformSupport(probe({ hasWebAssembly: false }));
  assert.equal(support.supported, false);
  assert.equal(support.kind, "unsupported");
  assert.ok(support.missing.includes("WebAssembly"));
  assert.equal(support.message, PLATFORM_UNSUPPORTED_MESSAGE);
});

test("checkPlatformSupport: Worker present but no module-worker -> unsupported, lists 'module worker'", () => {
  const support = checkPlatformSupport(probe({ hasModuleWorker: false }));
  assert.equal(support.supported, false);
  assert.equal(support.kind, "unsupported");
  assert.ok(support.missing.includes("module worker"));
  assert.equal(support.message, PLATFORM_UNSUPPORTED_MESSAGE);
});

test("checkPlatformSupport: a missing Worker hides the module-worker miss (no double-report)", () => {
  // module worker only matters when Worker exists; a missing Worker dominates.
  const support = checkPlatformSupport(probe({ hasWorker: false, hasModuleWorker: false }));
  assert.deepEqual([...support.missing], ["Worker"]);
});

test("checkPlatformSupport: several missing capabilities are all listed", () => {
  const support = checkPlatformSupport(probe({ hasWorker: true, hasWebAssembly: false, hasModuleWorker: false }));
  assert.equal(support.kind, "unsupported");
  assert.ok(support.missing.includes("WebAssembly"));
  assert.ok(support.missing.includes("module worker"));
});

test("checkPlatformSupport: capable + Safari -> safari info notice with SAFARI_COMPAT_MESSAGE", () => {
  const support = checkPlatformSupport(probe({ isSafari: true }));
  assert.equal(support.supported, true);
  assert.equal(support.kind, "safari");
  assert.deepEqual(support.missing, []);
  assert.equal(support.message, SAFARI_COMPAT_MESSAGE);
});

test("checkPlatformSupport: a hard capability miss outranks Safari", () => {
  // Even on Safari, a missing capability is the dominant (unsupported) outcome.
  const support = checkPlatformSupport(probe({ isSafari: true, hasWebAssembly: false }));
  assert.equal(support.kind, "unsupported");
});

/* -------------------------------------------------------------------------- */
/* detectPlatform — probe booleans + Safari UA logic (Requirement 12.5)        */
/* -------------------------------------------------------------------------- */

const SAFARI_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 " +
  "(KHTML, like Gecko) Version/17.1 Safari/605.1.15";
const CHROME_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const EDGE_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, " +
  "like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0";
const FIREFOX_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0";

test("detectPlatform: reads hasWorker/hasWebAssembly from the scope globals", () => {
  const present = detectPlatform({
    Worker: function () {},
    WebAssembly: {},
    navigator: { userAgent: CHROME_UA },
  });
  assert.equal(present.hasWorker, true);
  assert.equal(present.hasWebAssembly, true);
  // hasModuleWorker mirrors hasWorker in this environment-free probe.
  assert.equal(present.hasModuleWorker, true);

  const absent = detectPlatform({ navigator: { userAgent: CHROME_UA } });
  assert.equal(absent.hasWorker, false);
  assert.equal(absent.hasWebAssembly, false);
  assert.equal(absent.hasModuleWorker, false);
});

test("detectPlatform: a genuine Safari UA is flagged isSafari", () => {
  const p = detectPlatform({ Worker: function () {}, WebAssembly: {}, navigator: { userAgent: SAFARI_UA } });
  assert.equal(p.isSafari, true);
});

test("detectPlatform: a Chrome UA (which contains 'Safari') is NOT flagged isSafari", () => {
  const p = detectPlatform({ Worker: function () {}, WebAssembly: {}, navigator: { userAgent: CHROME_UA } });
  assert.equal(p.isSafari, false);
});

test("detectPlatform: an Edge UA is NOT flagged isSafari", () => {
  const p = detectPlatform({ Worker: function () {}, WebAssembly: {}, navigator: { userAgent: EDGE_UA } });
  assert.equal(p.isSafari, false);
});

test("detectPlatform: a Firefox UA is NOT flagged isSafari", () => {
  const p = detectPlatform({ Worker: function () {}, WebAssembly: {}, navigator: { userAgent: FIREFOX_UA } });
  assert.equal(p.isSafari, false);
});

test("detectPlatform: a missing/empty userAgent is not Safari", () => {
  const p = detectPlatform({ Worker: function () {}, WebAssembly: {} });
  assert.equal(p.isSafari, false);
});

/* -------------------------------------------------------------------------- */
/* entryFromClientError — recoverable vs non-recoverable (Req 12.4 / 12.1)     */
/* -------------------------------------------------------------------------- */

test("entryFromClientError: a recoverable error -> input surface with the engine message verbatim", () => {
  const err = new PlateClientError("could not decode image: truncated PNG", {
    recoverable: true,
  });
  const entry = entryFromClientError(err);
  assert.equal(entry.surface, "input");
  assert.equal(entry.kind, "error");
  assert.equal(entry.recoverable, true);
  assert.equal(entry.message, INPUT_RECOVERY_HINT);
  // The engine's own message, verbatim, as the detail (never reworded).
  assert.equal(entry.detail, "could not decode image: truncated PNG");
});

test("entryFromClientError: a non-recoverable error -> runtime surface with the fixed notice", () => {
  const err = new PlateClientError("opencv-python failed to install", {
    recoverable: false,
  });
  const entry = entryFromClientError(err);
  assert.equal(entry.surface, "runtime");
  assert.equal(entry.kind, "error");
  assert.equal(entry.recoverable, false);
  assert.equal(entry.message, RUNTIME_UNSUPPORTED_MESSAGE);
  assert.equal(entry.dismissible, true);
  // No packages recorded -> no per-package breakdown.
  assert.equal(entry.detail, undefined);
});

test("entryFromClientError: a non-recoverable error with packages -> per-package breakdown detail", () => {
  const packages: PackageLoadResults = {
    numpy: "pass",
    scipy: "pass",
    "opencv-python": "fail",
    pillow: "pass",
    "scikit-image": "pass",
  };
  const err = new PlateClientError("bring-up failed", { recoverable: false, packages });
  const entry = entryFromClientError(err);
  assert.equal(entry.surface, "runtime");
  assert.ok(entry.detail, "a packages breakdown must be present");
  assert.equal(entry.detail, describePackages(packages));
  assert.match(entry.detail!, /opencv-python: failed/);
  assert.match(entry.detail!, /numpy: loaded/);
});

test("describePackages: renders loaded/failed for each package", () => {
  const text = describePackages(allPass());
  assert.match(text, /^Package load — /);
  assert.match(text, /numpy: loaded/);
  assert.match(text, /scipy: loaded/);
  assert.match(text, /opencv-python: loaded/);
});

/* -------------------------------------------------------------------------- */
/* renderErrorEntry — DOM output + per-surface replacement (Req 12.1/12.4)     */
/* -------------------------------------------------------------------------- */

function inputEntry(detail = "decode failed"): ErrorEntry {
  return {
    kind: "error",
    surface: "input",
    message: INPUT_RECOVERY_HINT,
    detail,
    recoverable: true,
    dismissible: true,
  };
}

test("renderErrorEntry: writes a .message tagged with data-kind + data-surface", () => {
  const { doc, container } = withMessagesContainer();
  const el = renderErrorEntry(inputEntry(), { container: asElement(container), document: asDocument(doc) });
  assert.equal((el as unknown as FakeElement).className, "message");
  assert.equal((el as unknown as FakeElement).getAttribute("data-kind"), "error");
  assert.equal((el as unknown as FakeElement).getAttribute("data-surface"), "input");
  assert.equal((el as unknown as FakeElement).getAttribute("data-recoverable"), "true");
  assert.equal(container.children.length, 1);
  // message text + detail line are rendered.
  const node = el as unknown as FakeElement;
  assert.equal(node.findByClass("message-text")!.textContent, INPUT_RECOVERY_HINT);
  assert.equal(node.findByClass("message-detail")!.textContent, "decode failed");
});

test("renderErrorEntry: a second entry for the SAME surface replaces the first (no stacking)", () => {
  const { doc, container } = withMessagesContainer();
  const opts = { container: asElement(container), document: asDocument(doc) };
  renderErrorEntry(inputEntry("first decode error"), opts);
  renderErrorEntry(inputEntry("second decode error"), opts);
  assert.equal(container.children.length, 1);
  assert.equal(
    (container.children[0] as FakeElement).findByClass("message-detail")!.textContent,
    "second decode error",
  );
});

test("renderErrorEntry: a different surface does NOT replace another surface's entry", () => {
  const { doc, container } = withMessagesContainer();
  const opts = { container: asElement(container), document: asDocument(doc) };
  renderErrorEntry(inputEntry(), opts);
  renderErrorEntry(
    {
      kind: "error",
      surface: "runtime",
      message: RUNTIME_UNSUPPORTED_MESSAGE,
      recoverable: false,
      dismissible: true,
    },
    opts,
  );
  // Two distinct surfaces coexist.
  assert.equal(container.children.length, 2);
  const surfaces = container.children.map((c) => c.getAttribute("data-surface")).sort();
  assert.deepEqual(surfaces, ["input", "runtime"]);
});

test("renderErrorEntry: leaves a foreign warning (no data-surface) untouched", () => {
  const { doc, container } = withMessagesContainer();
  const foreign = seedForeignWarning(container);
  renderErrorEntry(inputEntry(), { container: asElement(container), document: asDocument(doc) });
  // Foreign warning still present alongside the new input error.
  assert.ok(container.children.includes(foreign), "the foreign warning must survive");
  assert.equal(container.children.length, 2);
});

test("renderErrorEntry: the dismiss button removes the entry and calls onDismiss", () => {
  const { doc, container } = withMessagesContainer();
  const entry = inputEntry();
  const dismissed: ErrorEntry[] = [];
  const el = renderErrorEntry(entry, {
    container: asElement(container),
    document: asDocument(doc),
    onDismiss: (e) => dismissed.push(e),
  });
  const node = el as unknown as FakeElement;
  const button = node.findByClass("message-dismiss");
  assert.ok(button, "a dismissible entry must render a dismiss button");
  button!.dispatch("click");
  assert.equal(container.children.length, 0, "dismiss removes the entry");
  assert.deepEqual(dismissed, [entry], "onDismiss is called with the entry");
});

test("renderClientError: renders a recoverable client error as an input surface entry", () => {
  const { doc, container } = withMessagesContainer();
  const err = new PlateClientError("ImageLoadError: unsupported WebP", { recoverable: true });
  const el = renderClientError(err, { container: asElement(container), document: asDocument(doc) });
  const node = el as unknown as FakeElement;
  assert.equal(node.getAttribute("data-surface"), "input");
  assert.equal(node.findByClass("message-detail")!.textContent, "ImageLoadError: unsupported WebP");
});

/* -------------------------------------------------------------------------- */
/* renderPlatformSupport (Requirement 12.5)                                    */
/* -------------------------------------------------------------------------- */

test("renderPlatformSupport: 'ok' renders nothing and returns null", () => {
  const { doc, container } = withMessagesContainer();
  const result = renderPlatformSupport(
    { supported: true, kind: "ok", missing: [] },
    { container: asElement(container), document: asDocument(doc) },
  );
  assert.equal(result, null);
  assert.equal(container.children.length, 0);
});

test("renderPlatformSupport: 'safari' renders a dismissible info notice", () => {
  const { doc, container } = withMessagesContainer();
  const el = renderPlatformSupport(
    { supported: true, kind: "safari", missing: [], message: SAFARI_COMPAT_MESSAGE },
    { container: asElement(container), document: asDocument(doc) },
  );
  assert.ok(el, "safari notice must render");
  const node = el as unknown as FakeElement;
  assert.equal(node.getAttribute("data-kind"), "info");
  assert.equal(node.getAttribute("data-surface"), "platform");
  assert.equal(node.findByClass("message-text")!.textContent, SAFARI_COMPAT_MESSAGE);
  // Safari info is dismissible.
  assert.ok(node.findByClass("message-dismiss"), "safari notice is dismissible");
});

test("renderPlatformSupport: 'unsupported' renders a non-dismissible error with a Missing detail", () => {
  const { doc, container } = withMessagesContainer();
  const el = renderPlatformSupport(
    {
      supported: false,
      kind: "unsupported",
      missing: ["Worker", "WebAssembly"],
      message: PLATFORM_UNSUPPORTED_MESSAGE,
    },
    { container: asElement(container), document: asDocument(doc) },
  );
  assert.ok(el);
  const node = el as unknown as FakeElement;
  assert.equal(node.getAttribute("data-kind"), "error");
  assert.equal(node.getAttribute("data-surface"), "platform");
  assert.equal(node.findByClass("message-text")!.textContent, PLATFORM_UNSUPPORTED_MESSAGE);
  assert.match(node.findByClass("message-detail")!.textContent, /Missing: Worker, WebAssembly\./);
  // A hard platform miss stays put (not dismissible).
  assert.equal(node.findByClass("message-dismiss"), undefined);
});

test("surfacePlatformCheck: classifies a supplied probe and renders its notice", () => {
  const { doc, container } = withMessagesContainer();
  const support = surfacePlatformCheck({
    probe: probe({ isSafari: true }),
    container: asElement(container),
    document: asDocument(doc),
  });
  assert.equal(support.kind, "safari");
  assert.equal(container.children.length, 1);
  assert.equal(container.children[0]!.getAttribute("data-surface"), "platform");
});

test("surfacePlatformCheck: an 'ok' probe surfaces nothing", () => {
  const { doc, container } = withMessagesContainer();
  const support = surfacePlatformCheck({
    probe: probe(),
    container: asElement(container),
    document: asDocument(doc),
  });
  assert.equal(support.kind, "ok");
  assert.equal(container.children.length, 0);
});

/* -------------------------------------------------------------------------- */
/* renderLongRunNotice (Requirement 12.7)                                      */
/* -------------------------------------------------------------------------- */

test("renderLongRunNotice: renders the long-run message with keep/cancel controls", () => {
  const { doc, container } = withMessagesContainer();
  const el = renderLongRunNotice({}, { container: asElement(container), document: asDocument(doc) });
  const node = el as unknown as FakeElement;
  assert.equal(node.getAttribute("data-surface"), "long-run");
  assert.equal(node.getAttribute("data-kind"), "error");
  assert.equal(node.getAttribute("data-recoverable"), "true");
  assert.equal(node.findByClass("message-text")!.textContent, LONG_RUN_MESSAGE);
  assert.ok(node.findByClass("message-continue"), "a keep-waiting button must render");
  assert.ok(node.findByClass("message-cancel"), "a cancel button must render");
});

test("renderLongRunNotice: keep-waiting calls onContinue and removes the notice", () => {
  const { doc, container } = withMessagesContainer();
  let continued = 0;
  const el = renderLongRunNotice(
    { onContinue: () => (continued += 1) },
    { container: asElement(container), document: asDocument(doc) },
  );
  (el as unknown as FakeElement).findByClass("message-continue")!.dispatch("click");
  assert.equal(continued, 1);
  assert.equal(container.children.length, 0, "keep-waiting removes the notice");
});

test("renderLongRunNotice: cancel calls onCancel and removes the notice", () => {
  const { doc, container } = withMessagesContainer();
  let cancelled = 0;
  const el = renderLongRunNotice(
    { onCancel: () => (cancelled += 1) },
    { container: asElement(container), document: asDocument(doc) },
  );
  (el as unknown as FakeElement).findByClass("message-cancel")!.dispatch("click");
  assert.equal(cancelled, 1);
  assert.equal(container.children.length, 0, "cancel removes the notice");
});

test("renderLongRunNotice: a second notice replaces the first (no stacking)", () => {
  const { doc, container } = withMessagesContainer();
  const opts = { container: asElement(container), document: asDocument(doc) };
  renderLongRunNotice({}, opts);
  renderLongRunNotice({}, opts);
  assert.equal(container.children.length, 1);
});

/* -------------------------------------------------------------------------- */
/* clearSurface / clearAllErrorSurfaces — own entries only (composability)     */
/* -------------------------------------------------------------------------- */

test("clearSurface: removes only this module's entries for the named surface", () => {
  const { doc, container } = withMessagesContainer();
  const opts = { container: asElement(container), document: asDocument(doc) };
  renderErrorEntry(inputEntry(), opts);
  renderErrorEntry(
    { kind: "error", surface: "runtime", message: RUNTIME_UNSUPPORTED_MESSAGE, recoverable: false, dismissible: true },
    opts,
  );
  assert.equal(container.children.length, 2);

  clearSurface("input", opts);
  assert.equal(container.children.length, 1);
  assert.equal(container.children[0]!.getAttribute("data-surface"), "runtime");
});

test("clearSurface: leaves a foreign warning untouched", () => {
  const { doc, container } = withMessagesContainer();
  const opts = { container: asElement(container), document: asDocument(doc) };
  const foreign = seedForeignWarning(container);
  renderErrorEntry(inputEntry(), opts);
  clearSurface("input", opts);
  assert.ok(container.children.includes(foreign), "foreign warning survives clearSurface");
  assert.equal(container.children.length, 1);
});

test("clearAllErrorSurfaces: removes every owned surface but keeps foreign warnings", () => {
  const { doc, container } = withMessagesContainer();
  const opts = { container: asElement(container), document: asDocument(doc) };
  const foreign = seedForeignWarning(container);
  renderErrorEntry(inputEntry(), opts);
  renderErrorEntry(
    { kind: "error", surface: "runtime", message: RUNTIME_UNSUPPORTED_MESSAGE, recoverable: false, dismissible: true },
    opts,
  );
  renderPlatformSupport(
    { supported: true, kind: "safari", missing: [], message: SAFARI_COMPAT_MESSAGE },
    opts,
  );
  renderLongRunNotice({}, opts);
  // 4 owned surfaces + 1 foreign warning.
  assert.equal(container.children.length, 5);

  clearAllErrorSurfaces(opts);
  // Only the foreign warning remains.
  assert.equal(container.children.length, 1);
  assert.ok(container.children.includes(foreign), "foreign warning survives clearAllErrorSurfaces");
});

/* -------------------------------------------------------------------------- */
/* Exported constants (pin the acceptance-criteria copy + thresholds)          */
/* -------------------------------------------------------------------------- */

test("the thresholds match the acceptance criteria (120s long-run, 60s bring-up)", () => {
  assert.equal(LONG_RUN_THRESHOLD_MS, 120_000);
  assert.equal(BRING_UP_TIMEOUT_MS, 60_000);
});

test("the Safari copy degrades to a 'best in Chrome, Edge, Firefox' message", () => {
  assert.match(SAFARI_COMPAT_MESSAGE, /best in Chrome, Edge, Firefox/);
});
