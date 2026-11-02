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


# --------------------------------------------------------------- Task 4 (R2): free-edge completion
def _occluded_recovery(images_dir, truth_dir):
    """Per-kind and overall occluded-object recovery over the corpus: an occluded object counts
    as recovered when some emitted element matches its FULL silhouette at IoU >= 0.9, plus the
    mean per-scene `hidden_completion`. Mirrors score.structure's matching so the pin tracks the
    same number the bake-off reports."""
    from plate import pipeline
    from plate.bakeoff.score import _down, _iou_matrix, _match, element_masks
    per_kind, scene_hc = {}, []
    for img in sorted(images_dir.iterdir()):
        if img.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        tr = corpus.load_truth(truth_dir / f"{img.stem}.json")
        svg = pipeline.run(img).svg
        hc = score.structure(svg, tr)["hidden_completion"]
        if hc is not None:
            scene_hc.append(hc)
        objs = tr["objects"]
        bg = next((i for i, o in enumerate(objs) if o.get("background")), None)
        occluded = [i for i in range(len(objs)) if i != bg
                    and tr["visible"][i].sum() < 0.97 * tr["full"][i].sum()]
        gfull = np.stack([_down(m) for m in tr["full"]])
        cfull, *_ = element_masks(svg)
        mc = _match(_iou_matrix(gfull, cfull), 0.9)
        for i in occluded:
            rec, tot = per_kind.get(objs[i]["kind"], (0, 0))
            per_kind[objs[i]["kind"]] = (rec + (1 if i in mc else 0), tot + 1)
    overall = (sum(r for r, _ in per_kind.values()), sum(t for _, t in per_kind.values()))
    return per_kind, overall, float(np.mean(scene_hc))


@pytest.fixture(scope="module")
def recovery(jpeg_corpus):
    return _occluded_recovery(jpeg_corpus / "images", jpeg_corpus / "truth")


def test_free_edge_lifts_occluded_rectilinear_completion(recovery):
    """R2 state (a): extending partly-hidden rectilinear free edges by line intersection in
    complete.try_complete lifts occluded completion on the seed-1 (n=24) corpus WITHOUT loosening
    the primitive-fit tolerance or the 15-deg _occludes threshold.

    Measured baseline (free-edge path disabled) -> with the path:
      overall occluded recovery 32/57 -> 33/57; polygon 2/10 -> 3/10;
      mean per-scene hidden_completion 0.549 -> 0.562.
    The circle/ellipse/rect/rrect per-kind counts never drop. Pins the measured floor so the
    number cannot silently regress or be inflated by weakening a gate.

    Validates: Requirements 2 (R2).
    """
    per_kind, (rec, tot), hc = recovery
    assert tot == 57, per_kind
    # overall and the polygon per-kind count rose above the pre-free-edge baseline and hold
    assert rec >= 33, f"overall occluded recovery {rec}/{tot} fell below the pinned 33"
    assert per_kind["polygon"][0] >= 3, f"occluded polygon recovery regressed: {per_kind['polygon']}"
    assert hc >= 0.56, f"mean hidden_completion {hc:.3f} fell below the pinned 0.56 floor"
    # no rectilinear kind regressed below its measured baseline
    assert per_kind["rect"][0] >= 6 and per_kind["rrect"][0] >= 6
    assert per_kind["circle"][0] >= 14 and per_kind["ellipse"][0] >= 4


def test_free_edge_residual_rrect_is_a_measured_near_miss(jpeg_corpus):
    """R2 state (b): some occluded shapes are reconstructed cleanly by the free-edge path yet
    stay just under the IoU 0.9 match - notably rounded rectangles, whose sharp reconstructed
    corners lose the corner rounding the truth keeps. scene09's occluded rrect reconstructs to a
    best IoU in [0.85, 0.90): a measured near-miss, not an invented-geometry failure. Pinned so
    it is not re-chased by loosening the IoU threshold or the completion gates (GC-5). Update the
    pin if a corner-radius-aware reconstruction later lifts it over 0.9.

    Validates: Requirements 2 (R2).
    """
    from plate import pipeline
    from plate.bakeoff.score import _down, _iou_matrix, element_masks
    tr = corpus.load_truth(jpeg_corpus / "truth" / "scene09.json")
    svg = pipeline.run(jpeg_corpus / "images" / "scene09.png").svg
    gfull = np.stack([_down(m) for m in tr["full"]])
    cfull, *_ = element_masks(svg)
    iou = _iou_matrix(gfull, cfull)
    objs = tr["objects"]
    rrects = [i for i, o in enumerate(objs) if o["kind"] == "rrect" and not o.get("background")
              and tr["visible"][i].sum() < 0.97 * tr["full"][i].sum()]
    assert rrects, "scene09 must carry an occluded rounded rectangle"
    best = max(float(iou[i].max()) for i in rrects)
    assert 0.85 <= best < 0.90, f"scene09 occluded rrect best IoU {best:.3f} left the pinned band"


# --------------------------------------------------------------- Task 14 (R?): quality verification
# The bake-off already answers everything Task 14 asks: it verifies the SVG by rendering it back
# to PNG (fidelity: ssim/mae/edge_f1), checks for good objects / lack of artifacts (topology:
# topo_extra = specks/splits/pinched tips, topo_missing = dropped pieces/merges), and measures
# smooth lines and curves (smoothness/wobble). The per-metric functions are pinned in
# tests/test_topology_metric.py and tests/test_smoothness_metric.py. These end-to-end pins assert
# the three signals survive the WHOLE bake-off path (score_svg -> summarise -> HTML report), so a
# refactor cannot silently drop one. All three are report-only / unweighted except ssim+edge_f1;
# smoothness and topology must never enter DEFAULT_WEIGHTS (GC-5 / AGENTS.md).

def test_quality_signals_are_computed_by_score_svg(mini):
    """Task 14 state (b): one score_svg call yields all three quality families on a real render.

    - round-trip fidelity: ssim, mae, edge_f1 (score renders the SVG back to PNG via render_svg)
    - artifacts / good objects: topology, topo_extra, topo_missing
    - smooth lines and curves: smoothness, wobble
    """
    img = sorted((mini / "images").glob("*.png"))[0]
    ref = np.asarray(Image.open(img).convert("RGB"))
    svg = (mini / "truth" / f"{img.stem}.svg").read_text()
    raw = score.score_svg(svg, ref)["raw"]
    for k in ("ssim", "mae", "edge_f1", "topology", "topo_extra", "topo_missing", "smoothness", "wobble"):
        assert k in raw, f"score_svg dropped the {k} quality signal"
    # the truth SVG rendered against its own source is a near-perfect round-trip with no artifacts
    assert raw["ssim"] > 0.99 and raw["edge_f1"] > 0.95
    assert raw["topo_extra"] == 0 and raw["topo_missing"] == 0
    assert raw["smoothness"] >= 0.9 and raw["wobble"] <= 0.05


def test_quality_signals_survive_the_full_bakeoff(mini, tmp_path):
    """Task 14 state (a)+(b): the three quality families are carried through summarise AND
    surfaced in the HTML report, and the report-only ones never touch the composite.

    This pins the silent-drop fix: smoothness has a METRIC_LABEL but the norm-keyed column loop
    had dropped it from report.html because it is report-only (not normalised). It now appears as
    an explicit w=0 column sourced from the raw aggregate, next to topology.
    """
    summ = runner.run(mini / "images", tmp_path, ["plate", "vtracer"], truth=mini / "truth", log=lambda m: None)
    for s in summ:
        raw = s["raw"]
        # round-trip + artifacts + smoothness all aggregated per tool
        for k in ("ssim", "topology", "topo_extra", "topo_missing", "smoothness", "wobble"):
            assert k in raw, f"summarise dropped {k} for {s['tool']}"
    page = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert runner.METRIC_LABEL["ssim"] in page              # round-trip fidelity column
    assert runner.METRIC_LABEL["edge_f1"] in page
    assert runner.METRIC_LABEL["topology"] in page          # artifact / same-pieces column
    assert runner.METRIC_LABEL["smoothness"] in page        # smooth lines/curves column (was dropped)
    # report-only quality signals never move the composite
    assert "topology" not in score.DEFAULT_WEIGHTS
    assert "smoothness" not in score.DEFAULT_WEIGHTS and "wobble" not in score.DEFAULT_WEIGHTS


def test_artifacts_and_wobble_are_measured_end_to_end():
    """Task 14 state (a): the whole score_svg path (not just the metric helpers) catches a bad
    render - a stray same-colour speck raises topo_extra, and a wavy outline lowers smoothness -
    so 'lack of artifacts' and 'smooth curves' are real numbers in a scored SVG, not an eyeball.

    The reference is a two-colour scene (a dark block on a light field) so both colours are
    dominant palette entries; the artifact is painted in the block's own colour so it registers
    as a same-colour extra piece the way a real tracer's speck would.
    """
    from plate.bakeoff.corpus import SIZE
    BG, INK = "#14282c", "#f0f0e6"
    block = f'<rect x="40" y="40" width="120" height="120" fill="{INK}"/>'
    base = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
            f'viewBox="0 0 {SIZE} {SIZE}"><rect width="{SIZE}" height="{SIZE}" fill="{BG}"/>{{body}}</svg>')
    ref = np.asarray(_rasterize(base.format(body=block), SIZE).convert("RGB"))
    # a render that adds a stray INK-coloured speck the source does not have
    speck_svg = base.format(body=block + f'<rect x="20" y="20" width="7" height="7" fill="{INK}"/>')
    raw = score.score_svg(speck_svg, ref)["raw"]
    assert raw["topo_extra"] >= 1, raw        # the extra piece is caught end-to-end
    assert raw["topology"] < 1.0
    # smoothness is one-sided excess turning: a clean matching render is never penalised
    clean = score.score_svg(base.format(body=block), ref)["raw"]
    assert clean["smoothness"] == 1.0 and clean["wobble"] == 0.0


def _rasterize(svg: str, size: int):
    import io

    import cairosvg
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png))
