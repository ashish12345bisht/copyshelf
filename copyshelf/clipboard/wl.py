"""Watch the clipboard with wl-clipboard (wl-paste / wl-copy).

Used on KDE, Sway, Hyprland and other Wayland desktops that support the "data-control"
protocol, which lets a clipboard manager see every copy without having focus.
GNOME doesn't support it, so GNOME uses the GTK backend instead.

`wl-paste --watch CMD` runs CMD after every copy. Our CMD just prints one line, which we
read in a background thread; then we fetch the new content with plain `wl-paste`.
"""
import logging
import shutil
import subprocess
import threading
import time

from copyshelf._gi import GdkPixbuf, GLib
from copyshelf.clipboard import is_sensitive

log = logging.getLogger(__name__)

TEXT_TYPES = ("text/plain;charset=utf-8", "UTF8_STRING", "text/plain", "STRING", "TEXT")
# wl-paste sets CLIPBOARD_STATE for the command: "data", "nil", "clear" or "sensitive".
WATCH_CMD = ["sh", "-c", 'cat >/dev/null; echo "${CLIPBOARD_STATE:-data}"']


def available():
    return bool(shutil.which("wl-paste") and shutil.which("wl-copy"))


def _run(args, input=None, timeout=3):
    return subprocess.run(args, input=input, capture_output=True, timeout=timeout)


def _to_png(data):
    """Convert any image format GdkPixbuf understands (JPEG, BMP, ...) to PNG bytes."""
    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    ok, buf = loader.get_pixbuf().save_to_bufferv("png", [], [])
    return bytes(buf) if ok else None


class WlClipboard:
    name = "wl-clipboard"

    def __init__(self):
        self.skip_sensitive = True
        self.proc = None

    def start(self, on_text, on_image, on_failed=None):
        self.on_text, self.on_image, self.on_failed = on_text, on_image, on_failed
        self.proc = subprocess.Popen(["wl-paste", "--watch", *WATCH_CMD],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        started = time.monotonic()
        for line in self.proc.stdout:
            state = line.strip()
            log.debug("clipboard changed (state=%s)", state)
            if state == "sensitive" and self.skip_sensitive:
                log.debug("  skipped: marked as a password")
            elif state in ("data", "sensitive"):
                self._read()
        # wl-paste only stops if it failed (e.g. the compositor lacks data-control) or we quit.
        err = self.proc.stderr.read().strip()
        log.warning("wl-paste stopped after %.0fs: %s", time.monotonic() - started, err or "no error")
        if self.on_failed:
            GLib.idle_add(self.on_failed)

    def _read(self):
        """Runs on the watcher thread; results are handed to the main thread with idle_add."""
        try:
            types = _run(["wl-paste", "--list-types"]).stdout.decode(errors="replace").split()
            log.debug("  formats: %s", sorted(types))
            if self.skip_sensitive and is_sensitive(types):
                log.debug("  skipped: marked as a password")
                return
            image_type = "image/png" if "image/png" in types else next(
                (t for t in types if t.startswith("image/")), None)
            if image_type:
                data = _run(["wl-paste", "--no-newline", "--type", image_type], timeout=10).stdout
                if data:
                    GLib.idle_add(self._deliver_image, data, image_type)
                return
            text_type = next((t for t in TEXT_TYPES if t in types), None)
            if text_type:
                text = _run(["wl-paste", "--no-newline", "--type", text_type]).stdout
                GLib.idle_add(self.on_text, text.decode("utf-8", errors="replace"))
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("Could not read the clipboard: %s", e)

    def _deliver_image(self, data, image_type):
        try:
            png = data if image_type == "image/png" else _to_png(data)
        except GLib.Error as e:
            log.warning("Could not decode %s image: %s", image_type, e.message)
            return False
        if png:
            self.on_image(png)
        return False

    def set_item(self, item):
        try:
            if item["type"] == "text":
                mime, data = "text/plain;charset=utf-8", item["text"].encode("utf-8")
            else:
                with open(item["path"], "rb") as f:
                    mime, data = "image/png", f.read()
            # wl-copy forks into the background to serve the clipboard. Its output must not
            # be captured: the background copy would keep the pipe open and we'd wait forever.
            subprocess.run(["wl-copy", "--type", mime], input=data, timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except (OSError, subprocess.SubprocessError) as e:
            log.error("wl-copy failed: %s", e)
            return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.on_failed = None   # we're stopping on purpose
            self.proc.terminate()
