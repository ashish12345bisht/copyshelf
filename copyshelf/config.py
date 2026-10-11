"""Settings file and standard folder locations.

Settings live in ~/.config/copyshelf/config.json. Anything missing or invalid in that
file falls back to the default, so a hand-edited typo can never stop Copyshelf starting.
"""
import json
import logging
import os

from copyshelf import APP_ID

log = logging.getLogger(__name__)

PASTE_METHODS = ("auto", "gnome-extension", "xdotool", "wtype", "portal", "none")

DEFAULTS = {
    "max_items": 25,          # unpinned items kept
    "auto_paste": True,       # press Ctrl+V in the focused app after picking an item
    "paste_method": "auto",   # one of PASTE_METHODS; "auto" picks the best for your desktop
    "skip_sensitive": True,   # don't record copies that password managers mark as secret
    "popup_at_pointer": True, # open the popup at the mouse pointer (else screen centre)
    "show_tray_icon": True,   # top-bar icon on GNOME, tray icon elsewhere
    "check_updates": True,    # look for a new version on GitHub once a day
}


def _xdg(var, fallback):
    return os.environ.get(var) or os.path.expanduser(fallback)


def config_dir():
    return os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), APP_ID)


def data_dir():
    return os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), APP_ID)


def state_dir():
    """For things Copyshelf remembers that aren't settings, e.g. when it last checked for updates."""
    return os.path.join(_xdg("XDG_STATE_HOME", "~/.local/state"), APP_ID)


def runtime_dir():
    """Folder for the socket and lock file. XDG_RUNTIME_DIR is private to the user;
    if it's missing we use our own private folder rather than the shared /tmp."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base and os.path.isdir(base):
        return base
    path = os.path.join(_xdg("XDG_CACHE_HOME", "~/.cache"), APP_ID)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def config_path():
    return os.path.join(config_dir(), "config.json")


def _valid(key, value):
    default = DEFAULTS[key]
    if type(value) is not type(default):   # note: isinstance(True, int) is True, so compare types
        return False
    if key == "max_items":
        return 1 <= value <= 500
    if key == "paste_method":
        return value in PASTE_METHODS
    return True


def load_config(path=None):
    """Return the settings as a dict: defaults, overridden by valid values from the file."""
    path = path or config_path()
    cfg = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except FileNotFoundError:
        return cfg
    except (OSError, ValueError) as e:
        log.warning("Ignoring unreadable settings file %s (%s)", path, e)
        return cfg
    if not isinstance(saved, dict):
        log.warning("Ignoring settings file %s: expected a JSON object", path)
        return cfg
    for key, value in saved.items():
        if key not in DEFAULTS:
            log.warning("Ignoring unknown setting %r", key)
        elif not _valid(key, value):
            log.warning("Ignoring invalid value for %r: %r (using %r)", key, value, DEFAULTS[key])
        else:
            cfg[key] = value
    return cfg


def save_config(cfg, path=None):
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({k: cfg[k] for k in DEFAULTS}, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
