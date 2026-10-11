"""Paste with wtype, for Sway, Hyprland and other compositors that support the
"virtual keyboard" Wayland protocol. No permission dialog is involved.

To spot terminals we ask the compositor which window has focus (Sway and Hyprland only).
"""
import json
import logging
import os
import shutil
import subprocess

from copyshelf.terminals import is_terminal

log = logging.getLogger(__name__)


def _find_focused(node):
    if node.get("focused"):
        return node
    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        found = _find_focused(child)
        if found:
            return found
    return None


def focused_app():
    """App id / window class of the focused window, or '' if we can't tell."""
    try:
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
            out = subprocess.run(["hyprctl", "activewindow", "-j"],
                                 capture_output=True, text=True, timeout=1).stdout
            return json.loads(out or "{}").get("class", "")
        if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
            out = subprocess.run(["swaymsg", "-t", "get_tree"],
                                 capture_output=True, text=True, timeout=1).stdout
            node = _find_focused(json.loads(out or "{}")) or {}
            return node.get("app_id") or node.get("window_properties", {}).get("class", "")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return ""


class WtypePaster:
    name = "wtype"

    def available(self):
        return bool(shutil.which("wtype")) and bool(os.environ.get("WAYLAND_DISPLAY"))

    def paste(self):
        app = focused_app()
        mods = ["ctrl", "shift"] if is_terminal(app) else ["ctrl"]
        args = ["wtype"]
        for m in mods:
            args += ["-M", m]
        args += ["-k", "v"]
        for m in reversed(mods):
            args += ["-m", m]
        log.debug("wtype: pasting into %r with %s+v", app, "+".join(mods))
        try:
            # wtype exits with an error if the compositor lacks the virtual keyboard protocol.
            result = subprocess.run(args, capture_output=True, text=True, timeout=2)
            if result.returncode != 0:
                log.warning("wtype failed: %s", result.stderr.strip())
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("wtype failed: %s", e)
            return False
