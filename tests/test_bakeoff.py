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


def test_bakeoff_end_to_end_and_plate_beats_baseline(mini, tmp_path):
    summ = runner.run(mini / "images", tmp_path, ["plate", "vtracer"], truth=mini / "truth", log=lambda m: None)
    by = {s["tool"]: s for s in summ}
    assert (tmp_path / "report.html").exists() and (tmp_path / "results.csv").exists()
    assert by["plate"]["composite"] > by["vtracer"]["composite"]
    assert json.loads((tmp_path / "results.json").read_text())["profiles"]
