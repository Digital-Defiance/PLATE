/**
 * Preview — render the source image, the converted SVG, the top-level layer
 * list, and any warnings into the Browser_Shell's existing DOM (main thread;
 * design Component 1 "show source vs SVG side by side with the layer list").
 *
 * This module owns the result view only. It is handed a {@link ConvertResult}
 * (the JSON-serialisable dict `plate.web.convert_bytes` returns, typed in
 * `./protocol.ts`) plus the source image bytes + filename the user uploaded,
 * and it fills the panes the static shell (`web/index.html`, task 6.1) already
 * ships: `#source-preview`, `#svg-preview`, `#layer-list`, `#messages`, and the
 * `#result[data-ready]` toggle. It never calls the engine or the worker; all
 * heavy work stays in the Conversion_Worker (Property 5: non-blocking main
 * thread). Rendering is cheap DOM work only.
 *
 * What it satisfies (Requirement 7):
 *   - 7.1 source image and SVG preview side by side, each at native aspect
 *     ratio without distortion. The shell's CSS (`.preview-body :where(img,svg)`
 *     with `height/width: auto`) does the no-distortion part; this module only
 *     injects an `<img>` (source) and the SVG markup (converted output) into the
 *     two panes and flips `#result[data-ready]` so they show together.
 *   - 7.2 render the top-level layer list from the result's layer summary in the
 *     summary's order (the glue returns it bottom->top paint order), showing each
 *     layer's name, using the shell's `.layer-item`/`.layer-kind` markup.
 *   - 7.3 a zero-layer summary shows an empty-state message (`.layer-empty`) and
 *     renders no `.layer-item` entries.
 *   - 7.6 each result warning renders as its own visible entry in `#messages`.
 *
 * Design decisions that matter:
 *   - Plain DOM, no framework; `document` is injectable so the renderer can be
 *     exercised in Node without a real browser (mirrors `settings.ts`/`links.ts`
 *     and keeps task 9.3's suite able to drive it against a DOM stub).
 *   - The SVG preview is the engine's exact SVG text, injected as markup so the
 *     browser renders it natively (design: "browsers render the SVG preview
 *     natively"; the preview must reflect the ACTUAL converted output, so the
 *     result's `svg` string is used verbatim, never re-derived).
 *   - The source image is shown from an object URL over the uploaded bytes; the
 *     URL is revoked on the next render and on {@link Preview.clear} so a long
 *     session converting many images does not leak blob URLs.
 *   - The download control is task 9.2 (`web/src/download.ts`); the pre-convert
 *     JPEG/noise warning is task 10.1 (`web/src/warnings.ts`). This module only
 *     surfaces the RESULT's own `warnings` and leaves those seams alone.
 */

import type { ConvertResult, LayerInfo } from "./protocol.js";

/** Default base name used for the source `<img>` alt text when none is known. */
const DEFAULT_SOURCE_ALT = "Source image";

/** Message the layer pane shows when the result has zero top-level layers (7.3). */
export const NO_LAYERS_MESSAGE = "No layers in this result.";

/** The DOM element ids the static shell (`web/index.html`) reserves for us. */
export const PREVIEW_ELEMENT_IDS = {
  result: "result",
  sourcePreview: "source-preview",
  svgPreview: "svg-preview",
  layerList: "layer-list",
  messages: "messages",
} as const;

/** Short, human-friendly label for each layer kind (shown in `.layer-kind`). */
const LAYER_KIND_LABELS: Record<LayerInfo["kind"], string> = {
  layer: "Layer",
  group: "Group",
  shape: "Shape",
};

/** The source image to render alongside the SVG: the user's uploaded bytes. */
export interface PreviewSource {
  /** Raw uploaded file bytes (the same bytes handed to the worker). */
  imageBytes: Uint8Array;
  /** Original filename; drives the `<img>` alt text and MIME guess. */
  filename: string;
}

/**
 * The shell DOM elements the renderer writes into. Resolved once from the
 * document (via {@link resolvePreviewElements}) or supplied directly in a test.
 */
export interface PreviewElements {
  /** `#result`: the container toggled via `data-ready` (7.1). */
  result: HTMLElement;
  /** `#source-preview`: pane for the uploaded image (7.1). */
  sourcePreview: HTMLElement;
  /** `#svg-preview`: pane for the converted SVG markup (7.1). */
  svgPreview: HTMLElement;
  /** `#layer-list`: the `<ul>` the layer entries go into (7.2, 7.3). */
  layerList: HTMLElement;
  /** `#messages`: where result warnings render as entries (7.6). */
  messages: HTMLElement;
}

/**
 * The minimal object-URL surface the renderer needs. Injectable so a Node test
 * can supply a fake without a DOM `URL` global; defaults to the ambient `URL`.
 */
export interface ObjectUrlApi {
  createObjectURL(blob: Blob): string;
  revokeObjectURL(url: string): void;
}

/** Options for {@link Preview}. */
export interface PreviewOptions {
  /** Document used to create elements / resolve ids; defaults to global `document`. */
  document?: Document;
  /**
   * Pre-resolved shell elements. When omitted they are looked up by id from the
   * document (the production path against `web/index.html`).
   */
  elements?: PreviewElements;
  /** Object-URL API for the source `<img>`; defaults to the global `URL`. */
  objectUrl?: ObjectUrlApi;
}

/** Resolve a usable `document`, erroring clearly in a non-DOM environment. */
function resolveDocument(doc?: Document): Document {
  const resolved = doc ?? globalThis.document;
  if (!resolved) {
    throw new Error(
      "preview.ts needs a document; pass one explicitly in a non-DOM environment",
    );
  }
  return resolved;
}

/** Resolve a usable object-URL API, erroring clearly when none exists. */
function resolveObjectUrl(api?: ObjectUrlApi): ObjectUrlApi {
  const resolved = api ?? (globalThis.URL as unknown as ObjectUrlApi | undefined);
  if (!resolved || typeof resolved.createObjectURL !== "function") {
    throw new Error(
      "preview.ts needs an object-URL API; pass one via options.objectUrl in a non-DOM environment",
    );
  }
  return resolved;
}

/**
 * Look up the shell's preview elements by their fixed ids (`web/index.html`).
 * Throws a descriptive error naming any missing id so a shell/renderer drift is
 * caught immediately rather than silently no-op'ing.
 */
export function resolvePreviewElements(doc: Document): PreviewElements {
  const get = (id: string): HTMLElement => {
    const el = doc.getElementById(id);
    if (!el) {
      throw new Error(`preview.ts: missing shell element #${id}`);
    }
    return el;
  };
  return {
    result: get(PREVIEW_ELEMENT_IDS.result),
    sourcePreview: get(PREVIEW_ELEMENT_IDS.sourcePreview),
    svgPreview: get(PREVIEW_ELEMENT_IDS.svgPreview),
    layerList: get(PREVIEW_ELEMENT_IDS.layerList),
    messages: get(PREVIEW_ELEMENT_IDS.messages),
  };
}

/** Lowercase file extension without the dot, or "" when there is none. */
function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  if (dot < 0 || dot === filename.length - 1) return "";
  return filename.slice(dot + 1).toLowerCase();
}

/** Best-effort MIME type for the source blob from the filename extension. */
function mimeForFilename(filename: string): string {
  switch (extensionOf(filename)) {
    case "png":
      return "image/png";
    case "jpg":
    case "jpeg":
      return "image/jpeg";
    default:
      // Let the browser sniff; an empty type on a Blob is still renderable.
      return "";
  }
}

/** Number of drawable leaves; grouping folders are not counted as objects. */
function objectCount(layer: LayerInfo): number {
  if (layer.children?.length) return layer.children.reduce((total, child) => total + objectCount(child), 0);
  return layer.kind === "group" ? 0 : 1;
}

/** Preserve sibling paint order while exposing the actual nested object tree. */
function buildLayerItem(doc: Document, layer: LayerInfo, expandAll: boolean, depth = 0): HTMLLIElement {
  const item = doc.createElement("li");
  item.className = "layer-item";
  item.setAttribute("data-order", String(layer.order));
  item.setAttribute("data-kind", layer.kind);

  const name = doc.createElement("span");
  name.className = "layer-name";
  // Engine names remain inert text, including at every nested level.
  name.textContent = layer.name;
  const kind = doc.createElement("span");
  kind.className = "layer-kind";
  kind.textContent = LAYER_KIND_LABELS[layer.kind] ?? layer.kind;

  const children = layer.children ?? [];
  if (children.length === 0) {
    item.appendChild(name);
    item.appendChild(kind);
    return item;
  }

  item.className = "layer-item layer-branch";
  const group = doc.createElement("details");
  group.className = "layer-group";
  group.open = expandAll || depth === 0;
  const summary = doc.createElement("summary");
  summary.className = "layer-summary";
  const chevron = doc.createElement("span");
  chevron.className = "layer-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▸";
  summary.appendChild(chevron);
  summary.appendChild(name);
  summary.appendChild(kind);
  const count = objectCount(layer);
  const counter = doc.createElement("span");
  counter.className = "layer-count";
  counter.textContent = `${count} ${count === 1 ? "object" : "objects"}`;
  summary.appendChild(counter);
  group.appendChild(summary);

  const list = doc.createElement("ul");
  list.className = "layer-children";
  list.setAttribute("aria-label", `${layer.name} contents`);
  for (const child of children) list.appendChild(buildLayerItem(doc, child, expandAll, depth + 1));
  group.appendChild(list);
  item.appendChild(group);
  return item;
}

/**
 * Preview renderer for the Browser_Shell's result view. Construct it once (the
 * shell reuses a single instance), then call {@link Preview.render} with each
 * conversion result + its source image, or {@link Preview.clear} to reset the
 * view between conversions.
 */
export class Preview {
  private readonly doc: Document;
  private readonly els: PreviewElements;
  private readonly objectUrl: ObjectUrlApi;

  /** The live source object URL, tracked so it can be revoked (no blob leaks). */
  private sourceUrl: string | null = null;

  constructor(options: PreviewOptions = {}) {
    this.doc = resolveDocument(options.document);
    this.els = options.elements ?? resolvePreviewElements(this.doc);
    this.objectUrl = resolveObjectUrl(options.objectUrl);
  }

  /**
   * Render a conversion result beside its source image (Requirement 7.1-7.3,
   * 7.6). Fills the source pane (`<img>` over the uploaded bytes), the SVG pane
   * (the result's exact SVG markup), the layer list (bottom->top summary order,
   * or an empty state), and the warnings area, then flips `#result[data-ready]`
   * so the panes show together. Any previous source object URL is revoked first.
   */
  render(result: ConvertResult, source: PreviewSource): void {
    this.renderSource(source);
    this.renderSvg(result.svg);
    this.renderLayers(result.layers);
    this.renderWarnings(result.warnings);
    this.els.result.setAttribute("data-ready", "true");
  }

  /**
   * Clear the result view and revoke the source object URL (Requirement 7's
   * reset path between conversions). Empties the source/SVG panes, the layer
   * list and the warnings area, and flips `#result[data-ready]` off. Safe to
   * call repeatedly.
   */
  clear(): void {
    this.revokeSourceUrl();
    this.els.sourcePreview.replaceChildren();
    this.els.svgPreview.replaceChildren();
    this.els.layerList.replaceChildren();
    this.els.messages.replaceChildren();
    this.els.result.setAttribute("data-ready", "false");
  }

  /** Revoke and forget the current source object URL, if any. */
  dispose(): void {
    this.revokeSourceUrl();
  }

  /* ---------------------------------------------------------------------- */
  /* Rendering helpers                                                       */
  /* ---------------------------------------------------------------------- */

  /** Fill `#source-preview` with an `<img>` over the uploaded bytes (7.1). */
  private renderSource(source: PreviewSource): void {
    // Revoke the previous URL before creating a new one so URLs never pile up.
    this.revokeSourceUrl();

    const type = mimeForFilename(source.filename);
    // A fresh Uint8Array view guards against the original buffer being detached
    // (the convert path transfers the buffer to the worker); copy the bytes.
    const bytes = source.imageBytes.slice();
    const blob =
      type === "" ? new Blob([bytes]) : new Blob([bytes], { type });
    const url = this.objectUrl.createObjectURL(blob);
    this.sourceUrl = url;

    const img = this.doc.createElement("img");
    img.className = "source-image";
    img.src = url;
    img.alt = source.filename ? `Source image: ${source.filename}` : DEFAULT_SOURCE_ALT;
    // Decoding off the main thread keeps the shell responsive (Property 5).
    img.decoding = "async";

    this.els.sourcePreview.replaceChildren(img);
  }

  /**
   * Fill `#svg-preview` with the result's exact SVG markup (7.1). The SVG text
   * is the engine's own output; injecting it as markup lets the browser render
   * it natively so the preview reflects the ACTUAL converted result.
   */
  private renderSvg(svg: string): void {
    // The SVG is the engine's trusted output (not user-authored HTML); render
    // it as markup so the browser parses the vector document natively.
    this.els.svgPreview.innerHTML = svg;
  }

  /**
   * Render the nested layer/object list from the result summary (7.2) or an empty
   * state when there are no layers (7.3). The summary is already in bottom->top
   * paint order from the glue, so entries are rendered in array order.
   */
  private renderLayers(layers: readonly LayerInfo[]): void {
    if (layers.length === 0) {
      // 7.3: show an empty-state message and render NO layer entries.
      const empty = this.doc.createElement("li");
      empty.className = "layer-empty";
      empty.textContent = NO_LAYERS_MESSAGE;
      this.els.layerList.replaceChildren(empty);
      return;
    }

    // Small examples should immediately show what was found; larger artwork
    // keeps its top-level groups open and lets the user expand deeper folders.
    const expandAll = layers.reduce((total, layer) => total + objectCount(layer), 0) <= 30;
    const items = layers.map((layer) => buildLayerItem(this.doc, layer, expandAll));
    this.els.layerList.replaceChildren(...items);
  }

  /**
   * Render each result warning as its own visible `.message` entry in
   * `#messages` (7.6). Empty/whitespace-only warning strings are skipped so a
   * blank entry never shows. The messages area is cleared first so stale
   * warnings from a prior conversion do not linger.
   */
  private renderWarnings(warnings: readonly string[]): void {
    const entries = warnings
      .filter((text) => text.trim() !== "")
      .map((text) => {
        const entry = this.doc.createElement("div");
        entry.className = "message";
        entry.setAttribute("data-kind", "warning");
        entry.setAttribute("role", "status");
        entry.textContent = text;
        return entry;
      });
    this.els.messages.replaceChildren(...entries);
  }

  /** Revoke the current source object URL and forget it. */
  private revokeSourceUrl(): void {
    if (this.sourceUrl !== null) {
      this.objectUrl.revokeObjectURL(this.sourceUrl);
      this.sourceUrl = null;
    }
  }
}
