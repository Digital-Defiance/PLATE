"""Opt-in per-object diagnostic report for authored challenges.

Run from the ``tests/`` directory with the worktree ``src`` on ``PYTHONPATH``::

    python -m challenge_report complex_mission_patch
    python -m challenge_report --all

For each named challenge it runs the PLATE pipeline on the sample PNG, loads the
authored ``.target.svg``, computes the full per-object diff with
``challenge_diff.diff_target`` and prints the readable table plus the
machine-readable JSON. It is NOT collected by pytest (no ``test_`` functions) so
it cannot change suite pass/skip/xfail counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1] / "samples" / "challenges"


def _challenge_names():
    from challenges import CHALLENGES
    return list(CHALLENGES)


def report(name: str) -> int:
    from plate import pipeline
    from plate.config import Config

    from challenge_diff import diff_target

    image = DIRECTORY / f"{name}.png"
    target_path = DIRECTORY / f"{name}.target.svg"
    if not image.exists() or not target_path.exists():
        print(f"== {name}: missing sample or target, skipping ==")
        return 1
    result = pipeline.run(image, Config())
    diff = diff_target(result.svg, target_path.read_text())
    print(f"== {name} ==")
    print(diff.summary())
    print(json.dumps(diff.to_dict(), indent=2, sort_keys=True))
    print()
    return 0


def main(argv) -> int:
    from plate.raster import have_renderer

    if not have_renderer():
        print("challenge_report requires the render extra and libcairo "
              "(cairosvg not importable); nothing rendered.")
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        print("challenges:", ", ".join(_challenge_names()))
        return 0
    names = _challenge_names() if argv[0] == "--all" else argv
    status = 0
    for name in names:
        status |= report(name)
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
