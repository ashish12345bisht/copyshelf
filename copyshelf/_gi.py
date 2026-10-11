"""Load GTK 3 and friends in one place. gi.require_version must run before the first
`from gi.repository import ...`, so every module imports GTK from here."""
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

# GLib 2.86+ moved Unix-only APIs into GioUnix / GLibUnix and deprecated the old names.
# Older distros (Ubuntu 22.04/24.04) only have the old names, so use whichever exists.
try:
    gi.require_version("GioUnix", "2.0")
    from gi.repository import GioUnix
    DesktopAppInfo = GioUnix.DesktopAppInfo
except (ValueError, ImportError):
    DesktopAppInfo = Gio.DesktopAppInfo

try:
    gi.require_version("GLibUnix", "2.0")
    from gi.repository import GLibUnix
    unix_signal_add = GLibUnix.signal_add
except (ValueError, ImportError):
    unix_signal_add = GLib.unix_signal_add

__all__ = ["DesktopAppInfo", "Gdk", "GdkPixbuf", "GdkX11", "Gio", "GLib", "Gtk", "Pango",
           "unix_signal_add"]
