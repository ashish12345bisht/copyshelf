"""Test helper: put something on the X11 clipboard and keep serving it until killed.

    python3 clip_owner.py text "hello"
    python3 clip_owner.py image
    python3 clip_owner.py secret "hunter2"   # text marked as a password, like KeePassXC does
"""
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

kind = sys.argv[1]
value = sys.argv[2] if len(sys.argv) > 2 else ""
CLIPBOARD = Gdk.Atom.intern("CLIPBOARD", False)

if kind == "text":
    Gtk.Clipboard.get(CLIPBOARD).set_text(value, -1)
elif kind == "image":
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 6, 4)
    pixbuf.fill(0x3366CCFF)
    Gtk.Clipboard.get(CLIPBOARD).set_image(pixbuf)
elif kind == "secret":
    # Gtk.Clipboard.set_with_data isn't usable from Python, so serve the selection
    # from a widget instead, offering text plus the password-manager marker.
    owner = Gtk.Window()
    owner.realize()
    UTF8 = Gdk.Atom.intern("UTF8_STRING", False)
    HINT = Gdk.Atom.intern("x-kde-passwordManagerHint", False)

    def on_get(widget, selection, info, time):
        if info == 0:
            selection.set_text(value, -1)
        else:
            selection.set(HINT, 8, b"secret")

    owner.connect("selection-get", on_get)
    Gtk.selection_add_target(owner, CLIPBOARD, UTF8, 0)
    Gtk.selection_add_target(owner, CLIPBOARD, HINT, 1)
    assert Gtk.selection_owner_set(owner, CLIPBOARD, Gdk.CURRENT_TIME)

print("ready", flush=True)
Gtk.main()
