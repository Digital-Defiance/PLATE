"""Objective scoring of one SVG (any tool) against a source image and, when available, ground truth.

Three families, all in [0,1] after normalisation (raw values are kept too):
  FIDELITY    ssim, edge_f1            how close the render is to the reference image
  TOPOLOGY    topology                 same number of solid same-colour pieces as the reference
                                       (report-only by default: weight 0, so composites are unchanged)
  EDITABILITY anchor_eff, primitive_ratio, named
  STRUCTURE   obj_visible_f1, obj_complete_f1, hidden_completion, order_acc, primitive_acc
              (needs truth: compares the SVG's elements with the known objects)
`composite()` is a weighted mean over the metrics that exist; weights are a plain dict
(see DEFAULT_WEIGHTS / `--weights file.toml`). Nothing here is PLATE-specific.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from ..metrics import _path_anchors, analyze_svg

S = 192                                   # structure-matching resolution
SHAPES = {"path", "circle", "ellipse", "rect", "polygon", "polyline"}
SKIP = {"defs", "clipPath", "mask", "linearGradient", "radialGradient", "style", "title", "desc", "metadata"}
_GENERIC = re.compile(r"^(path|rect|circle|ellipse|polygon|polyline|g|group|layer|shape|object|"
                      r"xmlid|svgid|_?x?[0-9a-f]+)[_\-\s]*\d*$", re.IGNORECASE)
IDEAL_ANCHORS = {"circle": 4, "ellipse": 4, "rect": 4, "rrect": 8}
KIND_TAGS = {"circle": {"circle"}, "ellipse": {"ellipse"}, "rect": {"rect"}, "rrect": {"rect"},
             "polygon": {"polygon"}}

DEFAULT_WEIGHTS = dict(ssim=0.20, edge_f1=0.10, obj_visible_f1=0.10, obj_complete_f1=0.20,
                       hidden_completion=0.10, order_acc=0.05, anchor_eff=0.10, primitive_ratio=0.05,
                       named=0.10)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _num(s):
    m = re.match(r"\s*([-+]?\d*\.?\d+)", s or "")
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------- element extraction
def leaf_elements(svg: str):
    root = ET.fromstring(svg)
    w, h = _num(root.get("width")), _num(root.get("height"))
    vb = root.get("viewBox")
    if vb:
        vals = [float(v) for v in re.split(r"[ ,]+", vb.strip())]
        w = w or vals[2]; h = h or vals[3]
    else:
        vb = f"0 0 {w} {h}"
    out = []

    def walk(el, anc):
        t = _local(el.tag)
        if t in SKIP:
            return
        if t == "g":
            tr = el.get("transform")
            for c in el:
                walk(c, anc + ([tr] if tr else []))
        elif t in SHAPES:
            out.append((el, anc))

    for c in root:
        walk(c, [])
    return out, vb, (w, h)


def _solo_svg(el, anc, vb) -> str:
    keep = {k: v for k, v in el.attrib.items()
            if "{" not in k and k not in ("fill", "stroke", "style", "id", "class", "opacity",
                                          "fill-opacity", "stroke-width", "clip-path", "mask", "filter")
            and not k.startswith("data-")}
    attrs = " ".join(f"{k}={quoteattr(v)}" for k, v in keep.items())
    inner = f'<{_local(el.tag)} {attrs} fill="#000"/>'
    for tr in reversed(anc):
        inner = f"<g transform={quoteattr(tr)}>{inner}</g>"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{inner}</svg>'


def element_masks(svg: str, max_elements: int = 4000):
    """-> (masks (N,S,S) bool in document order, tags, anchors, n_elements)."""
    import io

    import cairosvg
    from PIL import Image
    els, vb, _ = leaf_elements(svg)
    masks, tags, anchors = [], [], []
    for el, anc in els[:max_elements]:
        try:
            png = cairosvg.svg2png(bytestring=_solo_svg(el, anc, vb).encode(), output_width=S, output_height=S)
            m = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))[..., 3] > 127
        except Exception:                                   # noqa: BLE001 - unrenderable element = empty
            m = np.zeros((S, S), bool)
        masks.append(m)
        t = _local(el.tag)
        tags.append(t)
        anchors.append(_path_anchors(el.get("d", "")) if t == "path" else
                       {"circle": 4, "ellipse": 4, "rect": 8 if el.get("rx") else 4}.get(t, len(re.findall(r"[-\d.]+,[-\d.]+", el.get("points", "")))))
    arr = np.stack(masks) if masks else np.zeros((0, S, S), bool)
    return arr, tags, anchors, len(els)


# ---------------------------------------------------------------- fidelity
def fidelity(svg: str, ref_rgb: np.ndarray) -> dict:
    from skimage.metrics import structural_similarity as ssim

    from ..raster import render_svg
    h, w = ref_rgb.shape[:2]
    ren = render_svg(svg, (w, h), (255, 255, 255))
    mae = float(np.abs(ren.astype(np.float32) - ref_rgb.astype(np.float32)).mean())
    ge = cv2.Canny(cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2GRAY), 60, 160) > 0
    re_ = cv2.Canny(cv2.cvtColor(ren, cv2.COLOR_RGB2GRAY), 60, 160) > 0
    k = np.ones((3, 3), np.uint8)
    dg, dr = cv2.dilate(ge.astype(np.uint8), k, iterations=2) > 0, cv2.dilate(re_.astype(np.uint8), k, iterations=2) > 0
    p = (re_ & dg).sum() / max(re_.sum(), 1) if re_.any() else 1.0
    r = (ge & dr).sum() / max(ge.sum(), 1) if ge.any() else 1.0
    return dict(ssim=float(ssim(ref_rgb, ren, channel_axis=2)), mae=mae,
                edge_f1=float(2 * p * r / max(p + r, 1e-9)), **topology(ren, ref_rgb), **smoothness(ren, ref_rgb))


# ---------------------------------------------------------------- topology
def _ref_palette(ref: np.ndarray, max_colors: int = 12) -> np.ndarray:
    """Dominant colours of the reference: 5-bit histogram peaks holding >= 0.2% of its flat
    pixels (3x3 neighbourhood within 12 RGB), at least 40 RGB apart. Only flat pixels vote, so
    the repeated blend along a long straight anti-aliased edge never becomes a colour."""
    k = np.ones((3, 3), np.uint8)
    flat = (cv2.dilate(ref, k).astype(int) - cv2.erode(ref, k).astype(int)).max(2) <= 12
    px = ref[flat] if flat.sum() >= 0.05 * flat.size else ref.reshape(-1, 3)
    q = (px >> 3).reshape(-1, 3).astype(np.int32)
    vals, counts = np.unique((q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2], return_counts=True)
    pal: list[np.ndarray] = []
    for i in np.argsort(-counts):
        if counts[i] < 0.002 * len(q) or len(pal) >= max_colors:
            break
        c = np.array([(vals[i] >> 10) & 31, (vals[i] >> 5) & 31, vals[i] & 31], float) * 8 + 4
        if all(np.linalg.norm(c - p) >= 40 for p in pal):
            pal.append(c)
    return np.array(pal, float).reshape(-1, 3)


TOPO_SHARE = 0.4    # a pixel belongs to a colour only within 40% of the way to the next palette colour


def _class_map(img: np.ndarray, pal: np.ndarray) -> np.ndarray:
    """Nearest palette index per pixel, or -1 where the pixel is a blend (anti-aliasing, JPEG ringing)."""
    x = img.astype(np.float32)
    d = np.sqrt(np.stack([((x - c) ** 2).sum(2) for c in pal]))
    gap = np.linalg.norm(pal[:, None] - pal[None], axis=2)
    np.fill_diagonal(gap, np.inf)
    lab = d.argmin(0)
    return np.where(d.min(0) <= TOPO_SHARE * gap.min(1)[lab], lab, -1)


def _labels(m: np.ndarray, min_area: int) -> tuple[np.ndarray, int]:
    n, cc, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    small = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] < min_area)
    cc[np.isin(cc, small[small > 0])] = 0
    return cc, n


def topology_pieces(ren: np.ndarray, ref_rgb: np.ndarray) -> list[dict]:
    """Pieces that do not line up one-to-one between reference and render, with their colour,
    kind ('extra' or 'missing'), centre (x, y) and size: for reports and debugging."""
    pal = _ref_palette(ref_rgb)
    if len(pal) < 2:
        return []
    min_area = max(4, int(4e-6 * ref_rgb.shape[0] * ref_rgb.shape[1]))
    ca, cb = _class_map(ref_rgb, pal), _class_map(ren, pal)
    out = []
    for k in range(len(pal)):
        A, na = _labels(ca == k, min_area)
        B, nb = _labels(cb == k, min_area)
        Bd = cv2.dilate(B.astype(np.float32), np.ones((3, 3), np.uint8)).astype(np.int64)  # 1 px slack
        Ad = cv2.dilate(A.astype(np.float32), np.ones((3, 3), np.uint8)).astype(np.int64)
        parent = list(range(na + nb))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for X, Y in ((A, Bd), (Ad, B)):          # (reference label, render label) pairs that touch
            both = (X > 0) & (Y > 0)
            for a, b in set(zip(X[both].tolist(), Y[both].tolist())):
                parent[find(a)] = find(na + b)
        present_a = set(np.unique(A[A > 0]).tolist())
        present_b = set(np.unique(B[B > 0]).tolist())
        groups: dict[int, tuple[list, list]] = {}
        for a in present_a:
            groups.setdefault(find(a), ([], []))[0].append(a)
        for b in present_b:
            groups.setdefault(find(na + b), ([], []))[1].append(b)
        for ga, gb in groups.values():
            if len(gb) > len(ga):
                pick, L, kind = gb, B, "extra"
            elif len(ga) > len(gb):
                pick, L, kind = ga, A, "missing"
            else:
                continue
            sizes = sorted(((int((L == i).sum()), i) for i in pick))      # smallest pieces are the odd ones
            for area, i in sizes[:abs(len(gb) - len(ga))]:
                ys, xs = np.nonzero(L == i)
                out.append(dict(color=tuple(int(v) for v in pal[k]), kind=kind,
                                at=(float(xs.mean()), float(ys.mean())), area=area))
    return out


def topology(ren: np.ndarray, ref_rgb: np.ndarray) -> dict:
    """Do the same pieces exist? Solid same-colour pieces (per dominant reference colour) are
    matched by overlap. topo_extra counts pieces the SVG adds (specks, pinched-off wedge tips,
    shapes split in two); topo_missing counts pieces it loses (dropped dots and periods, shapes
    merged together). topology = 1 - (extra + missing) / reference pieces, clipped to [0, 1].
    Blend pixels are ignored on both sides, so a soft JPEG and a crisp render compare fairly."""
    pal = _ref_palette(ref_rgb)
    if len(pal) < 2:
        return dict(topology=1.0, topo_extra=0, topo_missing=0)
    min_area = max(4, int(4e-6 * ref_rgb.shape[0] * ref_rgb.shape[1]))
    ca = _class_map(ref_rgb, pal)
    total = sum(len(np.unique(_labels(ca == k, min_area)[0])) - 1 for k in range(len(pal)))
    odd = topology_pieces(ren, ref_rgb)
    extra = sum(p["kind"] == "extra" for p in odd)
    missing = sum(p["kind"] == "missing" for p in odd)
    return dict(topology=float(max(0.0, 1 - (extra + missing) / max(total, 1))),
                topo_extra=extra, topo_missing=missing)

# ---------------------------------------------------------------- smoothness (outline wobble)
def _color_contours(img: np.ndarray, pal: np.ndarray, min_area: int):
    """Outer contours (as float (x, y) arrays) of every solid same-colour piece, blend pixels
    excluded. Reuses the topology palette/class machinery so soft and crisp images agree."""
    cm = _class_map(img, pal)
    out = []
    for k in range(len(pal)):
        cc, _ = _labels(cm == k, min_area)
        for i in np.unique(cc):
            if i == 0:
                continue
            cs, _ = cv2.findContours((cc == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            for c in cs:
                if len(c) >= 16 and cv2.contourArea(c) >= min_area:
                    out.append(c.reshape(-1, 2).astype(np.float64))
    return out


def _turning_per_length(contour: np.ndarray, step: float = 3.0) -> tuple[float, float]:
    """(total absolute turning in radians, perimeter) of one closed contour, resampled at a fixed
    arc-length `step` so single-pixel staircase jitter does not dominate. A smooth arc turns the
    same total angle whether crisp or wavy; wobble adds back-and-forth turning that cancels in a
    clean outline, so excess turning over the reference is the wobble signal."""
    p = np.vstack([contour, contour[:1]])
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    peri = float(seg.sum())
    if peri < 4 * step:
        return 0.0, peri
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(8, int(peri / step))
    u = np.linspace(0.0, peri, n, endpoint=False)
    rx = np.interp(u, s, p[:, 0])
    ry = np.interp(u, s, p[:, 1])
    d = np.stack([np.gradient(rx), np.gradient(ry)], 1)
    ang = np.arctan2(d[:, 1], d[:, 0])
    dth = np.diff(np.concatenate([ang, ang[:1]]))
    dth = (dth + np.pi) % (2 * np.pi) - np.pi      # wrap to (-pi, pi]
    return float(np.abs(dth).sum()), peri


def _wobble(img: np.ndarray, pal: np.ndarray, min_area: int) -> tuple[float, float]:
    """(total absolute turning, total perimeter) summed over every solid piece of `img`."""
    turn = length = 0.0
    for c in _color_contours(img, pal, min_area):
        t, lp = _turning_per_length(c)
        turn += t
        length += lp
    return turn, length


def smoothness(ren: np.ndarray, ref_rgb: np.ndarray) -> dict:
    """How much more do the render's outlines wiggle than the reference's? For each dominant
    reference colour we sum the absolute turning (direction change) of every solid outline and
    divide by its total length: a smooth curve and its wavy copy turn the same net angle, but the
    wavy one accumulates extra back-and-forth turning. `wobble` is the render's turning-per-length
    minus the reference's (>= 0, clipped); `smoothness = 1/(1+8*wobble)` maps it to [0, 1] with 1 =
    as smooth as the source. Report-only: it is not in DEFAULT_WEIGHTS, so composites never move.
    SSIM/edge-F1 are blind to this - a lumpy line can render almost pixel-identical to a clean one."""
    pal = _ref_palette(ref_rgb)
    if len(pal) < 2:
        return dict(smoothness=1.0, wobble=0.0)
    min_area = max(16, int(1e-5 * ref_rgb.shape[0] * ref_rgb.shape[1]))
    tr, lr = _wobble(ref_rgb, pal, min_area)
    tc, lc = _wobble(ren, pal, min_area)
    ref_tpl = tr / lr if lr else 0.0
    ren_tpl = tc / lc if lc else 0.0
    wob = max(0.0, ren_tpl - ref_tpl)
    return dict(smoothness=float(1.0 / (1.0 + 8.0 * wob)), wobble=float(wob))



# ---------------------------------------------------------------- structure vs truth
def _down(m: np.ndarray) -> np.ndarray:
    return cv2.resize(m.astype(np.uint8) * 255, (S, S), interpolation=cv2.INTER_AREA) > 127


def _iou_matrix(G: np.ndarray, C: np.ndarray) -> np.ndarray:
    out = np.zeros((len(G), len(C)), np.float32)
    if len(C) == 0:
        return out
    Cf = C.reshape(len(C), -1)
    ca = Cf.sum(1)
    for i, g in enumerate(G):
        gf = g.reshape(-1)
        inter = (Cf & gf).sum(1)
        out[i] = inter / np.maximum(gf.sum() + ca - inter, 1)
    return out


def _match(iou: np.ndarray, thr: float):
    """Hungarian on IoU; returns {gt_index: cand_index} for pairs with IoU >= thr."""
    if iou.size == 0:
        return {}
    r, c = linear_sum_assignment(-iou)
    return {int(i): int(j) for i, j in zip(r, c) if iou[i, j] >= thr}


def structure(svg: str, truth: dict, thr: float = 0.9) -> dict:
    objs = truth["objects"]
    gfull = np.stack([_down(m) for m in truth["full"]])
    gvis = np.stack([_down(m) for m in truth["visible"]])
    cfull, tags, anchors, n_el = element_masks(svg)
    # candidate visible region = element minus everything painted after it
    cvis = np.zeros_like(cfull)
    above = np.zeros((S, S), bool)
    for i in range(len(cfull) - 1, -1, -1):
        cvis[i] = cfull[i] & ~above
        above |= cfull[i]
    bg = next((i for i, o in enumerate(objs) if o.get("background")), None)
    objs_i = [i for i in range(len(objs)) if i != bg]
    out = {}

    def f1(match, n_cand_effective):
        tp = len([i for i in match if i != bg])
        n_gt = len(objs_i)
        p = tp / max(n_cand_effective, 1)
        r = tp / max(n_gt, 1)
        return 2 * p * r / max(p + r, 1e-9)

    mv = _match(_iou_matrix(gvis, cvis), thr)
    mc = _match(_iou_matrix(gfull, cfull), thr)
    n_eff = n_el - (1 if bg is not None and bg in mc else 0)
    out["obj_visible_f1"] = f1(mv, n_el - (1 if bg is not None and bg in mv else 0))
    out["obj_complete_f1"] = f1(mc, n_eff)
    out["n_elements"] = n_el
    occluded = [i for i in objs_i if truth["visible"][i].sum() < 0.97 * truth["full"][i].sum()]
    out["hidden_completion"] = (sum(i in mc for i in occluded) / len(occluded)) if occluded else None
    # stacking order among matched, overlapping pairs
    good = tot = 0
    ids = [i for i in objs_i if i in mc]
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            if (gfull[i] & gfull[j]).sum() < 30:
                continue
            tot += 1
            good += (mc[i] < mc[j]) == (i < j)
    out["order_acc"] = good / tot if tot else None
    # primitive kind + anchor economy on completely-matched objects
    kinds = [tags[mc[i]] in KIND_TAGS.get(objs[i]["kind"], set()) for i in ids]
    out["primitive_acc"] = float(np.mean(kinds)) if kinds else None
    ratios = [anchors[mc[i]] / max(IDEAL_ANCHORS.get(objs[i]["kind"], len(objs[i].get("pts", [])) or 4), 1) for i in ids]
    out["anchor_ratio_vs_ideal"] = float(np.mean(ratios)) if ratios else None
    return out


# ---------------------------------------------------------------- editability
def editability(svg: str) -> dict:
    m = analyze_svg(svg)
    root = ET.fromstring(svg)
    named = total = 0
    for el in root.iter():
        t = _local(el.tag)
        if t == "g" or t in SHAPES:
            total += 1
            nm = el.get("data-name") or el.get("id") or el.get("{http://www.inkscape.org/namespaces/inkscape}label") or ""
            named += bool(nm) and not _GENERIC.match(nm)
    return dict(shapes=m["shapes"], anchors=m["anchors"], anchors_per_shape=m["anchors_per_shape"],
                primitive_ratio=m["primitive_ratio"], layer_depth=m["layer_depth"], bytes=m["bytes"],
                named=named / max(total, 1))


# ---------------------------------------------------------------- composite
def normalise(raw: dict) -> dict:
    c = lambda v: float(min(1.0, max(0.0, v)))
    n = {}
    if "ssim" in raw: n["ssim"] = c((raw["ssim"] - 0.85) / 0.14)
    if "edge_f1" in raw: n["edge_f1"] = c(raw["edge_f1"])
    if "topology" in raw: n["topology"] = c(raw["topology"])
    if "anchors_per_shape" in raw: n["anchor_eff"] = c(1 - (raw["anchors_per_shape"] - 4) / 36)
    if "primitive_ratio" in raw: n["primitive_ratio"] = c(raw["primitive_ratio"])
    if "named" in raw: n["named"] = c(raw["named"])
    for k in ("obj_visible_f1", "obj_complete_f1", "hidden_completion", "order_acc"):
        if raw.get(k) is not None:
            n[k] = c(raw[k])
    return n


def composite(raw: dict, weights: dict | None = None) -> tuple[float, dict]:
    w = weights or DEFAULT_WEIGHTS
    n = normalise(raw)
    use = {k: w[k] for k in n if w.get(k, 0) > 0}
    tot = sum(use.values())
    return (sum(n[k] * v for k, v in use.items()) / tot if tot else 0.0), n


def score_svg(svg: str, ref_rgb: np.ndarray, truth: dict | None = None, weights: dict | None = None) -> dict:
    raw = {**fidelity(svg, ref_rgb), **editability(svg)}
    if truth is not None:
        raw.update(structure(svg, truth))
    comp, norm = composite(raw, weights)
    return dict(raw=raw, norm=norm, composite=comp)
