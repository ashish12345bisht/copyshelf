"""copyshelf._gi picks the newest GLib API that exists. GLib versions differ a lot between
distros, so this is tested with fake modules for each situation."""
import importlib
import types

from copyshelf import _gi


def fake_import(modules):
    def import_module(name):
        short = name.rsplit(".", 1)[-1]
        if short not in modules:
            raise ImportError(name)
        return modules[short]
    return import_module


def test_uses_new_api_when_present(monkeypatch):
    monkeypatch.setattr(_gi.gi, "require_version", lambda *a: None)
    new = types.SimpleNamespace(signal_add="new")
    monkeypatch.setattr(importlib, "import_module", fake_import({"GLibUnix": new}))
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "new"


def test_module_present_but_function_missing(monkeypatch):
    """Ubuntu 24.04: GLibUnix exists, but has no signal_add yet."""
    monkeypatch.setattr(_gi.gi, "require_version", lambda *a: None)
    monkeypatch.setattr(importlib, "import_module", fake_import({"GLibUnix": types.SimpleNamespace()}))
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "old"


def test_module_missing(monkeypatch):
    """Ubuntu 22.04: no GLibUnix at all."""
    def no_such_namespace(*a):
        raise ValueError("Namespace GLibUnix not available")
    monkeypatch.setattr(_gi.gi, "require_version", no_such_namespace)
    assert _gi._newest("GLibUnix", "signal_add", lambda: "old") == "old"


def test_real_values_are_callable():
    assert callable(_gi.unix_signal_add)
    assert callable(_gi.DesktopAppInfo.new)
