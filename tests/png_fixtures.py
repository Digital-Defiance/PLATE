"""Small independent PNG encoder for decode contracts, not a production decoder.

No Pillow/OpenCV encoding: raw samples, tRNS keys and Adam7 passes follow the PNG
specification. Expected pixels are computed from the original integer samples.
https://www.w3.org/TR/png/
"""
import struct
import zlib

import numpy as np

SIGNATURE = b'\x89PNG\r\n\x1a\n'
FORMATS = [(0, d) for d in (1, 2, 4, 8, 16)] + [(2, d) for d in (8, 16)] + [
    (3, d) for d in (1, 2, 4, 8)] + [(t, d) for t in (4, 6) for d in (8, 16)]
ADAM7 = [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
         (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]


def chunk(tag, data):
    return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)


def _paeth(left, up, upper_left):
    predicted = left + up - upper_left
    distances = [abs(predicted - n) for n in (left, up, upper_left)]
    return (left, up, upper_left)[distances.index(min(distances))]


def encode(samples, depth, kind, *, transparency=None, palette=None, interlace=False,
           ancillary=(), filters=(0, 1, 2, 3, 4), split_idat=False):
    """Encode integer samples; filter on packed bytes, with per-pass previous rows."""
    samples = np.asarray(samples)
    height, width = samples.shape[:2]
    channels = 1 if samples.ndim == 2 else samples.shape[2]
    bpp = max(1, (channels * depth + 7) // 8)
    data = []
    for x, y, dx, dy in ADAM7 if interlace else [(0, 0, 1, 1)]:
        subset = samples[y::dy, x::dx]
        if not subset.size:
            continue
        previous = None
        for row_number, row in enumerate(subset):
            if depth == 16:
                raw = row.astype('>u2').tobytes()
            elif depth == 8:
                raw = row.astype('uint8').tobytes()
            else:
                values, per_byte = row.reshape(-1).tolist(), 8 // depth
                raw = bytes(sum(int(v) << (8-depth*(j+1)) for j, v in enumerate(values[i:i+per_byte]))
                            for i in range(0, len(values), per_byte))
            filtered = bytearray()
            method = filters[row_number % len(filters)]
            for i, value in enumerate(raw):
                left = raw[i-bpp] if i >= bpp else 0
                up = previous[i] if previous else 0
                upper_left = previous[i-bpp] if previous and i >= bpp else 0
                predictor = (0, left, up, (left+up)//2, _paeth(left, up, upper_left))[method]
                filtered.append((value-predictor) & 255)
            data.append(bytes([method]) + filtered)
            previous = raw
    header = struct.pack('!IIBBBBB', width, height, depth, kind, 0, 0, int(interlace))
    chunks = [chunk(b'IHDR', header)]
    chunks.extend(chunk(tag, payload) for tag, payload in ancillary)
    if palette is not None:
        chunks.append(chunk(b'PLTE', np.asarray(palette, dtype='uint8').tobytes()))
    if transparency is not None:
        chunks.append(chunk(b'tRNS', transparency))
    compressed = zlib.compress(b''.join(data))
    parts = [compressed] if not split_idat else [compressed[:3], b'', compressed[3:]]
    chunks.extend(chunk(b'IDAT', part) for part in parts)
    return SIGNATURE + b''.join(chunks) + chunk(b'IEND', b'')


def case(kind, depth, *, keyed=False, interlace=False, size=(17, 13), **options):
    """Return an encoded PNG and its independent 8-bit RGBA sample reference."""
    width, height = size
    yy, xx = np.mgrid[:height, :width]
    index = xx + 3*yy
    maximum = (1 << depth)-1
    values = ([0, 1, 127, 128, 200, 201, 255, 256, 257, 1000, 3000, 32768, 65535]
              if depth == 16 else sorted({0, 1, maximum//2, maximum}))
    values = np.array(values)
    gray = values[index % len(values)]
    alpha = values[(index+2) % len(values)]
    palette, transparency = None, None
    if kind == 3:
        n = 1 << depth
        indices = (xx + width*yy) % n
        indices[0, 0] = n-1  # exercise high palette indices and implicit opaque tail
        if indices.size > 1:
            indices.flat[-1] = 0
        samples = indices
        numbers = np.arange(n)
        palette = np.stack([(numbers*37) % 256, (numbers*67) % 256, (numbers*17) % 256], axis=-1)
        expected = np.concatenate([palette[indices], np.full((height, width, 1), 255)], axis=-1).astype('uint8')
        if keyed:
            alphas = np.full(n, 255, dtype='uint8')
            alphas[:min(n-1, 4)] = [0, 64, 128, 191][:min(n-1, 4)]
            transparency = alphas[:-1].tobytes()
            expected[..., 3] = alphas[indices]
    else:
        rgb = np.repeat(gray[..., None], 3, axis=2) if kind in (0, 4) else np.stack(
            [values[(index+i) % len(values)] for i in range(3)], axis=-1)
        samples = {0: gray, 2: rgb, 4: np.stack([gray, alpha], axis=-1),
                   6: np.concatenate([rgb, alpha[..., None]], axis=-1)}[kind]
        expected = np.concatenate([np.rint(rgb*255/maximum),
                                   np.full((height, width, 1), 255)], axis=-1).astype('uint8')
        if kind in (4, 6):
            expected[..., 3] = np.rint(alpha*255/maximum).astype('uint8')
        if keyed:
            if kind == 0:
                key = 200 if depth == 16 else 1 if depth < 4 else maximum//2
                transparency = struct.pack('!H', key)
                expected[..., 3][gray == key] = 0
            else:
                key = rgb[0, 0]
                transparency = struct.pack('!HHH', *key)
                expected[..., 3][np.all(rgb == key, axis=-1)] = 0
    return encode(samples, depth, kind, transparency=transparency, palette=palette,
                  interlace=interlace, **options), expected
