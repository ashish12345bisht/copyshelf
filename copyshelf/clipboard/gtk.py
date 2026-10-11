"""Watch the clipboard with GTK.

Used on X11, and on GNOME Wayland through XWayland: on Wayland an app can only read the
clipboard while it has focus, but GNOME passes every copy over to X11 apps, so running
as an X11 app (GDK_BACKEND=x11) lets us see copies while in the background.
"""
import logging

from copyshelf._gi import Gdk, GdkPixbuf, GLib, Gtk

from copyshelf.clipboard import is_sensitive

log = logging.getLogger(__name__)


class GtkClipboard:
    name = "gtk"

    def __init__(self):
        self.skip_sensitive = True
        self.cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.on_text = self.on_image = None

    def start(self, on_text, on_image, on_failed=None):
        self.on_text, self.on_image = on_text, on_image
        self.cb.connect("owner-change", self._on_owner_change)

    # ----- watching -----
    def _on_owner_change(self, cb, event):
        log.debug("clipboard changed (reason=%s)", event.reason.value_nick)
        # Ask which formats are on offer. The request_* calls don't block: GTK calls us back
        # when the other app answers, so a slow app can't freeze Copyshelf.
        cb.request_targets(self._on_targets)

    def _on_targets(self, cb, atoms, *args):
        atoms = atoms or []
        names = [a.name() for a in atoms]
        log.debug("  formats: %s", sorted(names))
        if self.skip_sensitive and is_sensitive(names):
            log.debug("  skipped: marked as a password")
            return
        if Gtk.targets_include_image(atoms, False):
            cb.request_image(self._on_image)
        elif Gtk.targets_include_text(atoms):
            cb.request_text(self._on_text)

    def _on_image(self, cb, pixbuf, *args):
        if pixbuf is None:
            return
        log.debug("  image: %dx%d", pixbuf.get_width(), pixbuf.get_height())
        ok, buf = pixbuf.save_to_bufferv("png", [], [])
        if ok:
            self.on_image(bytes(buf))

    def _on_text(self, cb, text, *args):
        if text:
            log.debug("  text: %r", text[:60])
            self.on_text(text)

    # ----- setting -----
    def set_item(self, item):
        if item["type"] == "text":
            self.cb.set_text(item["text"], -1)
            return True
        try:
            self.cb.set_image(GdkPixbuf.Pixbuf.new_from_file(item["path"]))
            return True
        except GLib.Error as e:
            log.error("Could not load image %s: %s", item["path"], e.message)
            return False
