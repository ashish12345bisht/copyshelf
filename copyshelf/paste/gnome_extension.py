"""Paste through our GNOME Shell extension (gnome-extension/ in the repo).

On Wayland, apps can't send keys to other apps. The extension runs inside GNOME Shell,
which is allowed to, and offers a D-Bus method that presses Ctrl+V (or Ctrl+Shift+V in
terminals). No permission dialog is involved.
"""
import json
import logging
import os

from copyshelf._gi import Gio, GLib

log = logging.getLogger(__name__)

SHELL_BUS = "org.gnome.Shell"
OBJECT_PATH = "/io/github/Copyshelf"
INTERFACE = "io.github.Copyshelf"
EXTENSION_UUID = "copyshelf@ashish12345bisht.github.io"


def installed_version():
    """version-name of the extension files on disk, or None if it isn't installed."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, "gnome-shell", "extensions", EXTENSION_UUID, "metadata.json")
    try:
        with open(path, encoding="utf-8") as f:
            return str(json.load(f).get("version-name", ""))
    except (OSError, ValueError, AttributeError):
        return None


def running_version():
    """version-name of the extension GNOME is running, or None if it isn't running (or is an
    old version without GetVersion)."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync(SHELL_BUS, OBJECT_PATH, INTERFACE, "GetVersion", None,
                              GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 1000, None)
        return reply.unpack()[0]
    except GLib.Error:
        return None


def needs_relogin():
    """True if newer extension files are installed than GNOME is running: GNOME on Wayland
    only loads extension code at login."""
    installed = installed_version()
    return installed is not None and running_version() != installed


class GnomeExtensionPaster:
    name = "gnome-extension"

    def available(self):
        # The extension may be enabled later (e.g. after the next login), so we
        # check on each paste instead of once at startup.
        return True

    def paste(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            bus.call_sync(SHELL_BUS, OBJECT_PATH, INTERFACE, "Paste",
                          None, None, Gio.DBusCallFlags.NONE, 1000, None)
            return True
        except GLib.Error as e:
            log.warning("GNOME extension paste failed (%s). Is the Copyshelf extension enabled? "
                        "Check with: gnome-extensions info copyshelf@ashish12345bisht.github.io", e.message)
            return False
