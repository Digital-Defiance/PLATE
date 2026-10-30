# Releasing PLATE and updating the Homebrew tap

PLATE ships to macOS users through the Digital Defiance tap
(`/Volumes/Code/homebrew-tap`, GitHub `Digital-Defiance/homebrew-tap`):

```sh
brew tap digital-defiance/tap
brew install plate
```

The formula installs PLATE into a private virtualenv using Homebrew's `python@3.14`,
with its dependencies as pinned prebuilt PyPI wheels, and depends on Homebrew `cairo`
so `--report`, `bench` and `sweep` can render SVGs. It requires macOS 13+ on Apple
Silicon and 14+ on Intel (the opencv-python-headless wheel sets that floor).

Why wheels rather than Homebrew's numpy/scipy/opencv formulae: those build against
`python@3.15`, for which numpy, scipy, scikit-image and vtracer publish no wheels
yet, and Homebrew's `opencv` pulls in Qt, VTK, FFmpeg and OpenVINO (108 dependencies)
for what is a headless CLI. The installed keg is about 313 MB.

## Cut a release

1. `pytest -q` green with the renderer on (see AGENTS.md); both benches inspected.
2. Bump the version in `pyproject.toml` and `src/plate/__init__.py` (the packaging
   test asserts they agree). Commit.
3. Check a clean, extras-free install still works:
   `python3.11 -m venv /tmp/v && /tmp/v/bin/pip install . && /tmp/v/bin/plate trace samples/overlap.png -o /tmp/o.svg`
4. Tag and push: `git tag -s vX.Y.Z -m "PLATE X.Y.Z" && git push origin main vX.Y.Z`.
5. Hash GitHub's tag archive (download it; do not hash a local `git archive`):
   ```sh
   URL=https://github.com/Digital-Defiance/PLATE/archive/refs/tags/vX.Y.Z.tar.gz
   curl -sL "$URL" | shasum -a 256
   ```
6. Generate the formula (needs pypi.org access):
   ```sh
   .venv/bin/python scripts/make_brew_formula.py "$URL" <sha256> -o /Volumes/Code/homebrew-tap/Formula/plate.rb
   ```
   If dependency versions changed, update `PINS` in the script first from
   `pip freeze` of a clean `pip install '.[render]'` venv that passed the test suite.
7. Verify from the tap working copy before pushing it:
   ```sh
   cd /Volumes/Code/homebrew-tap
   brew style Formula/plate.rb
   HOMEBREW_NO_INSTALL_FROM_API=1 brew install --build-from-source ./Formula/plate.rb   # or via a local tap
   brew test plate && brew audit --strict plate
   ```
   `brew audit` reports a flat-namespace warning for three dylibs bundled inside the
   upstream opencv wheel (`libb2`, `libtheoradec`, `libtheoraenc`). It is not caused
   by PLATE and does not affect it.
8. Commit `Formula/plate.rb` (and the README entry) in the tap and push.

## Formula notes

- `preserve_rpath` is required: Homebrew rewrites each Mach-O's `@rpath` ID to an
  absolute path, and vtracer's extension module has no header padding for that.
- Binary wheels are copied from each resource's `cached_download` to their canonical
  filename because Homebrew would otherwise unzip them during `stage`.
- PLATE builds offline with `--no-build-isolation`; hatchling and its four helpers are
  pure-wheel resources for that reason.
