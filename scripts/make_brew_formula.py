"""Generate the Homebrew formula (Formula/plate.rb in Digital-Defiance/homebrew-tap).

    python scripts/make_brew_formula.py URL SHA256 [-o plate.rb] [--python 3.14]

URL/SHA256 are the release tarball (GitHub tag archive). Runtime dependencies are
installed from prebuilt PyPI wheels pinned below: building numpy/scipy/scikit-image/
opencv from source is slow and fragile, and Homebrew's opencv pulls Qt, VTK and FFmpeg
into a headless CLI. To refresh the pins, install the release in a clean venv
(`pip install .[render]`), copy `pip freeze` versions into PINS, and regenerate.
Needs network access to pypi.org. Checks that every pin has a wheel for both macOS
architectures and the chosen CPython, and reports the minimum macOS they require.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

# Runtime closure of `plate-svg[render]`, at the versions the test suite runs against.
PINS = {
    "numpy": "2.4.6", "scipy": "1.17.1", "opencv-python-headless": "5.0.0.93",
    "pillow": "13.0.0", "scikit-image": "0.26.0", "vtracer": "0.6.15",
    "networkx": "3.6.1", "imageio": "2.38.1", "tifffile": "2026.3.3",
    "lazy-loader": "0.6", "packaging": "26.3",
    "cairosvg": "2.9.1", "cairocffi": "1.7.1", "cffi": "2.1.1", "pycparser": "3.12",
    "cssselect2": "0.10.1", "tinycss2": "1.5.1", "webencodings": "0.6.1", "defusedxml": "0.7.1",
}
# Build backend for PLATE itself (pip runs offline, without build isolation).
BUILD = {"hatchling": "1.33.0", "pathspec": "1.1.1", "pluggy": "1.7.0",
         "trove-classifiers": "2026.9.21.13", "tomlkit": "0.15.2"}
MACOS = {(13, 0): ":ventura", (14, 0): ":sonoma", (15, 0): ":sequoia"}


def _files(name: str, version: str) -> list[dict]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=30) as r:
        return json.load(r)["urls"]


def _pick(name: str, version: str, arch: str | None, cp: str) -> tuple[dict, tuple[int, int]] | None:
    """Best wheel: pure if arch is None, else an arch-specific macOS wheel (lowest min OS)."""
    best = None
    for f in _files(name, version):
        fn = f["filename"]
        if not fn.endswith(".whl"):
            continue
        py, abi, plat = fn[:-4].split("-")[-3:]
        if arch is None:
            if plat == "any":
                return f, (0, 0)
            continue
        if plat == "any":
            continue
        cps = [int(t[2:]) for t in py.split(".") if t.startswith("cp")]
        if not (int(cp) in cps or (abi == "abi3" and cps and min(cps) <= int(cp))):
            continue
        mins = [(int(m[1]), int(m[2])) for m in (re.match(r"macosx_(\d+)_(\d+)_(\w+)", p)
                                               for p in plat.split(".")) if m and m[3] in (arch, "universal2")]
        if not mins:
            continue
        key = ("universal2" in fn, min(mins))
        if best is None or key < best[0]:
            best = (key, f, min(mins))
    return (best[1], best[2]) if best else None


def _resource(name: str, f: dict, indent: int) -> str:
    p = " " * indent
    return f'{p}resource "{name}" do\n{p}  url "{f["url"]}"\n{p}  sha256 "{f["digests"]["sha256"]}"\n{p}end\n'


def render(url: str, sha: str, python: str = "3.14") -> str:
    cp = python.replace(".", "")
    pure, per_arch, floor = [], [], {"arm64": (0, 0), "x86_64": (0, 0)}
    for name, version in PINS.items():
        p = _pick(name, version, None, cp)
        if p:
            pure.append((name, p[0]))
            continue
        wheels = {}
        for arch in floor:
            got = _pick(name, version, arch, cp)
            if got is None:
                sys.exit(f"no cp{cp} macOS {arch} wheel for {name}=={version}")
            wheels[arch] = got[0]
            floor[arch] = max(floor[arch], got[1])
        per_arch.append((name, wheels))
    build = []
    for name, version in BUILD.items():
        p = _pick(name, version, None, cp)
        if p is None:
            sys.exit(f"no pure wheel for build dependency {name}=={version}")
        build.append((name, p[0]))

    def floor_symbol(v):
        return next(sym for ver, sym in sorted(MACOS.items()) if ver >= v)

    out = [
        "class Plate < Formula\n  include Language::Python::Virtualenv\n\n",
        '  desc "Raster-to-SVG with editable layers, primitives, strokes and gradients"\n',
        '  homepage "https://github.com/Digital-Defiance/PLATE"\n',
        f'  url "{url}"\n  sha256 "{sha}"\n  license "MIT"\n',
        '  head "https://github.com/Digital-Defiance/PLATE.git", branch: "main"\n\n',
        '  depends_on "cairo" # SVG rendering for --report, bench and sweep SSIM\n',
        "  depends_on :macos\n",
        f'  depends_on "python@{python}"\n\n',
        "  # Prebuilt PyPI wheels pinned to the versions PLATE's test suite runs against\n"
        "  # (regenerate with scripts/make_brew_formula.py in the PLATE repo).\n",
    ]
    for block, arch in (("on_arm", "arm64"), ("on_intel", "x86_64")):
        out.append(f"  {block} do\n    depends_on macos: {floor_symbol(floor[arch])}\n\n")
        out.append("\n".join(_resource(n, w[arch], 4) for n, w in per_arch))
        out.append("  end\n\n")
    out.append("  # Prebuilt wheels name their extension modules @rpath/...; vtracer's has no\n"
               "  # Mach-O header padding, so rewriting its ID to an absolute path fails.\n"
               "  preserve_rpath\n\n")
    out.append("\n".join(_resource(n, f, 2) for n, f in pure) + "\n")
    out.append("  # Build backend for PLATE itself (pip runs without network or build isolation).\n")
    out.append("\n".join(_resource(n, f, 2) for n, f in build))
    out.append(f'''
  def install
    python = formula_opt_bin("python@{python}")/"python{python}"
    venv = virtualenv_create(libexec, python, system_site_packages: false)
    wheels = buildpath/"wheels"
    wheels.mkpath
    # pip reads a wheel's tags from its filename, so restore the canonical name.
    resources.each {{ |r| cp r.cached_download, wheels/File.basename(URI(r.url).path) }}
    pip = [python, "-m", "pip", "--python=#{{venv.root}}/bin/python", "install",
           "--no-deps", "--no-index", "--find-links=#{{wheels}}", "--no-compile"]
    system(*pip, *wheels.children.map(&:to_s))
    system(*pip, "--no-build-isolation", buildpath)
    bin.install_symlink libexec/"bin/plate"
  end

  test do
    assert_match version.to_s, shell_output("#{{bin}}/plate --version")
    system libexec/"bin/python", "-c", <<~PYTHON
      from PIL import Image, ImageDraw
      im = Image.new("RGB", (96, 64), "white")
      ImageDraw.Draw(im).rectangle([12, 10, 60, 46], fill=(200, 40, 40))
      im.save("in.png")
    PYTHON
    system bin/"plate", "trace", "in.png", "-o", "out.svg"
    svg = (testpath/"out.svg").read
    assert_match "<rect", svg
    assert_match "#c82828", svg
    assert_match "renderer ready", shell_output("#{{bin}}/plate doctor --vlm-url http://127.0.0.1:9/v1")
    assert_match "not a recognised image", shell_output("#{{bin}}/plate trace #{{test_fixtures("test.svg")}} 2>&1", 2)
  end
end
''')
    print(f"cp{cp}: {len(per_arch)} per-arch wheels (min macOS arm64 {floor['arm64']}, "
          f"x86_64 {floor['x86_64']}), {len(pure)} pure, {len(build)} build", file=sys.stderr)
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url"); ap.add_argument("sha256")
    ap.add_argument("-o", "--output", default="plate.rb")
    ap.add_argument("--python", default="3.14")
    a = ap.parse_args()
    with open(a.output, "w") as fh:
        fh.write(render(a.url, a.sha256, a.python))
    print(a.output, file=sys.stderr)


if __name__ == "__main__":
    main()
