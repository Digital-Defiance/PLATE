/**
 * Unit tests for image intake validation (web/src/intake.ts, task 7.1).
 *
 * These cover every Requirement-3 path and, crucially, the ORDER the checks run
 * in (type -> size -> read -> dimension probe), asserting the ordering via a spy
 * `readBytes` that records whether/when bytes were read. Real minimal PNG (IHDR)
 * and JPEG (SOF) byte headers are built in-process so `probeDimensions` parses
 * true dimensions without a DOM: `FileLike` is the module's injectable, minimal
 * `{name,type,size,arrayBuffer}` shape, so everything runs under Node.
 *
 *   - 3.1 read within a deadline (injected readDeadlineMs + slow reader)
 *   - 3.2 wrong-type rejected BEFORE bytes are read (MIME + extension fallback)
 *   - 3.3 too-large-bytes before read + post-read re-check when size under-reports
 *   - 3.4 too-large-dimensions via the header probe, with a downsize prompt
 *   - 3.5 empty (zero size / zero bytes) and unreadable (throw / timeout / junk)
 *   - 9.2 pre-decode rejection for the size/dimension caps
 *
 * Run: `cd web && npm run test:spike` (Node's built-in test runner via tsx).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import type { FileLike, IntakeResult, ImageDimensions } from "../src/intake.js";
import {
  ACCEPTED_EXTENSIONS,
  ACCEPTED_MIME_TYPES,
  MAX_DIMENSION_PX,
  READ_DEADLINE_MS,
  UPLOAD_CAP_BYTES,
  extensionOf,
  isAcceptedType,
  probeDimensions,
  readFileBytes,
  toConvertRequest,
  validateFile,
} from "../src/intake.js";

// --- Byte-header builders -------------------------------------------------
//
// These produce *real* minimal headers so `probeDimensions` reads true width
// and height. We only need enough of each format for the IHDR / SOF probe, not
// a decodable image — intake deliberately parses the header and never decodes.

/** 8-byte PNG signature, as `intake.ts` checks it. */
const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

/** Write a 32-bit big-endian value into `buf` at `offset`. */
function writeUint32BE(buf: Uint8Array, offset: number, value: number): void {
  buf[offset] = (value >>> 24) & 0xff;
  buf[offset + 1] = (value >>> 16) & 0xff;
  buf[offset + 2] = (value >>> 8) & 0xff;
  buf[offset + 3] = value & 0xff;
}

/** Write a 16-bit big-endian value into `buf` at `offset`. */
function writeUint16BE(buf: Uint8Array, offset: number, value: number): void {
  buf[offset] = (value >>> 8) & 0xff;
  buf[offset + 1] = value & 0xff;
}

/**
 * A minimal PNG header: 8-byte signature, then the IHDR chunk length, the
 * "IHDR" type tag, and the big-endian width/height the probe reads (offsets
 * 16 and 20). 24 bytes is exactly what `pngDimensions` requires.
 */
function pngHeader(width: number, height: number): Uint8Array {
  const buf = new Uint8Array(24);
  buf.set(PNG_SIGNATURE, 0);
  writeUint32BE(buf, 8, 13); // IHDR data length is always 13
  buf[12] = 0x49; // 'I'
  buf[13] = 0x48; // 'H'
  buf[14] = 0x44; // 'D'
  buf[15] = 0x52; // 'R'
  writeUint32BE(buf, 16, width);
  writeUint32BE(buf, 20, height);
  return buf;
}

/**
 * A minimal JPEG header: SOI, a short APP0/JFIF-ish segment to exercise the
 * marker walk, then a Start-Of-Frame segment carrying the dimensions. `sof`
 * selects the frame marker byte (0xC0 baseline, 0xC2 progressive).
 *
 * SOF segment layout after the 0xFF <marker>: [length:2][precision:1]
 * [height:2][width:2][components...]. We use one component so length = 11.
 */
function jpegHeader(width: number, height: number, sof = 0xc0): Uint8Array {
  const bytes: number[] = [];
  bytes.push(0xff, 0xd8); // SOI
  // A small APP0 segment (length 4: the 2 length bytes + 2 payload bytes) so
  // the marker walk has a real segment to skip before reaching the SOF.
  bytes.push(0xff, 0xe0, 0x00, 0x04, 0x00, 0x00);
  // SOF marker + segment.
  bytes.push(0xff, sof);
  const segLen = 8 + 3 * 1; // length(2)+precision(1)+h(2)+w(2)+ (3 bytes * 1 component)
  const seg = new Uint8Array(segLen);
  writeUint16BE(seg, 0, segLen);
  seg[2] = 8; // sample precision
  writeUint16BE(seg, 3, height);
  writeUint16BE(seg, 5, width);
  seg[7] = 1; // number of components
  seg[8] = 1; // component id
  seg[9] = 0x11; // sampling factors
  seg[10] = 0; // quant table selector
  for (const b of seg) bytes.push(b);
  return new Uint8Array(bytes);
}

// --- FileLike fakes + a spy reader ---------------------------------------

/**
 * Build a `FileLike` from raw bytes. `size` defaults to the real byte length
 * but can be overridden to model a browser-declared size that differs from the
 * actual read (used for the under-report re-check and the pre-read size gate).
 */
function fileFrom(
  name: string,
  type: string,
  bytes: Uint8Array,
  size?: number,
): FileLike {
  return {
    name,
    type,
    size: size ?? bytes.byteLength,
    async arrayBuffer() {
      // Return a standalone ArrayBuffer slice so callers never see our array.
      return bytes.slice().buffer;
    },
  };
}

/** A declared-only FileLike whose `arrayBuffer` must never be called. */
function declaredFile(name: string, type: string, size: number): FileLike {
  return {
    name,
    type,
    size,
    async arrayBuffer(): Promise<ArrayBuffer> {
      throw new Error("arrayBuffer() must not be called for this file");
    },
  };
}

/** A spy byte-reader: records call count and the resolved/overridden bytes. */
function spyReader(bytes: Uint8Array): {
  read: (file: FileLike) => Promise<Uint8Array>;
  calls: () => number;
} {
  let calls = 0;
  return {
    read: async () => {
      calls++;
      return bytes;
    },
    calls: () => calls,
  };
}

function assertAccepted(
  result: IntakeResult,
): asserts result is Extract<IntakeResult, { ok: true }> {
  assert.equal(result.ok, true, `expected accepted, got ${JSON.stringify(result)}`);
}

function assertRejected(
  result: IntakeResult,
): asserts result is Extract<IntakeResult, { ok: false }> {
  assert.equal(result.ok, false, `expected rejection, got ${JSON.stringify(result)}`);
}

// --- Acceptance paths (Requirement 3.1) ----------------------------------

test("accepts a valid PNG: ok with bytes, filename, and true dimensions", async () => {
  const bytes = pngHeader(640, 480);
  const file = fileFrom("logo.png", "image/png", bytes);
  const result = await validateFile(file);

  assertAccepted(result);
  assert.equal(result.filename, "logo.png");
  assert.equal(result.width, 640);
  assert.equal(result.height, 480);
  assert.deepEqual(Array.from(result.imageBytes), Array.from(bytes));
});

test("accepts a valid JPG: ok with bytes, filename, and true dimensions", async () => {
  const bytes = jpegHeader(800, 600);
  const file = fileFrom("photo.jpg", "image/jpeg", bytes);
  const result = await validateFile(file);

  assertAccepted(result);
  assert.equal(result.filename, "photo.jpg");
  assert.equal(result.width, 800);
  assert.equal(result.height, 600);
  assert.deepEqual(Array.from(result.imageBytes), Array.from(bytes));
});

// --- wrong-type (Requirement 3.2) ----------------------------------------

test("wrong-type: rejected BEFORE bytes are read, message names PNG and JPG", async () => {
  const spy = spyReader(new Uint8Array([1, 2, 3]));
  const file = declaredFile("notes.gif", "image/gif", 1234);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "wrong-type");
  assert.equal(spy.calls(), 0, "readBytes must not be called for a wrong-type file");
  assert.match(result.message, /PNG/);
  assert.match(result.message, /JPG/);
});

test("wrong-type: extension fallback when MIME type is empty", async () => {
  // Empty `type` (some drops arrive with no MIME); .bmp extension is rejected.
  const spy = spyReader(new Uint8Array([1, 2, 3]));
  const file = declaredFile("drawing.bmp", "", 1234);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "wrong-type");
  assert.equal(spy.calls(), 0);
});

test("type detection: MIME authoritative, extension used only when MIME empty", () => {
  // MIME present and accepted -> accepted regardless of a misleading extension.
  assert.equal(isAcceptedType({ name: "x.gif", type: "image/png" }), true);
  // MIME present but not accepted -> rejected even with a .png extension.
  assert.equal(isAcceptedType({ name: "x.png", type: "image/gif" }), false);
  // Empty MIME -> fall back to extension.
  assert.equal(isAcceptedType({ name: "x.png", type: "" }), true);
  assert.equal(isAcceptedType({ name: "x.jpeg", type: "" }), true);
  assert.equal(isAcceptedType({ name: "x.webp", type: "" }), false);
});

// --- too-large-bytes (Requirement 3.3, 9.2) ------------------------------

test("too-large-bytes: over-cap File.size rejected before read, downsize prompt", async () => {
  const spy = spyReader(new Uint8Array([1, 2, 3]));
  const file = declaredFile("huge.png", "image/png", UPLOAD_CAP_BYTES + 1);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "too-large-bytes");
  assert.equal(spy.calls(), 0, "an over-cap file must never be read into memory");
  assert.match(result.message, /too large/i);
  assert.match(result.message, /downsize/i);
});

test("too-large-bytes: post-read re-check when File.size under-reports", async () => {
  // Declared size is under the cap, but the real bytes exceed it. Intake reads
  // (the pre-read gate passed), then re-checks the actual length (Req 3.3).
  const realBytes = new Uint8Array(UPLOAD_CAP_BYTES + 10);
  // Give it a valid PNG header so a dimension probe would otherwise succeed;
  // the size re-check must fire first.
  realBytes.set(pngHeader(10, 10), 0);
  const spy = spyReader(realBytes);
  const file = declaredFile("liar.png", "image/png", 100);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "too-large-bytes");
  assert.equal(spy.calls(), 1, "the under-reported file is read, then re-checked");
});

// --- too-large-dimensions (Requirement 3.4, 9.2) -------------------------

test("too-large-dimensions: header over 8192 px on width rejected with downsize prompt", async () => {
  const bytes = pngHeader(MAX_DIMENSION_PX + 1, 100);
  const file = fileFrom("wide.png", "image/png", bytes);
  const result = await validateFile(file);

  assertRejected(result);
  assert.equal(result.reason, "too-large-dimensions");
  assert.match(result.message, /downsize/i);
});

test("too-large-dimensions: header over 8192 px on height rejected (JPEG SOF)", async () => {
  const bytes = jpegHeader(100, MAX_DIMENSION_PX + 1);
  const file = fileFrom("tall.jpg", "image/jpeg", bytes);
  const result = await validateFile(file);

  assertRejected(result);
  assert.equal(result.reason, "too-large-dimensions");
});

test("exactly 8192 px on each axis is accepted (boundary is inclusive)", async () => {
  const bytes = pngHeader(MAX_DIMENSION_PX, MAX_DIMENSION_PX);
  const file = fileFrom("edge.png", "image/png", bytes);
  const result = await validateFile(file);

  assertAccepted(result);
  assert.equal(result.width, MAX_DIMENSION_PX);
  assert.equal(result.height, MAX_DIMENSION_PX);
});

// --- empty (Requirement 3.5) ---------------------------------------------

test("empty: zero declared size rejected without reading", async () => {
  const spy = spyReader(new Uint8Array(0));
  const file = declaredFile("blank.png", "image/png", 0);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "empty");
  assert.equal(spy.calls(), 0, "a zero-size file needs no read");
});

test("empty: zero-length bytes after read rejected", async () => {
  // Declared size is non-zero but the read comes back empty (short read).
  const spy = spyReader(new Uint8Array(0));
  const file = declaredFile("short.png", "image/png", 50);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "empty");
  assert.equal(spy.calls(), 1, "a non-zero declared size is read before the empty check");
});

// --- unreadable (Requirement 3.5) ----------------------------------------

test("unreadable: a readBytes that throws becomes a could-not-read rejection", async () => {
  const file = declaredFile("err.png", "image/png", 100);
  const result = await validateFile(file, {
    readBytes: async () => {
      throw new Error("disk gone");
    },
  });

  assertRejected(result);
  assert.equal(result.reason, "unreadable");
  assert.match(result.message, /could not be read/i);
});

test("unreadable: a read exceeding READ_DEADLINE_MS becomes a could-not-read rejection", async () => {
  const file = declaredFile("slow.png", "image/png", 100);
  // A reader that resolves far later than the (small, injected) deadline.
  const slowRead = () =>
    new Promise<Uint8Array>((resolve) => {
      setTimeout(() => resolve(pngHeader(10, 10)), 100);
    });
  const result = await validateFile(file, { readBytes: slowRead, readDeadlineMs: 5 });

  assertRejected(result);
  assert.equal(result.reason, "unreadable");
});

test("unreadable: a never-resolving read is bounded by the deadline", async () => {
  const file = declaredFile("hang.png", "image/png", 100);
  const neverRead = () => new Promise<Uint8Array>(() => {});
  const result = await validateFile(file, { readBytes: neverRead, readDeadlineMs: 5 });

  assertRejected(result);
  assert.equal(result.reason, "unreadable");
});

test("unreadable: an unrecognised/truncated header is rejected after read", async () => {
  // Valid type + size, read succeeds, but the bytes are neither PNG nor JPEG.
  const junk = new Uint8Array([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]);
  const spy = spyReader(junk);
  const file = declaredFile("junk.png", "image/png", junk.byteLength);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "unreadable");
  assert.equal(spy.calls(), 1, "the bytes are read before the header probe can fail");
});

// --- Ordering (Requirement 3.2 < 3.3 < 3.1 read < 3.4) -------------------

test("ordering: type check precedes size check (wrong type + oversize -> wrong-type)", async () => {
  const spy = spyReader(new Uint8Array([1]));
  const file = declaredFile("bad.gif", "image/gif", UPLOAD_CAP_BYTES + 1);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "wrong-type");
  assert.equal(spy.calls(), 0);
});

test("ordering: size check precedes read (oversize valid type -> no read)", async () => {
  const spy = spyReader(new Uint8Array([1]));
  const file = declaredFile("big.png", "image/png", UPLOAD_CAP_BYTES + 1);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "too-large-bytes");
  assert.equal(spy.calls(), 0, "the size gate short-circuits before any read");
});

test("ordering: read precedes dimension probe (oversize header read then probed)", async () => {
  // Valid type and under the byte cap, so intake reads; only then does the
  // header probe see the oversized dimensions. A spy proves the read happened
  // before the dimension rejection.
  const spy = spyReader(pngHeader(MAX_DIMENSION_PX + 5, 10));
  const file = declaredFile("wide.png", "image/png", 100);
  const result = await validateFile(file, { readBytes: spy.read });

  assertRejected(result);
  assert.equal(result.reason, "too-large-dimensions");
  assert.equal(spy.calls(), 1, "bytes are read before the dimension probe runs");
});

// --- probeDimensions directly --------------------------------------------

test("probeDimensions: parses PNG IHDR width/height", () => {
  const dims = probeDimensions(pngHeader(1920, 1080));
  assert.deepEqual(dims, { width: 1920, height: 1080 } satisfies ImageDimensions);
});

test("probeDimensions: parses baseline JPEG SOF0 width/height", () => {
  const dims = probeDimensions(jpegHeader(1024, 768, 0xc0));
  assert.deepEqual(dims, { width: 1024, height: 768 } satisfies ImageDimensions);
});

test("probeDimensions: parses progressive JPEG SOF2 width/height", () => {
  const dims = probeDimensions(jpegHeader(512, 384, 0xc2));
  assert.deepEqual(dims, { width: 512, height: 384 } satisfies ImageDimensions);
});

test("probeDimensions: returns null for junk bytes", () => {
  assert.equal(probeDimensions(new Uint8Array([0, 1, 2, 3, 4, 5, 6, 7, 8])), null);
});

test("probeDimensions: returns null for a truncated PNG header", () => {
  // Valid signature + IHDR tag but cut off before the full width/height fields.
  assert.equal(probeDimensions(pngHeader(10, 10).slice(0, 18)), null);
});

test("probeDimensions: returns null for a truncated JPEG (SOI only)", () => {
  assert.equal(probeDimensions(new Uint8Array([0xff, 0xd8])), null);
});

test("probeDimensions: returns null for a zero-dimension PNG", () => {
  assert.equal(probeDimensions(pngHeader(0, 100)), null);
});

// --- Pure helpers + constants + toConvertRequest -------------------------

test("extensionOf lowercases, handles no-dot and trailing-dot names", () => {
  assert.equal(extensionOf("photo.JPG"), "jpg");
  assert.equal(extensionOf("archive.tar.gz"), "gz");
  assert.equal(extensionOf("noext"), "");
  assert.equal(extensionOf("trailing."), "");
});

test("constants hold the Requirement-3 limits", () => {
  assert.equal(UPLOAD_CAP_BYTES, 20_000_000);
  assert.equal(MAX_DIMENSION_PX, 8192);
  assert.equal(READ_DEADLINE_MS, 2000);
  assert.deepEqual([...ACCEPTED_EXTENSIONS], ["png", "jpg", "jpeg"]);
  assert.deepEqual([...ACCEPTED_MIME_TYPES], ["image/png", "image/jpeg"]);
});

test("readFileBytes reads a FileLike's arrayBuffer into a Uint8Array", async () => {
  const bytes = pngHeader(4, 4);
  const file = fileFrom("x.png", "image/png", bytes);
  const read = await readFileBytes(file);
  assert.deepEqual(Array.from(read), Array.from(bytes));
});

test("toConvertRequest packages accepted bytes, filename, and config", async () => {
  const bytes = pngHeader(32, 32);
  const file = fileFrom("mark.png", "image/png", bytes);
  const result = await validateFile(file);
  assertAccepted(result);

  const config = { preset: "logo" } as const;
  const request = toConvertRequest(result, config);
  assert.equal(request.filename, "mark.png");
  assert.deepEqual(request.config, config);
  assert.deepEqual(Array.from(request.imageBytes), Array.from(bytes));
});
