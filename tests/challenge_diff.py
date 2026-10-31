"""Structured per-object diff for authored-target vs PLATE-actual SVGs.

Diagnostics only. This module never mutates pipeline state and never raises on a
structural difference between the two SVGs: it classifies every expected and
actual object (matched / missing / extra / split / merged), records the same
per-object checks `challenges.assert_target` gates on (silhouette IoU +
boundary error, topology, primitive/fill kind, stroke-vs-fill, stroke width),
and reports relative paint-order correctness. Thresholds and helpers are reused
verbatim from `challenges` so the diff agrees with `assert_target`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

import numpy as np
from scipy import ndimage as ndi
from scipy.optimize import linear_sum_assignment

from challenges import (
    _gradient_kind,
    _mask,
    _topology,
    drawables,
    local,
)

# Presence floor: an expected and an actual object "overlap" when their
# silhouette IoU is at least this. Reused as the split/merge detection floor so
# the diagnostic introduces no new geometry threshold.
PRESENCE_FLOOR = 0.1

# Gates mirrored verbatim from challenges.assert_target.
SILHOUETTE_IOU = 0.96
BOUNDARY_ERROR = 0.75
STROKE_WIDTH_TOLERANCE = 1.0


def _label(element, index):
    return element.get("id") or f"<{local(element)}#{index}>"


def _allowed_primitives(want_element):
    allowed = {local(want_element)}
    if local(want_element) == "path" and not want_element.get("stroke"):
        allowed.add("polygon")  # outlined block lettering may simplify
    return allowed


@dataclass
class MatchedObject:
    expected: str
    actual: str
    iou: float
    boundary_error: float
    silhouette_ok: bool
    topology_ok: bool
    expected_topology: tuple
    actual_topology: tuple
    primitive_ok: bool
    expected_primitive: str
    actual_primitive: str
    fill_ok: bool
    expected_fill: object
    actual_fill: object
    stroke_ok: bool
    stroke_detail: str

    def to_dict(self):
        return {
            "expected": self.expected,
            "actual": self.actual,
            "iou": round(float(self.iou), 4),
            "boundary_error": round(float(self.boundary_error), 4),
            "silhouette_ok": bool(self.silhouette_ok),
            "topology_ok": bool(self.topology_ok),
            "expected_topology": {
                "components": int(self.expected_topology[0]),
                "holes": int(self.expected_topology[1]),
            },
            "actual_topology": {
                "components": int(self.actual_topology[0]),
                "holes": int(self.actual_topology[1]),
            },
            "primitive_ok": bool(self.primitive_ok),
            "expected_primitive": self.expected_primitive,
            "actual_primitive": self.actual_primitive,
            "fill_ok": bool(self.fill_ok),
            "expected_fill": self.expected_fill,
            "actual_fill": self.actual_fill,
            "stroke_ok": bool(self.stroke_ok),
            "stroke_detail": self.stroke_detail,
        }


@dataclass
class PaintOrderFinding:
    lower: str
    upper: str
    ok: bool
    note: str

    def to_dict(self):
        return {"lower": self.lower, "upper": self.upper,
                "ok": bool(self.ok), "note": self.note}


@dataclass
class TargetDiff:
    expected_count: int
    actual_count: int
    matched: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    extra: list = field(default_factory=list)
    split: list = field(default_factory=list)
    merged: list = field(default_factory=list)
    paint_order: list = field(default_factory=list)

    def to_dict(self):
        return {
            "expected_count": self.expected_count,
            "actual_count": self.actual_count,
            "matched": [m.to_dict() for m in self.matched],
            "missing": list(self.missing),
            "extra": list(self.extra),
            "split": [dict(s) for s in self.split],
            "merged": [dict(m) for m in self.merged],
            "paint_order": [p.to_dict() for p in self.paint_order],
        }

    def summary(self) -> str:
        lines = [
            (f"object count: {self.actual_count} actual vs "
             f"{self.expected_count} expected"),
            (f"  matched={len(self.matched)} missing={len(self.missing)} "
             f"extra={len(self.extra)} split={len(self.split)} "
             f"merged={len(self.merged)}"),
        ]
        if self.missing:
            lines.append(f"  missing: {', '.join(self.missing)}")
        if self.extra:
            lines.append(f"  extra: {', '.join(self.extra)}")
        for s in self.split:
            lines.append(
                f"  split: {s['expected']} -> {len(s['actual'])} actual "
                f"({', '.join(s['actual'])})")
        for m in self.merged:
            lines.append(
                f"  merged: {len(m['expected'])} expected "
                f"({', '.join(m['expected'])}) -> {m['actual']}")
        bad_sil = [m for m in self.matched if not m.silhouette_ok]
        if bad_sil:
            lines.append(
                "  silhouette IoU < gate: "
                + ", ".join(f"{m.expected}(IoU {m.iou:.4f}, "
                            f"boundary {m.boundary_error:.2f}px)"
                            for m in bad_sil))
        bad_topo = [m for m in self.matched if not m.topology_ok]
        if bad_topo:
            lines.append(
                "  topology differs: "
                + ", ".join(f"{m.expected}(got {m.actual_topology}, "
                            f"want {m.expected_topology})" for m in bad_topo))
        bad_prim = [m for m in self.matched if not m.primitive_ok]
        if bad_prim:
            lines.append(
                "  primitive differs: "
                + ", ".join(f"{m.expected}(got {m.actual_primitive}, "
                            f"want {m.expected_primitive})" for m in bad_prim))
        bad_fill = [m for m in self.matched if not m.fill_ok]
        if bad_fill:
            lines.append(
                "  fill kind differs: "
                + ", ".join(f"{m.expected}(got {m.actual_fill}, "
                            f"want {m.expected_fill})" for m in bad_fill))
        bad_stroke = [m for m in self.matched if not m.stroke_ok]
        if bad_stroke:
            lines.append(
                "  stroke differs: "
                + ", ".join(f"{m.expected}({m.stroke_detail})"
                            for m in bad_stroke))
        bad_order = [p for p in self.paint_order if not p.ok]
        if bad_order:
            lines.append(
                "  paint order wrong: "
                + ", ".join(f"({p.lower}, {p.upper}) {p.note}"
                            for p in bad_order))
        return "\n".join(lines)


def diff_target(actual_svg, target_svg) -> TargetDiff:
    """Compute a full per-object diff of actual vs target. Never raises."""
    actual = ET.fromstring(actual_svg)
    target = ET.fromstring(target_svg)
    got, want = drawables(actual), drawables(target)
    gm = [_mask(actual, e) for e in got]
    wm = [_mask(target, e) for e in want]
    want_labels = [_label(e, i) for i, e in enumerate(want)]
    got_labels = [_label(e, i) for i, e in enumerate(got)]

    diff = TargetDiff(expected_count=len(want), actual_count=len(got))

    # IoU[want][got]. Guard against empty sides so Hungarian has a matrix.
    if want and got:
        ious = np.array([[np.count_nonzero(a & b) / max(1, np.count_nonzero(a | b))
                          for a in gm] for b in wm])
        rows, cols = linear_sum_assignment(-ious)
        primary = dict(zip(rows.tolist(), cols.tolist()))
    else:
        ious = np.zeros((len(want), len(got)))
        primary = {}

    # Classify each expected object by its primary assignment's overlap.
    matches = {}  # want index -> got index for present (matched) pairs
    for wi in range(len(want)):
        gi = primary.get(wi)
        if gi is not None and ious[wi, gi] >= PRESENCE_FLOOR:
            matches[wi] = gi
            diff.matched.append(
                _evaluate_pair(actual, target, got, want, gm, wm, ious,
                               wi, gi, got_labels, want_labels))
        else:
            diff.missing.append(want_labels[wi])

    # Extras: actual objects not used as a present primary match.
    used = set(matches.values())
    for gi in range(len(got)):
        if gi not in used:
            diff.extra.append(got_labels[gi])

    # Actual objects that are the primary 1:1 Hungarian match for some
    # expected object; such an actual is a distinct object in its own right, so
    # its mere spatial overlap with another expected must not be read as a
    # fragment of that expected (split).
    claimed_actual = {gi: wi for wi, gi in primary.items()
                      if ious[wi, gi] >= PRESENCE_FLOOR}

    # Split: one expected object's silhouette is fragmented across >= 2 actual
    # objects that EACH account for a meaningful portion of it while NONE is a
    # good whole-object match -- and excluding any actual that is the primary
    # 1:1 match for a DIFFERENT expected (a distinct object merely overlapping).
    for wi in range(len(want)):
        fragments = []
        for gi in range(len(got)):
            if ious[wi, gi] < PRESENCE_FLOOR:
                continue
            owner = claimed_actual.get(gi)
            if owner is not None and owner != wi:
                continue  # distinct object matched 1:1 elsewhere, not a fragment
            coverage = (np.count_nonzero(gm[gi] & wm[wi])
                        / max(1, np.count_nonzero(wm[wi])))
            # A fragment covers part of the expected silhouette but is not a
            # whole-object match on its own.
            if coverage >= PRESENCE_FLOOR and ious[wi, gi] < SILHOUETTE_IOU:
                fragments.append(gi)
        if len(fragments) >= 2:
            diff.split.append({
                "expected": want_labels[wi],
                "actual": [got_labels[gi] for gi in fragments],
            })

    # Merged: one actual object subsumes >= 2 expected objects that have no
    # better individual match. Group expected objects by their best actual, but
    # exclude an expected whose own 1:1 Hungarian match is a DIFFERENT, distinct
    # actual (it merely overlaps the shared one; it is not merged into it).
    best_for_expected = {}
    for wi in range(len(want)):
        if not got:
            continue
        gi = int(np.argmax(ious[wi]))
        if ious[wi, gi] < PRESENCE_FLOOR:
            continue
        own = matches.get(wi)
        if own is not None and own != gi:
            continue  # distinct object with its own 1:1 match, not merged
        best_for_expected.setdefault(gi, []).append(want_labels[wi])
    for gi, labels in best_for_expected.items():
        if len(labels) >= 2:
            diff.merged.append({"expected": labels, "actual": got_labels[gi]})

    # Relative paint order for overlapping expected pairs where both matched.
    for lower in range(len(want)):
        for upper in range(lower + 1, len(want)):
            if np.count_nonzero(wm[lower] & wm[upper]) <= 16:
                continue
            if lower in matches and upper in matches:
                ok = matches[lower] < matches[upper]
                diff.paint_order.append(PaintOrderFinding(
                    want_labels[lower], want_labels[upper], ok,
                    "" if ok else "reversed"))
            else:
                unmatched = [want_labels[i] for i in (lower, upper)
                             if i not in matches]
                diff.paint_order.append(PaintOrderFinding(
                    want_labels[lower], want_labels[upper], False,
                    f"unordered: unmatched {', '.join(unmatched)}"))

    return diff


def _evaluate_pair(actual, target, got, want, gm, wm, ious,
                   wi, gi, got_labels, want_labels) -> MatchedObject:
    boundary = wm[wi] & ~ndi.binary_erosion(wm[wi])
    boundary_error = np.count_nonzero(wm[wi] ^ gm[gi]) / max(1, boundary.sum())
    silhouette_ok = bool(ious[wi, gi] >= SILHOUETTE_IOU
                         or boundary_error <= BOUNDARY_ERROR)

    expected_topo = _topology(wm[wi])
    actual_topo = _topology(gm[gi])
    topology_ok = actual_topo == expected_topo

    expected_primitive = local(want[wi])
    actual_primitive = local(got[gi])
    primitive_ok = actual_primitive in _allowed_primitives(want[wi])

    expected_fill = _gradient_kind(target, want[wi])
    actual_fill = _gradient_kind(actual, got[gi])
    fill_ok = actual_fill == expected_fill

    if want[wi].get("stroke"):
        is_stroke = (got[gi].get("stroke") is not None
                     and got[gi].get("fill") == "none")
        if not is_stroke:
            stroke_ok = False
            stroke_detail = "must remain an editable stroke"
        else:
            got_w = float(got[gi].get("stroke-width", "1"))
            want_w = float(want[wi].get("stroke-width"))
            width_ok = abs(got_w - want_w) <= STROKE_WIDTH_TOLERANCE
            stroke_ok = width_ok
            stroke_detail = ("" if width_ok
                             else f"stroke width {got_w} vs {want_w}")
    else:
        stroke_ok = True
        stroke_detail = ""

    return MatchedObject(
        expected=want_labels[wi],
        actual=got_labels[gi],
        iou=float(ious[wi, gi]),
        boundary_error=float(boundary_error),
        silhouette_ok=silhouette_ok,
        topology_ok=topology_ok,
        expected_topology=(int(expected_topo[0]), int(expected_topo[1])),
        actual_topology=(int(actual_topo[0]), int(actual_topo[1])),
        primitive_ok=primitive_ok,
        expected_primitive=expected_primitive,
        actual_primitive=actual_primitive,
        fill_ok=fill_ok,
        expected_fill=expected_fill,
        actual_fill=actual_fill,
        stroke_ok=stroke_ok,
        stroke_detail=stroke_detail,
    )
