/**
 * Image intake: drag-drop and file-picker validation (Browser_Shell, main thread).
 *
 * This is the first stage of the browser pipeline. It turns a dropped or picked
 * {@link File} into either validated bytes + filename (ready to hand to
 * {@link module:protocol.ConvertRequest}) or a typed rejection the UI can render.
 * It never calls the Conversion_Worker and never runs the engine: all heavy
 * pixel decoding happens later in the worker (task 8.1). Intake only does the
 * cheap, pre-decode checks Requirement 3 demands, in the order the requirement
 * demands, so the UI never waits on a conversion that cannot succeed.
 *
 * Validation order (Requirement 3.1-3.5, 9.2):
 *   1. Type check by MIME/extension, BEFORE reading bytes          (3.2)
 *   2. Byte-size check against the Upload_Cap, BEFORE reading bytes (3.3, 9.2)
 *   3. Read the bytes (deadline-bounded)                            (3.1)
 *   4. Empty / zero-byte check                                     (3.5)
 *   5. Dimension check via a lightweight header probe, BEFORE
 *      decode: parse PNG IHDR / JPEG SOF rather than decoding      (3.4, 9.2)
 *   6. Undecodable / unrecognised header -> could-not-read         (3.5)
 *
 * The caller keeps the drop zone ready on every rejection (Requirement 3.2,
 * 3.5); this module is pure and side-effect free, so "keeping the drop zone
 * ready" is simply the caller not tearing it down on a rejected result.
 *
 * Exact limits are fixed by the requirements, not guessed here:
 *   - Upload_Cap byte limit  = 20 MB   (Requirement 3.3)
 *   - Upload_Cap pixel limit = 8192 px on either axis (Requirement 3.4)
 *   - read deadline          = 2 s     (Requirement 3.1)
 */

import type { ConvertRequest } from "./protocol.js";

/**
 * Upload_Cap byte limit: 20 megabytes (Requirement 3.3). "Megabyte" here is the
 * decimal SI megabyte (10^6 bytes) the requirement states as "20 megabytes".
 */
export const UPLOAD_CAP_BYTES = 20_000_000;

/** Upload_Cap pixel limit: reject above 8192 px on either axis (Requirement 3.4). */
export const MAX_DIMENSION_PX = 8192;

/** Read deadline: accepted bytes must be available within 2 s (Requirement 3.1). */
export const READ_DEADLINE_MS = 2000;

/** The only accepted image types (Requirement 3.2). */
export const ACCEPTED_EXTENSIONS = ["png", "jpg", "jpeg"] as const;

/** MIME types that map to the accepted extensions (Requirement 3.2). */
export const ACCEPTED_MIME_TYPES = ["image/png", "image/jpeg"] as const;

/**
 * Why a file was rejected. Each reason maps to one Requirement 3 clause so the
 * UI can choose the right message and recovery affordance; the human-readable
 * {@link IntakeRejection.message} is the text the design's acceptance criteria
 * require the shell to display.
 */
export type IntakeRejectionReason =
  /** Not a PNG or JPG; rejected before reading bytes (3.2). */
  | "wrong-type"
  /** Above the 20 MB Upload_Cap; rejected before decode (3.3, 9.2). */
  | "too-large-bytes"
  /** Above 8192 px on either axis; rejected before decode (3.4, 9.2). */
  | "too-large-dimensions"
  /** Empty / zero-byte file (3.5). */
  | "empty"
  /** Bytes could not be read or the header could not be parsed (3.5). */
  | "unreadable";

/** A validated file: raw bytes plus the original filename, ready for conversion. */
export interface IntakeAccepted {
  ok: true;
  /** Raw file bytes; transfer (not copy) these into the worker on convert. */
  imageBytes: Uint8Array;
  /** Original filename; its extension selects the worker's `/input.<ext>` path. */
  filename: string;
  /** Pixel dimensions read from the header probe (never decoded). */
  width: number;
  height: number;
}

/** A typed rejection carrying the reason and a user-facing message. */
export interface IntakeRejection {
  ok: false;
  reason: IntakeRejectionReason;
  /** Message the Browser_Shell displays (Requirement 3.2-3.5). */
  message: string;
}

/** The result of validating one file: accepted bytes or a typed rejection. */
export type IntakeResult = IntakeAccepted | IntakeRejection;

/**
 * Options for {@link validateFile}, injectable so unit tests can supply a fake
 * byte reader and a deterministic clock without a DOM.
 */
export interface IntakeOptions {
  /**
   * Reads a file's bytes. Defaults to {@link readFileBytes}, which uses
   * {@link File.arrayBuffer}. Must reject if reading fails.
   */
  readBytes?: (file: FileLike) => Promise<Uint8Array>;
  /** Read deadline override (ms). Defaults to {@link READ_DEADLINE_MS}. */
  readDeadlineMs?: number;
}

/**
 * The minimal subset of the DOM {@link File} this module needs. Declaring it
 * explicitly keeps the module unit-testable in Node (no `File` global needed)
 * and documents exactly which fields intake reads.
 */
export interface FileLike {
  name: string;
  type: string;
  size: number;
  arrayBuffer(): Promise<ArrayBuffer>;
}

const WRONG_TYPE_MESSAGE =
  "Only PNG and JPG images are accepted. Please choose a PNG or JPG file.";
const TOO_LARGE_BYTES_MESSAGE =
  "That file is too large (over 20 MB). Please downsize the image and try again.";
const TOO_LARGE_DIMENSIONS_MESSAGE =
  `Those image dimensions are too large (over ${MAX_DIMENSION_PX} px on a side). ` +
  "Please downsize the image and try again.";
const EMPTY_MESSAGE = "That file is empty. Please choose a PNG or JPG image.";
const UNREADABLE_MESSAGE =
  "That image could not be read. Please choose a valid PNG or JPG file.";

/** Lowercase file extension without the dot, or "" when there is none. */
export function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  if (dot < 0 || dot === filename.length - 1) return "";
  return filename.slice(dot + 1).toLowerCase();
}

/**
 * True iff the file is a PNG or JPG, judged BEFORE reading bytes (Requirement
 * 3.2). A browser-supplied MIME type is authoritative when present; otherwise
 * we fall back to the filename extension (some drops arrive with an empty
 * `type`). The header is NOT inspected here — that would require reading bytes,
 * which 3.2 forbids before the type decision.
 */
export function isAcceptedType(file: Pick<FileLike, "name" | "type">): boolean {
  const mime = file.type.toLowerCase();
  if (mime) {
    return (ACCEPTED_MIME_TYPES as readonly string[]).includes(mime);
  }
  return (ACCEPTED_EXTENSIONS as readonly string[]).includes(extensionOf(file.name));
}

/** Reject helper: keeps the rejection shapes consistent. */
function reject(reason: IntakeRejectionReason, message: string): IntakeRejection {
  return { ok: false, reason, message };
}

/**
 * Validate one dropped or picked file.
 *
 * Runs the Requirement 3 checks in order and short-circuits on the first
 * failure so the cheapest checks (type, declared size) happen before any bytes
 * are read, and the header probe happens before any decode. Returns validated
 * bytes + filename on success or a typed rejection; never throws for an invalid
 * file (a failed byte read becomes an `unreadable` rejection, Requirement 3.5).
 *
 * The drop zone stays ready on rejection because this function has no side
 * effects: the caller simply leaves its UI in place when `ok` is false.
 */
export async function validateFile(
  file: FileLike,
  options: IntakeOptions = {},
): Promise<IntakeResult> {
  // 1. Type check BEFORE reading bytes (Requirement 3.2).
  if (!isAcceptedType(file)) {
    return reject("wrong-type", WRONG_TYPE_MESSAGE);
  }

  // 2. Byte-size check BEFORE reading bytes (Requirement 3.3, 9.2). `File.size`
  //    is known without reading the contents, so an over-cap file never gets
  //    read into memory.
  if (file.size > UPLOAD_CAP_BYTES) {
    return reject("too-large-bytes", TOO_LARGE_BYTES_MESSAGE);
  }

  // 2a. Zero declared size is an empty file (Requirement 3.5); no need to read.
  if (file.size === 0) {
    return reject("empty", EMPTY_MESSAGE);
  }

  // 3. Read the bytes, deadline-bounded (Requirement 3.1).
  const read = options.readBytes ?? readFileBytes;
  const deadline = options.readDeadlineMs ?? READ_DEADLINE_MS;
  let bytes: Uint8Array;
  try {
    bytes = await withDeadline(read(file), deadline);
  } catch {
    // A failed or timed-out read is a could-not-read rejection, not a crash.
    return reject("unreadable", UNREADABLE_MESSAGE);
  }

  // 4. Empty / zero-byte after reading (Requirement 3.5). `File.size` can lie
  //    or the read can come back short; guard on the actual bytes too.
  if (bytes.byteLength === 0) {
    return reject("empty", EMPTY_MESSAGE);
  }

  // The actual bytes may exceed the cap even if `File.size` under-reported;
  // re-check against the real length before going further (Requirement 3.3).
  if (bytes.byteLength > UPLOAD_CAP_BYTES) {
    return reject("too-large-bytes", TOO_LARGE_BYTES_MESSAGE);
  }

  // 5. Dimension check BEFORE decode via a lightweight header probe
  //    (Requirement 3.4, 9.2). We parse just enough of the PNG IHDR / JPEG SOF
  //    to read width/height; we do NOT decode pixels here (the worker does).
  const dims = probeDimensions(bytes);
  if (dims === null) {
    // 6. Header unrecognised / truncated -> could-not-read (Requirement 3.5).
    //    The engine's own `ImageLoadError` is the final authority on decode;
    //    this is the cheap pre-decode gate that rejects obviously bad headers.
    return reject("unreadable", UNREADABLE_MESSAGE);
  }
  if (dims.width > MAX_DIMENSION_PX || dims.height > MAX_DIMENSION_PX) {
    return reject("too-large-dimensions", TOO_LARGE_DIMENSIONS_MESSAGE);
  }

  return {
    ok: true,
    imageBytes: bytes,
    filename: file.name,
    width: dims.width,
    height: dims.height,
  };
}

/**
 * Build a {@link ConvertRequest} from an accepted intake result and the UI's
 * current settings. Intake stays decoupled from the client (task 6.1 wires
 * this into {@link module:protocol.ConvertRequest}); this helper just packages
 * the validated bytes + filename with the config.
 */
export function toConvertRequest(
  accepted: IntakeAccepted,
  config: ConvertRequest["config"],
): ConvertRequest {
  return {
    imageBytes: accepted.imageBytes,
    filename: accepted.filename,
    config,
  };
}

/** Default byte reader: read the whole file via {@link File.arrayBuffer}. */
export async function readFileBytes(file: FileLike): Promise<Uint8Array> {
  const buffer = await file.arrayBuffer();
  return new Uint8Array(buffer);
}

/** Reject a promise if it does not settle within `ms` milliseconds. */
function withDeadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  if (!Number.isFinite(ms) || ms <= 0) return promise;
  return new Promise<T>((resolve, reject_) => {
    const timer = setTimeout(() => reject_(new Error("read timed out")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject_(error);
      },
    );
  });
}

/** Pixel dimensions read from an image header, without decoding pixels. */
export interface ImageDimensions {
  width: number;
  height: number;
}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

/**
 * Read width/height from a PNG or JPEG header without a full decode.
 *
 * - PNG: the 8-byte signature is followed by the IHDR chunk whose first two
 *   32-bit big-endian fields are width and height.
 * - JPEG: scan marker segments for a Start-Of-Frame (SOF0..SOF15, excluding the
 *   non-frame markers) and read the 16-bit height and width that follow.
 *
 * Returns `null` when the bytes are neither a recognisable PNG nor JPEG header,
 * or when the header is truncated before the dimensions. This is a cheap gate,
 * not a decoder: the worker/engine does the authoritative decode (Requirement
 * 3.4 "before decode").
 */
export function probeDimensions(bytes: Uint8Array): ImageDimensions | null {
  if (isPng(bytes)) return pngDimensions(bytes);
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    return jpegDimensions(bytes);
  }
  return null;
}

function isPng(bytes: Uint8Array): boolean {
  if (bytes.length < PNG_SIGNATURE.length) return false;
  for (let i = 0; i < PNG_SIGNATURE.length; i++) {
    if (bytes[i] !== PNG_SIGNATURE[i]) return false;
  }
  return true;
}

function pngDimensions(bytes: Uint8Array): ImageDimensions | null {
  // After the 8-byte signature: [length:4][type:4 == "IHDR"][width:4][height:4]
  // IHDR starts at offset 8; width at 16, height at 20. Need 24 bytes total.
  if (bytes.length < 24) return null;
  const isIHDR =
    bytes[12] === 0x49 && // 'I'
    bytes[13] === 0x48 && // 'H'
    bytes[14] === 0x44 && // 'D'
    bytes[15] === 0x52; // 'R'
  if (!isIHDR) return null;
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const width = view.getUint32(16, false);
  const height = view.getUint32(20, false);
  if (width === 0 || height === 0) return null;
  return { width, height };
}

function jpegDimensions(bytes: Uint8Array): ImageDimensions | null {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  // Start after the SOI marker (0xFFD8).
  let offset = 2;
  const len = bytes.length;
  while (offset + 1 < len) {
    // Markers are 0xFF followed by a marker byte; skip any fill 0xFF bytes.
    if (bytes[offset] !== 0xff) {
      offset++;
      continue;
    }
    let marker = bytes[offset + 1]!;
    // Skip padding fill bytes (0xFF 0xFF ...).
    while (marker === 0xff && offset + 2 < len) {
      offset++;
      marker = bytes[offset + 1]!;
    }
    offset += 2;

    // Standalone markers with no length payload: RSTn (0xD0-0xD7), SOI, EOI, TEM.
    if (
      (marker >= 0xd0 && marker <= 0xd7) ||
      marker === 0xd8 ||
      marker === 0xd9 ||
      marker === 0x01
    ) {
      continue;
    }

    // Every other marker carries a 2-byte big-endian segment length.
    if (offset + 1 >= len) return null;
    const segmentLength = view.getUint16(offset, false);
    if (segmentLength < 2) return null;

    if (isSof(marker)) {
      // SOF payload: [precision:1][height:2][width:2]... starting after length.
      if (offset + 7 >= len) return null;
      const height = view.getUint16(offset + 3, false);
      const width = view.getUint16(offset + 5, false);
      if (width === 0 || height === 0) return null;
      return { width, height };
    }

    offset += segmentLength;
  }
  return null;
}

/**
 * True for a Start-Of-Frame marker that carries frame dimensions. SOF0-SOF15
 * are 0xC0-0xCF except 0xC4 (DHT), 0xC8 (JPG extension) and 0xCC (DAC), which
 * are not frame headers.
 */
function isSof(marker: number): boolean {
  if (marker < 0xc0 || marker > 0xcf) return false;
  return marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
}
