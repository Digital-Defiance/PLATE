"""Single-file HTML report: source vs SVG, metrics, layer tree."""
from __future__ import annotations

import base64
import html
import io

from .scene import Node


def _tree(nodes: list[Node]) -> str:
    out = ["<ul>"]
    for n in nodes:
        tag = {"group": "▸", "path": "✎", "circle": "●", "ellipse": "⬭", "rect": "▭", "rrect": "▢",
               "polygon": "⬠"}.get(n.kind, "·")
        extra = f" <small>{n.anchors} anchors</small>" if n.kind != "group" else ""
        sw = f'<i style="background:rgb{tuple(n.color)}"></i>' if n.color else ""
        out.append(f"<li>{sw}{tag} {html.escape(n.name)}{extra}")
        if n.children:
            out.append(_tree(n.children))
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)


def build(src_path, result, metrics: dict, fid: dict | None) -> str:
    from .imageio import open_rgba
    im = open_rgba(src_path)  # displayed orientation, 16-bit scaled — matches the SVG
    buf = io.BytesIO(); im.save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in {**metrics, **(fid or {}),
                                                                       **result.stats}.items()
                   if not isinstance(v, float) or k.startswith("mae") or k in ("psnr", "ssim"))
    return f"""<!doctype html><meta charset=utf-8><title>PLATE report</title>
<style>body{{font:14px system-ui;margin:20px;background:#f4f4f4}}.row{{display:flex;gap:16px;flex-wrap:wrap}}
.c{{background:repeating-conic-gradient(#ddd 0 25%,#fff 0 50%) 0 0/16px 16px;padding:8px;max-width:48%}}
.c img,.c svg{{max-width:100%;height:auto}}table{{border-collapse:collapse}}td{{padding:2px 10px;border-bottom:1px solid #ccc}}
ul{{list-style:none;padding-left:18px;margin:2px}}i{{display:inline-block;width:10px;height:10px;margin-right:4px;border:1px solid #888}}</style>
<h2>PLATE report</h2><div class=row><div class=c><b>Source</b><br><img src="data:image/png;base64,{b64}"></div>
<div class=c><b>SVG</b><br>{result.svg.split("?>", 1)[-1]}</div></div>
<div class=row><div><h3>Metrics</h3><table>{rows}</table></div><div><h3>Layers</h3>{_tree(result.nodes)}</div></div>"""
