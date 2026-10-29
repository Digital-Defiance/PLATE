"""Stage 1: classical colour-region segmentation tuned for flat artwork.

Idea: anti-aliased edge pixels are the enemy (they create fake in-between colours and
rings). So we (1) find *flat* pixels away from edges, (2) build the palette only from
those, (3) give every edge pixel the label of its nearest flat pixel, (4) clean specks,
(5) split labels into connected regions.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

from ..config import Config
from ..masks import Mask
from ..scene import Loaded, Segmentation, Shape


def _lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _build_palette(px: np.ndarray, cfg: Config) -> np.ndarray:
    if cfg.palette:
        return np.array([_hex_to_rgb(c) for c in cfg.palette], np.uint8)
    packed = (px[:, 0].astype(np.uint32) << 16) | (px[:, 1].astype(np.uint32) << 8) | px[:, 2]
    uniq, counts = np.unique(packed, return_counts=True)
    order = np.argsort(-counts)
    uniq, counts = uniq[order], counts[order]
    keep = counts >= max(2, int(0.0004 * len(px)))
    if not keep.any():
        keep[0] = True
    uniq, counts = uniq[keep][:3000], counts[keep][:3000]
    cols = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], 1).astype(np.uint8)
    labs = _lab(cols.reshape(-1, 1, 3)).reshape(-1, 3)
    pal, pal_lab = [], []
    for c, l in zip(cols, labs):          # heaviest colour first = representative
        if pal and np.min(np.linalg.norm(np.array(pal_lab) - l, axis=1)) < cfg.color_merge:
            continue
        pal.append(c)
        pal_lab.append(l)
    if len(pal) <= cfg.max_colors:
        return np.array(pal, np.uint8)
    # photo-like: too many distinct colours -> k-means in Lab
    sample = px if len(px) <= 200_000 else px[np.random.default_rng(0).choice(len(px), 200_000, replace=False)]
    data = _lab(sample.reshape(-1, 1, 3)).reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, _, centers = cv2.kmeans(data, cfg.max_colors, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    rgb = cv2.cvtColor(centers.reshape(-1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB).reshape(-1, 3)
    return np.clip(np.round(rgb * 255), 0, 255).astype(np.uint8)


def _fill_unknown(labels: np.ndarray, unknown: np.ndarray) -> np.ndarray:
    if not unknown.any():
        return labels
    _, (iy, ix) = ndi.distance_transform_edt(unknown, return_indices=True)
    return labels[iy, ix]


def segment(img: Loaded, cfg: Config) -> Segmentation:
    rgb, alpha = img.rgb, img.alpha
    H, W = alpha.shape
    opaque = alpha >= 128
    lab = _lab(rgb)

    gx = cv2.Sobel(lab, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lab, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt((gx * gx + gy * gy).sum(axis=2))
    edge = cv2.dilate((grad > cfg.edge_threshold).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    flat = ~edge & opaque
    if flat.sum() < 0.02 * max(opaque.sum(), 1):   # noisy / photographic: use everything
        flat = opaque.copy()

    palette = _build_palette(rgb[flat], cfg)
    plab = _lab(palette.reshape(-1, 1, 3)).reshape(-1, 3)
    _, idx = cKDTree(plab).query(lab[flat])

    src = np.full((H, W), -2, np.int32)       # -2 unknown (edge), -1 transparent
    src[flat] = idx
    src[~opaque] = -1

    # Edge pixels are anti-aliased blends of (usually) two nearby palette colours. For each
    # one find the pair (A, B) whose connecting segment passes closest to the pixel, then
    # estimate coverage alpha and give the pixel to whichever colour covers more of it.
    ey, ex = np.nonzero(src == -2)
    if ey.size:
        K = len(palette)
        ok = np.zeros((ey.size, K), bool)
        for k in range(K):
            m = src == k
            if m.any():
                ok[:, k] = ndi.binary_dilation(m, structure=np.ones((5, 5), bool))[ey, ex]
        pix = rgb[ey, ex].astype(np.float32)
        pal = palette.astype(np.float32)
        best_res = np.full(ey.size, np.inf, np.float32)
        best_lbl = np.full(ey.size, -2, np.int32)
        for i in range(K):
            for j in range(i, K):
                valid = ok[:, i] & ok[:, j]
                if not valid.any():
                    continue
                A, B = pal[i], pal[j]
                if i == j:
                    res = np.linalg.norm(pix - A, axis=1)
                    lbl = np.full(ey.size, i, np.int32)
                else:
                    d = B - A
                    alpha = np.clip(((pix - A) @ d) / float(d @ d), 0.0, 1.0)
                    res = np.linalg.norm(pix - (A + alpha[:, None] * d), axis=1)
                    lbl = np.where(alpha < 0.5, i, j).astype(np.int32)
                    res = res + 1.5   # prefer the plain single-colour explanation when equal
                better = valid & (res < best_res)
                best_res[better] = res[better]
                best_lbl[better] = lbl[better]
        got = best_lbl >= 0
        src[ey[got], ex[got]] = best_lbl[got]
    labels = _fill_unknown(src, src == -2)

    # remove specks (tiny connected components), refill from neighbours
    min_area = max(int(cfg.filter_speckle), 1)
    cleaned = labels.copy()
    for lbl in np.unique(labels):
        n, cc, stats, _ = cv2.connectedComponentsWithStats((labels == lbl).astype(np.uint8), connectivity=4)
        small = np.flatnonzero(stats[1:, cv2.CC_STAT_AREA] < min_area) + 1
        if small.size:
            cleaned[np.isin(cc, small)] = -2
    # transparent specks are kept as-is (never refilled)
    cleaned[(labels == -1)] = -1
    labels = _fill_unknown(cleaned, cleaned == -2)

    # regions
    rid = np.full((H, W), -1, np.int32)
    shapes: list[Shape] = []
    for lbl in np.unique(labels):
        if lbl < 0:
            continue
        n, cc, stats, _ = cv2.connectedComponentsWithStats((labels == lbl).astype(np.uint8), connectivity=4)
        for k in range(1, n):
            x, y, w, h, area = stats[k]
            sub = cc[y:y + h, x:x + w] == k
            sid = len(shapes)
            m = Mask(sub, y, x)
            rid[y:y + h, x:x + w][sub] = sid
            shapes.append(Shape(id=sid, color=tuple(int(c) for c in palette[lbl]), vis=m, full=m))
    return Segmentation(rid=rid, shapes=shapes, palette=palette)
