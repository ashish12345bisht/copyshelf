"""Reading and changing Copyshelf's global keyboard shortcut.

Only some desktops let another program set a global shortcut:
  GNOME   a "custom keybinding" in GNOME's settings (what Settings > Keyboard > Custom
          Shortcuts shows)
  Xfce    an entry in xfconf's xfce4-keyboard-shortcuts channel
Everywhere else the user sets it by hand, so kind() returns None and the settings window
shows instructions instead.

Shortcuts use GTK's "accelerator" format, e.g. "<Super>v" or "<Control><Alt>h".
"""
import logging
import shutil
import subprocess

from copyshelf._gi import Gio, Gtk

log = logging.getLogger(__name__)

GNOME_LIST_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
GNOME_ITEM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
GNOME_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/copyshelf/"
XFCE_CHANNEL = "xfce4-keyboard-shortcuts"
XFCE_PREFIX = "/commands/custom/"


def _schema_exists(schema_id):
    source = Gio.SettingsSchemaSource.get_default()
    return source is not None and source.lookup(schema_id, True) is not None


def kind(desktop):
    """'gnome', 'xfce', or None if this desktop can't be configured from here."""
    if desktop.name == "gnome" and _schema_exists(GNOME_ITEM_SCHEMA):
        return "gnome"
    if "XFCE" in desktop.raw.upper() and shutil.which("xfconf-query"):
        return "xfce"
    return None


def label(accel):
    """Human-readable form: '<Super>v' -> 'Super+V'."""
    if not accel:
        return "Not set"
    key, mods = Gtk.accelerator_parse(accel)
    return Gtk.accelerator_get_label(key, mods) if key else accel


def get_binding(kind_):
    if kind_ == "gnome":
        return Gio.Settings.new_with_path(GNOME_ITEM_SCHEMA, GNOME_PATH).get_string("binding")
    if kind_ == "xfce":
        prop = _xfce_find(_xfce_list())
        return prop[len(XFCE_PREFIX):] if prop else ""
    return ""


def set_binding(kind_, accel, command):
    if kind_ == "gnome":
        _gnome_set(accel, command)
    elif kind_ == "xfce":
        _xfce_set(accel, command)
    else:
        raise ValueError("this desktop's shortcuts can't be changed from Copyshelf")


# ----- GNOME -----
def _gnome_set(accel, command):
    item = Gio.Settings.new_with_path(GNOME_ITEM_SCHEMA, GNOME_PATH)
    item.set_string("name", "Copyshelf clipboard history")
    item.set_string("command", command)
    item.set_string("binding", accel)
    parent = Gio.Settings.new(GNOME_LIST_SCHEMA)
    paths = parent.get_strv("custom-keybindings")
    if GNOME_PATH not in paths:
        parent.set_strv("custom-keybindings", paths + [GNOME_PATH])
    # GNOME also uses Super+V for the notification list; don't let both fight over one key.
    shell = "org.gnome.shell.keybindings"
    if _schema_exists(shell):
        keys = Gio.Settings.new(shell)
        tray = keys.get_strv("toggle-message-tray")
        if accel in tray:
            keys.set_strv("toggle-message-tray", [a for a in tray if a != accel])
    Gio.Settings.sync()   # write now, not "eventually"


# ----- Xfce -----
def _xfce_list():
    out = subprocess.run(["xfconf-query", "-c", XFCE_CHANNEL, "-p", XFCE_PREFIX.rstrip("/"),
                          "-l", "-v"], capture_output=True, text=True, timeout=3)
    return out.stdout


def _xfce_find(listing):
    """The property (e.g. '/commands/custom/<Super>v') whose command runs `copyshelf --show`."""
    for line in listing.splitlines():
        prop, _, value = line.partition(" ")
        if value.strip().endswith("copyshelf --show"):
            return prop
    return None


def _xfce_set(accel, command):
    old = _xfce_find(_xfce_list())
    if old:
        subprocess.run(["xfconf-query", "-c", XFCE_CHANNEL, "-p", old, "-r"], timeout=3)
    subprocess.run(["xfconf-query", "-c", XFCE_CHANNEL, "-p", XFCE_PREFIX + accel,
                    "-n", "-t", "string", "-s", command], timeout=3, check=True)
