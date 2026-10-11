"""copyshelf._gi picks the GLib API that works on this GLib version. Versions differ a lot
between distros, so each situation is tested with fake modules."""
import importlib
import types

import pytest

from copyshelf import _gi


@pytest.fixture
def glib_286(monkeypatch):
    monkeypatch.setattr(_gi, "NEW_UNIX_API", True)
    monkeypatch.setattr(_gi.gi, "require_version", lambda *a: None)


def fake_import(modules):
    def import_module(name):
        short = name.rsplit(".", 1)[-1]
        if short not in modules:
            raise ImportError(name)
        return modules[short]
    return import_module


def test_new_api_on_glib_286(glib_286, monkeypatch):
    new = types.SimpleNamespace(signal_add="new")
    monkeypatch.setattr(importlib, "import_module", fake_import({"GLibUnix": new}))
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "new"


def test_old_api_before_glib_286_even_if_new_module_exists(monkeypatch):
    """Ubuntu 24.04 (GLib 2.80): GioUnix exists but is only partly usable."""
    monkeypatch.setattr(_gi, "NEW_UNIX_API", False)
    new = types.SimpleNamespace(signal_add="new")
    monkeypatch.setattr(importlib, "import_module", fake_import({"GLibUnix": new}))
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "old"


def test_missing_function_falls_back(glib_286, monkeypatch):
    monkeypatch.setattr(importlib, "import_module", fake_import({"GLibUnix": types.SimpleNamespace()}))
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "old"


def test_missing_module_falls_back(glib_286, monkeypatch):
    monkeypatch.setattr(importlib, "import_module", fake_import({}))
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "old"


def test_desktop_app_info_really_works():
    """Whatever was picked must be usable for what terminals.py does with it."""
    from copyshelf.terminals import is_terminal
    assert is_terminal("xterm")                      # known name
    assert not is_terminal("no-such-app-anywhere")   # no .desktop file
    for app_id in ("firefox", "org.gnome.TextEditor", "org.gnome.Nautilus"):
        is_terminal(app_id)   # must not raise, whether or not the app is installed
