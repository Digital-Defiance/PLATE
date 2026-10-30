"""Robustness of the input path: unusual formats, degenerate images, bad files.

Regressions from the input robustness sweep: 16-bit PNGs traced blank, EXIF-rotated
photos came out sideways, fully transparent images crashed, tiny icons emitted an
empty SVG or a stray lens, unreadable files printed tracebacks, small antialiased
text lost half its letters, and >16 flat swatch colours were k-means averaged.
"""
from xml.etree import ElementTree as ET

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont, ImageOps

from plate import metrics, pipeline
from plate.cli import main
from plate.config import Config
from plate.imageio import ImageLoadError, open_rgba
from plate.raster import have_renderer

SS = 4


def _flat_art(w=320, h=240, bg=(255, 255, 255, 255)):
    im = Image.new("RGBA", (w * SS, h * SS), bg)
    d = ImageDraw.Draw(im)
    d.rectangle([20 * SS, 20 * SS, 150 * SS, 110 * SS], fill=(40, 110, 200, 255))
    d.ellipse([90 * SS, 50 * SS, 200 * SS, 160 * SS], fill=(214, 40, 40, 255))
    d.polygon([(230 * SS, 200 * SS), (300 * SS, 200 * SS), (265 * SS, 140 * SS)], fill=(240, 180, 30, 255))
    return im.resize((w, h), Image.LANCZOS)


def _size(svg):
    root = ET.fromstring(svg)
    return int(float(root.get("width"))), int(float(root.get("height")))


def _ssim(svg, rgba):
    if not have_renderer():
        pytest.skip("requires renderer")
    return metrics.fidelity(svg, np.asarray(rgba))["ssim"]


def test_sixteen_bit_png_is_not_traced_blank(tmp_path):
    gray = np.asarray(_flat_art().convert("L"))
    path = tmp_path / "gray16.png"
    cv2.imwrite(str(path), gray.astype(np.uint16) * 257)
    assert Image.open(path).mode.startswith("I;16")
    loaded = np.asarray(open_rgba(path))[..., 0]
    assert np.abs(loaded.astype(int) - gray).max() <= 1      # scaled, not clipped to white
    r = pipeline.run(path, Config())
    assert r.stats["shapes"] == pipeline.run(_save(tmp_path, _flat_art().convert("L")), Config()).stats["shapes"]
    assert _ssim(r.svg, Image.fromarray(gray).convert("RGBA")) >= 0.96


def _save(tmp_path, im, name="ref.png"):
    p = tmp_path / name
    im.save(p)
    return p


def test_exif_orientation_is_applied(tmp_path):
    shown = _flat_art().convert("RGB")
    path = tmp_path / "rot.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6                                           # viewer rotates 90 deg clockwise
    shown.rotate(90, expand=True).save(path, quality=95, exif=exif.tobytes())
    r = pipeline.run(path, Config())
    assert _size(r.svg) == shown.size                          # displayed size, not stored
    reference = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    assert _ssim(r.svg, reference) >= 0.95


def test_fully_transparent_image_gives_an_empty_svg(tmp_path):
    path = _save(tmp_path, Image.new("RGBA", (300, 200), (0, 0, 0, 0)))
    r = pipeline.run(path, Config())
    assert r.stats["shapes"] == 0
    assert _size(r.svg) == (300, 200)


@pytest.mark.parametrize("n", [1, 2, 8])
def test_tiny_solid_image_is_one_canvas_rect(tmp_path, n):
    path = _save(tmp_path, Image.new("RGBA", (n, n), (200, 60, 60, 255)))
    r = pipeline.run(path, Config())
    rects = [e for e in ET.fromstring(r.svg).iter() if e.tag.endswith("}rect")]
    assert len(rects) == 1 and r.stats["shapes"] == 1
    rect = rects[0]
    assert rect.get("fill") == "#c83c3c"
    assert (float(rect.get("width")), float(rect.get("height"))) == (n, n)


def test_one_pixel_rows_are_not_fit_as_straight_strokes():
    from plate.masks import Mask
    from plate.stages.strokes import fit_straight
    row = Mask(np.ones((1, 29), bool), 40, 10)                 # used to raise inside scipy
    assert fit_straight(row, Config()) is None


@pytest.mark.parametrize("make,needle", [
    (lambda d: (d / "notimage.png").write_text("hello"), "not a recognised image"),
    (lambda d: (d / "empty.png").write_bytes(b""), "not a recognised image"),
    (lambda d: (d / "truncated.png").write_bytes(_png_bytes()[:600]), "cannot read"),
    (lambda d: (d / "adir.png").mkdir(), "is a directory"),
])
def test_unreadable_inputs_fail_cleanly(tmp_path, capsys, make, needle):
    make(tmp_path)
    target = next(tmp_path.iterdir())
    with pytest.raises(ImageLoadError):
        open_rgba(target)
    assert main(["trace", str(target), "-o", str(tmp_path / "out.svg")]) == 2
    err = capsys.readouterr().err
    assert err.startswith("plate: ") and needle in err and "Traceback" not in err


def _png_bytes():
    import io
    buf = io.BytesIO()
    _flat_art().save(buf, "PNG")
    return buf.getvalue()


def test_small_antialiased_text_keeps_its_letters(tmp_path):
    big = Image.new("RGB", (400 * SS, 120 * SS), (255, 255, 255))
    ImageDraw.Draw(big).text((20 * SS, 20 * SS), "PLATE 2026",
                             font=ImageFont.load_default(size=70 * SS), fill=(20, 30, 60))
    small = big.resize((400, 120), Image.LANCZOS)
    path = _save(tmp_path, small, "text.png")
    r = pipeline.run(path, Config())
    ink = np.asarray(small).sum(axis=2) < 300
    owner = np.full(ink.shape, -1)
    for s in r.shapes:
        owner[s.vis.to_full(ink.shape)] = s.id
    dark = [s.id for s in r.shapes if sum(s.color) < 300]
    # Each glyph keeps essentially all of its ink (was ~12% for P/2 and ~30% for A/6).
    assert np.isin(owner[ink], dark).mean() >= 0.97
    assert _ssim(r.svg, small.convert("RGBA")) >= 0.95


def test_more_flat_colours_than_max_colors_are_kept_exactly(tmp_path):
    rng = np.random.default_rng(3)
    im = Image.new("RGB", (400, 320), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for i, c in enumerate(rng.integers(0, 255, (80, 3))):
        r_, c_ = divmod(i, 10)
        d.rectangle([c_ * 40 + 2, r_ * 40 + 2, c_ * 40 + 37, r_ * 40 + 37], fill=tuple(int(v) for v in c))
    path = _save(tmp_path, im, "mosaic.png")
    r = pipeline.run(path, Config())
    assert len(r.seg.palette) > Config().max_colors
    assert r.stats["shapes"] >= 80
    assert _ssim(r.svg, im.convert("RGBA")) >= 0.98


def test_noisy_photo_palette_is_still_capped(tmp_path):
    rng = np.random.default_rng(1)
    yy, xx = np.mgrid[0:240, 0:320]
    photo = np.stack([128 + 100 * np.sin(xx / 30.0), 128 + 90 * np.cos(yy / 25.0),
                      128 + 80 * np.sin((xx + yy) / 40.0)], -1) + rng.normal(0, 6, (240, 320, 3))
    path = _save(tmp_path, Image.fromarray(np.clip(photo, 0, 255).astype(np.uint8)), "photo.png")
    assert len(pipeline.run(path, Config()).seg.palette) <= Config().max_colors


def test_svg_dimensions_follow_source_for_every_mode(tmp_path):
    base = _flat_art()
    for mode in ("RGB", "L", "P", "1", "CMYK"):
        im = base.convert(mode) if mode != "P" else base.convert("RGB").quantize(8)
        ext = "jpg" if mode == "CMYK" else "png"
        r = pipeline.run(_save(tmp_path, im, f"m_{mode}.{ext}"), Config())
        assert _size(r.svg) == base.size, mode
        # A 1-bit image has two colours: the blue rect and red disc both become black
        # and merge, the yellow triangle becomes white background.
        assert r.stats["shapes"] >= (2 if mode == "1" else 3), mode
