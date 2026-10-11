"""Start at login: the freedesktop "autostart" .desktop file that desktops run at login.

The user's copy lives in ~/.config/autostart/. A system package (like a future .deb) may
also put one in /etc/xdg/autostart/; the user's copy overrides it, which is how we turn
autostart *off* in that case (a copy with Hidden=true).
"""
import os
import shutil
import sys

FILE_NAME = "copyshelf.desktop"


def user_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", FILE_NAME)


def system_files():
    dirs = (os.environ.get("XDG_CONFIG_DIRS") or "/etc/xdg").split(":")
    return [os.path.join(d, "autostart", FILE_NAME) for d in dirs if d]


def launcher_command():
    """The command that runs Copyshelf, for autostart and keyboard shortcuts."""
    installed = os.path.expanduser("~/.local/bin/copyshelf")
    if os.access(installed, os.X_OK):
        return installed
    return shutil.which("copyshelf") or f"{sys.executable} -m copyshelf"


def _read(path):
    """The key=value lines of a .desktop file's main section, as a dict."""
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep:
                    values[key.strip()] = value.strip()
    except OSError:
        return None
    return values


def is_enabled():
    entry = _read(user_file())
    if entry is None:
        return any(os.path.exists(p) for p in system_files())
    return (entry.get("Hidden", "false").lower() != "true"
            and entry.get("X-GNOME-Autostart-enabled", "true").lower() != "false")


def set_enabled(enabled):
    path = user_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not enabled and not any(os.path.exists(p) for p in system_files()):
        try:
            os.remove(path)   # nothing system-wide to override: just remove ours
        except FileNotFoundError:
            pass
        return
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Copyshelf",
        "Comment=Clipboard history daemon (Super+V)",
        f"Exec={launcher_command()}",
        "Icon=copyshelf",
        "Terminal=false",
        "NoDisplay=true",
        f"Hidden={'false' if enabled else 'true'}",
        f"X-GNOME-Autostart-enabled={'true' if enabled else 'false'}",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
