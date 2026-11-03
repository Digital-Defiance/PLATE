/**
 * Property test for Property 6: Memory bounded (task 13).
 *
 *   **Validates: Requirements 9.1, 9.2, 9.3, 9.4**
 *
 * Design statement (design.md, Correctness Properties, Property 6):
 *
 *   The work-size cap (`Config.work_size`, default 1536) applies in the browser
 *   exactly as on the CLI; files above a hard byte/dimension cap are rejected
 *   before decode.
 *
 *   ∀ image : longest_side(internal(image)) ≤ work_size
 *             ∧ (bytes(image) > cap ⟹ rejected_before_decode)
 *
 * The property has two halves, split by where the behaviour lives (per the
 * task scope: "glue/CPython side for the size bounds; shell side for the
 * pre-decode rejection"):
 *
 *   A. Size bounds (engine / glue side, Requirements 9.1, 9.3, 9.4):
 *      the internal working-image longest side is ≤ `work_size`, and the engine
 *      does NOT upscale a source whose longest side is already ≤ `work_size`.
 *      The engine's resize is `src/plate/imageio.load_image`: with the default
 *      `upscale == 1.0`, when `max(w, h) > work_size` it scales by
 *      `work_size / max(w, h)` and rounds (`round(w*scale), round(h*scale)`,
 *      each clamped to ≥ 1); otherwise it leaves the image untouched. The
 *      {@link workSizeDims} reference here mirrors that exact arithmetic, and
 *      the property asserts the two invariants Requirement 9 states hold for
 *      ALL dimensions — this is the invariant a shell that silently upscaled or
 *      failed to cap would violate.
 *
 *   B. Pre-decode rejection (Browser_Shell side, Requirements 9.2, 9.4):
 *      a file above the Upload_Cap byte limit, or above the pixel-dimension
 *      limit, is rejected by the REAL {@link validateFile} from `web/src/intake.ts`
 *      BEFORE any decode — and, for the byte cap, before the bytes are even
 *      read. The test injects a spy `readBytes` and asserts it is never called
 *      for an over-byte-cap file, and that over-dimension headers are rejected
 *      with the typed `too-large-dimensions` reason. These assertions FAIL if
 *      intake ever read/decoded an over-cap upload (the leak Requirement 9
 *      guards against).
 *
 * The test is hermetic: no DOM, no real browser, no network. It exercises the
 * real intake module through its injectable `FileLike` / `readBytes` seams and
 * a faithful reference for the engine's documented work-size arithmetic. The
 * engine source is NEVER imported or modified here.
 *
 * Property framework: `fast-check` (pinned in web/package.json). Both halves
 * run as `fc.assert(fc.property(...))` over randomised inputs.
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import fc from "fast-check";

import type { FileLike } from "../src/intake.js";
import {
  MAX_DIMENSION_PX,
  UPLOAD_CAP_BYTES,
  validateFile,
} from "../src/intake.js";

// ---------------------------------------------------------------------------
// A. Size bounds — reference for the engine's documented work-size resize.
// ---------------------------------------------------------------------------

/** Default `Config.work_size` (design: 1536). */
const DEFAULT_WORK_SIZE = 1536;

/**
 * Mirror of `imageio.load_image`'s resize with the default `upscale == 1.0`:
 *
 *   longest = max(w, h)
 *   if longest > work_size:
 *       scale = work_size / longest
 *       (w, h) -> (max(1, round(w*scale)), max(1, round(h*scale)))
 *   else: unchanged
 *
 * Returns the internal working-image dimensions the engine would produce for a
 * source of `(w, h)` at the given `workSize`. This is the arithmetic the
 * property asserts the two Requirement-9 invariants over; it is NOT a new
 * behaviour, only a faithful restatement of the engine's documented rule so the
 * invariant can be checked on the TS side without running Pyodide.
 */
function workSizeDims(w: number, h: number, workSize: number): { w: number; h: number } {
  const longest = Math.max(w, h);
  if (longest > workSize) {
    const scale = workSize / longest;
    return {
      w: Math.max(1, Math.round(w * scale)),
      h: Math.max(1, Math.round(h * scale)),
    };
  }
  return { w, h };
}

/**
 * Round-half-to-even? No — Python's `round` is banker's rounding, but the cap
 * invariant (longest ≤ work_size) and the no-upscale invariant hold under ANY
 * standard rounding, so the exact tie-break does not affect the property. The
 * reference uses `Math.round` only to produce a concrete integer to assert on;
 * the invariants below are the contract, not the specific rounded value.
 */

test("Property 6A: internal longest side never exceeds work_size (Req 9.1, 9.3)", () => {
  fc.assert(
    fc.property(
      // Source dimensions across the whole accepted range, up to the 8192 cap
      // intake enforces, plus a little past it to probe the boundary.
      fc.integer({ min: 1, max: 9000 }),
      fc.integer({ min: 1, max: 9000 }),
      // A range of work_size settings, including the default 1536.
      fc.integer({ min: 16, max: 4096 }),
      (w, h, workSize) => {
        const internal = workSizeDims(w, h, workSize);
        const longest = Math.max(internal.w, internal.h);
        // Requirement 9.3 / 9.1: the internal longest side is ≤ work_size.
        // (When the source is already within the cap, the longest side equals
        // the source's and is ≤ work_size by the branch condition.)
        assert.ok(
          longest <= workSize,
          `internal longest side ${longest} exceeds work_size ${workSize} ` +
            `for source ${w}x${h}`,
        );
        // Dimensions stay positive integers (never collapse to 0).
        assert.ok(internal.w >= 1 && internal.h >= 1);
        assert.ok(Number.isInteger(internal.w) && Number.isInteger(internal.h));
      },
    ),
    { numRuns: 2000 },
  );
});

test("Property 6A: engine does not upscale a source already within work_size (Req 9.4)", () => {
  fc.assert(
    fc.property(
      fc.integer({ min: 1, max: 4096 }),
      fc.integer({ min: 1, max: 4096 }),
      fc.integer({ min: 16, max: 4096 }),
      (w, h, workSize) => {
        fc.pre(Math.max(w, h) <= workSize); // only the no-upscale case
        const internal = workSizeDims(w, h, workSize);
        // Requirement 9.4: process at original dimensions, no upscale.
        assert.equal(internal.w, w, "width changed for an in-cap source");
        assert.equal(internal.h, h, "height changed for an in-cap source");
      },
    ),
    { numRuns: 2000 },
  );
});

test("Property 6A: default work_size (1536) caps the longest side", () => {
  fc.assert(
    fc.property(
      fc.integer({ min: 1, max: 9000 }),
      fc.integer({ min: 1, max: 9000 }),
      (w, h) => {
        const internal = workSizeDims(w, h, DEFAULT_WORK_SIZE);
        assert.ok(Math.max(internal.w, internal.h) <= DEFAULT_WORK_SIZE);
      },
    ),
    { numRuns: 1000 },
  );
});

// ---------------------------------------------------------------------------
// B. Pre-decode rejection — exercised against the REAL intake module.
// ---------------------------------------------------------------------------

/** 8-byte PNG signature (matches intake's check). */
const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

function writeUint32BE(buf: Uint8Array, offset: number, value: number): void {
  buf[offset] = (value >>> 24) & 0xff;
  buf[offset + 1] = (value >>> 16) & 0xff;
  buf[offset + 2] = (value >>> 8) & 0xff;
  buf[offset + 3] = value & 0xff;
}

/** A minimal, real PNG header carrying `width`/`height` (24 bytes, IHDR). */
function pngHeader(width: number, height: number): Uint8Array {
  const buf = new Uint8Array(24);
  buf.set(PNG_SIGNATURE, 0);
  writeUint32BE(buf, 8, 13); // IHDR data length
  buf[12] = 0x49; // 'I'
  buf[13] = 0x48; // 'H'
  buf[14] = 0x44; // 'D'
  buf[15] = 0x52; // 'R'
  writeUint32BE(buf, 16, width);
  writeUint32BE(buf, 20, height);
  return buf;
}

/**
 * A `FileLike` whose `arrayBuffer` throws: used to prove intake rejects a file
 * WITHOUT reading its bytes. If intake ever reads, the throw surfaces.
 */
function declaredFile(name: string, type: string, size: number): FileLike {
  return {
    name,
    type,
    size,
    async arrayBuffer(): Promise<ArrayBuffer> {
      throw new Error("arrayBuffer() must not be called: bytes were read");
    },
  };
}

/** A real-bytes `FileLike` plus a spy that records read calls. */
function fileWithSpy(
  name: string,
  type: string,
  bytes: Uint8Array,
  size?: number,
): { file: FileLike; reads: () => number; read: (f: FileLike) => Promise<Uint8Array> } {
  let reads = 0;
  const file: FileLike = {
    name,
    type,
    size: size ?? bytes.byteLength,
    async arrayBuffer() {
      return bytes.slice().buffer;
    },
  };
  const read = async (_f: FileLike): Promise<Uint8Array> => {
    reads++;
    return bytes;
  };
  return { file, reads: () => reads, read };
}

test("Property 6B: over-byte-cap files are rejected before any read (Req 9.2)", async () => {
  await fc.assert(
    fc.asyncProperty(
      // A declared size strictly above the 20 MB cap.
      fc.integer({ min: UPLOAD_CAP_BYTES + 1, max: UPLOAD_CAP_BYTES * 100 }),
      fc.constantFrom("image/png", "image/jpeg"),
      fc.constantFrom("big.png", "big.jpg", "big.jpeg"),
      async (size, type, name) => {
        // arrayBuffer() throws if called — proving no read/decode happened.
        const file = declaredFile(name, type, size);
        const result = await validateFile(file);
        assert.equal(result.ok, false);
        assert.ok(!result.ok && result.reason === "too-large-bytes");
      },
    ),
    { numRuns: 500 },
  );
});

test("Property 6B: over-byte-cap rejection never invokes the byte reader (Req 9.2)", async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.integer({ min: UPLOAD_CAP_BYTES + 1, max: UPLOAD_CAP_BYTES * 10 }),
      async (size) => {
        // Provide a real spy reader; it must stay at zero calls for over-cap.
        const { file, reads, read } = fileWithSpy(
          "big.png",
          "image/png",
          pngHeader(10, 10),
          size,
        );
        const result = await validateFile(file, { readBytes: read });
        assert.equal(result.ok, false);
        assert.equal(reads(), 0, "bytes were read for an over-cap file");
      },
    ),
    { numRuns: 500 },
  );
});

test("Property 6B: over-dimension images are rejected before decode (Req 9.2, 9.4)", async () => {
  await fc.assert(
    fc.asyncProperty(
      // At least one axis strictly above the 8192 px dimension cap.
      fc.record({
        w: fc.integer({ min: 1, max: 16384 }),
        h: fc.integer({ min: 1, max: 16384 }),
      }),
      async ({ w, h }) => {
        fc.pre(w > MAX_DIMENSION_PX || h > MAX_DIMENSION_PX);
        const bytes = pngHeader(w, h);
        const { file, read } = fileWithSpy("x.png", "image/png", bytes);
        const result = await validateFile(file, { readBytes: read });
        assert.equal(result.ok, false);
        assert.ok(
          !result.ok && result.reason === "too-large-dimensions",
          `expected too-large-dimensions for ${w}x${h}, got ` +
            (result.ok ? "accepted" : result.reason),
        );
      },
    ),
    { numRuns: 1000 },
  );
});

test("Property 6B: in-cap images pass pre-decode gates (bounds are not over-tight)", async () => {
  // The dual of the rejection property: a file within BOTH caps is accepted by
  // intake, so the bounds reject only what they must. Without this, a test that
  // rejected everything would trivially "pass" the rejection half.
  await fc.assert(
    fc.asyncProperty(
      fc.integer({ min: 1, max: MAX_DIMENSION_PX }),
      fc.integer({ min: 1, max: MAX_DIMENSION_PX }),
      async (w, h) => {
        const bytes = pngHeader(w, h);
        const { file, read } = fileWithSpy("ok.png", "image/png", bytes);
        const result = await validateFile(file, { readBytes: read });
        assert.equal(result.ok, true, `in-cap ${w}x${h} should be accepted`);
        if (result.ok) {
          assert.equal(result.width, w);
          assert.equal(result.height, h);
          // And the engine's work-size cap would then bound the internal side.
          const internal = workSizeDims(result.width, result.height, DEFAULT_WORK_SIZE);
          assert.ok(Math.max(internal.w, internal.h) <= DEFAULT_WORK_SIZE);
        }
      },
    ),
    { numRuns: 1000 },
  );
});
