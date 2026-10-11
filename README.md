# Copyshelf

Clipboard history for Linux. Press **Super+V**, pick something you copied earlier, and it gets pasted into the app you're using.

If you've used the clipboard history on Windows (Win+V), it works the same way.

- Opens at the mouse pointer (GNOME and X11).
- Remembers your last 25 copies, text and images, across restarts.
- Pin items to keep them when you **Clear all**.
- Search, keyboard navigation (↑ ↓ Enter, Del to remove, Esc to close).
- Auto-paste into the focused app, including terminals (they get Ctrl+Shift+V).
- Skips copies that password managers mark as secret (KeePassXC, KDE apps).
- A settings window, and a top-bar icon on GNOME (a tray icon on other desktops).

## Supported desktops

| Desktop | Clipboard history | Auto-paste |
|---|---|---|
| GNOME 45+ on Wayland (Ubuntu 24.04+, Fedora 39+, Debian 13) | ✅ | ✅ via the included GNOME Shell extension, no permission prompts |
| Any X11 session (Xfce, MATE, Cinnamon, GNOME on Xorg, …) | ✅ | ✅ needs `xdotool` |
| KDE Plasma on Wayland | ✅ needs `wl-clipboard` | ✅ asks for permission once (RemoteDesktop portal) |
| Sway, Hyprland, river, labwc, … | ✅ needs `wl-clipboard` | ✅ needs `wtype` |
| GNOME 42–44 on Wayland (Ubuntu 22.04) | ✅ | ❌ copy only: you press Ctrl+V |

Wherever auto-paste isn't available, Copyshelf puts the item on the clipboard and shows a "Press Ctrl+V" notification, so it never just fails silently.

**Tested on:** Ubuntu 26.04 (GNOME 50, Wayland), by hand and with the automated tests. The automated tests also run on Ubuntu 22.04 and 24.04 in GitHub CI. The other desktops in the table use the same methods many other tools rely on, but haven't been tested by hand yet. See [docs/TESTING.md](docs/TESTING.md), and reports are welcome.

macOS and Windows aren't supported.

## Install

Open a terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/ashish12345bisht/copyshelf/main/get.sh | bash
```

That's it. The installer:
- puts Copyshelf in your home folder (`~/.local`), so it doesn't need admin rights;
- asks before installing any missing system packages (that step uses `sudo`, and many Ubuntu laptops already have everything);
- sets up Super+V and starts Copyshelf, and starts it automatically at every login.

On **GNOME**, log out and back in once afterwards, so GNOME loads the helper extension. Until then, Copyshelf copies the item you pick and you press Ctrl+V yourself.

To install missing packages without being asked: `curl -fsSL .../get.sh | bash -s -- --yes`

**To update:** run the same command again. **To remove:** `copyshelf --uninstall`; add `--purge` to also delete your history and settings.

<details>
<summary>Prefer to look before you run? Install from a downloaded copy instead.</summary>

```bash
git clone https://github.com/ashish12345bisht/copyshelf.git
cd copyshelf
less install.sh        # read what it does
./install.sh
```
</details>

## Settings

Open the settings window from the ⚙ button in the popup, from the top-bar/tray icon, or with `copyshelf --settings`. There you can change the history size, auto-paste, opening at the pointer, ignoring passwords, the icon, start at login, and the keyboard shortcut. Changes apply immediately.

Changing the shortcut from Copyshelf works on GNOME and Xfce. Other desktops don't let apps change global shortcuts, so the window shows the command to bind yourself.

The settings are stored in `~/.config/copyshelf/config.json`:

```json
{
  "max_items": 25,
  "auto_paste": true,
  "paste_method": "auto",
  "skip_sensitive": true
}
```

| Setting | Meaning |
|---|---|
| `max_items` | How many unpinned items to keep (1–500). Pinned items don't count. |
| `auto_paste` | `false`: only copy the picked item; you press Ctrl+V. |
| `paste_method` | `auto` picks the best for your desktop. Or force one of: `gnome-extension`, `xdotool`, `wtype`, `portal`, `none`. |
| `skip_sensitive` | Don't record copies marked as passwords. |
| `popup_at_pointer` | Open at the mouse pointer (GNOME, X11). `false`: centre of the screen. |
| `show_tray_icon` | Top-bar icon (GNOME) or tray icon (other desktops). |

If you edit the file by hand, restart Copyshelf afterwards: `copyshelf --quit; copyshelf &`

**Tray icon outside GNOME:** this needs the AppIndicator library (`gir1.2-ayatanaappindicator3-0.1` on Ubuntu/Debian). `install.sh` tells you if it's missing.

## Updates

When a new version comes out, Copyshelf shows a notification. Click it to see what's new, then choose **Update now**, **Remind me later** or **Skip this version**. You can also check any time from the top-bar/tray menu, from Settings, or with `copyshelf --check-updates`. Running the install command again also updates.

**What the update check does:** about once a day, Copyshelf downloads public information about the latest release (version number and release notes) from `api.github.com`. Nothing about you or your clipboard is sent. This is the only time Copyshelf uses the internet. To turn it off: Settings → "Check for updates automatically".

## Commands

```
copyshelf                           start the background service (done at login automatically)
copyshelf --show                    open/close the popup (what Super+V runs)
copyshelf --settings                open the settings window
copyshelf --clear                   clear the history (pinned items are kept)
copyshelf --check-updates           look for a new version
copyshelf --quit                    stop the background service
copyshelf --uninstall [--purge]     remove Copyshelf (--purge: also delete history and settings)
copyshelf --debug                   run with detailed logs, to see what's happening
copyshelf --reset-paste-permission  KDE: forget the saved paste permission
```

Your history lives in `~/.local/share/copyshelf/`, readable only by you.

## Troubleshooting

**Nothing pastes, I only get "Press Ctrl+V".** Run `copyshelf --quit; copyshelf --debug` in a terminal and try again. The log says which paste method was tried and why it failed.
- GNOME: check the extension with `gnome-extensions info copyshelf@ashish12345bisht.github.io`. It should say `State: ACTIVE`. If not, log out and back in.
- X11: install `xdotool`. Sway/Hyprland: install `wtype`.

**Copies don't show up in the history.** Run with `--debug` and copy something. Every copy should print `clipboard changed`. On KDE/Sway/Hyprland, make sure `wl-clipboard` is installed.

**Super+V opens GNOME's notification list instead.** Run `./install.sh` again; it moves that to Super+M.

## How it works

Copyshelf runs in the background and watches the clipboard. On Wayland, apps normally can't see the clipboard unless they have focus. Each desktop offers its own way around that, so Copyshelf picks a method per desktop ([copyshelf/desktop.py](copyshelf/desktop.py)):

- **Watching:** on GNOME, Copyshelf runs as an X11 app through XWayland, and GNOME passes every copy to X11 apps. Desktops that support the Wayland "data-control" protocol (KDE, wlroots) are watched with `wl-paste --watch`.
- **Placing the popup:** on GNOME Wayland, apps can't see the pointer or position their own windows, so the extension moves the popup to the pointer before it's drawn.
- **Pasting:** Wayland doesn't let apps press keys in other apps. On GNOME, a small GNOME Shell extension ([gnome-extension/](gnome-extension/)) runs inside GNOME and presses Ctrl+V when Copyshelf asks over D-Bus. Elsewhere Copyshelf uses `xdotool` (X11), `wtype` (wlroots) or the RemoteDesktop portal (KDE).

## Project layout

```
copyshelf/              the Python package
  __main__.py         command line (--show, --quit, ...)
  app.py              the background service: wires everything together
  config.py           settings file and folder locations
  history.py          history storage (plain Python, fully unit-tested)
  ipc.py              the socket that `copyshelf --show` uses to talk to the service
  desktop.py          desktop detection; picks watching and paste methods
  terminals.py        is the focused app a terminal?
  autostart.py        start at login on/off
  hotkey.py           read/change the keyboard shortcut (GNOME, Xfce)
  clipboard/          ways to watch and set the clipboard (gtk.py, wl.py)
  paste/              ways to press Ctrl+V (gnome_extension, xdotool, wtype, portal)
  ui/popup.py         the popup window
  ui/settings.py      the settings window
  ui/tray.py          tray icon for non-GNOME desktops
gnome-extension/      GNOME Shell helper extension (JavaScript)
data/                 app-menu entry, autostart entry, icon
tests/                automated tests
docs/TESTING.md       manual test checklist per desktop
```

## Development

```bash
sudo apt install python3-pytest          # once
python3 -m pytest                        # unit tests

# End-to-end tests run the real service on a private X display, so they never
# touch your real clipboard. Inside a desktop session:
Xwayland :87 -rootless &
COPYSHELF_TEST_DISPLAY=:87 python3 -m pytest
```

### Releasing a new version

1. Describe the changes in [CHANGELOG.md](CHANGELOG.md) under a new `## X.Y.Z - date` heading and commit it.
2. Run `./release.sh X.Y.Z`. It runs the tests, sets the version number, and after you confirm, tags the release and publishes it on GitHub with your changelog text as the notes.
3. Within a day, users' Copyshelf offers them the update; new installs get it right away.

To try changes without installing: `copyshelf --quit; python3 -m copyshelf --debug` from the project folder.

## Contributing

Bug reports and pull requests are welcome. For problems, please include the output of `copyshelf --debug` and your `echo $XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP`.

By submitting a pull request, you agree that your contribution is licensed under the GPL-3.0-or-later, and that the maintainer may also release it under other licenses in future versions of Copyshelf.

## License

Copyshelf is free software under the [GNU General Public License v3.0 or later](LICENSE).
