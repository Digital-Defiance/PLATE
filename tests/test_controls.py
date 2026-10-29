"""CONTROL regression suite: complex synthetic PNGs -> known SVG objects.

For each control image (scripts/make_controls.py) we run the full pipeline and
assert the structured Result against the ground-truth contract in controls.py:
object counts, primitive types, params within tolerance, layer names, paint
order and nesting. A soft golden-SVG diff is kept alongside as a review signal.

Hard gate   : the structured-Result assertions below (robust to SVG formatting).
Soft signal : golden .svg comparison (tests/golden/controls/<name>.svg).
              Set PLATE_UPDATE_GOLDEN=1 to (re)write goldens; a mismatch warns
              but does not fail, so harmless float/formatting drift is visible
              without breaking CI.
"""
from __future__ import annotations

import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from plate import pipeline
from plate.config import Config

from controls import ANGLE_TOL, CONTROLS, TOL, Control, Obj

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden" / "controls"


@pytest.fixture(scope="session")
def controls_dir():
    d = ROOT / "samples" / "controls"
    # (re)generate if any expected image is missing
    missing = [n for n in CONTROLS if not (d / f"{n}.png").exists()]
    if missing:
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "make_controls.py"), str(d)], cwd=ROOT
        )
    return d


# --- tree helpers ----------------------------------------------------------

def _flatten(nodes, depth=0, out=None):
    """Depth-first flatten into (node, depth) in paint order, skipping groups."""
    if out is None:
        out = []
    for n in nodes:
        if n.kind == "group":
            _flatten(n.children, depth + 1, out)
        else:
            out.append((n, depth))
    return out


def _check_params(name, node, expected, tol):
    for k, want in expected.items():
        assert k in node.params, f"{name}: {node.kind} {node.name!r} missing param {k!r}"
        got = node.params[k]
        assert abs(got - want) <= tol, (
            f"{name}: {node.name!r} param {k}={got:.2f} not within {tol} of {want}"
        )


# --- the parametrised control test ----------------------------------------

@pytest.mark.parametrize("cname", list(CONTROLS))
def test_control(cname, controls_dir):
    ctrl: Control = CONTROLS[cname]
    png = controls_dir / f"{cname}.png"
    assert png.exists(), f"missing control image {png}"

    r = pipeline.run(png, Config())

    # 1) top-level stats
    if ctrl.shapes is not None:
        assert r.stats["shapes"] == ctrl.shapes, (
            f"{cname}: shapes {r.stats['shapes']} != {ctrl.shapes}")
    if ctrl.completed is not None:
        assert r.stats["completed"] == ctrl.completed, (
            f"{cname}: completed {r.stats['completed']} != {ctrl.completed}")
    if ctrl.primitives is not None:
        assert r.stats["primitives"] == ctrl.primitives, (
            f"{cname}: primitives {r.stats['primitives']} != {ctrl.primitives}")
    if ctrl.max_total_anchors is not None:
        assert r.stats["anchors"] <= ctrl.max_total_anchors, (
            f"{cname}: anchors {r.stats['anchors']} > {ctrl.max_total_anchors}")

    # 2) object-by-object in paint order
    flat = _flatten(r.nodes)
    assert len(flat) == len(ctrl.objects), (
        f"{cname}: got {len(flat)} objects {[n.kind for n, _ in flat]}, "
        f"expected {len(ctrl.objects)} {[o.kind for o in ctrl.objects]}"
    )

    for i, (obj, (node, depth)) in enumerate(zip(ctrl.objects, flat)):
        where = f"{cname}[{i}]"
        # kind (single or set of acceptable)
        kinds = obj.kind if isinstance(obj.kind, set) else {obj.kind}
        assert node.kind in kinds, f"{where}: kind {node.kind!r} not in {kinds}"
        # name
        if obj.name is not None:
            assert node.name == obj.name, f"{where}: name {node.name!r} != {obj.name!r}"
        # nesting depth
        assert depth == obj.group_depth, (
            f"{where}: group depth {depth} != {obj.group_depth}")
        # anchors
        if obj.min_anchors is not None:
            assert node.anchors >= obj.min_anchors, (
                f"{where}: anchors {node.anchors} < {obj.min_anchors}")
        if obj.max_anchors is not None:
            assert node.anchors <= obj.max_anchors, (
                f"{where}: anchors {node.anchors} > {obj.max_anchors}")
        # params
        _check_params(where, node, obj.params, TOL)

    # 3) tier-specific structural checks
    if cname == "t3_ring":
        assert 'fill-rule="evenodd"' in r.svg, "ring must emit an even-odd fill"
    if cname == "t3_rotated_ellipse":
        ell = flat[1][0]
        rx, ry = ell.params["rx"], ell.params["ry"]
        major, minor = max(rx, ry), min(rx, ry)
        assert abs(major - 100) <= TOL, f"ellipse major axis {major:.1f} != ~100"
        assert abs(minor - 55) <= TOL, f"ellipse minor axis {minor:.1f} != ~55"
        assert major > minor + 10, "rotated ellipse should be clearly non-circular"

    # 4) fidelity floor (only when a renderer is available)
    from plate.raster import have_renderer
    if have_renderer():
        import numpy as np
        from PIL import Image
        from plate import metrics
        src = np.asarray(Image.open(png).convert("RGBA"))
        fid = metrics.fidelity(r.svg, src)
        ssim = fid.get("ssim")
        if ssim is not None:
            assert ssim >= ctrl.ssim_floor, (
                f"{cname}: SSIM {ssim} below floor {ctrl.ssim_floor}")

    # 5) soft golden-SVG diff
    _golden_check(cname, r.svg)


def _golden_check(cname, svg):
    GOLDEN.mkdir(parents=True, exist_ok=True)
    path = GOLDEN / f"{cname}.svg"
    if os.environ.get("PLATE_UPDATE_GOLDEN") == "1" or not path.exists():
        path.write_text(svg)
        return
    old = path.read_text()
    if old != svg:
        warnings.warn(
            f"golden SVG drift for {cname}: output differs from {path.name}. "
            f"If intended, run PLATE_UPDATE_GOLDEN=1 pytest -q to refresh.",
            stacklevel=2,
        )
