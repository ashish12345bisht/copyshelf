from copyshelf import hotkey
from copyshelf.desktop import Desktop


def test_label():
    assert hotkey.label("<Super>v") == "Super+V"
    assert hotkey.label("<Control><Alt>h") == "Ctrl+Alt+H"
    assert hotkey.label("") == "Not set"


def test_xfce_finds_our_shortcut():
    listing = ("/commands/custom/<Alt>F2          xfce4-appfinder --collapsed\n"
               "/commands/custom/<Super>v         /home/me/.local/bin/copyshelf --show\n"
               "/commands/custom/Print            xfce4-screenshooter\n")
    assert hotkey._xfce_find(listing) == "/commands/custom/<Super>v"
    assert hotkey._xfce_find("/commands/custom/Print  xfce4-screenshooter\n") is None


def test_kind_for_unsupported_desktops():
    assert hotkey.kind(Desktop("kde", True, "KDE")) is None
    assert hotkey.kind(Desktop("wlroots", True, "sway")) is None
