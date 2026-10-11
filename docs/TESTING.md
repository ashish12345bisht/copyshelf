# Manual test checklist

The automated tests (`python3 -m pytest`) cover history and storage, settings, desktop detection, the socket, and the background service on an X display. What they can't cover is a real desktop: real hotkeys, real apps and real auto-paste. Run this checklist on each desktop before a release.

Virtual machines are fine. **GNOME Boxes** (`sudo apt install gnome-boxes`) can download most of these distros for you.

## Desktops to cover

| # | Setup | How to get it |
|---|---|---|
| 1 | GNOME 50, Wayland | Ubuntu 26.04 (the developer's machine) |
| 2 | GNOME 46, Wayland | Ubuntu 24.04 LTS |
| 3 | GNOME 42, Wayland (copy only expected) | Ubuntu 22.04 LTS |
| 4 | GNOME on Xorg | Ubuntu 24.04: choose "Ubuntu on Xorg" on the login screen (gear icon) |
| 5 | KDE Plasma 6, Wayland | Kubuntu 24.04+ or Fedora KDE |
| 6 | Sway | Fedora Sway spin, or `sudo apt install sway` and pick it at login |
| 7 | Hyprland | Arch / EndeavourOS |
| 8 | Xfce (X11) | Xubuntu |

## Setup on each machine

```bash
git clone <repo> copyshelf && cd copyshelf
./install.sh               # follow any NOTE it prints (packages, shortcut, logout)
```

## Checks

For each desktop, mark ✅ / ❌ and note anything odd.

**Basics**
1. Copy text in a browser with Ctrl+C. Press Super+V: it's at the top of the list.
2. Copy text with the **right-click menu** → Copy. It shows up too.
3. Copy an image (right-click an image in the browser → Copy Image). A thumbnail appears.
4. Copy the same text twice. It appears only once, at the top.
5. Copy 30 different things. Only 25 unpinned items remain.

**Popup**
6. Super+V opens the popup; pressing it again closes it.
7. ↑ ↓ move the selection, Esc closes the popup, and clicking outside it closes it.
8. Type in the search box: the list filters as you type.
9. Pin an item (📌), then **Clear all**: only pinned items remain.
10. Delete an item with ✕, and with the Del key.

**Extras**
- 10a. The popup opens at the mouse pointer (GNOME, X11), fully on screen even with the pointer in a corner. KDE/Sway: centred.
- 10b. ⚙ in the popup opens Settings. Change the history size to 3, copy 5 things: only 3 remain.
- 10c. Settings → "Paste automatically" off: picking only copies.
- 10d. Settings → Keyboard shortcut → Change…, press Super+Shift+V: the new shortcut works and the old one doesn't. (GNOME/Xfce; elsewhere the window shows the command instead.)
- 10e. Settings → "Start at login" off, then log out and in: Copyshelf doesn't start. Turn it back on.
- 10f. Top-bar icon (GNOME) / tray icon (others): its menu shows the history, opens Settings and clears the history. The icon switch in Settings hides and shows it right away.
- 10g. Search for "image": only images are shown.

**Auto-paste** (expected result depends on the desktop; see the README table)
11. In a text editor: pick an item. It pastes by itself.
12. In a browser text field: same.
13. In a terminal: it pastes (Copyshelf sends Ctrl+Shift+V there).
14. Where auto-paste isn't supported: a "Press Ctrl+V" notification appears, and Ctrl+V works.
15. No unexpected permission dialogs. (KDE: one dialog, the first time only.)

**Persistence and privacy**
16. Log out and back in: the history is still there and Super+V still works.
17. With KeePassXC: copy a password. It does **not** appear in the history.
18. `ls -ld ~/.local/share/copyshelf` shows `drwx------` (only you can read it).

**Install / uninstall**
19. Run `./install.sh` twice in a row. Exactly one Copyshelf is running afterwards:
    `pgrep -fc "lib/copyshelf"` should print `1`.
20. `./uninstall.sh`: Super+V goes back to its old function and Copyshelf is gone. Your history is kept until you run `--purge`.

## Useful commands when something fails

```bash
copyshelf --quit; copyshelf --debug          # run in the foreground with detailed logs
gnome-extensions info copyshelf@ashish12345bisht.github.io    # GNOME: is the helper extension active?
journalctl --user -b -o cat /usr/bin/gnome-shell | grep -i copyshelf   # GNOME extension log
echo $XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP                           # what Copyshelf detects
```

When reporting a problem, include the output of `copyshelf --debug` and the two values from the last command.
