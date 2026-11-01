from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np

from . import __version__
from .config import PRESETS, Config, load

IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _coerce(cfg_field: dataclasses.Field, raw: str):
    t = cfg_field.type if isinstance(cfg_field.type, str) else cfg_field.type.__name__
    if t.startswith("bool"):
        return raw.lower() in ("1", "true", "yes", "on")
    if t.startswith("int"):
        return int(raw)
    if t.startswith("float"):
        return float(raw)
    if t.startswith("tuple"):
        return tuple(x.strip() for x in raw.split(",") if x.strip())
    return raw


def _overrides(pairs: list[str] | None) -> dict:
    fields = {f.name: f for f in dataclasses.fields(Config)}
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"plate: --set expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        k = k.strip().replace("-", "_")
        if k not in fields:
            raise SystemExit(f"plate: unknown lever {k!r}. Levers: {', '.join(sorted(fields))}")
        out[k] = _coerce(fields[k], v)
    return out


def _cfg(args) -> Config:
    ov = _overrides(getattr(args, "set", None))
    for name in ("simplify", "max_colors", "group_depth", "work_size", "denoise"):
        v = getattr(args, name, None)
        if v is not None:
            ov[name] = v
    if getattr(args, "vlm_url", None):
        ov["vlm_url"] = args.vlm_url
    if getattr(args, "vlm_model", None):
        ov["vlm_model"] = args.vlm_model
    return load(getattr(args, "preset", None), getattr(args, "config", None), **ov)


def _sidecar(src: Path, cfg: Config) -> Config:
    """IMG.plate.json next to the image overrides levers for that image."""
    sc = src.with_suffix(".plate.json")
    if sc.exists():
        return cfg.merged(**json.loads(sc.read_text()))
    return cfg


def _run_one(src: Path, dst: Path, cfg: Config, report: bool = False, quiet: bool = False) -> dict:
    from . import metrics, pipeline
    cfg = _sidecar(src, cfg)
    res = pipeline.run(src, cfg)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(res.svg, encoding="utf-8")
    m = metrics.analyze_svg(res.svg)
    fid = None
    try:
        from .raster import have_renderer
        if have_renderer():
            from .imageio import open_rgba
            rgba = np.asarray(open_rgba(src))
            fid = metrics.fidelity(res.svg, rgba)
    except Exception:                                   # noqa: BLE001
        pass
    if report:
        from . import report as rep
        dst.with_suffix(".report.html").write_text(rep.build(src, res, m, fid), encoding="utf-8")
    if not quiet:
        s = res.stats
        print(f"{src.name} -> {dst}  shapes={m['shapes']} anchors={m['anchors']} "
              f"({m['anchors_per_shape']}/shape) primitives={int(m['primitive_ratio']*100)}% "
              f"completed={s['completed']} {s['t_total']:.1f}s" + (f" ssim={fid.get('ssim')}" if fid else ""))
    return {**m, **(fid or {}), "time": round(res.stats["t_total"], 2)}


def _trace(args) -> int:
    src = Path(args.input)
    if not src.exists():
        print(f"plate: no such file: {src}", file=sys.stderr)
        return 2
    dst = Path(args.output) if args.output else src.with_suffix(".svg")
    if args.baseline:
        from .baseline import trace_baseline
        trace_baseline(src, dst, _cfg(args))
        print(f"baseline (VTracer only) -> {dst}")
        return 0
    _run_one(src, dst, _cfg(args), report=args.report)
    return 0


def _batch(args) -> int:
    src, out = Path(args.input), Path(args.output)
    files = sorted(p for p in src.rglob("*") if p.suffix.lower() in IMG_EXT)
    if not files:
        print(f"plate: no images in {src}", file=sys.stderr)
        return 2
    cfg = _cfg(args)
    failed = 0
    for f in files:
        try:
            _run_one(f, out / f.relative_to(src).with_suffix(".svg"), cfg, report=args.report)
        except Exception as e:                          # noqa: BLE001
            failed += 1
            print(f"{f.name}: FAILED ({e})", file=sys.stderr)
    print(f"plate: batch complete: {len(files) - failed} succeeded, {failed} failed",
          file=sys.stderr if failed else sys.stdout)
    return 1 if failed else 0


def _sweep(args) -> int:
    """Trace one image at several values of one lever and tabulate the trade-off."""
    src = Path(args.input)
    key = args.lever.replace("-", "_")
    base = _cfg(args)
    fields = {f.name: f for f in dataclasses.fields(Config)}
    if key not in fields:
        raise SystemExit(f"plate: unknown lever {key!r}")
    out = Path(args.output or f"{src.stem}_sweep")
    print(f"{key:>14} | shapes anchors /shape  prim%  ssim    mae")
    for raw in args.values:
        cfg = base.merged(**{key: _coerce(fields[key], raw)})
        m = _run_one(src, out / f"{src.stem}_{key}={raw}.svg", cfg, quiet=True)
        print(f"{raw:>14} | {m['shapes']:6} {m['anchors']:7} {m['anchors_per_shape']:6} "
              f"{m['primitive_ratio']*100:5.0f}  {m.get('ssim', '-')!s:7} {m.get('mae', '-')}")
    print(f"SVGs in {out}/")
    return 0


def _bench(args) -> int:
    """Compare PLATE against the plain-VTracer control on a folder of images."""
    from . import metrics
    from .baseline import trace_baseline
    from .raster import have_renderer
    files = sorted(p for p in Path(args.input).iterdir() if p.suffix.lower() in IMG_EXT)
    cfg = _cfg(args)
    out = Path(args.output or "bench_out")
    print(f"{'image':18} {'engine':8} {'shapes':>6} {'anchors':>7} {'/shape':>6} {'prim%':>5} {'named%':>6} {'ssim':>6}")
    from .imageio import open_rgba
    for f in files:
        rgba = np.asarray(open_rgba(f))
        rows = {}
        rows["plate"] = _run_one(f, out / f"{f.stem}.plate.svg", cfg, quiet=True)
        base_svg = out / f"{f.stem}.vtracer.svg"
        trace_baseline(f, base_svg, cfg)
        text = base_svg.read_text()
        rows["vtracer"] = {**metrics.analyze_svg(text),
                           **(metrics.fidelity(text, rgba) if have_renderer() else {})}
        for eng, m in rows.items():
            print(f"{f.stem:18} {eng:8} {m['shapes']:6} {m['anchors']:7} {m['anchors_per_shape']:6} "
                  f"{m['primitive_ratio']*100:5.0f} {(1-m['unnamed_ratio'])*100:6.0f} {m.get('ssim', '-')!s:>6}")
    return 0


def _corpus(args) -> int:
    from .bakeoff.corpus import make_corpus
    paths = make_corpus(Path(args.output), n=args.n, seed=args.seed)
    print(f"{len(paths)} scenes -> {args.output}/images (ground truth in {args.output}/truth)")
    return 0


def _bakeoff(args) -> int:
    from .bakeoff import adapters, runner
    tools = [t.strip() for t in args.tools.split(",") if t.strip()]
    bad = [t for t in tools if t not in adapters.BUILTIN]
    if bad:
        raise SystemExit(f"plate: unknown tool(s) {bad}. Built in: {', '.join(adapters.BUILTIN)}")
    out = Path(args.output)
    summ = runner.run(Path(args.images), out, tools, Path(args.truth) if args.truth else None,
                      Path(args.external) if args.external else None, runner.load_weights(args.weights),
                      log=(lambda m: None) if args.quiet else print)
    print(f"\n{'tool':16} {'composite':>9}  anchors/shape  time")
    for s in summ:
        print(f"{s['tool']:16} {s['composite']:9.3f}  {s['raw'].get('anchors_per_shape', 0):13.1f}  {s['seconds']:.1f}s")
    print(f"\nreport: {out / 'report.html'}   data: {out / 'results.csv'}")
    return 0


def _doctor(args) -> int:
    ok = True
    for mod, need in (("numpy", 1), ("PIL", 1), ("scipy", 1), ("cv2", 1), ("skimage", 1),
                      ("vtracer", 0)):
        try:
            __import__(mod); print(f"  ok        {mod}")
        except ImportError:
            print(f"  {'MISSING ' if need else 'optional'}  {mod}"); ok &= not need
        except Exception as e:                          # noqa: BLE001
            print(f"  {'BROKEN  ' if need else 'optional'}  {mod} ({type(e).__name__}: "
                  f"{str(e).splitlines()[0]})"); ok &= not need
    # cairosvg is special: it may import yet fail to load libcairo at render time,
    # so probe through the renderer helper (which preloads cairo on macOS).
    try:
        import importlib.util
        from .raster import have_renderer
        if have_renderer():
            print("  ok        cairosvg (renderer ready)")
        elif importlib.util.find_spec("cairosvg") is None:
            print("  optional  cairosvg not installed (pip install 'plate-svg[render]'); "
                  "enables SSIM in bench/sweep and --report")
        else:
            print("  optional  cairosvg installed but libcairo not found (brew install cairo)")
    except Exception as e:                              # noqa: BLE001
        print(f"  optional  cairosvg not usable ({type(e).__name__})")
    url = getattr(args, "vlm_url", None) or "http://localhost:1234/v1"
    try:
        from . import vlm
        print(f"  ok        LM Studio at {url}: {', '.join(vlm.list_models(url)) or 'no models loaded'}")
    except Exception as e:                              # noqa: BLE001
        print(f"  optional  LM Studio at {url} not reachable ({e}); start its server for semantic names")
    return 0 if ok else 1


def _common(p):
    p.add_argument("--preset", choices=sorted(PRESETS))
    p.add_argument("--config", type=Path, help="TOML file with any lever")
    p.add_argument("--set", action="append", metavar="LEVER=VALUE", help="set any lever (repeatable)")
    p.add_argument("--simplify", type=float)
    p.add_argument("--max-colors", type=int, dest="max_colors")
    p.add_argument("--group-depth", type=int, dest="group_depth")
    p.add_argument("--work-size", type=int, dest="work_size")
    p.add_argument("--denoise", type=int, help="-1 auto, 0 off, N bilateral passes")
    p.add_argument("--vlm-url", dest="vlm_url", help="e.g. http://localhost:1234/v1 (LM Studio)")
    p.add_argument("--vlm-model", dest="vlm_model")


def _ensure_renderer_env() -> None:
    """On macOS, re-exec once with DYLD_FALLBACK_LIBRARY_PATH pointing at the
    Homebrew cairo dir so cairosvg can load libcairo (SIP strips DYLD_* across
    protected binaries, so it must be present at process start). Guarded by
    PLATE_DYLD_REEXEC to avoid looping; silently skips if cairo isn't installed."""
    import os
    import sys
    if sys.platform != "darwin" or os.environ.get("PLATE_DYLD_REEXEC"):
        return
    from .raster import cairo_lib_dirs, ensure_dyld_cairo
    if ensure_dyld_cairo():
        return
    dirs = cairo_lib_dirs()
    if not dirs:
        return
    cur = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join([*dirs, cur]) if cur else ":".join(dirs)
    os.environ["PLATE_DYLD_REEXEC"] = "1"
    try:
        os.execv(sys.executable, [sys.executable, "-m", "plate", *sys.argv[1:]])
    except OSError:
        pass  # re-exec failed; carry on without the renderer


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        _ensure_renderer_env()
    p = argparse.ArgumentParser(prog="plate", description="Layered, primitive-aware raster-to-SVG for Illustrator.")
    p.add_argument("--version", action="version", version=f"plate {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trace", help="convert one image to a layered SVG")
    t.add_argument("input"); t.add_argument("-o", "--output")
    t.add_argument("--report", action="store_true", help="also write IMG.report.html")
    t.add_argument("--baseline", action="store_true", help="plain VTracer (control)")
    _common(t); t.set_defaults(fn=_trace)

    b = sub.add_parser("batch", help="convert a folder of images"); b.add_argument("input")
    b.add_argument("-o", "--output", required=True); b.add_argument("--report", action="store_true")
    _common(b); b.set_defaults(fn=_batch)

    s = sub.add_parser("sweep", help="try one lever at several values and tabulate")
    s.add_argument("input"); s.add_argument("lever"); s.add_argument("values", nargs="+")
    s.add_argument("-o", "--output"); _common(s); s.set_defaults(fn=_sweep)

    be = sub.add_parser("bench", help="PLATE vs plain VTracer on a folder (editability + fidelity)")
    be.add_argument("input"); be.add_argument("-o", "--output"); _common(be); be.set_defaults(fn=_bench)

    co = sub.add_parser("corpus", help="generate a synthetic bake-off corpus with exact ground truth")
    co.add_argument("-o", "--output", required=True); co.add_argument("-n", type=int, default=24)
    co.add_argument("--seed", type=int, default=1); co.set_defaults(fn=_corpus)

    bk = sub.add_parser("bakeoff", help="score PLATE and other tools objectively on a folder of images")
    bk.add_argument("images"); bk.add_argument("-o", "--output", required=True)
    bk.add_argument("--truth", help="folder from `plate corpus` (…/truth) to enable structure scoring")
    bk.add_argument("--external", help="folder of IMAGE.TOOL.svg exports from other tools (Illustrator, Vectorizer.AI…)")
    bk.add_argument("--tools", default="plate,vtracer,vtracer-cutout,potrace-color")
    bk.add_argument("--weights", type=Path, help="TOML overriding metric weights")
    bk.add_argument("--quiet", action="store_true"); bk.set_defaults(fn=_bakeoff)

    d = sub.add_parser("doctor", help="check dependencies and LM Studio")
    d.add_argument("--vlm-url", dest="vlm_url"); d.set_defaults(fn=_doctor)

    args = p.parse_args(argv)
    from .imageio import ImageLoadError
    try:
        return args.fn(args)
    except ImageLoadError as e:
        print(f"plate: {e}", file=sys.stderr)
        return 2
    except OSError as e:          # unwritable output dir, disk full, permission denied
        print(f"plate: {e.strerror or e}: {e.filename or ''}".rstrip(": "), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("plate: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
