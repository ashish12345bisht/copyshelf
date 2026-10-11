"""Paste through our GNOME Shell extension (gnome-extension/ in the repo).

On Wayland, apps can't send keys to other apps. The extension runs inside GNOME Shell,
which is allowed to, and offers a D-Bus method that presses Ctrl+V (or Ctrl+Shift+V in
terminals). No permission dialog is involved.
"""
import logging

from copyshelf._gi import Gio, GLib

log = logging.getLogger(__name__)

SHELL_BUS = "org.gnome.Shell"
OBJECT_PATH = "/io/github/Copyshelf"
INTERFACE = "io.github.Copyshelf"


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
