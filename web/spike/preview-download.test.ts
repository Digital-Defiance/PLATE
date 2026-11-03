/**
 * Unit tests for the result view's layer list + empty-state (web/src/preview.ts,
 * task 9.1) and the SVG download naming rule (web/src/download.ts, task 9.2).
 * These are task 9.3's tests; they pin Requirements 7.2, 7.3, 7.4, and 7.5.
 *
 * What each block covers:
 *   - Layer list (7.2): a result with several layers renders one `.layer-item`
 *     per `LayerInfo` in the summary's array order (the glue returns it
 *     bottom->top paint order), each showing the layer name and a kind label.
 *     Order, names, and kind labels are all asserted.
 *   - Empty state (7.3): a zero-layer result renders a single `.layer-empty`
 *     carrying `NO_LAYERS_MESSAGE` and NO `.layer-item` entries.
 *   - Warnings (7.6, bonus): each result warning renders as its own `.message`
 *     entry; blank/whitespace warnings are dropped.
 *   - clear(): resets the panes and revokes the source object URL (no blob
 *     leak) via an injected fake object-URL API.
 *   - Download naming (7.4/7.5): `downloadFilename` / `sourceBaseName` are
 *     exhaustively exercised against the spec's rule, including the odd cases
 *     (no extension, interior dots, trailing dot, dotfile, empty, bare
 *     extension, already-`.svg`, and path separators).
 *   - DownloadControl (7.4/7.5, bonus): enabling toggles `#download-row`, and a
 *     click triggers `saveSvg` with the computed name against an injected fake
 *     document + blob/URL env.
 *
 * A tiny fake DOM lets everything run under Node via tsx (mirrors
 * warnings.test.ts / settings.test.ts); the fakes implement only the members
 * the two modules touch and are cast to the DOM types at the boundary.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { ConvertResult, ConvertStats, LayerInfo } from "../src/protocol.js";
import {
  NO_LAYERS_MESSAGE,
  Preview,
  resolvePreviewElements,
  PREVIEW_ELEMENT_IDS,
  type ObjectUrlApi,
  type PreviewElements,
  type PreviewSource,
} from "../src/preview.js";
import {
  DEFAULT_BASE_NAME,
  DOWNLOAD_BUTTON_ID,
  DOWNLOAD_ROW_ID,
  DownloadControl,
  SVG_SUFFIX,
  downloadFilename,
  saveSvg,
  sourceBaseName,
  type AnchorLike,
  type DocumentLike,
  type DownloadEnv,
  type HTMLElementLike,
} from "../src/download.js";

/* -------------------------------------------------------------------------- */
/* Minimal fake DOM                                                            */
/* -------------------------------------------------------------------------- */

/** The slice of an element the two modules read/write; enough to assert output. */
class FakeElement {
  id = "";
  className = "";
  textContent = "";
  innerHTML = "";
  src = "";
  alt = "";
  decoding = "";
  href = "";
  download = "";
  disabled = false;
  children: FakeElement[] = [];
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
    this.children.push(child);
    return child;
  }

  removeChild(child: FakeElement): FakeElement {
    const i = this.children.indexOf(child);
    if (i >= 0) this.children.splice(i, 1);
    return child;
  }

  replaceChildren(...next: FakeElement[]): void {
    this.children = [...next];
    // Real DOM `replaceChildren()` also drops any markup set via innerHTML;
    // mirror that so clear() empties the SVG pane the way a browser would.
    this.innerHTML = "";
  }

  addEventListener(event: string, handler: () => void): void {
    const list = this.handlers.get(event) ?? [];
    list.push(handler);
    this.handlers.set(event, list);
  }

  removeEventListener(event: string, handler: () => void): void {
    const list = this.handlers.get(event);
    if (!list) return;
    const i = list.indexOf(handler);
    if (i >= 0) list.splice(i, 1);
  }

  click(): void {
    this.dispatch("click");
  }

  /** Fire the registered handlers for an event, mimicking a user interaction. */
  dispatch(event: string): void {
    for (const handler of [...(this.handlers.get(event) ?? [])]) handler();
  }
}

/** A fake `document` resolving by id, minting fake elements, with a body. */
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

/** A recording object-URL API so tests can assert create/revoke calls (no DOM). */
class FakeObjectUrl implements ObjectUrlApi {
  readonly created: string[] = [];
  readonly revoked: string[] = [];
  private counter = 0;

  createObjectURL(_blob: Blob): string {
    const url = `blob:fake/${this.counter++}`;
    this.created.push(url);
    return url;
  }

  revokeObjectURL(url: string): void {
    this.revoked.push(url);
  }
}

/* Cast helpers: the fakes implement only what the modules touch. */
function asDocument(doc: FakeDocument): Document {
  return doc as unknown as Document;
}
function asPreviewElements(els: Record<keyof PreviewElements, FakeElement>): PreviewElements {
  return els as unknown as PreviewElements;
}

/* -------------------------------------------------------------------------- */
/* Builders                                                                    */
/* -------------------------------------------------------------------------- */

/** Minimal stats object; the preview ignores stats, so values are arbitrary. */
function makeStats(): ConvertStats {
  return {
    shapes: 0,
    completed: 0,
    anchors: 0,
    primitives: 0,
    gradients: 0,
    strokes: 0,
    t_segment: 0,
    t_order: 0,
    t_trace: 0,
    t_total: 0,
    vlm_names: 0,
  };
}

function makeResult(
  layers: LayerInfo[],
  opts: { svg?: string; warnings?: string[] } = {},
): ConvertResult {
  return {
    svg: opts.svg ?? "<svg xmlns='http://www.w3.org/2000/svg'></svg>",
    stats: makeStats(),
    layers,
    warnings: opts.warnings ?? [],
  };
}

function makeSource(filename = "logo.png"): PreviewSource {
  return { imageBytes: new Uint8Array([1, 2, 3, 4]), filename };
}

/** Build a Preview wired to a fresh fake DOM + recording object-URL API. */
function buildPreview() {
  const doc = new FakeDocument();
  const els: Record<keyof PreviewElements, FakeElement> = {
    result: new FakeElement("div"),
    sourcePreview: new FakeElement("div"),
    svgPreview: new FakeElement("div"),
    layerList: new FakeElement("ul"),
    messages: new FakeElement("div"),
  };
  const objectUrl = new FakeObjectUrl();
  const preview = new Preview({
    document: asDocument(doc),
    elements: asPreviewElements(els),
    objectUrl,
  });
  return { preview, els, objectUrl };
}

/* -------------------------------------------------------------------------- */
/* Layer list — ordering, names, kind labels (Requirement 7.2)                 */
/* -------------------------------------------------------------------------- */

test("renders one .layer-item per LayerInfo in summary (bottom->top) order", () => {
  const { preview, els } = buildPreview();
  const layers: LayerInfo[] = [
    { name: "background", kind: "layer", order: 0 },
    { name: "body", kind: "group", order: 1 },
    { name: "red circle", kind: "shape", order: 2 },
  ];
  preview.render(makeResult(layers), makeSource());

  const items = els.layerList.children;
  assert.equal(items.length, 3, "one entry per layer");
  // No empty-state entry present when there are layers.
  assert.equal(items.filter((c) => c.className === "layer-empty").length, 0);
  // Every entry is a .layer-item in the summary's array order.
  assert.deepEqual(
    items.map((c) => c.className),
    ["layer-item", "layer-item", "layer-item"],
  );
});

test("each .layer-item shows the layer name and kind label, in order", () => {
  const { preview, els } = buildPreview();
  const layers: LayerInfo[] = [
    { name: "background", kind: "layer", order: 0 },
    { name: "body", kind: "group", order: 1 },
    { name: "red circle", kind: "shape", order: 2 },
  ];
  preview.render(makeResult(layers), makeSource());

  const items = els.layerList.children;
  // Name span (.layer-name) carries each layer's own name, in paint order.
  const names = items.map(
    (it) => it.children.find((c) => c.className === "layer-name")?.textContent,
  );
  assert.deepEqual(names, ["background", "body", "red circle"]);

  // Kind span (.layer-kind) carries the human label for each kind.
  const kinds = items.map(
    (it) => it.children.find((c) => c.className === "layer-kind")?.textContent,
  );
  assert.deepEqual(kinds, ["Layer", "Group", "Shape"]);

  // data-order / data-kind preserve the machine-readable paint order + kind.
  assert.deepEqual(
    items.map((it) => it.getAttribute("data-order")),
    ["0", "1", "2"],
  );
  assert.deepEqual(
    items.map((it) => it.getAttribute("data-kind")),
    ["layer", "group", "shape"],
  );
});

test("a single-layer result renders exactly one .layer-item", () => {
  const { preview, els } = buildPreview();
  preview.render(makeResult([{ name: "only", kind: "layer", order: 0 }]), makeSource());
  assert.equal(els.layerList.children.length, 1);
  assert.equal(els.layerList.children[0]!.className, "layer-item");
});

test("re-rendering replaces the previous layer list (no stacking)", () => {
  const { preview, els } = buildPreview();
  preview.render(
    makeResult([
      { name: "a", kind: "layer", order: 0 },
      { name: "b", kind: "layer", order: 1 },
    ]),
    makeSource(),
  );
  assert.equal(els.layerList.children.length, 2);
  preview.render(makeResult([{ name: "c", kind: "shape", order: 0 }]), makeSource());
  assert.equal(els.layerList.children.length, 1);
  assert.equal(
    els.layerList.children[0]!.children.find((c) => c.className === "layer-name")
      ?.textContent,
    "c",
  );
});

/* -------------------------------------------------------------------------- */
/* Empty state — zero layers (Requirement 7.3)                                 */
/* -------------------------------------------------------------------------- */

test("a zero-layer result renders a single .layer-empty with NO_LAYERS_MESSAGE", () => {
  const { preview, els } = buildPreview();
  preview.render(makeResult([]), makeSource());

  const items = els.layerList.children;
  assert.equal(items.length, 1, "exactly one empty-state node");
  assert.equal(items[0]!.className, "layer-empty");
  assert.equal(items[0]!.textContent, NO_LAYERS_MESSAGE);
});

test("a zero-layer result renders NO .layer-item entries", () => {
  const { preview, els } = buildPreview();
  preview.render(makeResult([]), makeSource());
  assert.equal(
    els.layerList.children.filter((c) => c.className === "layer-item").length,
    0,
  );
});

test("rendering layers after an empty state clears the empty-state node", () => {
  const { preview, els } = buildPreview();
  preview.render(makeResult([]), makeSource());
  assert.equal(els.layerList.children[0]!.className, "layer-empty");
  preview.render(makeResult([{ name: "x", kind: "layer", order: 0 }]), makeSource());
  assert.equal(els.layerList.children.length, 1);
  assert.equal(els.layerList.children[0]!.className, "layer-item");
  assert.equal(
    els.layerList.children.filter((c) => c.className === "layer-empty").length,
    0,
  );
});

/* -------------------------------------------------------------------------- */
/* Warnings (Requirement 7.6, bonus) + clear()/object-URL revoke               */
/* -------------------------------------------------------------------------- */

test("each result warning renders as its own #messages entry", () => {
  const { preview, els } = buildPreview();
  preview.render(
    makeResult([{ name: "x", kind: "layer", order: 0 }], {
      warnings: ["palette reduced", "background kept"],
    }),
    makeSource(),
  );
  assert.equal(els.messages.children.length, 2);
  assert.deepEqual(
    els.messages.children.map((c) => c.textContent),
    ["palette reduced", "background kept"],
  );
  for (const entry of els.messages.children) {
    assert.equal(entry.className, "message");
    assert.equal(entry.getAttribute("data-kind"), "warning");
  }
});

test("blank/whitespace-only warnings are dropped", () => {
  const { preview, els } = buildPreview();
  preview.render(
    makeResult([{ name: "x", kind: "layer", order: 0 }], {
      warnings: ["", "   ", "real warning"],
    }),
    makeSource(),
  );
  assert.equal(els.messages.children.length, 1);
  assert.equal(els.messages.children[0]!.textContent, "real warning");
});

test("render creates a source object URL; clear() revokes it and resets panes", () => {
  const { preview, els, objectUrl } = buildPreview();
  preview.render(makeResult([{ name: "x", kind: "layer", order: 0 }]), makeSource());

  // A source object URL was created and is live (not yet revoked).
  assert.equal(objectUrl.created.length, 1);
  assert.equal(objectUrl.revoked.length, 0);
  assert.equal(els.result.getAttribute("data-ready"), "true");

  preview.clear();

  // clear() revokes the live URL and empties every pane.
  assert.deepEqual(objectUrl.revoked, objectUrl.created);
  assert.equal(els.sourcePreview.children.length, 0);
  assert.equal(els.svgPreview.innerHTML, "");
  assert.equal(els.layerList.children.length, 0);
  assert.equal(els.messages.children.length, 0);
  assert.equal(els.result.getAttribute("data-ready"), "false");
});

test("re-rendering revokes the prior source URL before minting a new one", () => {
  const { preview, objectUrl } = buildPreview();
  preview.render(makeResult([]), makeSource("a.png"));
  preview.render(makeResult([]), makeSource("b.png"));
  // Two created, and the first was revoked when the second render started.
  assert.equal(objectUrl.created.length, 2);
  assert.ok(objectUrl.revoked.includes(objectUrl.created[0]!));
});

test("the SVG preview uses the result's exact SVG markup", () => {
  const { preview, els } = buildPreview();
  const svg = "<svg xmlns='http://www.w3.org/2000/svg'><rect/></svg>";
  preview.render(makeResult([], { svg }), makeSource());
  assert.equal(els.svgPreview.innerHTML, svg);
});

/* -------------------------------------------------------------------------- */
/* resolvePreviewElements — id wiring                                          */
/* -------------------------------------------------------------------------- */

test("resolvePreviewElements resolves the shell's fixed ids", () => {
  const doc = new FakeDocument();
  for (const id of Object.values(PREVIEW_ELEMENT_IDS)) {
    const el = new FakeElement("div");
    el.id = id;
    doc.register(el);
  }
  const els = resolvePreviewElements(asDocument(doc));
  assert.equal((els.result as unknown as FakeElement).id, PREVIEW_ELEMENT_IDS.result);
  assert.equal((els.layerList as unknown as FakeElement).id, PREVIEW_ELEMENT_IDS.layerList);
});

test("resolvePreviewElements throws naming a missing shell element", () => {
  const doc = new FakeDocument();
  // Register all but #layer-list.
  for (const id of Object.values(PREVIEW_ELEMENT_IDS)) {
    if (id === PREVIEW_ELEMENT_IDS.layerList) continue;
    const el = new FakeElement("div");
    el.id = id;
    doc.register(el);
  }
  assert.throws(
    () => resolvePreviewElements(asDocument(doc)),
    new RegExp(`#${PREVIEW_ELEMENT_IDS.layerList}`),
  );
});

/* -------------------------------------------------------------------------- */
/* sourceBaseName — the "base name" extraction rule (Requirement 7.4/7.5)      */
/* -------------------------------------------------------------------------- */

const BASE_NAME_CASES: Array<[string, string]> = [
  ["logo.png", "logo"], // ordinary extension stripped
  ["photo.JPG", "photo"], // case-insensitive: only the final ext is removed
  ["logo", "logo"], // no extension to strip
  ["my.logo.v2.png", "my.logo.v2"], // only the FINAL extension stripped
  [".logo", ".logo"], // leading dot is not an extension (dotfile)
  // Dotfile vs bare-extension convention (see download.ts header): a segment
  // whose only dot is the leading one has no strippable extension, so the whole
  // segment is kept. A bare extension like ".png" is indistinguishable from a
  // dotfile by name alone, so it is kept as the base too (-> ".png"), rather
  // than fabricated into the default. Only truly empty/whitespace/separator-
  // ending names are "unavailable".
  [".png", ".png"], // bare extension kept as base (same rule as a dotfile)
  ["logo.", "logo"], // trailing dot -> empty extension stripped
  ["a/b/logo.png", "logo"], // POSIX directory part dropped
  ["a\\b\\logo.png", "logo"], // Windows directory part dropped
  ["", ""], // empty -> no base
  ["   ", ""], // whitespace-only -> no base
  ["a/b/", ""], // ends in a separator -> no final segment
  ["logo.svg", "logo"], // an already-.svg name strips its final .svg
];

for (const [input, expected] of BASE_NAME_CASES) {
  test(`sourceBaseName(${JSON.stringify(input)}) === ${JSON.stringify(expected)}`, () => {
    assert.equal(sourceBaseName(input), expected);
  });
}

/* -------------------------------------------------------------------------- */
/* downloadFilename — the full naming rule (Requirement 7.4/7.5)               */
/* -------------------------------------------------------------------------- */

const DEFAULT_NAME = `${DEFAULT_BASE_NAME}${SVG_SUFFIX}`; // "plate.svg"

const DOWNLOAD_CASES: Array<[string, string]> = [
  ["logo.png", "logo.svg"], // ordinary PNG
  ["photo.JPG", "photo.svg"], // uppercase JPG
  ["photo.jpeg", "photo.svg"], // jpeg
  ["my.logo.v2.png", "my.logo.v2.svg"], // interior dots preserved
  ["logo", "logo.svg"], // no extension
  [".logo", ".logo.svg"], // dotfile keeps the whole name as base
  // Bare extension is kept as the base (same rule as a dotfile; see the
  // BASE_NAME_CASES comment and the download.ts header): ".png" -> ".png.svg".
  [".png", ".png.svg"], // bare extension kept as base
  ["", DEFAULT_NAME], // empty -> default base
  ["   ", DEFAULT_NAME], // whitespace-only -> default base
  ["logo.", "logo.svg"], // trailing dot
  ["a/b/", DEFAULT_NAME], // ends in separator -> no base -> default
  ["a/b/logo.png", "logo.svg"], // path separators stripped
  ["a\\b\\logo.png", "logo.svg"], // windows separators stripped
  ["logo.svg", "logo.svg"], // already a .svg: idempotent (no doubling)
  ["my.logo.svg", "my.logo.svg"], // interior dots + already-.svg
];

for (const [input, expected] of DOWNLOAD_CASES) {
  test(`downloadFilename(${JSON.stringify(input)}) === ${JSON.stringify(expected)}`, () => {
    assert.equal(downloadFilename(input), expected);
  });
}

test("every downloadFilename output ends in exactly .svg", () => {
  for (const [input] of DOWNLOAD_CASES) {
    const out = downloadFilename(input);
    assert.ok(out.endsWith(SVG_SUFFIX), `${out} must end with ${SVG_SUFFIX}`);
    // And never doubles the extension.
    assert.ok(!out.endsWith(".svg.svg"), out);
  }
});

test("re-downloading a .svg name is idempotent (no extension doubling)", () => {
  const once = downloadFilename("logo.png");
  assert.equal(once, "logo.svg");
  const twice = downloadFilename(once);
  assert.equal(twice, "logo.svg");
});

/* -------------------------------------------------------------------------- */
/* saveSvg + DownloadControl — enable/row toggle + click saves (7.4/7.5)       */
/* -------------------------------------------------------------------------- */

/** Build a fake document with the two download controls registered. */
function buildDownloadDoc() {
  const doc = new FakeDocument();
  const button = new FakeElement("button");
  button.id = DOWNLOAD_BUTTON_ID;
  const row = new FakeElement("div");
  row.id = DOWNLOAD_ROW_ID;
  doc.register(button);
  doc.register(row);
  return { doc, button, row };
}

/** A recording download env (blob + object URL) so saveSvg needs no browser. */
function recordingEnv() {
  const saved: Array<{ parts: BlobPart[]; type: string | undefined }> = [];
  const created: string[] = [];
  const revoked: string[] = [];
  let counter = 0;
  const env: DownloadEnv = {
    createBlob: (parts, options) => {
      saved.push({ parts, type: options.type });
      return { size: 0, type: options.type ?? "" } as unknown as Blob;
    },
    createObjectURL: () => {
      const url = `blob:dl/${counter++}`;
      created.push(url);
      return url;
    },
    revokeObjectURL: (url) => {
      revoked.push(url);
    },
  };
  return { env, saved, created, revoked };
}

test("saveSvg builds an image/svg+xml blob, clicks a named anchor, and revokes the URL", () => {
  const { doc } = buildDownloadDoc();
  const { env, saved, created, revoked } = recordingEnv();

  saveSvg(doc as unknown as DocumentLike, "<svg/>", "logo.svg", env);

  assert.equal(saved.length, 1);
  assert.deepEqual(saved[0]!.parts, ["<svg/>"]);
  assert.equal(saved[0]!.type, "image/svg+xml");
  assert.equal(created.length, 1);
  // URL is revoked after the click (no blob leak).
  assert.deepEqual(revoked, created);
  // The anchor was attached and then detached (DOM left as found).
  assert.equal(doc.body.children.length, 0);
});

test("DownloadControl starts disabled with the row not ready", () => {
  const { doc, button, row } = buildDownloadDoc();
  const control = new DownloadControl(doc as unknown as DocumentLike);
  assert.equal(button.disabled, true);
  assert.equal(row.getAttribute("data-ready"), "false");
  control.dispose();
});

test("setResult enables the button and flips #download-row to ready", () => {
  const { doc, button, row } = buildDownloadDoc();
  const control = new DownloadControl(doc as unknown as DocumentLike);
  control.setResult(makeResult([]), "logo.png");
  assert.equal(button.disabled, false);
  assert.equal(row.getAttribute("data-ready"), "true");
  control.dispose();
});

test("clicking the enabled button saves the SVG under the computed .svg name", () => {
  const { doc, button } = buildDownloadDoc();
  const { env, saved, created } = recordingEnv();
  const control = new DownloadControl(doc as unknown as DocumentLike, env);

  // Capture the anchor's download name at click time.
  let savedName = "";
  const realCreate = doc.createElement.bind(doc);
  (doc as FakeDocument).createElement = ((tag: string) => {
    const a = realCreate(tag);
    const realClick = a.click.bind(a);
    a.click = () => {
      savedName = a.download;
      realClick();
    };
    return a;
  }) as FakeDocument["createElement"];

  control.setResult(makeResult([], { svg: "<svg>out</svg>" }), "my.logo.v2.png");
  button.click();

  assert.equal(saved.length, 1);
  assert.deepEqual(saved[0]!.parts, ["<svg>out</svg>"]);
  assert.equal(created.length, 1);
  assert.equal(savedName, "my.logo.v2.svg");
  control.dispose();
});

test("a whitespace/unavailable source name falls back to the default .svg name", () => {
  const { doc, button } = buildDownloadDoc();
  const { env } = recordingEnv();
  const control = new DownloadControl(doc as unknown as DocumentLike, env);

  let savedName = "";
  const realCreate = doc.createElement.bind(doc);
  (doc as FakeDocument).createElement = ((tag: string) => {
    const a = realCreate(tag);
    const realClick = a.click.bind(a);
    a.click = () => {
      savedName = a.download;
      realClick();
    };
    return a;
  }) as FakeDocument["createElement"];

  // An empty/whitespace source name is genuinely unavailable -> default base.
  // (A bare extension like ".png" does NOT hit this path; it is kept as the
  // base and saves as ".png.svg". See the download.ts header for the rule.)
  control.setResult(makeResult([]), "   ");
  button.click();
  assert.equal(savedName, `${DEFAULT_BASE_NAME}${SVG_SUFFIX}`);
  control.dispose();
});

test("reset() disables the button and a click after reset saves nothing", () => {
  const { doc, button, row } = buildDownloadDoc();
  const { env, saved } = recordingEnv();
  const control = new DownloadControl(doc as unknown as DocumentLike, env);

  control.setResult(makeResult([]), "logo.png");
  control.reset();
  assert.equal(button.disabled, true);
  assert.equal(row.getAttribute("data-ready"), "false");

  button.click(); // guarded no-op: no current result
  assert.equal(saved.length, 0);
  control.dispose();
});

test("DownloadControl construction throws when a wired element is missing", () => {
  const doc = new FakeDocument();
  const button = new FakeElement("button");
  button.id = DOWNLOAD_BUTTON_ID;
  doc.register(button); // #download-row intentionally absent
  assert.throws(
    () => new DownloadControl(doc as unknown as DocumentLike),
    new RegExp(`#${DOWNLOAD_ROW_ID}`),
  );
});

test("dispose() detaches the click listener so later clicks are inert", () => {
  const { doc, button } = buildDownloadDoc();
  const { env, saved } = recordingEnv();
  const control = new DownloadControl(doc as unknown as DocumentLike, env);
  control.setResult(makeResult([]), "logo.png");
  control.dispose();
  button.click();
  assert.equal(saved.length, 0, "a disposed control must not save on click");
});

// Satisfy noUnusedLocals for the imported AnchorLike/HTMLElementLike types that
// document the download seam; referenced here so the import is not flagged.
const _typeWitness: [AnchorLike | null, HTMLElementLike | null] = [null, null];
void _typeWitness;
