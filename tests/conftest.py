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
