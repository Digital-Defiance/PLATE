"""Optional semantic layer: name shapes and group them with a local vision-language model.

Talks to any OpenAI-compatible chat endpoint; the default target is LM Studio
(`http://localhost:1234/v1`, load a vision model such as Qwen2.5-VL / Gemma 3 / Pixtral).
Stdlib only (urllib). Everything degrades gracefully: any failure -> classical names.

Two calls types:
  * name_shapes  : one request per shape (crop with the shape outlined) -> short layer name
  * group_shapes : one request for the whole picture + a shape table -> semantic groups
Responses are cached on disk (.plate-cache/vlm) keyed by request hash, so re-runs are free.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .scene import Node

MAX_SHAPES_NAMED = 48
CACHE_DIR = Path(".plate-cache") / "vlm"


def _png_b64(arr: np.ndarray) -> str:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _post(url: str, body: dict, timeout: float = 120.0) -> dict:
    req = urllib.request.Request(url.rstrip("/") + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": "Bearer lm-studio"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def list_models(url: str, timeout: float = 5.0) -> list[str]:
    with urllib.request.urlopen(url.rstrip("/") + "/models", timeout=timeout) as r:
        return [m["id"] for m in json.loads(r.read()).get("data", [])]


def _ask(url: str, model: str, text: str, images: list[np.ndarray], use_cache: bool = True) -> str:
    content = [{"type": "text", "text": text}] + [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _png_b64(i)}} for i in images]
    body = {"model": model or "local-model", "temperature": 0.1, "max_tokens": 600,
            "messages": [{"role": "user", "content": content}]}
    key = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
    cp = CACHE_DIR / f"{key}.txt"
    if use_cache and cp.exists():
        return cp.read_text()
    out = _post(url, body)["choices"][0]["message"]["content"]
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cp.write_text(out)
    return out


def _json(text: str):
    # Reasoning models (e.g. Qwen3) emit a <think>...</think> block and sometimes
    # fence the JSON in ```json ... ```. Strip those before extracting.
    text = re.sub(r"<think>.*?</think>", " ", text, flags=re.S | re.I)
    text = re.sub(r"```(?:json)?|```", " ", text)
    # find the first balanced {...} or [...] object rather than a greedy span that
    # may swallow trailing prose and break json.loads.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    # last resort: greedy span (handles simple single-object replies)
    m = re.search(r"\{.*\}|\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON in reply")
    return json.loads(m.group(0))


def _clean(name: str) -> str:
    name = re.sub(r"[^\w\- ]", "", str(name)).strip()
    return " ".join(name.split())[:40].title() if name else ""


def _crop(rgb: np.ndarray, mask_full: np.ndarray, pad: int = 12, side: int = 256) -> np.ndarray:
    ys, xs = np.nonzero(mask_full)
    y0, y1, x0, x1 = max(ys.min() - pad, 0), ys.max() + pad, max(xs.min() - pad, 0), xs.max() + pad
    im = rgb.copy()
    cnt, _ = cv2.findContours(mask_full.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(im, cnt, -1, (255, 0, 255), 2)
    im = im[y0:y1, x0:x1]
    r = side / max(im.shape[:2])
    return cv2.resize(im, (max(1, int(im.shape[1] * r)), max(1, int(im.shape[0] * r))))


def name_shapes(result, url: str, model: str = "", log=lambda m: None) -> dict[int, str]:
    """shape_id -> semantic name. Largest shapes first, capped at MAX_SHAPES_NAMED."""
    H, W = result.loaded.rgb.shape[:2]
    shapes = [s for s in result.shapes if not s.full.empty()]
    shapes.sort(key=lambda s: -s.full.area)
    names: dict[int, str] = {}
    whole = cv2.resize(result.loaded.rgb, (384, int(384 * H / W)))
    for s in shapes[:MAX_SHAPES_NAMED]:
        if s.is_background:
            continue
        crop = _crop(result.loaded.rgb, s.full.to_full((H, W)))
        q = ("Image 1 is a vector illustration; image 2 is a close-up with ONE shape outlined in magenta. "
             "Give that shape a short Illustrator layer name (1-3 words, e.g. 'Left Eye', 'Star', 'Card Shadow'). "
             'Reply ONLY with JSON: {"name": "..."}')
        try:
            n = _clean(_json(_ask(url, model, q, [whole, crop]))["name"])
            if n:
                names[s.id] = n
        except Exception as e:                          # noqa: BLE001 - never break the run
            log(f"vlm: shape {s.id} skipped ({e})")
            if isinstance(e, OSError):
                break                                   # server unreachable: stop trying
    return names


def group_shapes(result, names: dict[int, str], url: str, model: str = "", log=lambda m: None) -> list[dict]:
    """[{'name': str, 'members': [shape_id, ...]}] covering only shapes the model grouped."""
    H, W = result.loaded.rgb.shape[:2]
    table = []
    for s in result.shapes:
        if s.full.empty() or s.is_background:
            continue
        y0, x0, y1, x1 = s.full.bbox
        table.append({"id": s.id, "name": names.get(s.id) or s.name or "shape",
                      "bbox": [int(x0 * 100 / W), int(y0 * 100 / H), int(x1 * 100 / W), int(y1 * 100 / H)]})
    q = ("This is a vector illustration split into shapes (bbox in % of the image: x0,y0,x1,y1):\n"
         + json.dumps(table) +
         "\nGroup shapes that form one real-world object or UI element (e.g. an eye = eyeball + pupil + highlight). "
         "Only create groups of 2+ shapes; leave singletons out. "
         'Reply ONLY with JSON: {"groups": [{"name": "Left Eye", "members": [3, 5]}]}')
    try:
        reply = _json(_ask(url, model, q, [cv2.resize(result.loaded.rgb, (512, int(512 * H / W)))]))
        valid = {t["id"] for t in table}
        used, out = set(), []
        for g in reply.get("groups", []):
            mem = [int(m) for m in g.get("members", []) if int(m) in valid and int(m) not in used]
            if len(mem) >= 2 and _clean(g.get("name", "")):
                used.update(mem)
                out.append({"name": _clean(g["name"]), "members": mem})
        return out
    except Exception as e:                              # noqa: BLE001
        log(f"vlm: grouping skipped ({e})")
        return []


def apply_groups(tree: list[Node], groups: list[dict]) -> list[Node]:
    """Wrap top-level nodes that belong to the same semantic group into a named group.
    The group takes the z-position of its topmost member; member order is preserved."""
    def ids(n: Node) -> set[int]:
        s = {n.shape_id} if n.shape_id is not None else set()
        for c in n.children:
            s |= ids(c)
        return s

    def wrap(nodes: list[Node], g: dict) -> bool:
        want = set(g["members"])
        idx = [i for i, n in enumerate(nodes) if ids(n) & want]
        if len(idx) >= 2:
            members = [nodes[i] for i in idx]
            wrapper = Node(g["name"], "group", None, children=members)
            for i in reversed(idx):
                nodes.pop(i)
            nodes.insert(idx[-1] - len(idx) + 1, wrapper)
            return True
        if len(idx) == 1 and nodes[idx[0]].kind == "group":
            return wrap(nodes[idx[0]].children, g)      # members live deeper: descend
        return False

    for g in groups:
        wrap(tree, g)
    return tree


# substrings that mark a model as unusable for image naming (text/embedding only)
_NON_VISION_HINTS = ("embed", "embedding", "rerank", "whisper", "tts", "bge", "nomic")


def pick_model(models: list[str], preferred: str = "") -> str:
    """Choose a model id for the vision path. An explicit `preferred` wins if present.
    Otherwise skip obviously non-vision models (embeddings/rerankers); fall back to the
    first loaded model if every candidate looks non-vision (so we still try rather than
    silently do nothing)."""
    if preferred:
        return preferred
    usable = [m for m in models if not any(h in m.lower() for h in _NON_VISION_HINTS)]
    return (usable or models or [""])[0]


def describe(result, cfg, log=lambda m: print(m, file=sys.stderr)):
    """Entry point used by the pipeline. Returns (names, groups); both empty on any failure."""
    if not cfg.vlm_url:
        return {}, []
    try:
        models = list_models(cfg.vlm_url)
    except Exception as e:                              # noqa: BLE001
        log(f"vlm: cannot reach {cfg.vlm_url} ({e}); using classical names")
        return {}, []
    model = pick_model(models, cfg.vlm_model)
    if not model:
        log(f"vlm: no models loaded at {cfg.vlm_url}; using classical names")
        return {}, []
    log(f"vlm: using model {model!r}")
    names = name_shapes(result, cfg.vlm_url, model, log)
    if not names:
        log(f"vlm: model {model!r} returned no usable names "
            f"(is it a vision model? try --vlm-model); using classical names")
    groups = group_shapes(result, names, cfg.vlm_url, model, log) if cfg.vlm_groups else []
    return names, groups
