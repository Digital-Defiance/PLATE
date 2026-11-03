"""Lint/validation guard for the GitHub Pages deploy workflow (task 15.1,
`.github/workflows/deploy-web.yml`).

The deploy config is split across four files that must agree or the live page
silently breaks:

* `.github/workflows/deploy-web.yml`   — builds the wheel, bundles /web, publishes
* `web/src/worker.ts`                  — fetches the wheel by exact filename, pins Pyodide
* `web/package.json`                   — pins the `pyodide` devDependency
* `pyproject.toml`                     — the package name/version that names the wheel

This test parses the workflow and asserts it is well-formed and self-consistent
with those sources, so the deploy invariants cannot drift unnoticed:

  - the workflow YAML parses;
  - the published wheel filename == the worker's PLATE_WHEEL_URL ==
    pyproject's `{name}-{version}` (a rename would 404 the wheel at runtime);
  - the Pyodide version pinned in the worker == the `pyodide` devDependency
    (Requirement 11.3 — a float/mismatch is a bug);
  - permissions are least-privilege and present, `deploy` needs `build`, the
    build job has a timeout, every action/tool is pinned (no @main/floating);
  - the triggers and the `/web` source folder match the design.

Covers task 15.2. Validates: Requirements 11.2, 11.3 (and the 11.1/11.4/11.5
structure the workflow encodes).
"""
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-web.yml"
WORKER_TS = ROOT / "web" / "src" / "worker.ts"
PACKAGE_JSON = ROOT / "web" / "package.json"
PYPROJECT = ROOT / "pyproject.toml"


# --------------------------------------------------------------------------- #
# Loaders / small parsers (fixtures keep each test focused on one invariant)   #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def workflow() -> dict:
    """The parsed deploy workflow. `yaml.safe_load` parses the `on:` key as the
    Python boolean True, so normalise it back to the string "on" for lookups."""
    assert WORKFLOW.is_file(), f"missing deploy workflow: {WORKFLOW}"
    doc = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(doc, dict), "workflow did not parse to a mapping"
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    return doc


@pytest.fixture(scope="module")
def worker_src() -> str:
    assert WORKER_TS.is_file(), f"missing worker source: {WORKER_TS}"
    return WORKER_TS.read_text()


def _const(src: str, name: str) -> str:
    """Return the string literal assigned to `const <name> = "...";`."""
    m = re.search(rf'\b{name}\s*=\s*["\']([^"\']+)["\']', src)
    assert m, f"could not find const {name} in worker.ts"
    return m.group(1)


def _wheel_filename_from_worker(src: str) -> str:
    """The relative wheel URL the worker installs, e.g. ./plate_svg-0.1.0-...whl."""
    m = re.search(r'new URL\(\s*["\']\./([^"\']+\.whl)["\']', src)
    assert m, "could not find PLATE_WHEEL_URL wheel path in worker.ts"
    return m.group(1)


def _expected_wheel_name() -> str:
    meta = tomllib.loads(PYPROJECT.read_text())
    name = meta["project"]["name"].replace("-", "_")
    version = meta["project"]["version"]
    return f"{name}-{version}-py3-none-any.whl"


def _all_steps(workflow: dict) -> list[dict]:
    steps: list[dict] = []
    for job in workflow["jobs"].values():
        steps.extend(job.get("steps", []))
    return steps


# --------------------------------------------------------------------------- #
# The YAML is well-formed                                                      #
# --------------------------------------------------------------------------- #
def test_workflow_yaml_parses(workflow):
    assert workflow.get("name")
    assert "jobs" in workflow and {"build", "deploy"} <= set(workflow["jobs"])


# --------------------------------------------------------------------------- #
# Highest-value cross-file invariant: the wheel filename agrees everywhere     #
# (a rename would silently 404 the wheel in the browser at runtime).           #
# --------------------------------------------------------------------------- #
def test_published_wheel_name_matches_worker_and_pyproject(workflow, worker_src):
    expected = _expected_wheel_name()

    # pyproject's name/version produce the expected filename.
    assert expected == "plate_svg-0.1.0-py3-none-any.whl"

    # The worker fetches exactly that filename.
    assert _wheel_filename_from_worker(worker_src) == expected

    # The workflow builds/copies exactly that filename (it appears verbatim in
    # the assemble step).
    text = WORKFLOW.read_text()
    assert expected in text, (
        f"workflow never names the published wheel {expected!r}; a rename here "
        "would break the worker's same-origin wheel URL"
    )


# --------------------------------------------------------------------------- #
# Requirement 11.3: pinned Pyodide version agrees between worker and package   #
# --------------------------------------------------------------------------- #
def test_pyodide_version_pinned_and_consistent(worker_src):
    worker_pin = _const(worker_src, "PYODIDE_VERSION")
    meta = _load_json(PACKAGE_JSON)
    dep_pin = meta["devDependencies"]["pyodide"]

    # Exact pins (no ^, ~, *, ranges) on both sides.
    assert re.fullmatch(r"\d+\.\d+\.\d+", worker_pin), f"worker Pyodide not exact: {worker_pin}"
    assert re.fullmatch(r"\d+\.\d+\.\d+", dep_pin), f"package.json pyodide not exact: {dep_pin}"
    assert worker_pin == dep_pin, (
        f"Pyodide pin drift: worker.ts={worker_pin} vs package.json={dep_pin} "
        "(Requirement 11.3)"
    )


def _load_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# Requirement 11.2: a build failure must never reach publish                   #
# --------------------------------------------------------------------------- #
def test_deploy_needs_build_so_build_failure_aborts_publish(workflow):
    deploy = workflow["jobs"]["deploy"]
    needs = deploy.get("needs")
    needs = [needs] if isinstance(needs, str) else list(needs or [])
    assert "build" in needs, (
        "deploy must `needs: build` so a failed wheel build never uploads the "
        "artifact and the live site is preserved (Requirement 11.2)"
    )
    # Deploy is the job that actually publishes; the artifact upload lives in build.
    build_steps = workflow["jobs"]["build"].get("steps", [])
    uploads = [s for s in build_steps if "upload-pages-artifact" in str(s.get("uses", ""))]
    assert uploads, "build job must upload the Pages artifact before deploy consumes it"
    deploy_steps = workflow["jobs"]["deploy"].get("steps", [])
    assert any("deploy-pages" in str(s.get("uses", "")) for s in deploy_steps), (
        "deploy job must run actions/deploy-pages"
    )


# --------------------------------------------------------------------------- #
# Requirement 11.4: a build-and-publish timeout exists                         #
# --------------------------------------------------------------------------- #
def test_build_job_has_15_minute_timeout(workflow):
    assert workflow["jobs"]["build"].get("timeout-minutes") == 15, (
        "build job must cap at 15 minutes (Requirement 11.4)"
    )


# --------------------------------------------------------------------------- #
# Least-privilege permissions are present and nothing broader is granted       #
# --------------------------------------------------------------------------- #
def test_permissions_are_least_privilege(workflow):
    perms = workflow.get("permissions")
    assert isinstance(perms, dict), "top-level permissions block must be present"
    assert perms == {"contents": "read", "pages": "write", "id-token": "write"}, (
        f"permissions are not least-privilege for a Pages deploy: {perms}"
    )


# --------------------------------------------------------------------------- #
# Concurrency guard so overlapping deploys do not clobber each other           #
# --------------------------------------------------------------------------- #
def test_concurrency_group_present(workflow):
    conc = workflow.get("concurrency")
    assert isinstance(conc, dict) and conc.get("group"), (
        "a concurrency group is required so overlapping Pages deploys serialise"
    )


# --------------------------------------------------------------------------- #
# Requirement 11.3 (pinning): no action may float on a branch/@main            #
# --------------------------------------------------------------------------- #
def test_all_actions_are_pinned(workflow):
    floating = []
    for step in _all_steps(workflow):
        uses = step.get("uses")
        if not uses:
            continue
        assert "@" in uses, f"action is not version-pinned: {uses}"
        ref = uses.split("@", 1)[1]
        # A tag (v4) or a 40-char SHA is pinned; a branch like main/master is not.
        if ref in {"main", "master", "latest", "HEAD"}:
            floating.append(uses)
    assert not floating, f"actions must be pinned, not floating on a branch: {floating}"


# --------------------------------------------------------------------------- #
# Pinned tool versions (env block) are exact, not floating                     #
# --------------------------------------------------------------------------- #
def test_tool_versions_are_exact(workflow):
    env = workflow.get("env", {})
    for key in ("NODE_VERSION", "PYTHON_VERSION", "UV_VERSION"):
        assert key in env, f"missing pinned tool version {key}"
        value = str(env[key])
        assert re.fullmatch(r"\d+(\.\d+){1,2}", value), (
            f"{key} must be an exact version, got {value!r}"
        )


# --------------------------------------------------------------------------- #
# Requirements 11.1 / 11.5: triggers and the /web source folder match design   #
# --------------------------------------------------------------------------- #
def test_triggers_and_web_source(workflow):
    on = workflow["on"]
    assert "workflow_dispatch" in on, "an owner-triggered redeploy must be allowed"
    push = on.get("push")
    assert isinstance(push, dict), "must trigger on push"
    assert "main" in push.get("branches", []), "must redeploy on push to the default branch"

    # The shell is built and deployed from /web (Requirement 11.5): the build
    # job works in web/ and uploads web/dist.
    build = workflow["jobs"]["build"]
    workdirs = [s.get("working-directory") for s in build.get("steps", [])]
    assert "web" in workdirs, "build steps must run in the web/ folder (Requirement 11.5)"
    upload = next(
        s for s in build["steps"] if "upload-pages-artifact" in str(s.get("uses", ""))
    )
    assert upload.get("with", {}).get("path") == "web/dist", (
        "the Pages artifact must be the bundled web/dist directory"
    )
