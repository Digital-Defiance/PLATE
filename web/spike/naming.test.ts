/**
 * Unit tests for LM Studio naming enable/disable and the graceful fallback
 * (web/src/naming.ts, task 17.1). These cover Requirement 10's enable-decision
 * and fallback contract — the pure logic the Settings_Panel and shell both rely
 * on — without a browser or a live endpoint:
 *
 *   - 10.2 / 10.3 (enable decision): `isNamingEnabled` is true IFF `vlmUrl` is a
 *     present, trimmed-non-empty string; absent / "" / whitespace-only is
 *     disabled. This mirrors the glue's `build_config` trimmed-non-empty rule,
 *     so an "advanced toggle on" state with a blank URL still reports disabled.
 *   - 10.4 / 10.5 (fallback invariants): `namingFallback(cause)` always retains
 *     prior layer output and uses the engine's classical names, for every cause
 *     (cors / timeout / error) — naming failure NEVER breaks a conversion.
 *   - 10.4 / 10.5 (note wording): `NAMING_NOTES` — the cors note explains
 *     enabling CORS; the timeout note states naming was unavailable within 30 s.
 *     Pinned so wording drift is caught.
 *   - 10.4 / 10.5 (triage): `classifyNamingFailure` maps a timeout signal and an
 *     `AbortError` to "timeout", a cross-origin opaque network error to "cors",
 *     and every other failure to "error".
 *   - 10.5 (timeout bound): `NAMING_TIMEOUT_MS === 30_000`.
 *
 * naming.ts is pure (no DOM, no network), so these run under Node via tsx with
 * no fakes — mirrors the plain-data style of `warnings.test.ts`.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { PlateConfig } from "../src/protocol.js";
import {
  NAMING_NOTES,
  NAMING_TIMEOUT_MS,
  classifyNamingFailure,
  isNamingEnabled,
  namingFallback,
  type NamingFailureCause,
} from "../src/naming.js";

/** All three causes, so invariant/note assertions can iterate exhaustively. */
const ALL_CAUSES: NamingFailureCause[] = ["cors", "timeout", "error"];

/* -------------------------------------------------------------------------- */
/* isNamingEnabled — the enable decision (Requirements 10.2 / 10.3)            */
/* -------------------------------------------------------------------------- */

test("isNamingEnabled is false when vlmUrl is absent (default-off)", () => {
  // No vlmUrl at all -> naming off by default (10.1/10.2).
  assert.equal(isNamingEnabled({}), false);
});

test("isNamingEnabled is false for an empty or whitespace-only vlmUrl (10.2)", () => {
  // The "advanced toggle on, but URL blank" states all serialise to disabled.
  assert.equal(isNamingEnabled({ vlmUrl: "" }), false);
  assert.equal(isNamingEnabled({ vlmUrl: "   " }), false);
  assert.equal(isNamingEnabled({ vlmUrl: "\t" }), false);
  assert.equal(isNamingEnabled({ vlmUrl: "\n" }), false);
  assert.equal(isNamingEnabled({ vlmUrl: " \t\n " }), false);
});

test("isNamingEnabled is true for a non-empty, non-whitespace vlmUrl (10.3)", () => {
  // A present endpoint enables naming against it; surrounding whitespace that
  // still leaves content trims to non-empty, matching build_config.
  assert.equal(isNamingEnabled({ vlmUrl: "http://localhost:1234/v1" }), true);
  assert.equal(isNamingEnabled({ vlmUrl: "  http://localhost:1234/v1  " }), true);
  assert.equal(isNamingEnabled({ vlmUrl: "x" }), true);
});

test("isNamingEnabled decides on vlmUrl alone, ignoring other config fields", () => {
  // A fully-populated config with a blank URL is still disabled; the inverse
  // (blank everything but a real URL) is enabled. The decision mirrors the
  // glue's trimmed-non-empty test and nothing else.
  const enabledish: PlateConfig = {
    preset: "logo",
    maxColors: 8,
    vlmModel: "some-vision-model",
    vlmUrl: "   ",
  };
  assert.equal(isNamingEnabled(enabledish), false);

  const disabledish: PlateConfig = { vlmUrl: "http://localhost:1234/v1" };
  assert.equal(isNamingEnabled(disabledish), true);
});

/* -------------------------------------------------------------------------- */
/* namingFallback — always-true invariants + note (Requirements 10.4 / 10.5)   */
/* -------------------------------------------------------------------------- */

test("namingFallback never breaks a conversion: retains output + classical names for every cause", () => {
  // The core 10.4/10.5 guarantee: whatever the cause, the engine's already-
  // produced layer output is kept and classical names are used.
  for (const cause of ALL_CAUSES) {
    const fb = namingFallback(cause);
    assert.equal(fb.cause, cause);
    assert.equal(fb.retainedPriorOutput, true);
    assert.equal(fb.usedClassicalNames, true);
  }
});

test("namingFallback returns the matching note for each cause", () => {
  for (const cause of ALL_CAUSES) {
    assert.equal(namingFallback(cause).note, NAMING_NOTES[cause]);
  }
});

/* -------------------------------------------------------------------------- */
/* NAMING_NOTES — pinned user-facing wording (Requirements 10.4 / 10.5)        */
/* -------------------------------------------------------------------------- */

test("the CORS note explains enabling CORS and reports names were kept (10.4)", () => {
  assert.match(NAMING_NOTES.cors, /CORS/);
  assert.match(NAMING_NOTES.cors, /[Ee]nable CORS/);
  assert.match(NAMING_NOTES.cors, /classical/);
});

test("the timeout note states naming was unavailable within 30 seconds (10.5)", () => {
  assert.match(NAMING_NOTES.timeout, /unavailable/);
  assert.match(NAMING_NOTES.timeout, /30 seconds/);
  assert.match(NAMING_NOTES.timeout, /classical/);
});

test("the generic error note reports unavailability and kept classical names", () => {
  assert.match(NAMING_NOTES.error, /unavailable/);
  assert.match(NAMING_NOTES.error, /classical/);
});

/* -------------------------------------------------------------------------- */
/* classifyNamingFailure — triage (Requirements 10.4 / 10.5)                   */
/* -------------------------------------------------------------------------- */

test("classifyNamingFailure maps an explicit timeout signal to 'timeout'", () => {
  // A deliberate cancel on the 30 s bound wins over anything else.
  assert.equal(classifyNamingFailure(new Error("whatever"), { timedOut: true }), "timeout");
  // timedOut dominates even a cross-origin network error.
  assert.equal(
    classifyNamingFailure(new TypeError("failed to fetch"), {
      timedOut: true,
      crossOrigin: true,
    }),
    "timeout",
  );
});

test("classifyNamingFailure maps an AbortError to 'timeout'", () => {
  // Our own AbortController cancel surfaces as an AbortError.
  const abort = new Error("The operation was aborted");
  abort.name = "AbortError";
  assert.equal(classifyNamingFailure(abort), "timeout");
});

test("classifyNamingFailure maps a cross-origin opaque network error to 'cors'", () => {
  // Browsers surface a CORS block as an opaque TypeError from fetch; only with
  // the crossOrigin hint do we assert "cors".
  assert.equal(
    classifyNamingFailure(new TypeError("Failed to fetch"), { crossOrigin: true }),
    "cors",
  );
  // A TypeError-by-name (not a TypeError instance) also qualifies.
  const byName = new Error("Load failed");
  byName.name = "TypeError";
  assert.equal(classifyNamingFailure(byName, { crossOrigin: true }), "cors");
});

test("classifyNamingFailure maps a TypeError without the crossOrigin hint to 'error'", () => {
  // Without knowing the request was cross-origin, an opaque network error is
  // indistinguishable from a plain connection failure -> generic error.
  assert.equal(classifyNamingFailure(new TypeError("Failed to fetch")), "error");
  assert.equal(
    classifyNamingFailure(new TypeError("Failed to fetch"), { crossOrigin: false }),
    "error",
  );
});

test("classifyNamingFailure maps any other failure to 'error'", () => {
  // Non-network errors, and a cross-origin hint without a network error, both
  // fall through to the generic cause.
  assert.equal(classifyNamingFailure(new RangeError("boom")), "error");
  assert.equal(classifyNamingFailure(new Error("plain error")), "error");
  assert.equal(classifyNamingFailure("a string reason"), "error");
  assert.equal(classifyNamingFailure(undefined), "error");
  assert.equal(classifyNamingFailure(new Error("plain"), { crossOrigin: true }), "error");
});

test("classifyNamingFailure's cause always resolves to a note and a non-breaking fallback", () => {
  // End-to-end: triage any reason -> fallback that keeps output and names.
  const reasons: Array<[unknown, { timedOut?: boolean; crossOrigin?: boolean }]> = [
    [new Error("abort"), { timedOut: true }],
    [new TypeError("Failed to fetch"), { crossOrigin: true }],
    [new RangeError("boom"), {}],
  ];
  for (const [reason, opts] of reasons) {
    const cause = classifyNamingFailure(reason, opts);
    const fb = namingFallback(cause);
    assert.equal(fb.note, NAMING_NOTES[cause]);
    assert.equal(fb.retainedPriorOutput, true);
    assert.equal(fb.usedClassicalNames, true);
  }
});

/* -------------------------------------------------------------------------- */
/* Timeout bound (Requirement 10.5)                                            */
/* -------------------------------------------------------------------------- */

test("NAMING_TIMEOUT_MS is pinned at 30 seconds (10.5)", () => {
  assert.equal(NAMING_TIMEOUT_MS, 30_000);
});
