/**
 * Phase 1 spike decision-point halts (task 3.3).
 *
 * Task 3.2 (`measure.ts`) drives the task-3.1 worker across the 24-scene seed-1
 * bake-off corpus and records every outcome (per-package load results, per-scene
 * timings, per-image SVG classification) into `STATUS.md`. This module adds the
 * HALT logic layered on top of those measurements: the spike has explicit
 * decision points, and when one fails its threshold the spike must STOP and
 * surface a clear go/no-go verdict rather than silently continuing into Phase 2+.
 *
 * SCOPE (task 3.3 only): the decision points, their thresholds, the halt, and the
 * verdict surfaced into the report / STATUS.md. It deliberately does NOT:
 *   - record the raw measurements (task 3.2 / the task-4 checkpoint do that);
 *   - assert the full spike done-definition GATE that unlocks Phases 2/3/4 (that
 *     is task 5, which reads this verdict plus the recorded measurements).
 * This module reuses the task-3.2 types (`SpikeReport`, `SceneMeasurement`,
 * `SvgClassification`) and STATUS.md block markers; it does not duplicate them.
 *
 * The decision points (design "Phase 1 — Spike … Decision point"; Requirements
 * 2.4, 2.5, and the Requirement-2.3 "outside Bakeoff_Tolerance is a failure"):
 *
 *   1. opencv-python load == fail       → HALT, name an alternative approach (2.4)
 *   2. any per-scene time > 60 seconds  → HALT (2.5)
 *   3. any scene outside Bakeoff_Tolerance (incl. a scene that failed to convert
 *      or whose SVG never scored) → HALT; the browser SVG diverged from the CLI
 *      beyond the tolerance band, which Requirement 2.3 defines as a failure.
 *
 * When any decision point trips, the verdict is "not-met": the spike has halted
 * and a human decides before Phase 2+ proceeds. When none trips, the verdict is
 * "met": the measurements cleared every threshold (task 5 still performs the
 * formal gate assertion before unlocking later phases).
 */

import type {
  SceneMeasurement,
  SpikeReport,
  SvgClassification,
} from "./measure.js";
import { STATUS_BLOCK_END } from "./measure.js";

/* -------------------------------------------------------------------------- */
/* Thresholds (design + requirements)                                         */
/* -------------------------------------------------------------------------- */

/** Per-scene conversion-time ceiling in seconds (Requirement 2.5). */
export const PER_SCENE_TIME_LIMIT_SECONDS = 60;

/**
 * The alternative approach named when `opencv-python` cannot load (Requirement
 * 2.4; design "Why Pyodide … alternatives considered" + the OpenCV error
 * scenario). The spike's fallback is a non-Pyodide route: a Rust/TypeScript
 * rewrite, or a local `plate serve` page that keeps the Python engine.
 */
export const OPENCV_ALTERNATIVE_APPROACH =
  "opencv-python has no usable Pyodide build, so the browser cannot run the " +
  "unchanged engine. Reconsider the design's alternatives: a Rust/TypeScript " +
  "rewrite of the engine, or a local `plate serve` web page that keeps the " +
  "Python engine but requires the visitor to install PLATE.";

/* -------------------------------------------------------------------------- */
/* Verdict model                                                               */
/* -------------------------------------------------------------------------- */

/** Which decision point tripped (used to label each halt reason). */
export type DecisionPoint =
  | "opencv-load"
  | "per-scene-time"
  | "svg-equivalence";

/** One tripped decision point: why the spike halted, with the evidence. */
export interface HaltReason {
  point: DecisionPoint;
  /** One-line, human-readable explanation of the breach. */
  message: string;
  /** The scenes that breached this decision point (empty for opencv-load). */
  scenes: string[];
  /** The alternative approach to take, when the decision point names one. */
  alternative?: string;
}

/** The spike go/no-go verdict derived from a {@link SpikeReport}. */
export interface SpikeVerdict {
  /** "met" when no decision point tripped; "not-met" when the spike halted. */
  status: "met" | "not-met";
  /** True iff the spike must halt before any Phase 2 work (status === not-met). */
  halt: boolean;
  /** Every tripped decision point, in decision-point order (empty when met). */
  reasons: HaltReason[];
}

/* -------------------------------------------------------------------------- */
/* Classification helpers                                                      */
/* -------------------------------------------------------------------------- */

/**
 * The SVG classifications that satisfy the spike's equivalence contract
 * (Requirement 2.3 / 2.6: byte-identical or within Bakeoff_Tolerance). Any other
 * classification — `outside-tolerance` or a never-scored `missing-browser-svg` —
 * is a failure that trips the equivalence decision point.
 */
const ACCEPTABLE_CLASSIFICATIONS: ReadonlySet<SvgClassification> = new Set<SvgClassification>([
  "byte-identical",
  "within-tolerance",
]);

/** True iff a scene's SVG classification clears the equivalence contract. */
export function isEquivalenceAcceptable(scene: SceneMeasurement): boolean {
  return scene.converted === "pass" && ACCEPTABLE_CLASSIFICATIONS.has(scene.classification);
}

/* -------------------------------------------------------------------------- */
/* Verdict evaluation                                                          */
/* -------------------------------------------------------------------------- */

/**
 * Evaluate the three spike decision points against a recorded {@link SpikeReport}
 * and return the go/no-go verdict. Pure: no I/O, no mutation of the report. All
 * three points are evaluated (not short-circuited) so a single run surfaces every
 * breach at once, giving the human the full picture before deciding.
 */
export function evaluateVerdict(report: SpikeReport): SpikeVerdict {
  const reasons: HaltReason[] = [];

  // Decision point 1 — opencv-python must load (Requirement 2.4).
  if (report.packages["opencv-python"] === "fail") {
    reasons.push({
      point: "opencv-load",
      message: "`opencv-python` failed to load in the Pyodide runtime.",
      scenes: [],
      alternative: OPENCV_ALTERNATIVE_APPROACH,
    });
  }

  // Decision point 2 — every per-scene time must be at or below 60s (Req 2.5).
  const slow = report.scenes.filter((s) => s.seconds > PER_SCENE_TIME_LIMIT_SECONDS);
  if (slow.length > 0) {
    reasons.push({
      point: "per-scene-time",
      message:
        `${slow.length} scene(s) exceeded the ` +
        `${PER_SCENE_TIME_LIMIT_SECONDS}s per-scene conversion-time limit.`,
      scenes: slow.map((s) => s.name),
    });
  }

  // Decision point 3 — every scene's SVG must match the CLI within tolerance
  // (Requirement 2.3: outside Bakeoff_Tolerance is a failure).
  const diverged = report.scenes.filter((s) => !isEquivalenceAcceptable(s));
  if (diverged.length > 0) {
    reasons.push({
      point: "svg-equivalence",
      message:
        `${diverged.length} scene(s) did not match the CLI SVG within ` +
        "Bakeoff_Tolerance (outside-tolerance, unscored, or failed to convert).",
      scenes: diverged.map((s) => s.name),
    });
  }

  return {
    status: reasons.length === 0 ? "met" : "not-met",
    halt: reasons.length > 0,
    reasons,
  };
}

/* -------------------------------------------------------------------------- */
/* STATUS.md decision-point rendering                                          */
/* -------------------------------------------------------------------------- */

/** Marker lines bounding the decision-point block appended to the spike block. */
export const DECISION_BLOCK_START = "<!-- SPIKE:browser-web-page:decision:begin -->";
export const DECISION_BLOCK_END = "<!-- SPIKE:browser-web-page:decision:end -->";

/**
 * Render the decision-point verdict as the Markdown block recorded in STATUS.md.
 *
 * On a HALT (status "not-met") it lists every tripped decision point and, for the
 * opencv-load point, the named alternative approach — exactly what Requirements
 * 2.4/2.5 require recorded. On "met" it records that no decision point tripped and
 * that the formal done-definition gate is task 5's to assert.
 */
export function renderDecision(verdict: SpikeVerdict): string {
  const lines: string[] = [
    DECISION_BLOCK_START,
    "",
    "### Phase 1 spike decision points (task 3.3)",
    "",
  ];

  if (verdict.status === "met") {
    lines.push(
      "**Verdict: no decision point tripped.** `opencv-python` loaded, every " +
        `per-scene time is at or below ${PER_SCENE_TIME_LIMIT_SECONDS}s, and every ` +
        "scene matched the CLI SVG within Bakeoff_Tolerance. The spike does not " +
        "halt here; the formal done-definition gate (Requirements 2.6/2.7) is " +
        "asserted by task 5 before Phases 2/3/4 unlock.",
    );
  } else {
    lines.push(
      "**Verdict: SPIKE NOT MET — HALT before any Phase 2 work.** The following " +
        "decision point(s) tripped their threshold (Requirements 2.4, 2.5, 2.3). " +
        "A human must decide before Phase 2+ proceeds.",
      "",
    );
    for (const reason of verdict.reasons) {
      lines.push(`- **${reason.point}** — ${reason.message}`);
      if (reason.scenes.length > 0) {
        lines.push(`  - scenes: ${reason.scenes.join(", ")}`);
      }
      if (reason.alternative) {
        lines.push(`  - alternative approach: ${reason.alternative}`);
      }
    }
  }

  lines.push("", DECISION_BLOCK_END);
  return lines.join("\n");
}

/**
 * Fold the rendered decision-point block into the spike's STATUS.md block.
 *
 * The task-3.2 harness writes a block delimited by the SPIKE begin/end markers
 * (see `renderStatus`). This inserts the decision block immediately before that
 * block's closing marker, so the halt verdict lives inside the same spike block
 * the task-4 checkpoint and task-5 gate read. If the closing marker is absent
 * (no measurements recorded yet), the decision block is appended at the end.
 */
export function appendDecisionToStatusBlock(statusBlock: string, decision: string): string {
  const endIdx = statusBlock.lastIndexOf(STATUS_BLOCK_END);
  if (endIdx === -1) {
    const sep = statusBlock.endsWith("\n") ? "" : "\n";
    return `${statusBlock}${sep}\n${decision}\n`;
  }
  const before = statusBlock.slice(0, endIdx);
  const after = statusBlock.slice(endIdx);
  const sep = before.endsWith("\n") ? "" : "\n";
  return `${before}${sep}${decision}\n\n${after}`;
}
