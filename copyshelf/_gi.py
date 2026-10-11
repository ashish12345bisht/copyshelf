"""Load GTK 3 and friends in one place. gi.require_version must run before the first
`from gi.repository import ...`, so every module imports GTK from here."""
import importlib

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

try:
    gi.require_version("GdkX11", "3.0")
    from gi.repository import GdkX11
except (ValueError, ImportError):   # running on native Wayland
    GdkX11 = None

# GLib 2.86 finished moving Unix-only APIs into GioUnix / GLibUnix and deprecated the old
# names. Older GLib versions may already have those modules, but only partly working
# (Ubuntu 24.04's GioUnix.DesktopAppInfo breaks on get_categories()). So we go by GLib's
# version rather than by what happens to exist.
NEW_UNIX_API = GLib.check_version(2, 86, 0) is None   # None means "at least 2.86"


def _newest(namespace, attr, fallback):
    """`namespace.attr` on GLib 2.86+, else `fallback()`. The fallback is a function so the
    old, deprecated name is only touched when it's really needed (touching it warns)."""
    if not NEW_UNIX_API:
        return fallback()
    try:
        gi.require_version(namespace, "2.0")
        module = importlib.import_module(f"gi.repository.{namespace}")
    except (ValueError, ImportError):
        return fallback()
    return getattr(module, attr, None) or fallback()


DesktopAppInfo = _newest("GioUnix", "DesktopAppInfo", lambda: Gio.DesktopAppInfo)
unix_signal_add = _newest("GLibUnix", "signal_add", lambda: GLib.unix_signal_add)

__all__ = ["DesktopAppInfo", "Gdk", "GdkPixbuf", "GdkX11", "Gio", "GLib", "Gtk", "Pango",
           "unix_signal_add"]
