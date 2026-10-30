"""Regressions for the declared-depth and batch-status findings in docs/AUDIT.md."""
import numpy as np
import pytest
from PIL import Image

from plate import pipeline
from plate.cli import main
from plate.imageio import _to_8bit, open_rgba


@pytest.mark.parametrize('value', [0, 1, 127, 128, 200, 255, 256, 257, 32768, 65535])
def test_sixteen_bit_png_uses_its_declared_range_even_when_dark(tmp_path, value):
    path = tmp_path/'gray16.png'
    Image.fromarray(np.full((16, 16), value, np.uint16)).save(path)
    expected = round(value*255/65535)
    actual = np.asarray(open_rgba(path))
    assert np.all(actual[..., :3] == expected)
    assert np.all(actual[..., 3] == 255)


@pytest.mark.parametrize('dtype', ['<u2', '>u2'])
def test_declared_sixteen_bit_modes_use_the_same_range(dtype):
    values = np.array([[0, 128, 200], [255, 1, 127]], dtype=dtype)
    expected = np.rint(values.astype(float)*255/65535).astype(np.uint8)
    assert np.array_equal(np.asarray(_to_8bit(Image.fromarray(values))), expected)


def test_legacy_pillow_integer_png_keeps_declared_depth_after_exif_copy(tmp_path, monkeypatch):
    path = tmp_path/'legacy.png'
    Image.fromarray(np.full((16, 16), 200, np.uint16)).save(path)
    original_open = Image.open

    def legacy_open(filename):
        # Older Pillow versions expose a 16-bit PNG as mode I. EXIF transpose
        # returns a copy, so the format hint must be retained before that copy.
        with original_open(filename) as source:
            image = source.convert('I')
        image.format = 'PNG'
        return image

    monkeypatch.setattr(Image, 'open', legacy_open)
    assert np.all(np.asarray(open_rgba(path))[..., :3] == 1)


def test_general_integer_and_normalized_float_images_keep_existing_policy():
    integer = Image.fromarray(np.full((4, 4), 200, np.int32))
    normalized = Image.fromarray(np.full((4, 4), .5, np.float32))
    assert np.all(np.asarray(_to_8bit(integer)) == 200)
    assert np.all(np.asarray(_to_8bit(normalized)) == 128)


def test_dark_sixteen_bit_trace_matches_independent_eight_bit_reference(tmp_path):
    path16, path8 = tmp_path/'dark16.png', tmp_path/'dark8.png'
    Image.fromarray(np.full((40, 40), 200, np.uint16)).save(path16)
    Image.new('L', (40, 40), 1).save(path8)
    assert pipeline.run(path16).svg == pipeline.run(path8).svg


@pytest.mark.parametrize('good,bad', [(2, 0), (0, 2), (2, 2)])
def test_batch_exit_status_and_summary_reflect_failures_and_finish_valid_files(tmp_path, capsys, good, bad):
    source, output = tmp_path/'inputs', tmp_path/'outputs'
    source.mkdir()
    for i in range(bad):
        (source/f'a_bad_{i}.png').write_bytes(b'not an image')
    if good:
        nested = source/'z_nested'
        nested.mkdir()
        for i in range(good):
            Image.new('RGB', (16, 16), (200, 60, 60)).save(nested/f'good_{i}.png')
    code = main(['batch', str(source), '-o', str(output)])
    assert code == (1 if bad else 0)
    captured = capsys.readouterr()
    assert f'{good} succeeded, {bad} failed' in (captured.err if bad else captured.out)
    assert captured.err.count(': FAILED (') == bad
    assert len(list(output.rglob('*.svg'))) == good
    for i in range(good):
        assert (output/'z_nested'/f'good_{i}.svg').exists()


def test_batch_empty_input_keeps_usage_error_exit_code(tmp_path, capsys):
    source = tmp_path/'empty'
    source.mkdir()
    assert main(['batch', str(source), '-o', str(tmp_path/'output')]) == 2
    assert 'no images' in capsys.readouterr().err
