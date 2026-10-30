"""Packaging guards: a plain `pip install plate-svg` (and the Homebrew formula, which
installs the same dependency set) must be able to run the core pipeline.

Regression: scikit-image was only listed under the optional `render` extra although
`plate.geometry` imports it at module level, so a no-extras install failed on the
first trace with ModuleNotFoundError: No module named 'skimage'.
"""
import ast
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

import plate

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "plate"
# Imported only inside functions on optional paths (rendering/metrics, SAM, VLM).
OPTIONAL = {"cairosvg", "torch", "transformers"}


def _module_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in tree.body:                      # module level only, not inside functions
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Try):         # try: import tomllib / except: import tomli
            for sub in ast.walk(node):
                if isinstance(sub, ast.Import):
                    names |= {a.name.split(".")[0] for a in sub.names}
    return names


def _declared() -> set[str]:
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())
    out = set()
    for req in meta["project"]["dependencies"]:
        out.add(req.split(";")[0].split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower())
    return out


def test_every_third_party_module_level_import_is_a_core_dependency():
    stdlib = set(sys.stdlib_module_names)
    mapping = packages_distributions()
    declared = _declared()
    missing = {}
    for path in SRC.rglob("*.py"):
        for mod in _module_level_imports(path):
            if mod in stdlib or mod == "plate" or mod in OPTIONAL or mod in ("tomli",):
                continue
            dists = {d.lower() for d in mapping.get(mod, [mod])}
            if not dists & declared:
                missing.setdefault(mod, []).append(str(path.relative_to(ROOT)))
    assert not missing, f"imported at module level but not in [project].dependencies: {missing}"


def test_version_strings_agree():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert plate.__version__ == meta["project"]["version"]


def test_console_script_points_at_cli_main():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert meta["project"]["scripts"]["plate"] == "plate.cli:main"
