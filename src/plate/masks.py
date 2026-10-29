"""Bounding-box-cropped boolean masks: cheap to keep hundreds of in memory."""
from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


class Mask:
    __slots__ = ("a", "y0", "x0", "_area")

    def __init__(self, a: np.ndarray, y0: int, x0: int):
        self.a = np.asarray(a, dtype=bool)
        self.y0 = int(y0)
        self.x0 = int(x0)
        self._area: int | None = None

    # -- construction ---------------------------------------------------
    @staticmethod
    def from_full(full: np.ndarray) -> "Mask":
        rows = np.flatnonzero(full.any(axis=1))
        if rows.size == 0:
            return Mask(np.zeros((0, 0), bool), 0, 0)
        cols = np.flatnonzero(full.any(axis=0))
        y0, y1, x0, x1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
        return Mask(full[y0:y1, x0:x1].copy(), y0, x0)

    # -- properties -----------------------------------------------------
    @property
    def bbox(self) -> tuple[int, int, int, int]:
        h, w = self.a.shape
        return self.y0, self.x0, self.y0 + h, self.x0 + w

    @property
    def area(self) -> int:
        if self._area is None:
            self._area = int(self.a.sum())
        return self._area

    def empty(self) -> bool:
        return self.area == 0

    # -- conversion -----------------------------------------------------
    def to_full(self, shape: tuple[int, int]) -> np.ndarray:
        out = np.zeros(shape, bool)
        h, w = self.a.shape
        y0, x0 = max(self.y0, 0), max(self.x0, 0)
        y1, x1 = min(self.y0 + h, shape[0]), min(self.x0 + w, shape[1])
        if y1 > y0 and x1 > x0:
            out[y0:y1, x0:x1] = self.a[y0 - self.y0:y1 - self.y0, x0 - self.x0:x1 - self.x0]
        return out

    # -- operations -----------------------------------------------------
    def filled(self) -> "Mask":
        pad = np.pad(self.a, 1)
        return Mask(ndi.binary_fill_holes(pad)[1:-1, 1:-1], self.y0, self.x0)

    def dilated(self, r: int, shape: tuple[int, int]) -> "Mask":
        if r <= 0 or self.empty():
            return Mask(self.a.copy(), self.y0, self.x0)
        y0, x0 = max(self.y0 - r, 0), max(self.x0 - r, 0)
        h, w = self.a.shape
        y1, x1 = min(self.y0 + h + r, shape[0]), min(self.x0 + w + r, shape[1])
        canvas = np.zeros((y1 - y0, x1 - x0), bool)
        canvas[self.y0 - y0:self.y0 - y0 + h, self.x0 - x0:self.x0 - x0 + w] = self.a
        yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
        disk = (yy * yy + xx * xx) <= r * r + 1e-9
        return Mask(ndi.binary_dilation(canvas, structure=disk), y0, x0)


def _overlap(m: Mask, n: Mask):
    y0, x0 = max(m.y0, n.y0), max(m.x0, n.x0)
    y1, x1 = min(m.bbox[2], n.bbox[2]), min(m.bbox[3], n.bbox[3])
    if y1 <= y0 or x1 <= x0:
        return None
    return (m.a[y0 - m.y0:y1 - m.y0, x0 - m.x0:x1 - m.x0],
            n.a[y0 - n.y0:y1 - n.y0, x0 - n.x0:x1 - n.x0])


def inter_area(m: Mask, n: Mask) -> int:
    ov = _overlap(m, n)
    return 0 if ov is None else int((ov[0] & ov[1]).sum())


def contains(outer: Mask, inner: Mask, frac: float = 0.995) -> bool:
    """True when at least `frac` of inner's pixels lie inside outer."""
    if inner.area == 0:
        return False
    return inter_area(outer, inner) >= frac * inner.area


def touches(m: Mask, n: Mask, shape: tuple[int, int], gap: int = 2) -> bool:
    """True when the two masks come within `gap` pixels of each other."""
    if (m.bbox[0] - gap >= n.bbox[2] or n.bbox[0] - gap >= m.bbox[2]
            or m.bbox[1] - gap >= n.bbox[3] or n.bbox[1] - gap >= m.bbox[3]):
        return False
    return inter_area(m.dilated(gap, shape), n) > 0


def crop_like(m: Mask, ref: Mask) -> np.ndarray:
    """m's pixels as a bool array aligned to ref's bounding box."""
    out = np.zeros(ref.a.shape, bool)
    ov = _overlap_coords(m, ref)
    if ov is None:
        return out
    (my0, my1, mx0, mx1), (ry0, ry1, rx0, rx1) = ov
    out[ry0:ry1, rx0:rx1] = m.a[my0:my1, mx0:mx1]
    return out


def _overlap_coords(m: Mask, n: Mask):
    y0, x0 = max(m.y0, n.y0), max(m.x0, n.x0)
    y1, x1 = min(m.bbox[2], n.bbox[2]), min(m.bbox[3], n.bbox[3])
    if y1 <= y0 or x1 <= x0:
        return None
    return ((y0 - m.y0, y1 - m.y0, x0 - m.x0, x1 - m.x0), (y0 - n.y0, y1 - n.y0, x0 - n.x0, x1 - n.x0))
