"""Clipboard backends, tested with fakes instead of a real clipboard."""
import subprocess

import pytest

from copyshelf._gi import Gdk
from copyshelf.clipboard import gtk as gtk_backend
from copyshelf.clipboard import is_sensitive
from copyshelf.clipboard import wl


def test_is_sensitive():
    assert is_sensitive(["UTF8_STRING", "x-kde-passwordManagerHint"])
    assert not is_sensitive(["UTF8_STRING", "text/plain"])


# ----- GTK backend: deciding what to read from the list of formats -----
class FakeGtkClipboard:
    def __init__(self):
        self.requested = []

    def request_text(self, cb):
        self.requested.append("text")

    def request_image(self, cb):
        self.requested.append("image")


def atoms(*names):
    return [Gdk.Atom.intern(n, False) for n in names]


@pytest.mark.parametrize("formats, expected", [
    (["UTF8_STRING", "TARGETS"], ["text"]),
    (["image/png", "TARGETS"], ["image"]),
    (["UTF8_STRING", "x-kde-passwordManagerHint"], []),
    ([], []),
])
def test_gtk_backend_reads_right_format(formats, expected):
    backend = gtk_backend.GtkClipboard()
    fake = FakeGtkClipboard()
    backend._on_targets(fake, atoms(*formats) or None)
    assert fake.requested == expected


def test_gtk_backend_can_record_secrets_if_user_wants():
    backend = gtk_backend.GtkClipboard()
    backend.skip_sensitive = False
    fake = FakeGtkClipboard()
    backend._on_targets(fake, atoms("UTF8_STRING", "x-kde-passwordManagerHint"))
    assert fake.requested == ["text"]


# ----- wl-clipboard backend -----
@pytest.fixture
def wl_backend(monkeypatch):
    """A WlClipboard whose wl-paste calls return canned data, and whose results
    are delivered immediately instead of via the GTK main loop."""
    got = {"text": [], "image": []}
    backend = wl.WlClipboard()
    backend.on_text = lambda t: got["text"].append(t)
    backend.on_image = lambda b: got["image"].append(b)
    monkeypatch.setattr(wl.GLib, "idle_add", lambda fn, *args: fn(*args))

    def use(types, data=b""):
        def fake_run(args, input=None, timeout=3):
            out = "\n".join(types).encode() if "--list-types" in args else data
            return subprocess.CompletedProcess(args, 0, out, b"")
        monkeypatch.setattr(wl, "_run", fake_run)
        backend._read()
        return got
    return use


def test_wl_reads_text(wl_backend):
    got = wl_backend(["text/plain;charset=utf-8", "TEXT"], "héllo".encode())
    assert got["text"] == ["héllo"]


def test_wl_reads_png(wl_backend):
    got = wl_backend(["image/png", "text/html"], b"\x89PNG...")
    assert got["image"] == [b"\x89PNG..."]


def test_wl_skips_secrets(wl_backend):
    got = wl_backend(["text/plain", "x-kde-passwordManagerHint"], b"hunter2")
    assert got == {"text": [], "image": []}


def test_wl_ignores_unknown_formats(wl_backend):
    got = wl_backend(["application/x-something"], b"??")
    assert got == {"text": [], "image": []}


def test_wl_copy_does_not_capture_output(monkeypatch):
    """wl-copy forks into the background; capturing its output would hang until timeout."""
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    assert wl.WlClipboard().set_item({"type": "text", "text": "hi"})
    args, kw = calls[0]
    assert args == ["wl-copy", "--type", "text/plain;charset=utf-8"]
    assert kw["input"] == b"hi"
    assert kw["stdout"] is subprocess.DEVNULL and kw["stderr"] is subprocess.DEVNULL
