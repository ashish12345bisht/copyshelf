"""Paste with xdotool. X11 sessions only.

On Wayland, xdotool's fake keys go through GNOME's "Remote Desktop" permission dialog
(or don't work at all), so we never use it there.
"""
import logging
import os
import shutil
import subprocess

from copyshelf.terminals import is_terminal

log = logging.getLogger(__name__)


def _focused_window_class():
    try:
        out = subprocess.run(["xdotool", "getactivewindow", "getwindowclassname"],
                             capture_output=True, text=True, timeout=1)
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


class XdotoolPaster:
    name = "xdotool"

    def available(self):
        return (bool(shutil.which("xdotool")) and bool(os.environ.get("DISPLAY"))
                and os.environ.get("XDG_SESSION_TYPE") != "wayland")

    def paste(self):
        app = _focused_window_class()
        keys = "ctrl+shift+v" if is_terminal(app) else "ctrl+v"
        log.debug("xdotool: pasting into %r with %s", app, keys)
        try:
            result = subprocess.run(["xdotool", "key", "--clearmodifiers", keys], timeout=2)
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("xdotool failed: %s", e)
            return False
