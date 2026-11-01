"""Objective scoring of one SVG (any tool) against a source image and, when available, ground truth.

Three families, all in [0,1] after normalisation (raw values are kept too):
  FIDELITY    ssim, edge_f1            how close the render is to the reference image
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
                edge_f1=float(2 * p * r / max(p + r, 1e-9)))


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
