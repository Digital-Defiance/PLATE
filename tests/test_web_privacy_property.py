"""Property 2: Privacy by construction (browser-web-page spec, task 1.8).

The glue module must keep the uploaded image on the device: it leaves NO persisted
file behind after returning (on both the success and the failure paths) and performs
NO network I/O unless LM Studio naming is explicitly enabled via a non-empty
``vlmUrl``.

**Validates: Requirements 8.1, 8.2, 8.3**

Design Property 2 (Privacy by construction):

    ``convert_bytes`` performs no network I/O for the core path; the image bytes
    exist only in the worker and MEMFS and are removed after the call. The only
    outbound request is the optional, explicitly-enabled LM Studio call.

    ``∀ image : network_requests(convert_bytes(bytes(image), name, {})) == ∅``

This test drives the REAL ``plate.web`` functions (never a re-implementation). It
asserts the two halves of the property across randomized inputs and configs:

1. **No persist.** Snapshot the directory ``tempfile`` writes into (the only place
   the CPython glue can leave a file -- MEMFS ``/input.<ext>`` in the browser maps to
   a ``NamedTemporaryFile`` on disk here) before and after every call, and assert no
   new file remains. Additionally capture every path ``NamedTemporaryFile`` actually
   handed out during the call and assert each one is gone afterwards -- this proves
   the specific temp input/decode files created mid-conversion were removed in the
   ``finally``, on both the success path and the ``ImageLoadError``/``ConvertError``
   failure paths.

2. **No network unless vlmUrl is set.** Install tripwires on the lowest-level
   outbound primitives the engine could use (``socket.socket.connect`` and
   ``urllib.request.urlopen``, which ``plate.vlm`` builds on) so ANY outbound attempt
   raises. With no ``vlmUrl`` in the overrides the tripwires must never fire; this
   holds across randomized images, presets and lever maps.
"""
from __future__ import annotations

import io
import os
import socket
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image

from plate import web
from plate.config import PRESETS
from plate.imageio import ImageLoadError


# ---------------------------------------------------------------------------
# helpers: snapshot the temp dir + capture the temp paths the glue creates
# ---------------------------------------------------------------------------
class _NetworkCalled(AssertionError):
    """Raised by a tripwire the instant any outbound network primitive is used."""


def _snapshot(dir_path: Path) -> set[str]:
    """Names present in ``dir_path`` right now (best-effort; the dir always exists)."""
    try:
        return set(os.listdir(dir_path))
    except FileNotFoundError:
        return set()


class _PrivacyHarness:
    """Wrap a call to a real ``plate.web`` function so we can assert, afterwards:

    * no NEW file was left in the system temp dir, and
    * every temp path ``NamedTemporaryFile`` produced during the call was removed, and
    * no outbound network primitive was touched (unless the test opts in).

    The temp-path capture wraps the real ``tempfile.NamedTemporaryFile`` so the glue
    runs unmodified; we only record the names it hands back.
    """

    def __init__(self, monkeypatch, tmp_path, *, allow_network: bool = False):
        self._mp = monkeypatch
        self._allow_network = allow_network
        self.created_paths: list[Path] = []
        self.network_hits: list[str] = []
        # Point the glue's NamedTemporaryFile at a private, initially-empty dir so the
        # before/after snapshot is isolated from any other test writing to the shared
        # system temp dir (tasks 1.6/1.7 run concurrently). The glue calls
        # NamedTemporaryFile without an explicit dir, so it honours tempfile.tempdir.
        self._base = Path(tmp_path)
        self._tmpdir = self._base
        self._before: set[str] = set()

    # -- network tripwires -------------------------------------------------
    def _install_network_tripwires(self):
        real_connect = socket.socket.connect

        def guarded_connect(sock, address, *a, **k):
            self.network_hits.append(f"socket.connect{address!r}")
            if not self._allow_network:
                raise _NetworkCalled(f"unexpected network connect to {address!r}")
            return real_connect(sock, address, *a, **k)

        def guarded_urlopen(*a, **k):
            target = a[0] if a else k.get("url")
            self.network_hits.append(f"urlopen{target!r}")
            if not self._allow_network:
                raise _NetworkCalled(f"unexpected urlopen to {target!r}")
            raise _NetworkCalled("urlopen reached in allow_network test")

        self._mp.setattr(socket.socket, "connect", guarded_connect, raising=True)
        self._mp.setattr(urllib.request, "urlopen", guarded_urlopen, raising=True)

    # -- temp-path capture -------------------------------------------------
    def _install_temp_capture(self):
        real_ntf = tempfile.NamedTemporaryFile

        def capturing_ntf(*a, **k):
            handle = real_ntf(*a, **k)
            self.created_paths.append(Path(handle.name))
            return handle

        # plate.web calls tempfile.NamedTemporaryFile by attribute lookup on the
        # tempfile module, so patching the module attribute is enough.
        self._mp.setattr(tempfile, "NamedTemporaryFile", capturing_ntf, raising=True)

    def __enter__(self):
        # Create a fresh, unique, empty subdir for THIS call so the snapshot is not
        # polluted by a prior @given example reusing the same function-scoped base.
        self._tmpdir = Path(tempfile.mkdtemp(prefix="plate-privacy-", dir=self._base))
        # Redirect tempfile's default directory into our isolated dir for the call.
        self._mp.setattr(tempfile, "tempdir", str(self._tmpdir), raising=False)
        self._before = _snapshot(self._tmpdir)
        self._install_temp_capture()
        self._install_network_tripwires()
        return self

    def __exit__(self, *exc):
        # Assert no NEW file lingers in the temp dir and every captured temp path
        # was removed. Done regardless of whether the wrapped call raised.
        after = _snapshot(self._tmpdir)
        new_files = after - self._before
        assert not new_files, f"convert_bytes/check_noise left files behind: {new_files}"
        leftover = [p for p in self.created_paths if p.exists()]
        assert not leftover, f"temporary input/decode file(s) not removed: {leftover}"
        return False  # never suppress exceptions


# ---------------------------------------------------------------------------
# input generators
# ---------------------------------------------------------------------------
def _encode(arr: np.ndarray, fmt: str) -> bytes:
    mode = "RGBA" if arr.shape[2] == 4 else "RGB"
    im = Image.fromarray(arr, mode)
    buf = io.BytesIO()
    if fmt == "jpeg":
        im.convert("RGB").save(buf, format="JPEG", quality=30)
    else:
        im.save(buf, format="PNG")
    return buf.getvalue()


@st.composite
def _valid_images(draw):
    """Small, well-formed PNG/JPEG uploads with a matching recognised extension."""
    h = draw(st.integers(min_value=12, max_value=40))
    w = draw(st.integers(min_value=12, max_value=40))
    base = draw(st.integers(min_value=0, max_value=255))
    arr = np.full((h, w, 3), base, dtype=np.uint8)
    arr[: h // 2, : w // 2] = draw(st.integers(min_value=0, max_value=255))
    fmt = draw(st.sampled_from(["png", "jpeg"]))
    ext = "jpg" if fmt == "jpeg" else "png"
    return _encode(arr, fmt), f"upload.{ext}"


@st.composite
def _overrides_without_vlm(draw):
    """A valid override map that never enables LM Studio naming (no non-blank vlmUrl)."""
    overrides: dict[str, object] = {}
    if draw(st.booleans()):
        overrides["preset"] = draw(st.sampled_from(sorted(PRESETS)))
    if draw(st.booleans()):
        overrides["maxColors"] = draw(st.integers(min_value=1, max_value=64))
    if draw(st.booleans()):
        overrides["workSize"] = draw(st.integers(min_value=64, max_value=512))
    if draw(st.booleans()):
        overrides["snapPrimitives"] = draw(st.booleans())
    if draw(st.booleans()):
        overrides["strokes"] = draw(st.booleans())
    if draw(st.booleans()):
        overrides["gradients"] = draw(st.booleans())
    if draw(st.booleans()):
        overrides["removeBackground"] = draw(st.booleans())
    # Explicitly blank vlmUrl must still count as disabled.
    if draw(st.booleans()):
        overrides["vlmUrl"] = draw(st.sampled_from(["", "   ", "\t\n"]))
    return overrides


# Payloads that make the engine's decoder reject the input (ImageLoadError) or the
# glue reject the upload (ConvertError) -- the failure path of the property.
_FAILURE_CASES = [
    (b"not a real image, just text bytes", "broken.png", ImageLoadError),
    (bytes(64), "zeros.jpg", ImageLoadError),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "truncated.png", ImageLoadError),
    (b"", "empty.png", web.ConvertError),
    (b"\x89PNG\r\n", "image.gif", web.ConvertError),  # unrecognised extension
]


# ---------------------------------------------------------------------------
# Property 2a: convert_bytes leaves no file behind on the SUCCESS path
# ---------------------------------------------------------------------------
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(image=_valid_images(), overrides=_overrides_without_vlm())
def test_convert_bytes_no_persist_no_network_success(monkeypatch, tmp_path, image, overrides):
    """A successful conversion leaves no temp file and makes no network call.

    **Validates: Requirements 8.1, 8.2**
    """
    data, filename = image
    with _PrivacyHarness(monkeypatch, tmp_path) as h:
        result = web.convert_bytes(data, filename, overrides)
    # Sanity: we exercised the real success path, not an early error.
    assert set(result) == {"svg", "stats", "layers", "warnings"}
    assert result["svg"]
    # No network primitive was touched (no vlmUrl => classical naming only).
    assert h.network_hits == []
    # The conversion genuinely created at least one temp file (input + noise probe)
    # that it then removed -- proving the finally cleanup, not an empty no-op.
    assert h.created_paths, "expected convert_bytes to create a temp input file"


# ---------------------------------------------------------------------------
# Property 2b: convert_bytes leaves no file behind on the FAILURE path
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("data, filename, exc", _FAILURE_CASES)
def test_convert_bytes_no_persist_on_failure(monkeypatch, tmp_path, data, filename, exc):
    """A failed conversion (ImageLoadError / ConvertError) still removes every temp
    input entry before returning control, and performs no network I/O.

    **Validates: Requirements 8.1, 8.3**
    """
    with _PrivacyHarness(monkeypatch, tmp_path) as h, pytest.raises(exc):
        web.convert_bytes(data, filename, {})
    assert h.network_hits == []


# ---------------------------------------------------------------------------
# Property 2c: check_noise leaves no file behind and makes no network call
# ---------------------------------------------------------------------------
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(image=_valid_images())
def test_check_noise_no_persist_no_network(monkeypatch, tmp_path, image):
    """``check_noise`` removes its throwaway decode file and never hits the network,
    on both the success and the decode-failure paths.

    **Validates: Requirements 8.1, 8.2, 8.3**
    """
    data, filename = image
    with _PrivacyHarness(monkeypatch, tmp_path) as h:
        report = web.check_noise(data, filename)
    assert "error" not in report
    assert h.network_hits == []
    assert h.created_paths, "expected check_noise to create a temp decode file"


def test_check_noise_no_persist_on_decode_failure(monkeypatch, tmp_path):
    """check_noise returns a message-bearing error on undecodable bytes, yet still
    removes its temp decode file and performs no network I/O.

    **Validates: Requirements 8.1, 8.3**
    """
    with _PrivacyHarness(monkeypatch, tmp_path) as h:
        report = web.check_noise(b"definitely not an image", "bad.png")
    assert "error" in report
    assert h.network_hits == []


# ---------------------------------------------------------------------------
# Property 2d: concrete real-sample anchor for the no-persist/no-network claim
# ---------------------------------------------------------------------------
def test_convert_bytes_no_persist_on_real_sample(monkeypatch, tmp_path, samples):
    """A real shipped sample converts with no leftover file and no network call."""
    data = (samples / "badge.png").read_bytes()
    with _PrivacyHarness(monkeypatch, tmp_path) as h:
        result = web.convert_bytes(data, "badge.png")
    assert result["svg"]
    assert h.network_hits == []


# ---------------------------------------------------------------------------
# Property 2e: the tripwire itself fires -- guards against a false-negative test.
# If the network guard could never trip, 2a-2d would pass vacuously.
# ---------------------------------------------------------------------------
def test_network_tripwire_actually_trips(monkeypatch, tmp_path):
    """Sanity check: the installed tripwire raises on a genuine outbound attempt, so
    the no-network assertions in the other tests are meaningful."""
    with pytest.raises(_NetworkCalled), _PrivacyHarness(monkeypatch, tmp_path):
        # A urlopen attempt mirrors exactly what plate.vlm would do when enabled.
        urllib.request.urlopen("http://127.0.0.1:1/v1/models", timeout=0.01)
