import json

import numpy as np
import pytest
from PIL import Image

from plate.bakeoff import adapters, corpus, runner, score


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    d = tmp_path_factory.mktemp("corpus")
    corpus.make_corpus(d, n=6, seed=1, noisy_every=0)
    return d


def test_corpus_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    corpus.make_corpus(a, n=2, seed=7, noisy_every=0)
    corpus.make_corpus(b, n=2, seed=7, noisy_every=0)
    assert (a / "truth" / "scene00.json").read_text() == (b / "truth" / "scene00.json").read_text()
    assert (a / "images" / "scene01.png").read_bytes() == (b / "images" / "scene01.png").read_bytes()


def test_truth_svg_scores_perfect_structure(mini):
    svg = (mini / "truth" / "scene00.svg").read_text()
    ref = np.asarray(Image.open(mini / "images" / "scene00.png").convert("RGB"))
    r = score.score_svg(svg, ref, corpus.load_truth(mini / "truth" / "scene00.json"))["raw"]
    assert r["obj_complete_f1"] == 1.0 and r["obj_visible_f1"] == 1.0
    assert r["hidden_completion"] in (1.0, None) and r["ssim"] > 0.999


def test_hidden_part_matters(mini):
    """A tool that only cuts out the visible part must lose 'complete' credit but keep 'visible'."""
    tr = corpus.load_truth(mini / "truth" / "scene00.json")
    objs = tr["objects"]
    from plate.bakeoff.corpus import SIZE
    parts = []
    for i, o in enumerate(objs):
        ys, xs = np.nonzero(tr["visible"][i])
        if len(xs) == 0:
            continue
        # visible region as pixel-rect blocks is overkill; use run-length rows as <rect>s
        for y in range(ys.min(), ys.max() + 1):
            row = np.nonzero(tr["visible"][i][y])[0]
            if len(row):
                parts.append(f'<rect x="{row.min()}" y="{y}" width="{row.max() - row.min() + 1}" height="1" '
                             f'fill="#{o["color"][0]:02x}{o["color"][1]:02x}{o["color"][2]:02x}"/>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">{"".join(parts)}</svg>'
    s = score.structure(svg, tr)
    assert s["obj_complete_f1"] < 0.5          # not recovered as whole objects


def test_composite_renormalises_without_truth():
    c, n = score.composite(dict(ssim=0.99, edge_f1=1.0, anchors_per_shape=4, primitive_ratio=1, named=1))
    assert 0.9 < c <= 1.0 and "hidden_completion" not in n


def test_external_discovery(tmp_path):
    (tmp_path / "scene00.illustrator.svg").write_text("<svg/>")
    (tmp_path / "scene00.vectorizer-ai.svg").write_text("<svg/>")
    found = adapters.discover_external(tmp_path, ["scene00", "scene01"])
    assert set(found) == {"illustrator", "vectorizer-ai"} and "scene00" in found["illustrator"]


@pytest.fixture(scope="module")
def jpeg_corpus(tmp_path_factory):
    """The seed-1, 24-scene corpus pinned by docs/BAKEOFF.md; 6 scenes are JPEG-q55 variants."""
    d = tmp_path_factory.mktemp("jpeg_corpus")
    corpus.make_corpus(d, n=24, seed=1, noisy_every=4)
    return d


def _plate_hidden_completion(images_dir, truth_dir):
    """Aggregate (mean per-scene) `hidden_completion` for plate over the JPEG-variant scenes."""
    from plate import pipeline
    jpgs = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    assert jpgs, "corpus must contain JPEG-damaged variants"
    vals = []
    for src in jpgs:
        tr = corpus.load_truth(truth_dir / f"{src.stem}.json")
        hc = score.structure(pipeline.run(src).svg, tr)["hidden_completion"]
        if hc is not None:
            vals.append(hc)
    return float(np.mean(vals)), len(vals)


def test_jpeg_variant_hidden_completion_meets_floor(jpeg_corpus):
    """R1 state (a): the format-keyed JPEG denoise trigger (imageio.load_image) raises the
    JPEG-variant aggregate `hidden_completion` above the 0.4 floor. Pins docs/BAKEOFF.md's
    measured 3/10 -> 4/10 (aggregate 0.33 -> 0.42). The trigger fires on no PNG, so the 24
    shipped SVGs stay byte-identical by construction (GC-4).

    Validates: Requirements 1 (R1).
    """
    hc, n = _plate_hidden_completion(jpeg_corpus / "images", jpeg_corpus / "truth")
    assert n == 6
    assert hc >= 0.4, f"JPEG-variant hidden_completion {hc:.3f} fell below the 0.4 floor"


@pytest.fixture(scope="module")
def clean_completion_limits(jpeg_corpus, tmp_path_factory):
    """Render clean PNGs from independent truth, never by decoding/re-saving the JPEG."""
    import cairosvg

    clean = tmp_path_factory.mktemp("clean_completion_limits")
    scenes = {}
    for stem in ("scene15_jpg", "scene23_jpg"):
        path = clean / f"{stem}.png"
        truth = corpus.load_truth(jpeg_corpus / "truth" / f"{stem}.json")
        svg = (jpeg_corpus / "truth" / f"{stem}.svg").read_bytes()
        cairosvg.svg2png(bytestring=svg, write_to=str(path))
        scenes[stem] = path, truth
    return scenes


@pytest.mark.parametrize("stem,occluded_count", [("scene15_jpg", 2), ("scene23_jpg", 1)])
@pytest.mark.parametrize("denoise", [-1, 0, 1, 2, 3, 4, 6])
def test_clean_completion_floor_is_not_a_jpeg_failure(clean_completion_limits, stem, occluded_count, denoise):
    """R1(b) / Task 2: three misses persist on clean truth, owned by R2 / Task 4.

    This pins the measured completion limit, not an information-theoretic impossibility.
    Update the pin when Task 4 legitimately improves these independent truth matches;
    broadening JPEG denoise is not the fix. Includes every level tried in the investigation.
    """
    from plate import pipeline
    from plate.config import Config

    path, truth = clean_completion_limits[stem]
    with Image.open(path) as image:
        assert image.format == "PNG"
    occluded = [i for i, obj in enumerate(truth["objects"]) if not obj.get("background")
                and truth["visible"][i].sum() < .97 * truth["full"][i].sum()]
    assert len(occluded) == occluded_count
    result = pipeline.run(path, Config(denoise=denoise))
    measured = score.structure(result.svg, truth)
    assert measured["hidden_completion"] == 0., (stem, denoise, measured)


def test_bakeoff_end_to_end_and_plate_beats_baseline(mini, tmp_path):
    summ = runner.run(mini / "images", tmp_path, ["plate", "vtracer"], truth=mini / "truth", log=lambda m: None)
    by = {s["tool"]: s for s in summ}
    assert (tmp_path / "report.html").exists() and (tmp_path / "results.csv").exists()
    assert by["plate"]["composite"] > by["vtracer"]["composite"]
    assert json.loads((tmp_path / "results.json").read_text())["profiles"]
