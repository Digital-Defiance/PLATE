"""Repo-root pytest bootstrap.

On macOS, cairocffi's dlopen does not search Homebrew's lib dir, and SIP strips
DYLD_* from the environment inherited across protected binaries, so the renderer
path (cairosvg, used by the bake-off/metrics tests) only loads when
DYLD_FALLBACK_LIBRARY_PATH includes the Homebrew cairo dir *before* the Python
process starts. The `plate` CLI already re-execs itself once with that var set
(see ``plate.cli._ensure_renderer_env`` / ``plate.raster.ensure_dyld_cairo``);
this hook does the same for a bare ``pytest`` invocation so contributors don't
have to remember the prefix. Without it, the bake-off tests fail with
``OSError: no library called "cairo-2"`` on a stock macOS checkout.

Guarded by ``PLATE_PYTEST_DYLD_REEXEC`` so it re-execs at most once, and a no-op
when cairo is already discoverable, when cairo is not installed, or off macOS.
"""
import os
import sys


def _ensure_dyld_cairo_for_pytest() -> None:
    if sys.platform != "darwin" or os.environ.get("PLATE_PYTEST_DYLD_REEXEC"):
        return
    try:
        # Reuse the engine's own detection so the two stay in lockstep.
        from plate.raster import cairo_lib_dirs, ensure_dyld_cairo
    except Exception:  # noqa: BLE001 - plate not importable yet; nothing to do
        return
    if ensure_dyld_cairo():
        return  # already on the path, or no cairo to point at
    dirs = cairo_lib_dirs()
    if not dirs:
        return
    current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
        ":".join([*dirs, current]) if current else ":".join(dirs)
    )
    os.environ["PLATE_PYTEST_DYLD_REEXEC"] = "1"
    # Re-exec this exact pytest invocation with the var now set at process start.
    os.execv(sys.executable, [sys.executable, "-m", "pytest", *sys.argv[1:]])


_ensure_dyld_cairo_for_pytest()
