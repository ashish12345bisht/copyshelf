"""Tray icon for desktops other than GNOME (KDE, Xfce, Cinnamon, MATE, Sway with waybar...).

Uses AppIndicator, the standard tray icon protocol on Linux. It's optional: if the
library isn't installed, Copyshelf simply runs without an icon.
On GNOME, our GNOME Shell extension shows a top-bar icon instead (GNOME has no tray).
"""
import importlib
import logging

import gi

from copyshelf._gi import Gtk

log = logging.getLogger(__name__)


def _load_appindicator():
    for name in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(name, "0.1")
            return importlib.import_module(f"gi.repository.{name}")
        except (ValueError, ImportError):
            continue
    return None


class Tray:
    def __init__(self, on_show, on_settings, on_clear, on_check_updates):
        AppIndicator = _load_appindicator()
        if AppIndicator is None:
            log.info("No tray icon: install libayatana-appindicator (gir1.2-ayatanaappindicator3-0.1)")
            self.indicator = None
            return
        self.status = AppIndicator.IndicatorStatus
        self.indicator = AppIndicator.Indicator.new(
            "copyshelf", "edit-paste-symbolic", AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_title("Copyshelf")
        menu = Gtk.Menu()
        for label, callback in (("Show clipboard history", on_show), ("Settings", on_settings),
                                (None, None), ("Clear history", on_clear),
                                ("Check for updates", on_check_updates)):
            item = Gtk.SeparatorMenuItem() if label is None else Gtk.MenuItem(label=label)
            if callback:
                item.connect("activate", lambda _i, cb=callback: cb())
            menu.append(item)
        menu.show_all()
        self.indicator.set_menu(menu)

    def set_visible(self, visible):
        if self.indicator:
            self.indicator.set_status(self.status.ACTIVE if visible else self.status.PASSIVE)
