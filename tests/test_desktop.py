import pytest

from copyshelf.desktop import (Desktop, clipboard_method, detect, gdk_backend, paste_methods,
                             popup_placement)


@pytest.mark.parametrize("env, name, wayland", [
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, "gnome", True),
    ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, "gnome", False),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}, "gnome", True),       # Fedora
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "pop:GNOME"}, "gnome", True),   # Pop!_OS
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}, "kde", True),
    ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "KDE"}, "kde", False),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "sway"}, "wlroots", True),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"}, "wlroots", True),
    ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "XFCE"}, "other", False),
    ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "X-Cinnamon"}, "other", False),
    ({"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "Budgie:GNOME"}, "other", False),
    ({"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "COSMIC"}, "other", True),
    ({"WAYLAND_DISPLAY": "wayland-0", "DESKTOP_SESSION": "sway"}, "wlroots", True),        # no session type
    ({}, "other", False),
])
def test_detect(env, name, wayland):
    d = detect(env)
    assert (d.name, d.wayland) == (name, wayland)


def test_gdk_backend_prefers_xwayland():
    assert gdk_backend({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}) == "x11"
    assert gdk_backend({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"


def test_clipboard_method():
    assert clipboard_method(Desktop("gnome", True), True) == "gtk"   # GNOME lacks data-control
    assert clipboard_method(Desktop("kde", True), True) == "wl-clipboard"
    assert clipboard_method(Desktop("kde", True), False) == "gtk"   # wl-clipboard not installed
    assert clipboard_method(Desktop("other", False), True) == "gtk"


def test_paste_methods():
    assert paste_methods(Desktop("gnome", True)) == ["gnome-extension"]
    assert paste_methods(Desktop("gnome", False)) == ["xdotool"]
    assert paste_methods(Desktop("kde", True)) == ["portal"]
    assert paste_methods(Desktop("wlroots", True)) == ["wtype"]
    assert paste_methods(Desktop("other", False)) == ["xdotool"]
    assert paste_methods(Desktop("gnome", True), "none") == []
    assert paste_methods(Desktop("gnome", True), "portal") == ["portal"]


def test_popup_placement():
    assert popup_placement(Desktop("gnome", True), True) == "extension"
    assert popup_placement(Desktop("gnome", False), True) == "gtk-mouse"
    assert popup_placement(Desktop("other", False), True) == "gtk-mouse"
    assert popup_placement(Desktop("kde", True), True) == "center"
    assert popup_placement(Desktop("gnome", True), False) == "center"
