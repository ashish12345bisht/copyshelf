"""One-time move of data from the app's old name, WinClip, to Copyshelf.

Delete this module once no one is likely to still have a WinClip install.
"""
import logging
import os

from copyshelf import APP_ID

log = logging.getLogger(__name__)

OLD_ID = "winclip"


def _xdg(var, fallback):
    return os.environ.get(var) or os.path.expanduser(fallback)


def move_old_data():
    """Rename ~/.config/winclip and ~/.local/share/winclip to the new names, unless the
    new folders already exist (then the old ones are left alone, nothing is overwritten)."""
    for base in (_xdg("XDG_CONFIG_HOME", "~/.config"), _xdg("XDG_DATA_HOME", "~/.local/share")):
        old, new = os.path.join(base, OLD_ID), os.path.join(base, APP_ID)
        if os.path.isdir(old) and not os.path.exists(new):
            try:
                os.rename(old, new)
                log.info("Moved %s to %s", old, new)
            except OSError as e:
                log.warning("Could not move %s to %s: %s", old, new, e)
