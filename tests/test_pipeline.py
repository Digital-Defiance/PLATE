import re
import xml.etree.ElementTree as ET

from plate import metrics, pipeline
from plate.config import Config


def _els(svg, tag):
    root = ET.fromstring(svg)
    return [e for e in root.iter() if e.tag.endswith("}" + tag)]


def test_overlap_recovers_hidden_circle(samples):
    """Ground truth: circle centre (200.1, 210.1) r=100.1 is partly hidden behind a rect."""
    r = pipeline.run(samples / "overlap.png", Config())
    c = _els(r.svg, "circle")
    assert len(c) == 1
    cx, cy, rad = (float(c[0].get(k)) for k in ("cx", "cy", "r"))
    assert abs(cx - 200.1) < 1.0 and abs(cy - 210.1) < 1.0 and abs(rad - 100.1) < 1.0
    assert r.stats["completed"] == 1


def test_stack3_all_primitives_and_order(samples):
    r = pipeline.run(samples / "stack3.png", Config())
    assert len(_els(r.svg, "circle")) == 3
    assert r.stats["completed"] == 2
    assert r.stats["anchors"] <= 16


def test_face_eyes_keep_orientation(samples):
    r = pipeline.run(samples / "face.png", Config())
    eyes = [e for e in _els(r.svg, "ellipse") if float(e.get("ry")) > 40]
    assert len(eyes) == 2 and all(float(e.get("rx")) < float(e.get("ry")) for e in eyes)


def test_ring_is_two_circles(samples):
    r = pipeline.run(samples / "donut_alpha.png", Config())
    assert "fill-rule=\"evenodd\"" in r.svg and r.stats["anchors"] <= 16


def test_layers_named_and_unique(samples):
    r = pipeline.run(samples / "badge.png", Config())
    m = metrics.analyze_svg(r.svg)
    assert m["unnamed_ratio"] == 0
    ids = re.findall(r' id="([^"]+)"', r.svg)
    assert len(ids) == len(set(ids))


def test_noisy_input_is_denoised(samples):
    r = pipeline.run(samples / "noisy_badge.png", Config())
    assert r.stats["shapes"] <= 12


def test_metrics_counts():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg"><g id="a"><circle id="c" cx="1" cy="1" r="1"/>'
           '<path id="p" d="M0 0C1 1 2 2 3 3L4 4Z"/></g></svg>')
    m = metrics.analyze_svg(svg)
    assert m["shapes"] == 2 and m["anchors"] == 4 + 2 and m["primitive_ratio"] == 0.5
