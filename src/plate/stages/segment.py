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


# Upper bound on an automatic palette of exactly-repeated flat colours (swatch charts,
# mosaics, pixel art). Bounds the O(K^2) per-pair edge assignment cost.
FLAT_PALETTE_CEILING = 96


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
    # Many genuinely FLAT colours (a swatch chart, mosaic, pixel art) are not a photo:
    # k-means would merge distinct swatches into averaged blobs. The kept colours
    # already explain >=99% of flat pixels exactly (photo noise/ramps never do), so
    # honour them up to a hard ceiling that bounds the per-pair edge assignment cost.
    # Only automatic palettes reach here; max_colors stays a cap on noisy input.
    if len(pal) <= FLAT_PALETTE_CEILING and counts.sum() >= 0.99 * len(px):
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


def _edge_labels(pix: np.ndarray, pal: np.ndarray, nearby: np.ndarray):
    """Best local solid-colour or two-colour coverage explanation per pixel."""
    count, colors = nearby.shape
    best_res = np.full(count, np.inf, np.float32)
    best_lbl = np.full(count, -2, np.int32)
    for i in range(colors):
        for j in range(i, colors):
            valid = nearby[:, i] & nearby[:, j]
            if not valid.any():
                continue
            A, B = pal[i], pal[j]
            if i == j:
                res = np.linalg.norm(pix - A, axis=1)
                lbl = np.full(count, i, np.int32)
            else:
                d = B - A
                coverage = np.clip(((pix - A) @ d) / float(d @ d), 0.0, 1.0)
                res = np.linalg.norm(pix - (A + coverage[:, None] * d), axis=1) + 1.5
                lbl = np.where(coverage < 0.5, i, j).astype(np.int32)
            better = valid & (res < best_res)
            best_res[better], best_lbl[better] = res[better], lbl[better]
    return best_lbl, best_res


def segment(img: Loaded, cfg: Config) -> Segmentation:
    rgb, alpha = img.rgb, img.alpha
    H, W = alpha.shape
    opaque = alpha >= 128
    if not opaque.any():
        # Nothing visible (a fully transparent image): no palette, no shapes.
        return Segmentation(rid=np.full((H, W), -1, np.int32), shapes=[],
                            palette=np.zeros((0, 3), np.uint8))
    lab = _lab(rgb)

    gx = cv2.Sobel(lab, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lab, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt((gx * gx + gy * gy).sum(axis=2))
    edge = cv2.dilate((grad > cfg.edge_threshold).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    flat = ~edge & opaque
    if flat.sum() < 0.02 * max(opaque.sum(), 1):   # noisy / photographic: use everything
        flat = opaque.copy()

    palette = _build_palette(rgb[flat], cfg)
    # A narrow feature may have stable colour cores before edge dilation, but
    # contribute no pixels to `flat`. Admit repeated colours from those cores
    # within the remaining palette budget; explicit palettes remain authoritative.
    # A flat palette honoured above max_colors keeps that larger budget here, or thin
    # gaps between swatches (whose pixels are all edge) would lose their colour.
    budget = cfg.max_colors if len(palette) <= cfg.max_colors else FLAT_PALETTE_CEILING
    if not cfg.palette and len(palette) < budget:
        core = (grad <= cfg.edge_threshold) & edge & opaque
        colors, counts = np.unique(rgb[core], axis=0, return_counts=True)
        labs = _lab(colors.reshape(-1, 1, 3)).reshape(-1, 3) if len(colors) else []
        for i in np.argsort(-counts):
            if counts[i] < max(6, cfg.filter_speckle) or len(palette) >= budget:
                break
            existing = _lab(palette.reshape(-1, 1, 3)).reshape(-1, 3)
            if np.linalg.norm(existing-labs[i], axis=1).min() >= cfg.color_merge:
                # Prefer a repeated solid colour over one quantized sample of a
                # smooth ramp: it must dominate its nearby RGB neighbourhood.
                near = np.linalg.norm(colors.astype(float)-colors[i], axis=1) <= 12
                if counts[i] >= 0.25*counts[near].sum():
                    palette = np.vstack([palette, colors[i]])
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
        best_lbl, best_res = _edge_labels(pix, pal, ok)
        # Alpha independently identifies foreground along transparent contours.
        # Keep their repair separate from opaque colour/gradient boundaries.
        alpha_edge = ndi.maximum_filter(~opaque, size=7, mode="constant")[ey, ex]

        # Edge dilation can consume a whole narrow mark, leaving no local flat
        # seed for a colour that is already in the palette. Restore only nearly
        # unmixed pixels (<=12 RGB distance, allowing resampling overshoot) with
        # a clear gain over local fits.
        candidates = np.flatnonzero(best_res > 6.0)
        if candidates.size:
            distance, nearest = cKDTree(pal).query(pix[candidates])
            close = distance <= 12.0
            candidates, distance, nearest = candidates[close], distance[close], nearest[close]
            if candidates.size:
                # A third palette colour can equal an antialiased blend of two
                # neighbours. Include the edge halo in this veto, even when its
                # flat seeds sit beyond the normal assignment radius.
                wide = np.zeros((candidates.size, K), bool)
                for k in range(K):
                    wide[:, k] = ndi.maximum_filter(src == k, size=9, mode="constant")[
                        ey[candidates], ex[candidates]]
                local_lbl, local_res = _edge_labels(pix[candidates], pal, wide)
                # An unresolved opaque pixel may sit just beyond the normal
                # seed radius while the wider halo already explains its colour.
                # Preserve that explanation before nearest-label filling can
                # borrow transparency and break a thin loop. Reuse the same
                # solid/pair competition; do not invent a third blend colour or
                # replace any assignment the normal neighbourhood supported.
                explained = (best_lbl[candidates] < 0) & (local_res <= 12.0) & alpha_edge[candidates]
                rescued = candidates[explained]
                best_lbl[rescued], best_res[rescued] = local_lbl[explained], local_res[explained]
                ok[rescued] |= wide[explained]
                strong = local_res > distance + 6.0
                seeds, colors = candidates[strong], nearest[strong]
                affected = np.zeros(ey.size, bool)
                for k in np.unique(colors):
                    chosen = seeds[colors == k]
                    # Also rescue distant branches of partially seeded curves.
                    # Ordinary contours stay within the six-pixel resampling
                    # halo of their flat seeds; do not alter those junctions.
                    similar = (np.linalg.norm(rgb.astype(np.float32) - pal[k], axis=2)
                               <= 12.0) & opaque
                    count, components, boxes, _ = cv2.connectedComponentsWithStats(
                        similar.astype(np.uint8), connectivity=8)
                    supported = np.zeros(count, bool)
                    supported[components[src == k]] = True
                    distant = ndi.distance_transform_edt(src != k)[ey[chosen], ex[chosen]] > 7
                    labels = components[ey[chosen], ex[chosen]]
                    for label in np.unique(labels[distant & supported[labels]]):
                        x, y, w, h = boxes[label, :4]
                        member = components[y:y + h, x:x + w] == label
                        pixels = rgb[y:y + h, x:x + w]
                        sample = pixels[member]
                        sample = sample[::max(1, len(sample)//4096)]
                        _, frequencies = np.unique(sample, axis=0, return_counts=True)
                        # A flat branch has a repeated solid core. Smooth ramp
                        # bands contain many RGB values and must keep the old
                        # assignments so gradient fitting remains coherent.
                        if frequencies.max() < 0.3*len(sample):
                            # A thin antialiased stroke (small text, a curved
                            # rule) is mostly fringe, which dilutes the mode of
                            # the whole component. Judge its interior instead:
                            # a solid mark keeps one repeated core colour there,
                            # whereas a ramp band varies inside as well.
                            inner = pixels[ndi.binary_erosion(member)]
                            if len(inner):
                                inner = inner[::max(1, len(inner)//4096)]
                                _, core_freq = np.unique(inner, axis=0, return_counts=True)
                            if not len(inner) or core_freq.max() < 0.5*len(inner):
                                distant[labels == label] = False
                    # A colour-matching unresolved core needs a seed even inside
                    # the normal resampling halo; otherwise that halo can erase
                    # a whole thin alpha-supported loop. Already-assigned edges
                    # still require the existing disconnected/distant proof.
                    chosen = chosen[~supported[components[ey[chosen], ex[chosen]]] | distant
                                    | ((best_lbl[chosen] < 0) & alpha_edge[chosen])]
                    if not chosen.size:
                        continue
                    anchors = np.zeros((H, W), bool)
                    anchors[ey[chosen], ex[chosen]] = True
                    near = ndi.maximum_filter(anchors, size=9, mode="constant")[ey, ex]
                    ok[:, k] |= near
                    affected |= near
                if affected.any():
                    for k in range(K):
                        # Include the surrounding background through the edge
                        # halo too, so recovered antialiased fringes do not all
                        # get assigned to the new foreground colour.
                        ok[affected, k] |= ndi.maximum_filter(
                            src == k, size=13, mode="constant")[ey[affected], ex[affected]]
                    # Re-estimate coverage only near restored cores; other edges
                    # keep their original assignments. Speckle cleanup still runs.
                    best_lbl[affected], best_res[affected] = _edge_labels(
                        pix[affected], pal, ok[affected])
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
    if not (cleaned >= 0).any():
        # Every opaque region was a "speck" (e.g. a 2x2 icon): there is nothing left to
        # refill from, and removing them would emit an empty SVG. Keep the originals.
        cleaned = labels
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
