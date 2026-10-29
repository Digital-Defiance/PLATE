import subprocess, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def samples():
    d = ROOT / "samples"
    if not (d / "overlap.png").exists():
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "make_samples.py")], cwd=ROOT)
    return d


@pytest.fixture(scope="session")
def controls_dir():
    """Directory of CONTROL images; (re)generated if any expected image is missing."""
    from controls import CONTROLS
    d = ROOT / "samples" / "controls"
    missing = [n for n in CONTROLS if not (d / f"{n}.png").exists()]
    if missing:
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "make_controls.py"), str(d)], cwd=ROOT
        )
    return d
