/**
 * Splice the spike's marker-delimited block into STATUS.md without touching
 * anything else in the file.
 *
 * STATUS.md is a long, hand-maintained log. The spike owns exactly one region of
 * it, bounded by `STATUS_BLOCK_START` / `STATUS_BLOCK_END` (see `measure.ts`).
 * `replaceStatusBlock` replaces that region in place when it exists, appends it
 * when it does not, and refuses to edit when the markers are malformed, so a
 * broken marker can never cause unrelated text to be overwritten. Pure: no I/O.
 */

import { STATUS_BLOCK_END, STATUS_BLOCK_START } from "./measure.js";

/** Every index at which `needle` occurs in `haystack`. */
function occurrences(haystack: string, needle: string): number[] {
  const found: number[] = [];
  for (let i = haystack.indexOf(needle); i !== -1; i = haystack.indexOf(needle, i + 1)) {
    found.push(i);
  }
  return found;
}

/**
 * Return `existing` with the spike block replaced by `block`.
 *
 * - `block` must start with the begin marker, end with the end marker, and hold
 *   each marker exactly once.
 * - If `existing` holds no spike markers, `block` is appended after one blank
 *   line; every existing byte is kept as the prefix.
 * - If `existing` holds exactly one begin marker followed by exactly one end
 *   marker, the text from the begin marker through the end marker is replaced;
 *   everything before and after it is kept byte for byte.
 * - Any other marker layout (only one marker, reversed, duplicated) throws.
 */
export function replaceStatusBlock(existing: string, block: string): string {
  const body = block.replace(/\n+$/, "");
  if (
    !body.startsWith(STATUS_BLOCK_START) ||
    !body.endsWith(STATUS_BLOCK_END) ||
    occurrences(body, STATUS_BLOCK_START).length !== 1 ||
    occurrences(body, STATUS_BLOCK_END).length !== 1
  ) {
    throw new Error(
      "spike block must start with the begin marker, end with the end marker, " +
        "and contain each marker exactly once",
    );
  }

  const starts = occurrences(existing, STATUS_BLOCK_START);
  const ends = occurrences(existing, STATUS_BLOCK_END);

  if (starts.length === 0 && ends.length === 0) {
    const sep = existing.length === 0 ? "" : existing.endsWith("\n") ? "\n" : "\n\n";
    return `${existing}${sep}${body}\n`;
  }

  if (starts.length !== 1 || ends.length !== 1 || ends[0]! < starts[0]!) {
    throw new Error(
      `STATUS.md spike markers are malformed (begin x${starts.length}, end x${ends.length}); ` +
        "refusing to edit it. Fix the markers by hand first.",
    );
  }

  const start = starts[0]!;
  const end = ends[0]! + STATUS_BLOCK_END.length;
  return `${existing.slice(0, start)}${body}${existing.slice(end)}`;
}
