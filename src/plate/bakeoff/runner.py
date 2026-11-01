"""Bake-off orchestration + report."""
from __future__ import annotations

import base64
import csv
import html
import io
import json
import time
from pathlib import Path

import numpy as np
import tomllib
from PIL import Image

from . import adapters, score
from .corpus import load_truth

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_weights(path: Path | None) -> dict:
    if not path:
        return dict(score.DEFAULT_WEIGHTS)
    return {**score.DEFAULT_WEIGHTS, **tomllib.loads(Path(path).read_text())}


def run(images: Path, out: Path, tools: list[str], truth: Path | None = None, external: Path | None = None,
        weights: dict | None = None, log=print) -> dict:
    files = sorted(p for p in images.iterdir() if p.suffix.lower() in IMG_EXT)
    stems = [p.stem for p in files]
    ext = adapters.discover_external(external, stems) if external else {}
    all_tools = list(tools) + sorted(ext)
    (out / "svg").mkdir(parents=True, exist_ok=True)
    rows = []
    for f in files:
        ref = np.asarray(Image.open(f).convert("RGB"))
        tr = None
        if truth and (truth / f"{f.stem}.json").exists():
            tr = load_truth(truth / f"{f.stem}.json")
            import cairosvg

            from .corpus import scene_svg
            png = cairosvg.svg2png(bytestring=scene_svg(tr["objects"]).encode(), output_width=ref.shape[1], output_height=ref.shape[0])
            ref_clean = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))   # fidelity vs CLEAN truth
        else:
            ref_clean = ref
        for tool in all_tools:
            dst = out / "svg" / f"{f.stem}.{tool}.svg"
            t0 = time.time()
            try:
                if tool in ext:
                    if f.stem not in ext[tool]:
                        continue
                    dst.write_text(ext[tool][f.stem].read_text(encoding="utf-8"), encoding="utf-8")
                else:
                    adapters.BUILTIN[tool](f, dst)
                dt = time.time() - t0
                r = score.score_svg(dst.read_text(encoding="utf-8"), ref_clean, tr, weights)
                rows.append(dict(image=f.stem, tool=tool, seconds=round(dt, 2), composite=r["composite"],
                                 has_truth=tr is not None, raw=r["raw"], norm=r["norm"]))
                log(f"{f.stem:14} {tool:15} composite={r['composite']:.3f}  ({dt:.1f}s)")
            except Exception as e:                          # noqa: BLE001 - one failure must not sink the run
                log(f"{f.stem:14} {tool:15} FAILED: {e}")
                rows.append(dict(image=f.stem, tool=tool, seconds=0, composite=0.0, has_truth=tr is not None,
                                 raw={}, norm={}, error=str(e)))
    summary = summarise(rows, weights or score.DEFAULT_WEIGHTS)
    (out / "results.json").write_text(json.dumps(dict(summary=summary, rows=rows,
                                                      profiles=profile_scores(summary, weights or score.DEFAULT_WEIGHTS)), indent=1))
    with open(out / "results.csv", "w", newline="") as fh:
        keys = sorted({k for r in rows for k in r["raw"]})
        w = csv.writer(fh)
        w.writerow(["image", "tool", "composite", "seconds", *keys])
        for r in rows:
            w.writerow([r["image"], r["tool"], round(r["composite"], 4), r["seconds"], *[r["raw"].get(k, "") for k in keys]])
    (out / "report.html").write_text(report_html(rows, summary, files, out, weights or score.DEFAULT_WEIGHTS), encoding="utf-8")
    return summary


PROFILES = {
    "balanced (default)": None,
    "geometry-only (no names/primitive credit)": dict(ssim=0.25, edge_f1=0.15, obj_visible_f1=0.15, obj_complete_f1=0.20,
                                                      hidden_completion=0.10, order_acc=0.05, anchor_eff=0.10,
                                                      primitive_ratio=0.0, named=0.0),
    "fidelity-first": dict(ssim=0.40, edge_f1=0.30, obj_visible_f1=0.05, obj_complete_f1=0.05, hidden_completion=0.0,
                           order_acc=0.0, anchor_eff=0.10, primitive_ratio=0.0, named=0.10),
    "editability-first": dict(ssim=0.10, edge_f1=0.05, obj_visible_f1=0.05, obj_complete_f1=0.10, hidden_completion=0.05,
                              order_acc=0.05, anchor_eff=0.25, primitive_ratio=0.15, named=0.20),
    "structure-first": dict(ssim=0.05, edge_f1=0.05, obj_visible_f1=0.20, obj_complete_f1=0.30, hidden_completion=0.20,
                            order_acc=0.10, anchor_eff=0.05, primitive_ratio=0.0, named=0.05),
}


def profile_scores(summary: list[dict], weights: dict) -> dict:
    """{profile: {tool: composite}} recomputed from each tool's mean normalised metrics."""
    out = {}
    for name, w in PROFILES.items():
        w = w or weights
        out[name] = {}
        for s in summary:
            use = {k: w[k] for k in s["norm"] if w.get(k, 0) > 0}
            tot = sum(use.values())
            out[name][s["tool"]] = sum(s["norm"][k] * v for k, v in use.items()) / tot if tot else 0.0
    return out


def summarise(rows: list[dict], weights: dict) -> list[dict]:
    tools = sorted({r["tool"] for r in rows})
    out = []
    for t in tools:
        rs = [r for r in rows if r["tool"] == t]
        ok = [r for r in rs if r["norm"]]
        agg = {}
        for k in set().union(*[r["norm"].keys() for r in ok]) if ok else []:
            agg[k] = float(np.mean([r["norm"][k] for r in ok if k in r["norm"]]))
        raw = {}
        for k in ("ssim", "anchors_per_shape", "shapes", "primitive_ratio", "named", "hidden_completion",
                  "obj_complete_f1", "primitive_acc"):
            vals = [r["raw"][k] for r in ok if r["raw"].get(k) is not None]
            if vals:
                raw[k] = float(np.mean(vals))
        out.append(dict(tool=t, composite=float(np.mean([r["composite"] for r in rs])) if rs else 0.0,
                        n=len(rs), failed=len(rs) - len(ok), seconds=float(np.mean([r["seconds"] for r in rs])) if rs else 0,
                        norm=agg, raw=raw))
    return sorted(out, key=lambda s: -s["composite"])


def _thumb(svg_path: Path, size: int = 200) -> str:
    try:
        from ..raster import render_svg
        arr = render_svg(svg_path.read_text(encoding="utf-8"), (size, size))
        buf = io.BytesIO(); Image.fromarray(arr).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:                                       # noqa: BLE001
        return ""


METRIC_LABEL = dict(ssim="SSIM", edge_f1="Edge F1", obj_visible_f1="Objects found (visible)",
                    obj_complete_f1="Objects found (complete)", hidden_completion="Hidden parts completed",
                    order_acc="Stacking order", anchor_eff="Anchor economy", primitive_ratio="True primitives",
                    named="Meaningful names")


def report_html(rows, summary, files, out: Path, weights: dict) -> str:
    tools = [s["tool"] for s in summary]
    metrics = [k for k in METRIC_LABEL if any(k in s["norm"] for s in summary)]
    head = "".join(f"<th>{html.escape(METRIC_LABEL[k])}<br><small>w={weights.get(k, 0):g}</small></th>" for k in metrics)
    body = ""
    for s in summary:
        cells = "".join(f"<td style='background:rgba(46,160,67,{0.08 + 0.55 * s['norm'].get(k, 0):.2f})'>{s['norm'][k]:.2f}</td>"
                        if k in s["norm"] else "<td>–</td>" for k in metrics)
        body += (f"<tr><th>{html.escape(s['tool'])}</th><td class=big>{s['composite']:.3f}</td>{cells}"
                 f"<td>{s['raw'].get('anchors_per_shape', 0):.1f}</td><td>{s['seconds']:.1f}s</td></tr>")
    grid = ""
    byimg = {}
    for r in rows:
        byimg.setdefault(r["image"], {})[r["tool"]] = r
    for f in files:
        cells = f"<td><img src='{_thumb_src(f)}'><br>source</td>"
        for t in tools:
            r = byimg.get(f.stem, {}).get(t)
            p = out / "svg" / f"{f.stem}.{t}.svg"
            if r and p.exists():
                cells += f"<td><img src='{_thumb(p)}'><br><b>{r['composite']:.2f}</b></td>"
            else:
                cells += "<td>–</td>"
        grid += f"<tr><th>{html.escape(f.stem)}</th>{cells}</tr>"
    prof = profile_scores(summary, weights)
    ph = "".join(f"<th>{html.escape(t)}</th>" for t in tools)
    pb = ""
    for name, sc in prof.items():
        best = max(sc, key=sc.get)
        pb += f"<tr><th>{html.escape(name)}</th>" + "".join(
            f"<td{' class=big' if t == best else ''}>{sc[t]:.3f}</td>" for t in tools) + f"<td>{html.escape(best)}</td></tr>"
    gh = "<th></th><th>source</th>" + "".join(f"<th>{html.escape(t)}</th>" for t in tools)
    return f"""<!doctype html><meta charset=utf-8><title>PLATE bake-off</title>
<style>body{{font:14px system-ui;margin:24px;color:#222}}table{{border-collapse:collapse;margin:12px 0}}
td,th{{border:1px solid #ddd;padding:5px 9px;text-align:center}}.big{{font-size:18px;font-weight:700}}
img{{width:160px;height:160px;object-fit:contain;background:#fff}}small{{font-weight:400;color:#777}}</style>
<h1>Bake-off</h1><p>Composite = weighted mean of normalised metrics (0–1, higher is better). Weights shown under each column;
structure metrics only exist for images with ground truth.</p>
<table><tr><th>tool</th><th>composite</th>{head}<th>anchors<br>/shape</th><th>time</th></tr>{body}</table>
<h2>Does the ranking depend on what you value?</h2>
<table><tr><th>priorities</th>{ph}<th>winner</th></tr>{pb}</table>
<h2>Per image</h2><table><tr>{gh}</tr>{grid}</table>"""


def _thumb_src(f: Path, size: int = 200) -> str:
    im = Image.open(f).convert("RGB"); im.thumbnail((size, size))
    buf = io.BytesIO(); im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
