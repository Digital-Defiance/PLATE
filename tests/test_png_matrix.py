"""Empirical PNG coverage: exact decode pixels, plus equivalent-encoding traces."""
import struct

import numpy as np
import pytest
from PIL import Image
from png_fixtures import FORMATS, SIGNATURE, case, chunk, encode

from plate import pipeline
from plate.config import Config
from plate.imageio import ImageLoadError, open_rgba


@pytest.mark.parametrize('interlace', [False, True], ids=['rows', 'adam7'])
@pytest.mark.parametrize('kind,depth', FORMATS, ids=[f'type{t}-{d}bit' for t, d in FORMATS])
def test_all_fifteen_legal_png_encodings_decode_to_expected_samples(tmp_path, kind, depth, interlace):
    png, expected = case(kind, depth, interlace=interlace)
    path = tmp_path/'matrix.png'
    path.write_bytes(png)
    assert png[24:26] == bytes([depth, kind]) and png[28] == int(interlace)
    actual = open_rgba(path)
    assert actual.mode == 'RGBA' and actual.size == (17, 13)
    assert np.array_equal(np.asarray(actual), expected)


KEYED = [(t, d) for t, d in FORMATS if t in (0, 2, 3)]


@pytest.mark.parametrize('interlace', [False, True], ids=['rows', 'adam7'])
@pytest.mark.parametrize('kind,depth', KEYED, ids=[f'type{t}-{d}bit' for t, d in KEYED])
def test_trns_keys_and_palette_partial_alpha_keep_exact_transparency(tmp_path, kind, depth, interlace):
    png, expected = case(kind, depth, keyed=True, interlace=interlace)
    path = tmp_path/'transparent.png'
    path.write_bytes(png)
    assert (expected[..., 3] == 0).any() and (expected[..., 3] == 255).any()
    actual = np.asarray(open_rgba(path))
    assert np.array_equal(actual[..., 3], expected[..., 3])
    assert np.array_equal(actual, expected)


@pytest.mark.parametrize('kind', [0, 2])
@pytest.mark.parametrize('interlace', [False, True])
def test_16bit_transparency_compares_full_values_before_quantizing(tmp_path, kind, interlace):
    gray = np.tile([200, 201, 128, 129, 65535], (9, 1))
    samples = gray if kind == 0 else np.stack([gray, np.full_like(gray, 1000), np.full_like(gray, 3000)], axis=-1)
    key = struct.pack('!H', 200) if kind == 0 else struct.pack('!HHH', 200, 1000, 3000)
    path = tmp_path/'near-key.png'
    path.write_bytes(encode(samples, 16, kind, transparency=key, interlace=interlace))
    actual = np.asarray(open_rgba(path))
    assert np.array_equal(actual[..., 3], np.where(gray == 200, 0, 255))
    assert np.array_equal(actual[:, 0, :3], actual[:, 1, :3])  # same 8-bit RGB, different alpha


@pytest.mark.parametrize('size', [(1, 1), (1, 9), (9, 1), (3, 3), (8, 8), (9, 9)])
def test_adam7_empty_passes_and_partial_packed_bytes(tmp_path, size):
    png, expected = case(3, 2, keyed=True, interlace=True, size=size, split_idat=True)
    path = tmp_path/'tiny.png'
    path.write_bytes(png)
    assert np.array_equal(np.asarray(open_rgba(path)), expected)


@pytest.mark.parametrize('kind,depth', FORMATS, ids=[f'type{t}-{d}bit' for t, d in FORMATS])
def test_equivalent_png_encodings_produce_identical_editable_svg(tmp_path, kind, depth):
    yy, xx = np.mgrid[:48, :64]
    ink = (xx >= 10) & (xx < 54) & (yy >= 8) & (yy < 40)
    ink &= ~((xx >= 25) & (xx < 39) & (yy >= 18) & (yy < 30))
    gray = np.where(ink, 0, (1 << depth)-1)
    alpha = np.where(ink, (1 << depth)-1, 0)
    rgb = np.repeat(gray[..., None], 3, axis=-1)
    palette, transparency = None, None
    if kind == 0:
        samples = gray
        transparency = struct.pack('!H', (1 << depth)-1)
    elif kind == 2:
        samples = rgb
        transparency = struct.pack('!HHH', *([(1 << depth)-1]*3))
    elif kind == 3:
        samples = np.where(ink, 0, 1)
        palette = [[0, 0, 0], [255, 255, 255]]
        transparency = bytes([255, 0])
    elif kind == 4:
        samples = np.stack([gray, alpha], axis=-1)
    else:
        samples = np.concatenate([rgb, alpha[..., None]], axis=-1)
    path = tmp_path/'encoded.png'
    path.write_bytes(encode(samples, depth, kind, palette=palette, transparency=transparency, interlace=True))
    reference = np.repeat(np.where(ink, 0, 255)[..., None], 4, axis=-1).astype('uint8')
    reference[..., 3] = np.where(ink, 255, 0)
    ref = tmp_path/'reference.png'
    Image.fromarray(reference).save(ref)
    expected = pipeline.run(ref)
    assert expected.stats['shapes'] == 1 and 'fill-rule="evenodd"' in expected.svg
    assert pipeline.run(path).svg == expected.svg


@pytest.mark.parametrize('depth,kind', [(3, 0), (16, 3), (8, 7)])
def test_illegal_png_colour_depth_combinations_fail_cleanly(tmp_path, depth, kind):
    import zlib
    path = tmp_path/'illegal.png'
    path.write_bytes(SIGNATURE + chunk(b'IHDR', struct.pack('!IIBBBBB', 8, 8, depth, kind, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(bytes(72))) + chunk(b'IEND', b''))
    with pytest.raises(ImageLoadError):
        open_rgba(path)


@pytest.mark.parametrize('kind,depth', [(0, 8), (0, 16), (2, 8), (2, 16), (4, 16), (6, 16)])
def test_png_exif_orientation_is_applied_once_after_depth_normalization(tmp_path, kind, depth):
    exif = Image.Exif()
    exif[0x0112] = 6
    png, expected = case(kind, depth, ancillary=[(b'eXIf', exif.tobytes()[6:])])
    path = tmp_path/'oriented.png'
    path.write_bytes(png)
    assert np.array_equal(np.asarray(open_rgba(path)), np.rot90(expected, -1))


@pytest.mark.parametrize('kind,depth', [(0, 8), (0, 16), (2, 8), (2, 16), (6, 8), (6, 16)])
@pytest.mark.parametrize('metadata', [[(b'gAMA', struct.pack('!I', 100000))], [(b'sRGB', b'\x00')]],
                         ids=['gamma-1', 'srgb'])
def test_colour_metadata_follows_the_documented_sample_based_policy(tmp_path, kind, depth, metadata):
    # This pins the current limit, not colour-managed display equivalence. Samples
    # are normalized but no ICC/gamma conversion is claimed or silently applied.
    png, expected = case(kind, depth, ancillary=metadata)
    path = tmp_path/'tagged.png'
    path.write_bytes(png)
    assert np.array_equal(np.asarray(open_rgba(path)), expected)


@pytest.fixture(scope='module')
def srgb_profile():
    cms = pytest.importorskip('PIL.ImageCms', reason='profile fixture generation needs Pillow LittleCMS')
    return cms.ImageCmsProfile(cms.createProfile('sRGB')).tobytes()


@pytest.mark.parametrize('kind,depth', [(2, 8), (2, 16), (6, 8), (6, 16)])
def test_embedded_valid_icc_profile_is_not_a_colour_management_claim(tmp_path, kind, depth, srgb_profile):
    import zlib
    png, expected = case(kind, depth, ancillary=[(b'iCCP', b'sRGB\0\0'+zlib.compress(srgb_profile))])
    path = tmp_path/'profiled.png'
    path.write_bytes(png)
    with Image.open(path) as image:
        assert image.info['icc_profile'] == srgb_profile
    assert np.array_equal(np.asarray(open_rgba(path)), expected)


@pytest.mark.parametrize('work_size', [48, 1536])
def test_fully_transparent_rgb_cannot_change_the_traced_artwork(tmp_path, work_size):
    rng = np.random.default_rng(239)
    pixels = np.zeros((96, 128, 4), dtype='uint8')
    pixels[20:76, 30:98] = (40, 100, 210, 255)
    reference = tmp_path/'clean.png'
    Image.fromarray(pixels).save(reference)
    hidden = pixels[..., 3] == 0
    pixels[hidden, :3] = rng.integers(0, 256, (hidden.sum(), 3), dtype='uint8')
    noisy = tmp_path/'hidden-rgb.png'
    Image.fromarray(pixels).save(noisy)
    assert pipeline.run(noisy, Config(work_size=work_size)).svg == pipeline.run(reference, Config(work_size=work_size)).svg


@pytest.mark.parametrize('default_image', [False, True])
def test_apng_uses_only_the_default_or_first_image(tmp_path, default_image):
    first = Image.new('RGBA', (32, 24), (200, 30, 50, 255))
    second = Image.new('RGBA', first.size, (10, 100, 240, 128))
    path = tmp_path/'animation.png'
    first.save(path, save_all=True, append_images=[second], duration=100, loop=0, default_image=default_image)
    with Image.open(path) as image:
        assert image.is_animated
    assert np.array_equal(np.asarray(open_rgba(path)), np.asarray(first))


@pytest.mark.parametrize('broken', [None, np.zeros((13, 17), dtype='uint8')], ids=['missing', 'lost-depth'])
def test_unavailable_full_depth_decode_fails_without_a_lossy_fallback(tmp_path, monkeypatch, broken):
    import cv2
    path = tmp_path/'full-depth.png'
    path.write_bytes(case(2, 16)[0])
    monkeypatch.setattr(cv2, 'imread', lambda *args: broken)
    with pytest.raises(ImageLoadError, match='full sample depth'):
        open_rgba(path)


def test_full_depth_decoder_exceptions_are_readable_input_errors(tmp_path, monkeypatch):
    import cv2
    path = tmp_path/'full-depth.png'
    path.write_bytes(case(2, 16)[0])

    def broken_decode(*args):
        raise cv2.error('full-depth decode failed')

    monkeypatch.setattr(cv2, 'imread', broken_decode)
    with pytest.raises(ImageLoadError, match='cannot read.*full-depth decode failed'):
        open_rgba(path)


@pytest.mark.parametrize('damage', ['header-crc', 'truncated-deflate'])
def test_damaged_png_streams_fail_cleanly(tmp_path, damage):
    import zlib
    png, _ = case(6, 8)
    if damage == 'header-crc':
        png = png[:29] + bytes(4) + png[33:]
    else:
        png = SIGNATURE + chunk(b'IHDR', struct.pack('!IIBBBBB', 17, 13, 8, 6, 0, 0, 0))
        png += chunk(b'IDAT', zlib.compress(bytes(13*(17*4+1)))[:6]) + chunk(b'IEND', b'')
    path = tmp_path/'damaged.png'
    path.write_bytes(png)
    with pytest.raises(ImageLoadError):
        open_rgba(path)
