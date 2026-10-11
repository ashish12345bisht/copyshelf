"""Paste methods, tested with fakes (no real key presses)."""
import subprocess

import pytest

from copyshelf import paste
from copyshelf.paste import wtype, xdotool


class FakePaster:
    def __init__(self, name, available=True, works=True):
        self.name, self._available, self._works, self.calls = name, available, works, 0

    def available(self):
        return self._available

    def paste(self):
        self.calls += 1
        return self._works


@pytest.fixture
def notified(monkeypatch):
    calls = []
    monkeypatch.setattr(paste, "notify_copied", lambda: calls.append(1))
    return calls


def manager_with(monkeypatch, *pasters):
    by_name = {p.name: p for p in pasters}
    monkeypatch.setattr(paste, "make_paster", lambda name: by_name[name])
    return paste.PasteManager([p.name for p in pasters])


def test_first_working_paster_is_used(monkeypatch, notified):
    a, b = FakePaster("a"), FakePaster("b")
    manager_with(monkeypatch, a, b).paste()
    assert (a.calls, b.calls, notified) == (1, 0, [])


def test_falls_through_to_next_paster(monkeypatch, notified):
    a, b = FakePaster("a", works=False), FakePaster("b")
    manager_with(monkeypatch, a, b).paste()
    assert (a.calls, b.calls, notified) == (1, 1, [])


def test_unavailable_pasters_are_skipped(monkeypatch, notified):
    a, b = FakePaster("a", available=False), FakePaster("b")
    manager_with(monkeypatch, a, b).paste()
    assert (a.calls, b.calls) == (0, 1)


def test_notification_when_nothing_works(monkeypatch, notified):
    manager_with(monkeypatch, FakePaster("a", works=False)).paste()
    assert notified == [1]


def test_notification_when_no_pasters(notified):
    paste.PasteManager([]).paste()
    assert notified == [1]


def test_paste_returns_false_so_glib_timeout_runs_once(monkeypatch, notified):
    assert manager_with(monkeypatch, FakePaster("a")).paste() is False


# ----- wtype -----
@pytest.fixture
def recorded_runs(monkeypatch):
    runs = []

    def fake_run(args, **kw):
        runs.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    return runs


def test_wtype_ctrl_v(monkeypatch, recorded_runs):
    monkeypatch.setattr(wtype, "focused_app", lambda: "firefox")
    assert wtype.WtypePaster().paste()
    assert recorded_runs[-1] == ["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"]


def test_wtype_terminal_uses_ctrl_shift_v(monkeypatch, recorded_runs):
    monkeypatch.setattr(wtype, "focused_app", lambda: "foot")
    wtype.WtypePaster().paste()
    assert recorded_runs[-1] == ["wtype", "-M", "ctrl", "-M", "shift", "-k", "v",
                                 "-m", "shift", "-m", "ctrl"]


def test_wtype_failure_is_reported(monkeypatch):
    monkeypatch.setattr(wtype, "focused_app", lambda: "")
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(
        args, 1, "", "Compositor does not support the virtual keyboard protocol"))
    assert wtype.WtypePaster().paste() is False


def test_find_focused_in_sway_tree():
    tree = {"nodes": [{"nodes": [{"app_id": "a"}, {"app_id": "foot", "focused": True}]}],
            "floating_nodes": []}
    assert wtype._find_focused(tree)["app_id"] == "foot"
    assert wtype._find_focused({"nodes": []}) is None


# ----- xdotool -----
def test_xdotool_terminal_uses_ctrl_shift_v(monkeypatch, recorded_runs):
    monkeypatch.setattr(xdotool, "_focused_window_class", lambda: "Gnome-terminal")
    xdotool.XdotoolPaster().paste()
    assert recorded_runs[-1] == ["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"]


def test_xdotool_never_used_on_wayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":0")
    assert not xdotool.XdotoolPaster().available()
