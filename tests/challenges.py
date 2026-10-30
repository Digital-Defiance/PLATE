"""Desired-output contracts for authored SVG -> PNG -> PLATE challenges.

Unlike the control goldens these targets are independent input artwork. Geometry
matching ignores element IDs, formatting, and the order of disjoint objects.
"""
from __future__ import annotations

import copy
import io
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class Challenge:
    goal: str
    gap: str = ""  # A strict xfail for a demonstrated, documented feature gap only.
    ssim_floor: float = 0.95


CHALLENGES = {
    "nested_dial": Challenge("Eight objects; full concentric discs and repeated markers."),
    "perforated_plate": Challenge(
        "One compound path with three transparent holes, plus an island.",
        gap="The plate path contains two connected components instead of one."),
    "occlusion_chain": Challenge(
        "Recover three full circles behind successive occluders.",
        gap="Chained completion drifts from the authored full-circle silhouettes."),
    "twin_gradients": Challenge("Two independent opposite ramps, each behind a solid dot."),
    "gradient_badge": Challenge(
        "One full radial disc underneath an edge-crossing ribbon."),
    "edge_crossing_type": Challenge(
        "Recover the full disc behind three outlined block letters."),
    "discrete_palette": Challenge("Keep eight hard-edged flat swatches; emit zero gradients."),
    "stroked_route": Challenge(
        "Keep the route as one open stroked path with two endpoint discs."),
    "complex_mission_patch": Challenge(
        "45 objects: transparent perforated rim, two gradients, orbits, spacecraft and type.",
        gap="The patch duplicates radial planet fragments instead of recovering radial planet + linear hull.",
        ssim_floor=0.97),
    "complex_storefront": Challenge(
        "64 objects: repeated windows, fourteen awning panels, outlined sign and plants.",
        gap="The storefront merges and fragments author objects; target structure is unmet.",
        ssim_floor=0.96),
    "complex_instrument_panel": Challenge(
        "59 objects: three nested gauges, 27 strokes, title and connected status lights.",
        gap="Panel routes are continuous strokes; target still requires 27 strokes and 59 objects.",
        ssim_floor=0.97),
    "complex_event_poster": Challenge(
        "44 objects: gradient disc behind type, ring, ribbon, strokes and repeated dots.",
        gap="Crossing lettering, ribbon and lines fragment the poster's shapes.",
        ssim_floor=0.96),  # Thin-detail recovery improved SSIM to 0.9685.
    "logo_ember_crest": Challenge(
        "51 objects: fox facets, shield cutouts, laurel leaves, ribbon and outlined EMBER.",
        gap="Shield full silhouette is incomplete (IoU 0.8385); only 2 of 7 strokes recovered.",
        ssim_floor=0.96),
    "logo_orbit_wordmark": Challenge(
        "34 objects: gradient core, interlocking orbital strokes, compound monogram and wordmark.",
        gap="Orbital emblem and wordmark fragment into 60 objects instead of 34.",
        ssim_floor=0.97),
    "logo_root_seal": Challenge(
        "56 objects: organic leaves, 32 strokes, counter-cut trunk and outlined ROOT.",
        gap="Tree/leaf/stroke objects merge or disappear: 52 objects and no editable strokes.",
        ssim_floor=0.97),
}

DRAWABLE = {"rect", "circle", "ellipse", "path", "polygon", "polyline", "line"}


def local(element):
    return element.tag.rsplit("}", 1)[-1]


def drawables(root):
    return [element for element in root.iter() if local(element) in DRAWABLE]


class TargetMismatch(AssertionError):
    """An editable-structure mismatch, distinct from crashes or fidelity failures."""


def _require(condition, message):
    if not condition:
        raise TargetMismatch(message)


def _mask(root, element):
    """Render ONE complete editable object, including its hidden silhouette/holes.

    Authored targets and PLATE's emitter put paint/geometry on leaves; their groups
    carry labels only. Keep defs so gradient-backed shapes render in isolation.
    """
    import cairosvg

    isolated = ET.Element(root.tag, root.attrib)
    for child in root:
        if local(child) == "defs":
            isolated.append(copy.deepcopy(child))
    isolated.append(copy.deepcopy(element))
    png = cairosvg.svg2png(bytestring=ET.tostring(isolated))
    with Image.open(io.BytesIO(png)) as image:
        return np.asarray(image.convert("RGBA"))[..., 3] >= 128


def _topology(mask):
    # Use 8-connected foreground and 4-connected background, so diagonal pixels
    # are treated consistently. Anti-aliased fringes are excluded by _mask.
    components = ndi.label(mask, np.ones((3, 3)))[1]
    holes = ndi.binary_fill_holes(mask) & ~mask
    return components, ndi.label(holes)[1]


def _gradient_kind(root, element):
    fill = element.get("fill", "")
    if not fill.startswith("url(#"):
        return None
    gid = fill[5:-1]
    return next((local(e) for e in root.iter() if e.get("id") == gid), "unresolved")


def assert_target(actual_svg, target_svg):
    """Match objects by silhouette, then check primitive/fill/topology/paint order."""
    actual, target = ET.fromstring(actual_svg), ET.fromstring(target_svg)
    got, want = drawables(actual), drawables(target)
    _require(len(got) == len(want),
             f"object count {len(got)} != target {len(want)}; got {[local(e) for e in got]}")
    gm = [_mask(actual, e) for e in got]
    wm = [_mask(target, e) for e in want]
    ious = np.array([[np.count_nonzero(a & b) / max(1, np.count_nonzero(a | b))
                      for a in gm] for b in wm])
    rows, cols = linear_sum_assignment(-ious)
    matches = dict(zip(rows, cols))
    for wi, gi in matches.items():
        label = want[wi].get("id")
        # Native-size masks quantize small circles heavily: allow subpixel area
        # error (xor / boundary length) even when their relative IoU is lower.
        boundary = wm[wi] & ~ndi.binary_erosion(wm[wi])
        boundary_error = np.count_nonzero(wm[wi] ^ gm[gi]) / max(1, boundary.sum())
        _require(ious[wi, gi] >= 0.96 or boundary_error <= 0.75,
                 f"{label}: full silhouette IoU {ious[wi, gi]:.4f} < 0.96; "
                 f"boundary error {boundary_error:.2f}px > 0.75px")
        allowed = {local(want[wi])}
        if local(want[wi]) == "path" and not want[wi].get("stroke"):
            allowed.add("polygon")  # outlined block lettering may simplify
        _require(local(got[gi]) in allowed,
                 f"{label}: {local(got[gi])} != target {local(want[wi])}")
        _require(_topology(gm[gi]) == _topology(wm[wi]),
                 f"{label}: connected components/holes differ from target")
        _require(_gradient_kind(actual, got[gi]) == _gradient_kind(target, want[wi]),
                 f"{label}: gradient fill kind differs from target")
        if want[wi].get("stroke"):
            _require(got[gi].get("stroke") is not None and got[gi].get("fill") == "none",
                     f"{label}: must remain an editable open stroke")
            _require(abs(float(got[gi].get("stroke-width", "1")) -
                         float(want[wi].get("stroke-width"))) <= 1,
                     f"{label}: stroke width differs from target")
    for lower in range(len(want)):
        for upper in range(lower + 1, len(want)):
            if np.count_nonzero(wm[lower] & wm[upper]) > 16:
                _require(matches[lower] < matches[upper],
                         f"paint order reversed: {want[lower].get('id')} / {want[upper].get('id')}")
