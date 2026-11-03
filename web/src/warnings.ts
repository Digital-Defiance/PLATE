/**
 * Messages renderer for the Browser_Shell's `#messages` area — the pre-conversion
 * noise/JPEG beta warning in particular (main thread; design Component 1 /
 * Phase 4 "Polish": "a noisy/JPEG-image warning").
 *
 * WHAT THIS OWNS. The static shell (`web/index.html`) reserves one
 * `<div class="messages" id="messages">` for warnings, errors and compatibility
 * notices, styled by the `.message[data-kind="warning"|"error"|"info"]` CSS
 * already in the page. Three sibling concerns write into that same area —
 * result warnings (task 9.1 preview.ts), the JPEG/noise beta warning (this task,
 * 10.1) and runtime/input/platform errors (task 11.1 errors.ts). To keep them
 * from fighting over the DOM, THIS module is the reusable renderer for that
 * area: it appends `.message` entries with the right `data-kind`, de-duplicates,
 * and clears entries between conversions. Siblings compose by calling
 * {@link renderMessages} / {@link showWarning} / {@link clearMessages} (or the
 * `MessageArea` handle) rather than each hand-rolling its own `innerHTML`, so a
 * warning, a result-warning and an error can coexist as separate entries under
 * one convention (the `data-kind` attribute) without clobbering one another.
 *
 * THE NOISE/JPEG WARNING — where the check actually runs. The design's
 * `check_noise` (`src/plate/web.py`) decides `{noisy, jpeg}` using the engine's
 * own `noise_fraction` / `interior_noise_fraction` estimators and the exact
 * `imageio.load_image` auto-denoise trigger, so the warning reflects what the
 * engine will actually do (design Property 4). Crucially, `convert_bytes`
 * ALREADY calls `check_noise` and, when it reports BOTH `jpeg` and `noisy`,
 * appends the human-readable `BETA_JPEG_WARNING` string to the result's
 * `warnings` list (see `convert_bytes` in `src/plate/web.py`). The worker
 * converts that dict straight across, so the beta warning arrives on
 * `ConvertResult.warnings` with every conversion that needs it.
 *
 * Requirement 4.4 asks for the beta warning "before OR at conversion", and the
 * worker protocol (`web/src/protocol.ts`) exposes exactly `init` + `convert`
 * with no separate `check_noise` message. Adding a pre-conversion `check_noise`
 * round-trip would (a) invent a new worker protocol message and (b) run the
 * engine's noise estimators twice for the same image (once in the pre-check,
 * once again inside `convert_bytes`). So this module surfaces the warning the
 * engine already emits, AT conversion, by rendering `result.warnings` into
 * `#messages` and recognising the beta JPEG entry among them — satisfying 4.4
 * without a redundant estimation pass or a new protocol surface. The recogniser
 * ({@link isBetaJpegWarning}) keys off the engine's `BETA_JPEG_WARNING` text so
 * the shell can style/label that specific warning if it wants, while any other
 * warning the engine adds later still renders generically.
 *
 * PRIVACY (Requirement 8.4). The core conversion path makes NO outbound request
 * that transmits any portion of the image bytes: image bytes are transferred
 * only to the same-origin Web Worker (which runs the engine locally in Pyodide),
 * and this renderer touches the DOM only. {@link assertNoImageEgress} documents
 * and defends that invariant for tests — it accepts the list of outbound request
 * targets the shell made on the conversion path and asserts none of them is a
 * remote (cross-origin, non-worker) destination. There is intentionally no
 * `fetch`/`XHR`/`sendBeacon` anywhere in this module.
 *
 * Design decisions that matter:
 *   - Plain DOM, no framework; `document` is injectable so every branch runs in
 *     Node without a real browser (mirrors `settings.ts` / `links.ts`).
 *   - Pure where it can be: {@link renderMessages} takes a container + a list of
 *     entries, clears it, renders each as a `.message[data-kind]`, and returns
 *     the rendered elements so a test can assert them directly.
 *   - Idempotent & de-duplicated: the same warning text is never shown twice in
 *     one render, so re-rendering a result's warnings (e.g. after a re-layout)
 *     cannot stack duplicates.
 */

import type { ConvertResult } from "./protocol.js";

/**
 * The exact human-readable beta warning `src/plate/web.py` appends to a result's
 * `warnings` when `check_noise` reports both a JPEG source and a noisy image
 * (`BETA_JPEG_WARNING` there). Pinned here verbatim so the shell can recognise
 * that specific warning among the result's warnings; kept in one place so a
 * change to the engine text is a single-line update with a test to catch drift.
 */
export const BETA_JPEG_WARNING =
  "beta: compressed JPEG detected; hidden-object recovery is limited on noisy " +
  "JPEGs today, so some occluded shapes may not be fully reconstructed";

/** The id of the shell's shared messages container (see `web/index.html`). */
export const MESSAGES_CONTAINER_ID = "messages";

/** How a `.message` entry is styled — matches the shell's CSS `data-kind`. */
export type MessageKind = "warning" | "error" | "info";

/** One message to render into `#messages`: its text plus how to style it. */
export interface MessageEntry {
  /** The visible message text. */
  text: string;
  /** Styling bucket; drives `data-kind` and the left-border colour. */
  kind: MessageKind;
}

/** Resolve a usable `document`, erroring clearly in a non-DOM environment. */
function resolveDocument(doc?: Document): Document {
  const resolved = doc ?? globalThis.document;
  if (!resolved) {
    throw new Error(
      "warnings.ts needs a document; pass one explicitly in a non-DOM environment",
    );
  }
  return resolved;
}

/**
 * Is `text` the engine's beta JPEG/noise warning? Keyed off the pinned
 * {@link BETA_JPEG_WARNING} string so the shell can single out that specific
 * warning (for example to label it a "beta" notice) while still rendering any
 * other warning the engine emits generically. Trimmed-equality, so trailing
 * whitespace from the transport cannot hide it.
 */
export function isBetaJpegWarning(text: string): boolean {
  return text.trim() === BETA_JPEG_WARNING;
}

/**
 * Create one `.message` element for `entry`, styled by its `kind`. The shell CSS
 * styles `.message[data-kind="warning"|"error"|"info"]`, so the entry sets both
 * the class and the `data-kind` attribute. The beta JPEG warning additionally
 * carries `data-beta="jpeg"` so a stylesheet or test can target it specifically
 * without re-matching the whole string.
 */
function createMessageElement(doc: Document, entry: MessageEntry): HTMLElement {
  const el = doc.createElement("div");
  el.className = "message";
  el.setAttribute("data-kind", entry.kind);
  el.textContent = entry.text;
  if (entry.kind === "warning" && isBetaJpegWarning(entry.text)) {
    el.setAttribute("data-beta", "jpeg");
  }
  return el;
}

/**
 * Render `entries` into `container`, replacing whatever was there. Each entry
 * becomes one `.message[data-kind]` child in order; duplicate texts within the
 * one call are dropped so a render can never stack the same notice twice.
 * Returns the rendered elements (in order) for direct assertion in tests.
 *
 * This is the one place that writes the `#messages` DOM, so result warnings
 * (task 9.1), the beta JPEG warning (this task) and errors (task 11.1) all go
 * through it and compose by `data-kind` rather than clobbering each other.
 */
export function renderMessages(
  container: HTMLElement,
  entries: readonly MessageEntry[],
  options: { document?: Document } = {},
): HTMLElement[] {
  const doc = resolveDocument(options.document);

  container.replaceChildren();

  const seen = new Set<string>();
  const rendered: HTMLElement[] = [];
  for (const entry of entries) {
    const key = `${entry.kind}\u0000${entry.text}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const el = createMessageElement(doc, entry);
    container.appendChild(el);
    rendered.push(el);
  }
  return rendered;
}

/** Remove every rendered message from `container` (between conversions). */
export function clearMessages(container: HTMLElement): void {
  container.replaceChildren();
}

/**
 * Turn a result's `warnings` list into renderable {@link MessageEntry} items.
 * Every warning the engine emits renders as a `warning`-kind entry (Requirement
 * 7.6: each warning shown as a separate visible entry). Blank/whitespace-only
 * strings are dropped so a stray empty warning never renders an empty box. The
 * beta JPEG warning is not special-cased here — it renders like any warning and
 * is merely tagged by {@link createMessageElement} — so the engine stays the
 * single source of which warnings exist (design Property 1: thin shell).
 */
export function warningsToEntries(warnings: readonly string[]): MessageEntry[] {
  const entries: MessageEntry[] = [];
  for (const text of warnings) {
    const trimmed = text.trim();
    if (trimmed.length === 0) continue;
    entries.push({ text, kind: "warning" });
  }
  return entries;
}

/**
 * Whether a conversion result carries the beta JPEG/noise warning (so the shell
 * can, for instance, flag the result as beta-limited). This is exactly the
 * `check_noise`-reports-both-jpeg-and-noisy signal: `convert_bytes` appends
 * {@link BETA_JPEG_WARNING} precisely in that case, so its presence in
 * `result.warnings` is the pre/at-conversion warning Requirement 4.4 asks for.
 */
export function resultHasBetaJpegWarning(result: Pick<ConvertResult, "warnings">): boolean {
  return result.warnings.some(isBetaJpegWarning);
}

/**
 * A thin handle over the shell's `#messages` area so the shell and its siblings
 * (9.1 result warnings, 11.1 errors) share one renderer instead of each finding
 * and mutating the container independently. Mount it once with {@link mountMessageArea};
 * call {@link MessageArea.showResultWarnings} after a conversion, {@link MessageArea.showWarning}
 * / {@link MessageArea.showError} / {@link MessageArea.showInfo} for ad-hoc notices,
 * and {@link MessageArea.clear} between conversions.
 */
export interface MessageArea {
  /** The resolved `#messages` container element. */
  readonly container: HTMLElement;
  /**
   * Render a conversion result's warnings (Requirement 7.6), surfacing the beta
   * JPEG/noise warning among them when present (Requirement 4.4). Replaces any
   * warnings shown for a previous conversion. Returns the rendered elements.
   */
  showResultWarnings(result: Pick<ConvertResult, "warnings">): HTMLElement[];
  /** Replace the area with the given entries (siblings compose through this). */
  render(entries: readonly MessageEntry[]): HTMLElement[];
  /** Append-style helpers (clear first, then one entry) for a single notice. */
  showWarning(text: string): HTMLElement[];
  showError(text: string): HTMLElement[];
  showInfo(text: string): HTMLElement[];
  /** Clear all messages (between conversions). */
  clear(): void;
  /** True iff the beta JPEG warning is among `result.warnings`. */
  hasBetaJpegWarning(result: Pick<ConvertResult, "warnings">): boolean;
}

/** Options for {@link mountMessageArea}. */
export interface MountMessageAreaOptions {
  /** Document used to resolve the container; defaults to the global `document`. */
  document?: Document;
  /** Container id; defaults to {@link MESSAGES_CONTAINER_ID}. */
  containerId?: string;
  /**
   * Fallback host to attach a freshly created container to when the shell lacks
   * one (defaults to `document.body`). The static shell already ships
   * `#messages`, so this is only a safety net for a shell assembled without it.
   */
  host?: HTMLElement | null;
}

/**
 * Resolve (or, as a fallback, create) the shell's `#messages` container and
 * return a {@link MessageArea} handle bound to it. The static shell already
 * carries `#messages`; the fallback only guards a shell assembled without it so
 * warnings are never silently dropped.
 */
export function mountMessageArea(options: MountMessageAreaOptions = {}): MessageArea {
  const doc = resolveDocument(options.document);
  const containerId = options.containerId ?? MESSAGES_CONTAINER_ID;

  let container = doc.getElementById(containerId);
  if (!container) {
    container = doc.createElement("div");
    container.id = containerId;
    container.className = "messages";
    container.setAttribute("aria-live", "polite");
    const host = options.host ?? doc.body;
    if (host) host.appendChild(container);
  }
  const el = container as HTMLElement;

  const render = (entries: readonly MessageEntry[]): HTMLElement[] =>
    renderMessages(el, entries, { document: doc });

  return {
    container: el,
    render,
    showResultWarnings: (result) => render(warningsToEntries(result.warnings)),
    showWarning: (text) => render([{ text, kind: "warning" }]),
    showError: (text) => render([{ text, kind: "error" }]),
    showInfo: (text) => render([{ text, kind: "info" }]),
    clear: () => clearMessages(el),
    hasBetaJpegWarning: (result) => resultHasBetaJpegWarning(result),
  };
}

/**
 * Privacy guard for Requirement 8.4: the core conversion path must make no
 * outbound request that transmits any portion of the image bytes. This module
 * never performs network I/O; image bytes only cross to the same-origin Web
 * Worker, which runs the engine locally (Pyodide), and `convert_bytes` itself
 * does zero network I/O (design Property 2 / Requirement 8.1).
 *
 * This helper lets a test assert that invariant explicitly: pass the list of
 * outbound request targets the shell issued on the conversion path and the URL
 * of the shell's own origin (and optionally the worker URL). It throws if any
 * target is a remote destination (a different origin, or any non-same-origin
 * `http(s)` URL), returning silently when the only "targets" are same-origin /
 * worker URLs or when there were none at all. It makes no request itself.
 *
 * @param targets  Outbound request URLs issued on the conversion path.
 * @param sameOrigin  The shell's own origin (e.g. `location.origin`); same-origin
 *                    targets (the worker, the wheel) are allowed.
 */
export function assertNoImageEgress(
  targets: readonly string[],
  sameOrigin: string,
): void {
  const offenders: string[] = [];
  for (const target of targets) {
    // Blob/data/worker-relative URLs never leave the device; only absolute
    // http(s) URLs to a different origin are egress.
    let url: URL | undefined;
    try {
      url = new URL(target, sameOrigin);
    } catch {
      // A non-URL target (e.g. a blob: handle) is not network egress.
      continue;
    }
    const isHttp = url.protocol === "http:" || url.protocol === "https:";
    if (isHttp && url.origin !== new URL(sameOrigin).origin) {
      offenders.push(target);
    }
  }
  if (offenders.length > 0) {
    throw new Error(
      `image egress on the conversion path is forbidden (Requirement 8.4); ` +
        `offending outbound target(s): ${offenders.join(", ")}`,
    );
  }
}
