"""Auto-paste: press Ctrl+V in the app that has focus, using whatever the desktop allows.

Each paster has:
    name          used in settings ("paste_method") and log messages
    available()   quick check that its tool/service exists
    paste()       returns True if the paste was sent (or will be, for the portal)

If no paster works, the user gets a "Copied — press Ctrl+V" notification instead.
"""
import logging

from copyshelf import APP_ID
from copyshelf._gi import Gio, GLib

log = logging.getLogger(__name__)


def notify(summary, body=""):
    """Show a desktop notification by talking to the notification service directly."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.freedesktop.Notifications", "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications", "Notify",
            GLib.Variant("(susssasa{sv}i)", (APP_ID, 0, "edit-paste", summary, body, [], {}, 3000)),
            None, Gio.DBusCallFlags.NONE, 1000, None)
    except GLib.Error as e:
        log.warning("Could not show notification: %s", e.message)


def notify_copied():
    notify("Copied to clipboard", "Press Ctrl+V to paste.")


def make_paster(name):
    if name == "gnome-extension":
        from copyshelf.paste.gnome_extension import GnomeExtensionPaster
        return GnomeExtensionPaster()
    if name == "xdotool":
        from copyshelf.paste.xdotool import XdotoolPaster
        return XdotoolPaster()
    if name == "wtype":
        from copyshelf.paste.wtype import WtypePaster
        return WtypePaster()
    if name == "portal":
        from copyshelf.paste.portal import PortalPaster
        return PortalPaster(on_failed=notify_copied)
    raise ValueError(f"unknown paste method {name!r}")


class PasteManager:
    def __init__(self, method_names):
        self.pasters = []
        for name in method_names:
            paster = make_paster(name)
            if paster.available():
                self.pasters.append(paster)
            else:
                log.info("Paste method %r is not available here", name)
        log.info("Paste methods: %s", [p.name for p in self.pasters] or "none (copy only)")

    def paste(self):
        for paster in self.pasters:
            if paster.paste():
                return False   # False: don't repeat when used as a GLib timeout
            log.info("Paste via %s failed, trying the next method", paster.name)
        notify_copied()
        return False
