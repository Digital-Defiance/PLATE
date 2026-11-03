/**
 * SVG download control (Browser_Shell, main thread).
 *
 * The last stage of the browser pipeline: once a conversion produces a
 * {@link module:protocol.ConvertResult}, this module enables the download
 * control and, on click, saves the SVG text to a correctly named file. It runs
 * no engine code and touches no pixels — it is a thin main-thread affordance
 * that turns a result's `svg` string into a browser download (Requirement 7.4,
 * 7.5). Preview rendering (task 9.1) and the layer list (task 9.1) live in a
 * sibling module; this file only owns the download button + row.
 *
 * Filename rule (Requirement 7.4, 7.5), fixed by the spec, not guessed:
 *   - The output is named from the *source base name* with a plain `.svg`
 *     extension (design: `replaceExt(file.name, ".svg")`). `logo.png` saves as
 *     `logo.svg` — there is no `.plate` marker.
 *   - The "base name" is the source filename with its final extension stripped:
 *     the text before the last `.` in the last path segment. A name with no `.`
 *     keeps the whole name as its base; interior dots are preserved
 *     (`my.logo.v2.png` -> `my.logo.v2`).
 *   - Dotfile vs bare-extension convention: a final path segment whose ONLY dot
 *     is the leading one is treated as having no strippable extension, so the
 *     whole segment is kept as the base. This covers both a true dotfile
 *     (`.logo` -> base `.logo` -> `.logo.svg`) and a bare extension
 *     (`.png` -> base `.png` -> `.png.svg`); they are indistinguishable from the
 *     filename alone, so both keep the segment rather than fabricating a guess.
 *   - Only a truly empty/whitespace-only filename, or a path that ends in a
 *     separator (no final segment), is "unavailable"; those fall back to
 *     {@link DEFAULT_BASE_NAME} and save as `plate.svg` (Requirement 7.5).
 *   - The rule is idempotent on an already-`.svg` name: the final `.svg` is
 *     stripped as the extension and re-appended, so `logo.svg` -> `logo.svg`
 *     (no doubling).
 *
 * The pure {@link downloadFilename} function is exported so task 9.3 can
 * unit-test the naming rule without a DOM. The document is injectable so the
 * controller is testable under Node (task 9.3) with a fake document.
 */

import type { ConvertResult } from "./protocol.js";

/** The SVG filename suffix every download ends with (Requirement 7.4). */
export const SVG_SUFFIX = ".svg";

/**
 * Default base name used when the source base name is empty or unavailable
 * (Requirement 7.5). Produces `plate.svg` so the file is still clearly a PLATE
 * SVG and never an empty-named download.
 */
export const DEFAULT_BASE_NAME = "plate";

/**
 * The MIME type SVG downloads are tagged with. `image/svg+xml` is the standard
 * SVG media type; the blob carries it so the browser and OS treat the saved
 * file as an SVG image.
 */
export const SVG_MIME_TYPE = "image/svg+xml";

/**
 * Strip the directory part from a filename, keeping only the last path segment.
 *
 * A dropped/picked {@link File} normally has a bare `name`, but a path-like
 * value (`a/b/logo.png`, `a\\b\\logo.png`) can arrive from some sources; we
 * keep only the final segment so the base name never contains separators.
 * Returns "" when the value ends in a separator (no final segment).
 */
function lastSegment(filename: string): string {
  const normalised = filename.replace(/\\/g, "/");
  const slash = normalised.lastIndexOf("/");
  return slash < 0 ? normalised : normalised.slice(slash + 1);
}

/**
 * The base name of a source filename: the final path segment with its last
 * extension removed, per the rule in this module's header.
 *
 * Handles odd names deterministically:
 *   - `"logo.png"`        -> `"logo"`       (ordinary extension stripped)
 *   - `"logo"`            -> `"logo"`        (no extension to strip)
 *   - `"my.logo.v2.png"`  -> `"my.logo.v2"` (only the final extension stripped)
 *   - `".logo"`           -> `".logo"`       (leading dot is not an extension)
 *   - `".png"`            -> `".png"`         (bare ext == dotfile: kept as base)
 *   - `"logo."`           -> `"logo"`        (trailing dot: empty extension)
 *   - `"a/b/logo.png"`    -> `"logo"`        (directory part dropped)
 *   - `""` / `"   "`      -> `""`            (empty/whitespace: no base)
 *
 * Returns the base with surrounding whitespace trimmed; an empty return signals
 * "base name unavailable" so {@link downloadFilename} applies the default.
 */
export function sourceBaseName(filename: string): string {
  const segment = lastSegment(filename).trim();
  if (segment === "") return "";

  const dot = segment.lastIndexOf(".");
  // No dot, or the only dot is a leading one (dotfile): no extension to strip.
  if (dot <= 0) {
    return segment;
  }
  return segment.slice(0, dot).trim();
}

/**
 * Compute the download filename for a source filename (Requirement 7.4, 7.5).
 *
 * Pure and DOM-free so task 9.3 can unit-test it directly. Takes the source
 * {@link sourceBaseName}, falls back to {@link DEFAULT_BASE_NAME} when that base
 * is empty/unavailable, and appends {@link SVG_SUFFIX}. Because the base name is
 * the segment with its final extension stripped, an already-`.svg` source has
 * its `.svg` stripped and re-appended, so the rule is idempotent (no doubling).
 *
 * Examples:
 *   - `"logo.png"`        -> `"logo.svg"`
 *   - `"photo.JPG"`       -> `"photo.svg"`
 *   - `"my.logo.v2.png"`  -> `"my.logo.v2.svg"`
 *   - `".png"`            -> `".png.svg"`   (bare ext kept as base; see header)
 *   - `""`                -> `"plate.svg"`  (unavailable -> default)
 *   - `"logo.svg"`        -> `"logo.svg"`   (idempotent on an already-.svg name)
 */
export function downloadFilename(sourceFilename: string): string {
  let base = sourceBaseName(sourceFilename);
  if (base === "") {
    base = DEFAULT_BASE_NAME;
  }
  return `${base}${SVG_SUFFIX}`;
}

/**
 * The minimal subset of `Document` the controller needs. Declaring it keeps the
 * module unit-testable in Node (task 9.3) with a fake document — no DOM global
 * required — and documents exactly which members the download path uses.
 */
export interface DocumentLike {
  getElementById(id: string): HTMLElementLike | null;
  createElement(tagName: "a"): AnchorLike;
  readonly body: NodeLike;
}

/** The subset of `HTMLElement` the controller reads/writes on the row+button. */
export interface HTMLElementLike {
  disabled?: boolean;
  setAttribute(name: string, value: string): void;
  addEventListener(type: "click", listener: () => void): void;
  removeEventListener(type: "click", listener: () => void): void;
}

/** The subset of a temporary `<a download>` the controller uses to save a file. */
export interface AnchorLike {
  href: string;
  download: string;
  click(): void;
}

/** The subset of a parent node used to attach/detach the temporary anchor. */
export interface NodeLike {
  appendChild(child: AnchorLike): void;
  removeChild(child: AnchorLike): void;
}

/**
 * The blob + object-URL plumbing, injectable so tests can observe that a URL is
 * created and later revoked without a real browser. Production defaults use the
 * `Blob`, `URL.createObjectURL` and `URL.revokeObjectURL` globals.
 */
export interface DownloadEnv {
  /** Build a Blob from the SVG text; defaults to the `Blob` global. */
  createBlob?: (parts: BlobPart[], options: BlobPropertyBag) => Blob;
  /** Create an object URL for the blob; defaults to `URL.createObjectURL`. */
  createObjectURL?: (blob: Blob) => string;
  /** Revoke a previously created object URL; defaults to `URL.revokeObjectURL`. */
  revokeObjectURL?: (url: string) => void;
}

/** The DOM ids the download control is wired to (see web/index.html). */
export const DOWNLOAD_BUTTON_ID = "download-button";
export const DOWNLOAD_ROW_ID = "download-row";

/**
 * Save SVG text to a named file via a temporary `<a download>` + blob URL.
 *
 * Builds a blob tagged `image/svg+xml`, creates an object URL, clicks a
 * detached-then-attached anchor to trigger the browser download, and revokes
 * the object URL afterwards so it does not leak (Requirement 7.4). Pure of the
 * controller's button state so it can be reused/tested on its own.
 */
export function saveSvg(
  doc: DocumentLike,
  svg: string,
  filename: string,
  env: DownloadEnv = {},
): void {
  const createBlob =
    env.createBlob ?? ((parts, options) => new Blob(parts, options));
  const createObjectURL = env.createObjectURL ?? URL.createObjectURL.bind(URL);
  const revokeObjectURL = env.revokeObjectURL ?? URL.revokeObjectURL.bind(URL);

  const blob = createBlob([svg], { type: SVG_MIME_TYPE });
  const url = createObjectURL(blob);
  const anchor = doc.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  // Some browsers only honour a click on an attached element; attach, click,
  // then detach so the DOM is left exactly as it was found.
  doc.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    doc.body.removeChild(anchor);
    revokeObjectURL(url);
  }
}

/**
 * Controller for the SVG download control (`#download-button` + `#download-row`).
 *
 * Lifecycle, driven by the shell (task 6.1 wires it up):
 *   - {@link setResult}: a conversion finished — remember the SVG + source
 *     filename, enable the button and show the row (Requirement 7.4).
 *   - click on the button: save the SVG to {@link downloadFilename} of the
 *     source filename via {@link saveSvg} (Requirement 7.4, 7.5).
 *   - {@link reset}: a new conversion is starting — disable the button, hide the
 *     row and forget the previous result so a stale SVG can never be saved.
 *   - {@link dispose}: detach the click listener (for teardown/tests).
 *
 * The document is injected so the controller runs under Node in tests. It reads
 * the two elements once at construction; a missing element is a wiring bug, so
 * construction throws rather than silently doing nothing.
 */
export class DownloadControl {
  private readonly doc: DocumentLike;
  private readonly button: HTMLElementLike;
  private readonly row: HTMLElementLike;
  private readonly env: DownloadEnv;
  private readonly onClick: () => void;
  private current: { svg: string; filename: string } | null = null;

  constructor(doc: DocumentLike, env: DownloadEnv = {}) {
    const button = doc.getElementById(DOWNLOAD_BUTTON_ID);
    const row = doc.getElementById(DOWNLOAD_ROW_ID);
    if (button === null) {
      throw new Error(`Download control: #${DOWNLOAD_BUTTON_ID} not found`);
    }
    if (row === null) {
      throw new Error(`Download control: #${DOWNLOAD_ROW_ID} not found`);
    }
    this.doc = doc;
    this.button = button;
    this.row = row;
    this.env = env;
    this.onClick = () => this.handleClick();
    this.button.addEventListener("click", this.onClick);
    // Start in the reset (disabled/hidden) state regardless of the initial DOM.
    this.reset();
  }

  /**
   * Record a finished conversion and enable the control (Requirement 7.4). The
   * source filename drives the download name; the SVG text is what gets saved.
   */
  setResult(result: ConvertResult, sourceFilename: string): void {
    this.current = { svg: result.svg, filename: sourceFilename };
    this.button.disabled = false;
    this.row.setAttribute("data-ready", "true");
  }

  /**
   * Clear any recorded result and return the control to disabled/hidden
   * (Requirement 7.4). Called between conversions so a new run never offers the
   * previous SVG.
   */
  reset(): void {
    this.current = null;
    this.button.disabled = true;
    this.row.setAttribute("data-ready", "false");
  }

  /** Detach the click listener; use on teardown. */
  dispose(): void {
    this.button.removeEventListener("click", this.onClick);
  }

  /**
   * Handle a click on the download button: save the current SVG under its
   * computed name. A click with no current result is a no-op (the button is
   * disabled in that state, but guard anyway so a stray programmatic click is
   * harmless).
   */
  private handleClick(): void {
    if (this.current === null) return;
    const filename = downloadFilename(this.current.filename);
    saveSvg(this.doc, this.current.svg, filename, this.env);
  }
}
