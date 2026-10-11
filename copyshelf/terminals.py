"""Is the focused app a terminal? Terminals paste with Ctrl+Shift+V, not Ctrl+V.

Main check: the app's .desktop file lists "TerminalEmulator" in Categories.
Backup: well-known app ids / window class names, for apps without a proper .desktop file.
"""
from copyshelf._gi import DesktopAppInfo

KNOWN_TERMINALS = {
    "org.gnome.ptyxis", "org.gnome.terminal", "gnome-terminal", "gnome-terminal-server",
    "org.gnome.console", "kgx", "kitty", "alacritty", "com.mitchellh.ghostty", "ghostty",
    "org.wezfurlong.wezterm", "foot", "footclient", "tilix", "com.gexperts.tilix", "terminator",
    "org.kde.konsole", "konsole", "xfce4-terminal", "mate-terminal", "lxterminal", "qterminal",
    "xterm", "urxvt", "st", "st-256color", "terminology", "guake", "tilda", "yakuake",
}


def is_terminal(app_id):
    if not app_id:
        return False
    app_id = app_id.strip()
    if app_id.lower().removesuffix(".desktop") in KNOWN_TERMINALS:
        return True
    for name in {app_id, app_id.lower()}:
        try:
            info = DesktopAppInfo.new(name.removesuffix(".desktop") + ".desktop")
        except TypeError:   # PyGObject raises this when no such .desktop file exists
            continue
        if "TerminalEmulator" in (info.get_categories() or "").split(";"):
            return True
    return False
