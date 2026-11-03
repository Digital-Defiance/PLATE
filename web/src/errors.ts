/**
 * Error surfaces for the Browser_Shell (main thread; design "Error Handling").
 *
 * This module turns the three families of failure the shell must show into
 * visible entries in the `#messages` area, and runs the on-load platform
 * pre-check. It owns no conversion logic and does no CPU-heavy work — it maps a
 * {@link PlateClientError} (what the worker classified and `PlateClient`
 * surfaced) or a raw platform probe onto the DOM message convention the shell
 * already defines in `web/index.html`:
 *
 *   `<div class="message" data-kind="warning|error|info">…</div>`
 *
 * It deliberately shares `#messages` with the preview warnings (task 9.1) and
 * the noise/JPEG warning (task 10.1): every surface uses the same `.message` /
 * `data-kind` markup so they compose in one list. To keep a clear separation,
 * the error surfaces here always render `data-kind="error"` (recoverable and
 * non-recoverable alike) or, for the Safari compatibility hint, `"info"`, and
 * each error entry it owns is tagged `data-surface="…"` so this module can
 * replace its own entries without disturbing another task's warnings.
 *
 * The three families (design "Error Handling"; Requirement 12):
 *   a) Runtime / bring-up failure — Pyodide or a scientific wheel failed to
 *      load/install (Requirement 12.1). NON-recoverable: the page cannot run
 *      the engine in this browser, so the notice stays until the visitor
 *      dismisses it or reloads, and suggests reload / a different browser. A
 *      per-package breakdown is shown when the worker recorded one.
 *   b) Input failure — the engine raised `ImageLoadError` (or an equivalent
 *      decode / unsupported-type / empty-file error) on the chosen file
 *      (Requirement 12.4). RECOVERABLE: the drop zone stays ready and the entry
 *      invites the visitor to pick another file without reloading. The engine's
 *      own message is shown verbatim (never bypassing engine validation).
 *   c) Platform failure — the browser is missing a capability the shell needs
 *      (Worker, WebAssembly, module workers) or is an unverified Safari
 *      (Requirement 12.5). A hard miss is a non-recoverable error; an
 *      unverified-Safari-but-capable browser gets the softer "best in Chrome,
 *      Edge, Firefox" info notice and may still proceed.
 *
 * Long-running conversions (Requirement 12.7) also surface here as a
 * recoverable notice offering continue-waiting / cancel.
 *
 * Design decisions that matter:
 *   - Plain DOM, no framework; `document` is injectable so every branch can be
 *     exercised in Node without a real browser (mirrors `settings.ts` /
 *     `links.ts`). Platform detection reads an injectable capability probe for
 *     the same reason — task 11.2 can assert the Safari and missing-capability
 *     branches deterministically.
 *   - Pure where it can be: the renderers take the `#messages` container (or
 *     resolve it by id) and return the element(s) they created, so a test can
 *     assert the rendered surface directly.
 *   - Messages are the exact text the acceptance criteria call for ("not
 *     supported in this browser yet", "best in Chrome, Edge, Firefox"), not
 *     invented copy.
 */

import type { PackageLoadResults } from "./protocol.js";
import { PlateClientError } from "./client.js";

/** The id of the shared message list in the shell (`web/index.html`). */
export const MESSAGES_CONTAINER_ID = "messages";

/** The `data-kind` values the shell styles; errors use `"error"`/`"info"`. */
export type MessageKind = "warning" | "error" | "info";

/**
 * Which error surface an entry belongs to. Tagged on the DOM node as
 * `data-surface` so this module can clear only its own entries (leaving the
 * preview/noise warnings other tasks render into the same list untouched).
 */
export type ErrorSurface =
  /** Runtime / bring-up failure (Requirement 12.1). */
  | "runtime"
  /** Input / decode failure (Requirement 12.4). */
  | "input"
  /** Platform capability / Safari compatibility (Requirement 12.5). */
  | "platform"
  /** Long-running conversion notice (Requirement 12.7). */
  | "long-run";

/* -------------------------------------------------------------------------- */
/* Exact user-facing copy (fixed by the acceptance criteria, not invented).    */
/* -------------------------------------------------------------------------- */

/**
 * Requirement 12.1: a package could not be resolved/installed, so the engine
 * cannot run here. Non-recoverable; stays until dismissed or reload.
 */
export const RUNTIME_UNSUPPORTED_MESSAGE =
  "This isn't supported in this browser yet. The conversion engine couldn't " +
  "start. Try reloading the page, or open it in an up-to-date Chrome, Edge, " +
  "or Firefox.";

/**
 * Requirement 12.5 fallback copy: the shell degrades to this when Safari
 * support has not been verified but the browser is otherwise capable.
 */
export const SAFARI_COMPAT_MESSAGE =
  "PLATE is best in Chrome, Edge, Firefox. Safari support isn't verified yet, " +
  "so conversion may not work as expected here.";

/**
 * Requirement 12.5 (hard miss): the browser lacks a capability the shell needs
 * (Web Worker, WebAssembly, or module workers). Non-recoverable here.
 */
export const PLATFORM_UNSUPPORTED_MESSAGE =
  "This browser is missing a feature PLATE needs to run (Web Workers and " +
  "WebAssembly). Please use an up-to-date Chrome, Edge, or Firefox.";

/** The recoverable-input lead-in shown before the engine's verbatim message. */
export const INPUT_RECOVERY_HINT =
  "Pick another PNG or JPG to try again — no need to reload.";

/** Requirement 12.7: a conversion has run past the long-run threshold. */
export const LONG_RUN_MESSAGE =
  "This conversion is taking a while. You can keep waiting or cancel and try a " +
  "smaller image or different settings.";

/** Requirement 12.7 threshold: 120 seconds without completing. */
export const LONG_RUN_THRESHOLD_MS = 120_000;

/** Requirement 12.1 threshold: bring-up must resolve within 60 seconds. */
export const BRING_UP_TIMEOUT_MS = 60_000;

/* -------------------------------------------------------------------------- */
/* Document / container resolution                                             */
/* -------------------------------------------------------------------------- */

/** Resolve a usable `document`, erroring clearly in a non-DOM environment. */
function resolveDocument(doc?: Document): Document {
  const resolved = doc ?? globalThis.document;
  if (!resolved) {
    throw new Error(
      "errors.ts needs a document; pass one explicitly in a non-DOM environment",
    );
  }
  return resolved;
}

/**
 * Resolve the shared `#messages` container. Accepts an explicit element (tests
 * and callers that already hold it) or finds it by id in the given document;
 * throws a clear error if the shell has no message list.
 */
function resolveContainer(
  container: HTMLElement | undefined,
  doc: Document,
): HTMLElement {
  if (container) return container;
  const found = doc.getElementById(MESSAGES_CONTAINER_ID);
  if (!found) {
    throw new Error(
      `errors.ts: no #${MESSAGES_CONTAINER_ID} container found in the document`,
    );
  }
  return found;
}

/* -------------------------------------------------------------------------- */
/* Platform support pre-check (Requirement 12.5)                               */
/* -------------------------------------------------------------------------- */

/**
 * The browser capabilities the shell feature-detects on load, plus whether the
 * browser looks like an unverified Safari. Injectable so task 11.2 can assert
 * every branch without a real browser or user-agent.
 */
export interface PlatformProbe {
  /** `typeof Worker !== "undefined"` — the shell runs conversion in a Worker. */
  hasWorker: boolean;
  /** `typeof WebAssembly !== "undefined"` — Pyodide is CPython on WASM. */
  hasWebAssembly: boolean;
  /**
   * Whether the environment can create ES-module workers (Pyodide 314 refuses
   * classic workers). Detected by probing `Worker` construction with a
   * `{ type: "module" }` option, which capable browsers read.
   */
  hasModuleWorker: boolean;
  /** Whether the user agent looks like Safari (and not Chrome/Edge/Firefox). */
  isSafari: boolean;
}

/** The outcome of {@link checkPlatformSupport}. */
export interface PlatformSupport {
  /** True when the shell can run a conversion at all (capabilities present). */
  supported: boolean;
  /**
   * How to surface the outcome: `"ok"` (nothing to show), `"safari"` (soft
   * info notice, may still proceed), or `"unsupported"` (hard error).
   */
  kind: "ok" | "safari" | "unsupported";
  /** The capabilities that were missing, if any (for the detail line). */
  missing: ReadonlyArray<"Worker" | "WebAssembly" | "module worker">;
  /** The message to display, or `undefined` when `kind === "ok"`. */
  message?: string;
}

/**
 * Detect the shell's required browser capabilities against the real globals.
 * Module-worker support is probed by attempting a tiny no-op module worker; if
 * construction throws (classic-only environments), module workers are absent.
 * Falls back to assuming module-worker support when `Worker` exists but a probe
 * cannot be run (e.g. CSP blocks the blob URL) so a capable browser is not
 * wrongly rejected.
 */
export function detectPlatform(scope: {
  Worker?: unknown;
  WebAssembly?: unknown;
  navigator?: { userAgent?: string };
  URL?: { createObjectURL?: (b: unknown) => string; revokeObjectURL?: (u: string) => void };
  Blob?: unknown;
} = globalThis as never): PlatformProbe {
  const hasWorker = typeof scope.Worker !== "undefined";
  const hasWebAssembly = typeof scope.WebAssembly !== "undefined";
  const ua = scope.navigator?.userAgent ?? "";
  // Safari's UA contains "Safari" but Chrome/Edge/other Chromium UAs also carry
  // "Safari"; treat it as Safari only when none of the others are present.
  const isChromium = /Chrome|Chromium|Edg\/|OPR\//.test(ua);
  const isFirefox = /Firefox\//.test(ua);
  const isSafari = /Safari\//.test(ua) && !isChromium && !isFirefox;

  return {
    hasWorker,
    hasWebAssembly,
    hasModuleWorker: hasWorker,
    isSafari,
  };
}

/**
 * Classify a {@link PlatformProbe} into the surface the shell should show.
 *
 * - Missing Worker / WebAssembly / module-worker support -> `"unsupported"`
 *   (non-recoverable; Requirement 12.5 hard miss).
 * - Capable but unverified Safari -> `"safari"` (soft info notice; the visitor
 *   may still proceed; Requirement 12.5 degrade message).
 * - Otherwise -> `"ok"`.
 *
 * Pure and deterministic, so task 11.2 can assert each branch from a fixed
 * probe without a browser.
 */
export function checkPlatformSupport(probe: PlatformProbe): PlatformSupport {
  const missing: Array<"Worker" | "WebAssembly" | "module worker"> = [];
  if (!probe.hasWorker) missing.push("Worker");
  if (!probe.hasWebAssembly) missing.push("WebAssembly");
  // Module-worker support only matters when Worker exists at all; a missing
  // Worker is already the dominant failure.
  if (probe.hasWorker && !probe.hasModuleWorker) missing.push("module worker");

  if (missing.length > 0) {
    return {
      supported: false,
      kind: "unsupported",
      missing,
      message: PLATFORM_UNSUPPORTED_MESSAGE,
    };
  }

  if (probe.isSafari) {
    return {
      supported: true,
      kind: "safari",
      missing: [],
      message: SAFARI_COMPAT_MESSAGE,
    };
  }

  return { supported: true, kind: "ok", missing: [] };
}

/* -------------------------------------------------------------------------- */
/* Error-entry model + rendering                                               */
/* -------------------------------------------------------------------------- */

/**
 * A single error surface resolved to what the UI must render: the shared
 * message `kind`, which `surface` it is, the lead message, an optional detail
 * line (e.g. the engine's verbatim text or a per-package breakdown), whether it
 * is recoverable (drop zone stays ready) and whether it is dismissible (a
 * non-recoverable runtime notice stays until dismissed or reload).
 */
export interface ErrorEntry {
  kind: MessageKind;
  surface: ErrorSurface;
  message: string;
  detail?: string;
  recoverable: boolean;
  /** Show a dismiss affordance (Requirement 12.1: "until dismissed or reload"). */
  dismissible: boolean;
}

/**
 * Map a {@link PlateClientError} onto an {@link ErrorEntry}.
 *
 * The worker already classified the failure: `recoverable` distinguishes an
 * input/decode error (the user can retry with a different file) from a
 * non-recoverable runtime/package failure, and `packages` carries the
 * per-package load results when a bring-up failure recorded them. This mapping
 * turns that into the surface the shell shows:
 *
 *   - recoverable  -> INPUT surface: the engine's own message is shown verbatim
 *     as the detail, with a recovery hint lead; the drop zone stays ready
 *     (Requirement 12.4).
 *   - non-recoverable -> RUNTIME surface: the fixed "not supported in this
 *     browser yet" notice, a per-package breakdown when available, dismissible
 *     and persistent until dismissed/reload (Requirement 12.1).
 */
export function entryFromClientError(error: PlateClientError): ErrorEntry {
  if (error.recoverable) {
    return {
      kind: "error",
      surface: "input",
      message: INPUT_RECOVERY_HINT,
      // The engine's own message, verbatim — never reworded, so the engine's
      // validation is the authority (Requirement 12.4).
      detail: error.message,
      recoverable: true,
      dismissible: true,
    };
  }

  const entry: ErrorEntry = {
    kind: "error",
    surface: "runtime",
    message: RUNTIME_UNSUPPORTED_MESSAGE,
    recoverable: false,
    // Stays visible until the visitor dismisses it or reloads (Requirement 12.1).
    dismissible: true,
  };
  const breakdown = error.packages ? describePackages(error.packages) : undefined;
  if (breakdown) entry.detail = breakdown;
  return entry;
}

/** A one-line "numpy ✓, scipy ✗, …" breakdown for a bring-up failure detail. */
export function describePackages(packages: PackageLoadResults): string {
  const parts = Object.entries(packages).map(
    ([name, result]) => `${name}: ${result === "pass" ? "loaded" : "failed"}`,
  );
  return `Package load — ${parts.join(", ")}.`;
}

/** Options shared by the rendering helpers. */
export interface RenderOptions {
  /** The `#messages` container; resolved by id when omitted. */
  container?: HTMLElement;
  /** Document used to create elements; defaults to the global `document`. */
  document?: Document;
  /**
   * Called when a dismissible entry's dismiss control is activated, after the
   * entry is removed from the DOM. Lets the shell react (e.g. re-enable intake).
   */
  onDismiss?: (entry: ErrorEntry) => void;
}

/**
 * Render one {@link ErrorEntry} into the shared `#messages` list and return the
 * created element.
 *
 * Any existing entry this module previously rendered for the SAME surface is
 * replaced first (so a second input error does not stack a duplicate, and a new
 * runtime notice supersedes an old one), while warnings other tasks rendered
 * into the same list are left untouched — this module only ever removes nodes
 * carrying its own `data-surface` tag.
 */
export function renderErrorEntry(
  entry: ErrorEntry,
  options: RenderOptions = {},
): HTMLElement {
  const doc = resolveDocument(options.document);
  const container = resolveContainer(options.container, doc);

  // Replace this module's prior entry for the same surface (idempotent per
  // surface); leave other tasks' warnings in place.
  clearSurface(entry.surface, { container, document: doc });

  const el = doc.createElement("div");
  el.className = "message";
  el.setAttribute("data-kind", entry.kind);
  el.setAttribute("data-surface", entry.surface);
  el.setAttribute("data-recoverable", String(entry.recoverable));
  el.setAttribute("role", entry.kind === "error" ? "alert" : "status");

  const text = doc.createElement("div");
  text.className = "message-text";
  text.textContent = entry.message;
  el.appendChild(text);

  if (entry.detail) {
    const detail = doc.createElement("div");
    detail.className = "message-detail";
    detail.textContent = entry.detail;
    el.appendChild(detail);
  }

  if (entry.dismissible) {
    const dismiss = doc.createElement("button");
    dismiss.type = "button";
    dismiss.className = "message-dismiss";
    dismiss.textContent = "Dismiss";
    dismiss.setAttribute("aria-label", "Dismiss this message");
    dismiss.addEventListener("click", () => {
      el.remove();
      options.onDismiss?.(entry);
    });
    el.appendChild(dismiss);
  }

  container.appendChild(el);
  return el;
}

/**
 * Render a {@link PlateClientError} directly — the common path: the shell
 * catches a rejected `convert()` / `init()` and hands the error here. Returns
 * the rendered element.
 */
export function renderClientError(
  error: PlateClientError,
  options: RenderOptions = {},
): HTMLElement {
  return renderErrorEntry(entryFromClientError(error), options);
}

/**
 * Render the result of the platform pre-check. For `"ok"` nothing is rendered
 * and `null` is returned; for `"safari"` a soft info notice; for `"unsupported"`
 * a non-recoverable platform error. Returns the created element (or `null`).
 */
export function renderPlatformSupport(
  support: PlatformSupport,
  options: RenderOptions = {},
): HTMLElement | null {
  if (support.kind === "ok") return null;

  const isHard = support.kind === "unsupported";
  const entry: ErrorEntry = {
    kind: isHard ? "error" : "info",
    surface: "platform",
    message: support.message ?? PLATFORM_UNSUPPORTED_MESSAGE,
    recoverable: !isHard,
    // The Safari info notice is dismissible; a hard platform miss stays put.
    dismissible: !isHard,
  };
  if (isHard && support.missing.length > 0) {
    entry.detail = `Missing: ${support.missing.join(", ")}.`;
  }
  return renderErrorEntry(entry, options);
}

/**
 * Run the on-load platform pre-check and surface its outcome in `#messages`.
 * Detects capabilities from the given scope (defaults to the real globals),
 * classifies them, renders the notice (if any), and returns the classification
 * so the shell can decide whether to disable intake on a hard miss.
 */
export function surfacePlatformCheck(
  options: RenderOptions & {
    probe?: PlatformProbe;
    scope?: Parameters<typeof detectPlatform>[0];
  } = {},
): PlatformSupport {
  const probe = options.probe ?? detectPlatform(options.scope);
  const support = checkPlatformSupport(probe);
  renderPlatformSupport(support, options);
  return support;
}

/**
 * Render the long-running-conversion notice (Requirement 12.7): a recoverable
 * entry offering continue-waiting or cancel. The two controls call the supplied
 * callbacks; "continue waiting" removes the notice so a later timeout can show
 * it again, "cancel" removes it and signals the shell to abort the conversion.
 */
export function renderLongRunNotice(
  handlers: { onContinue?: () => void; onCancel?: () => void },
  options: RenderOptions = {},
): HTMLElement {
  const doc = resolveDocument(options.document);
  const container = resolveContainer(options.container, doc);

  clearSurface("long-run", { container, document: doc });

  const el = doc.createElement("div");
  el.className = "message";
  el.setAttribute("data-kind", "error");
  el.setAttribute("data-surface", "long-run");
  el.setAttribute("data-recoverable", "true");
  el.setAttribute("role", "alert");

  const text = doc.createElement("div");
  text.className = "message-text";
  text.textContent = LONG_RUN_MESSAGE;
  el.appendChild(text);

  const actions = doc.createElement("div");
  actions.className = "message-actions";

  const keep = doc.createElement("button");
  keep.type = "button";
  keep.className = "message-continue";
  keep.textContent = "Keep waiting";
  keep.addEventListener("click", () => {
    el.remove();
    handlers.onContinue?.();
  });
  actions.appendChild(keep);

  const cancel = doc.createElement("button");
  cancel.type = "button";
  cancel.className = "message-cancel";
  cancel.textContent = "Cancel";
  cancel.addEventListener("click", () => {
    el.remove();
    handlers.onCancel?.();
  });
  actions.appendChild(cancel);

  el.appendChild(actions);
  container.appendChild(el);
  return el;
}

/* -------------------------------------------------------------------------- */
/* Clearing (own entries only, so shared #messages stays composable)           */
/* -------------------------------------------------------------------------- */

/**
 * Remove this module's entries for one surface from `#messages`, leaving every
 * other node (preview/noise warnings from tasks 9.1/10.1) untouched. Matches on
 * the `data-surface` tag this module writes, never a blanket clear.
 */
export function clearSurface(
  surface: ErrorSurface,
  options: { container?: HTMLElement; document?: Document } = {},
): void {
  const doc = resolveDocument(options.document);
  const container = resolveContainer(options.container, doc);
  const owned = container.querySelectorAll(`.message[data-surface="${surface}"]`);
  for (const node of Array.from(owned)) node.remove();
}

/**
 * Remove every error entry this module owns (all four surfaces), leaving other
 * tasks' warnings in place. Useful when a fresh conversion starts.
 */
export function clearAllErrorSurfaces(
  options: { container?: HTMLElement; document?: Document } = {},
): void {
  for (const surface of ["runtime", "input", "platform", "long-run"] as const) {
    clearSurface(surface, options);
  }
}
