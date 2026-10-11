"""Work out which desktop we're running on, and which methods suit it.

Each Linux desktop handles the clipboard and fake key presses differently:

  desktop          watch clipboard via              paste via
  ---------------  -------------------------------  -------------------------------
  GNOME, Wayland   GTK on XWayland (GNOME bridges)  our GNOME Shell extension
  KDE, Wayland     wl-clipboard (data-control)      RemoteDesktop portal (asks once)
  Sway/Hyprland..  wl-clipboard (data-control)      wtype
  any X11 session  GTK                              xdotool

Anything else falls back to GTK for watching and "copy only, press Ctrl+V" for pasting.
"""
import os
from dataclasses import dataclass

# Compositors that support the wlr data-control and virtual-keyboard protocols.
WLROOTS_LIKE = {"sway", "hyprland", "river", "wayfire", "labwc", "niri", "dwl", "hikari"}


@dataclass(frozen=True)
class Desktop:
    name: str       # "gnome", "kde", "wlroots" or "other"
    wayland: bool
    raw: str = ""   # XDG_CURRENT_DESKTOP as reported, for log messages

    def __str__(self):
        return f"{self.name} ({'Wayland' if self.wayland else 'X11'}, XDG_CURRENT_DESKTOP={self.raw!r})"


def detect(env=None):
    env = os.environ if env is None else env
    session = env.get("XDG_SESSION_TYPE", "").lower()
    wayland = session == "wayland" or (session != "x11" and bool(env.get("WAYLAND_DISPLAY")))

    raw = env.get("XDG_CURRENT_DESKTOP", "")
    names = {n.strip().lower() for n in raw.split(":") if n.strip()}
    names.add(env.get("DESKTOP_SESSION", "").lower())

    if "kde" in names:
        name = "kde"
    elif names & WLROOTS_LIKE:
        name = "wlroots"
    elif "gnome" in names and not names & {"budgie", "pantheon", "unity"}:
        # Budgie and Pantheon list GNOME too, but don't run GNOME Shell.
        name = "gnome"
    else:
        name = "other"
    return Desktop(name, wayland, raw)


def gdk_backend(env=None):
    """Which GTK backend to use for our own windows. XWayland (x11) when available: it's the
    tested path, it lets GNOME bridge the clipboard to us, and it allows always-on-top."""
    env = os.environ if env is None else env
    return "x11" if env.get("DISPLAY") else "wayland"


def clipboard_method(desktop, have_wl_clipboard):
    """'wl-clipboard' or 'gtk'. GNOME doesn't support the data-control protocol that
    wl-clipboard's watch mode needs, so GNOME always uses GTK via XWayland."""
    if desktop.wayland and desktop.name != "gnome" and have_wl_clipboard:
        return "wl-clipboard"
    return "gtk"


def paste_methods(desktop, configured="auto"):
    """Paste methods to try, best first. If all fail, the user is told to press Ctrl+V."""
    if configured == "none":
        return []
    if configured != "auto":
        return [configured]
    if not desktop.wayland:
        return ["xdotool"]
    return {
        "gnome": ["gnome-extension"],
        "kde": ["portal"],
        "wlroots": ["wtype"],
    }.get(desktop.name, ["wtype"])   # other Wayland compositors: wtype works if they support it


def popup_placement(desktop, at_pointer):
    """How to place the popup:
    'extension'  GNOME Wayland: our GNOME Shell extension moves it to the pointer. (Copyshelf runs
                 on XWayland and can't see the pointer over native Wayland apps.)
    'gtk-mouse'  X11: GTK can read the pointer itself.
    'center'     everywhere else, or when the user turned the option off."""
    if not at_pointer:
        return "center"
    if not desktop.wayland:
        return "gtk-mouse"
    if desktop.name == "gnome":
        return "extension"
    return "center"
