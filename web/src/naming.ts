/**
 * LM Studio naming — the enable/disable decision and the graceful fallback to
 * the engine's classical color-and-shape names (Browser_Shell, main thread;
 * design Component 4 "advanced" section, Requirement 10 and 8.5).
 *
 * WHY THIS MODULE EXISTS. LM Studio naming is the one optional, off-by-default
 * feature that can (a) be enabled only through an advanced toggle + a `vlmUrl`
 * field in the Settings_Panel (`settings.ts`) and (b) fail at runtime in ways
 * the core conversion never does — because the browser calling a localhost LM
 * Studio server is subject to CORS, and the server may reject the page's origin
 * or simply not answer. This module is the single, pure place that answers two
 * questions the shell and the panel both need:
 *
 *   1. "Is naming actually enabled for this config?" ({@link isNamingEnabled})
 *      — the exact same contract the glue's `build_config` enforces: naming is
 *      on IFF `vlmUrl` is a present, non-empty, non-whitespace string. A blank
 *      or absent `vlmUrl` is disabled, no matter what else is set. Keeping this
 *      decision here (and importing it into `settings.ts`) means the panel can
 *      never half-enable naming: the toggle being "on" with an empty URL still
 *      serialises to "disabled", matching `src/plate/web.py`'s `build_config`
 *      (which clamps a blank `vlm_url` to the engine default empty endpoint).
 *
 *   2. "When naming is unavailable or fails, what happens?" — the FALLBACK. The
 *      design (Scenario: LM Studio naming requested but CORS not enabled) and
 *      Requirement 10.4/10.5 are explicit: naming failure must NEVER break a
 *      conversion. The engine already produced classical names; the LM Studio
 *      call only *refines* them. So on a CORS rejection or a 30 s timeout the
 *      shell keeps the already-produced layer output unchanged, uses the
 *      engine's classical names, and shows a note. {@link namingFallback}
 *      classifies the failure and returns the user-facing note to render (via
 *      the shell's shared message area) plus the invariant that prior layer
 *      output is retained.
 *
 * PURITY / TESTABILITY. This module performs NO DOM work and NO network I/O. It
 * is pure data in, pure data out, so task 17.2's unit tests can exercise every
 * branch (default-off, empty-vs-nonempty `vlmUrl`, CORS-rejection fallback, and
 * the 30 s timeout fallback) without a browser or a live endpoint. The actual
 * LM Studio request is NOT issued here — that network call lives with whoever
 * wires the optional request (the engine's naming path, reached via the glue);
 * this module only decides enablement and shapes the fallback response the
 * shell renders. It intentionally contains no `fetch`/`XHR`.
 *
 * PRIVACY (Requirement 8.5). When naming is enabled, the single LM Studio call
 * is the ONLY outbound request permitted to carry image bytes; every other path
 * stays local. This module does not transmit anything itself; {@link NAMING_TIMEOUT_MS}
 * is pinned here so whoever issues the call bounds it at 30 s (Requirement 10.5)
 * and so a test can assert the bound without a magic number.
 */

import type { PlateConfig } from "./protocol.js";

/**
 * The hard timeout for a single LM Studio naming request (Requirement 10.5): if
 * no naming response arrives within 30 seconds, the request is cancelled and the
 * shell falls back to classical names. Pinned here so the caller that issues the
 * request and any test share one bound.
 */
export const NAMING_TIMEOUT_MS = 30_000;

/**
 * Is LM Studio naming enabled for `config`? True IFF `vlmUrl` is present and,
 * trimmed, non-empty. This is the browser-side mirror of the glue's
 * `build_config` rule ("leave LM Studio naming disabled unless `vlmUrl` is a
 * non-empty, non-whitespace string"): a blank/whitespace/absent `vlmUrl` is
 * disabled (Requirement 10.2), a non-blank one enables naming against that
 * endpoint (Requirement 10.3). The settings panel uses this so an "advanced
 * toggle on" state with an empty URL still reports disabled, and the glue is
 * guaranteed to agree because both apply the identical trimmed-non-empty test.
 */
export function isNamingEnabled(config: Pick<PlateConfig, "vlmUrl">): boolean {
  const url = config.vlmUrl;
  return typeof url === "string" && url.trim().length > 0;
}

/**
 * Why a naming attempt ended without refining names, so the shell can show the
 * right note:
 *   - `"cors"`: the LM Studio server rejected the page's origin (CORS not
 *     enabled). Requirement 10.4 — explain how to enable CORS.
 *   - `"timeout"`: no response within {@link NAMING_TIMEOUT_MS}. Requirement
 *     10.5 — report that naming was unavailable.
 *   - `"error"`: any other failure reaching/parsing the endpoint; treated like
 *     unavailability (fall back, do not break the conversion).
 */
export type NamingFailureCause = "cors" | "timeout" | "error";

/** The user-facing notes for each failure cause, pinned for panel + tests. */
export const NAMING_NOTES: Record<NamingFailureCause, string> = {
  cors:
    "LM Studio naming was rejected by CORS. Enable CORS for this page's origin " +
    "in LM Studio (Developer tab) and retry; the conversion kept its classical " +
    "color-and-shape names.",
  timeout:
    "LM Studio naming was unavailable (no response within 30 seconds). The " +
    "conversion kept its classical color-and-shape names.",
  error:
    "LM Studio naming was unavailable. The conversion kept its classical " +
    "color-and-shape names.",
};

/**
 * The graceful outcome of a naming attempt that did not refine names. The shell
 * renders {@link note} (as an `info` message via the shared message area) and,
 * because {@link retainedPriorOutput} is always true, leaves the already-produced
 * layer output exactly as the engine emitted it — naming failure NEVER breaks a
 * conversion (Requirement 10.4/10.5; design Scenario: CORS not enabled).
 */
export interface NamingFallback {
  /** Why naming did not apply (drives the note and any styling/telemetry). */
  cause: NamingFailureCause;
  /** The user-facing note to show. */
  note: string;
  /**
   * Always true: the conversion's existing (classical) layer output is retained
   * unchanged. Encoded as a field so the contract is explicit and testable, not
   * just implied by prose.
   */
  retainedPriorOutput: true;
  /**
   * Always true: on fallback the shell uses the engine's classical
   * color-and-shape names (the engine's default `name_layers` path), not VLM
   * names.
   */
  usedClassicalNames: true;
}

/**
 * Build the fallback outcome for a failed/unavailable naming attempt. Pure: it
 * maps a {@link NamingFailureCause} to the note and the two always-true
 * invariants (retain prior output, use classical names). The caller that issued
 * the (bounded) LM Studio request calls this on CORS rejection or on the 30 s
 * timeout and hands {@link NamingFallback.note} to the shell's message area; the
 * conversion result itself is untouched.
 */
export function namingFallback(cause: NamingFailureCause): NamingFallback {
  return {
    cause,
    note: NAMING_NOTES[cause],
    retainedPriorOutput: true,
    usedClassicalNames: true,
  };
}

/**
 * Classify a failure raised while attempting the LM Studio naming request into a
 * {@link NamingFailureCause}, so the caller can turn any thrown/rejected value
 * into a {@link namingFallback} without re-implementing the triage.
 *
 * Browsers surface a CORS rejection as a generic opaque network failure (a
 * `TypeError` from `fetch`, with no readable status), so a CORS block and a
 * plain connection failure are indistinguishable from JS alone. We therefore
 * only assert `"cors"` when the caller tells us the request was cross-origin
 * (the LM Studio localhost endpoint differs from the page origin — the usual
 * case) AND the failure is the opaque network error; an explicit timeout signal
 * maps to `"timeout"`; anything else is a generic `"error"`. The caller passes
 * `timedOut` when it cancelled on {@link NAMING_TIMEOUT_MS}.
 */
export function classifyNamingFailure(
  reason: unknown,
  opts: { timedOut?: boolean; crossOrigin?: boolean } = {},
): NamingFailureCause {
  if (opts.timedOut) return "timeout";
  // An AbortError from our own 30 s cancel also means timeout.
  if (reason instanceof Error && reason.name === "AbortError") return "timeout";
  // Opaque network failure on a cross-origin endpoint is the CORS signature.
  const isNetworkError =
    reason instanceof TypeError ||
    (reason instanceof Error && reason.name === "TypeError");
  if (opts.crossOrigin && isNetworkError) return "cors";
  return "error";
}
