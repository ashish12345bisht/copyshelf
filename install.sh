#!/usr/bin/env bash
# Installs Copyshelf for the current user. Everything goes under ~/.local; sudo is only used
# to install missing system packages, and only after asking (or with --yes).
# Run it again to update. `copyshelf --uninstall` (or ./uninstall.sh) removes it.
set -euo pipefail
cd "$(dirname "$0")"

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
LIB_DIR="$HOME/.local/lib/copyshelf"
BIN="$HOME/.local/bin/copyshelf"
EXT_UUID="copyshelf@ashish12345bisht.github.io"
EXT_DIR="$DATA_HOME/gnome-shell/extensions/$EXT_UUID"
KEYBINDING="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/copyshelf/"

notes=()   # things to tell the user at the end
note() { notes+=("$*"); }

YES=false   # --yes: install missing packages without asking (for unattended installs)
for arg in "$@"; do
  case $arg in --yes|-y) YES=true ;; esac
done

# This distro's package manager. Package names differ between distros, so each package
# below is written as "apt-name:dnf-name:pacman-name:zypper-name"; PM_COL picks the column.
if command -v apt-get >/dev/null; then PM=(sudo apt-get install -y) PM_COL=1
elif command -v dnf >/dev/null; then PM=(sudo dnf install -y) PM_COL=2
elif command -v pacman >/dev/null; then PM=(sudo pacman -S --needed --noconfirm) PM_COL=3
elif command -v zypper >/dev/null; then PM=(sudo zypper install -y) PM_COL=4
else PM=() PM_COL=1
fi

# Asks a yes/no question (default yes). Reads from the terminal itself, because when run as
# `curl ... | bash` our normal input is the script, not the keyboard.
have_tty() { { : </dev/tty; } 2>/dev/null; }
ask() {
  $YES && return 0
  have_tty || return 1
  local reply
  read -r -p "$1 [Y/n] " reply </dev/tty || return 1
  case $reply in ""|[Yy]*) return 0 ;; *) return 1 ;; esac
}

# offer_install "why" package-spec...  Offers to install the packages; returns 0 if it did.
offer_install() {
  local why=$1 names=() spec
  shift
  for spec in "$@"; do names+=("$(echo "$spec" | cut -d: -f"$PM_COL")"); done
  echo
  echo "$why"
  echo "  Packages: ${names[*]}"
  if [ ${#PM[@]} -eq 0 ]; then
    echo "  Please install them with your package manager."
    return 1
  fi
  ask "Install them now? (uses sudo; it may ask for your password)" || return 1
  local input=/dev/stdin
  have_tty && input=/dev/tty
  if ! "${PM[@]}" "${names[@]}" <"$input"; then
    # On Debian/Ubuntu a stale package list is the usual cause; refresh it and retry once.
    [ "$PM_COL" = 1 ] || return 1
    sudo apt-get update <"$input" && "${PM[@]}" "${names[@]}" <"$input" || return 1
  fi
}

# Adds $3 to the gsettings string-list key $1 $2 (if it isn't there already).
gsettings_list_add() {
  local cur new
  cur=$(gsettings get "$1" "$2")
  new=$(python3 -c "import ast,sys; l=ast.literal_eval(sys.argv[1].replace('@as ','')); p=sys.argv[2]; l.append(p) if p not in l else None; print(l)" "$cur" "$3")
  gsettings set "$1" "$2" "$new"
}

# Removes $3 from the gsettings string-list key $1 $2.
gsettings_list_remove() {
  local cur new
  cur=$(gsettings get "$1" "$2")
  new=$(python3 -c "import ast,sys; l=ast.literal_eval(sys.argv[1].replace('@as ','')); print([x for x in l if x != sys.argv[2]])" "$cur" "$3")
  gsettings set "$1" "$2" "$new"
}

# This app used to be called WinClip. Remove an old WinClip install so the two don't
# both grab Super+V. (Its history and settings are moved over when Copyshelf first starts.)
remove_old_winclip() {
  local old_bin="$HOME/.local/bin/winclip" old_ext="winclip@winclip"
  local old_kb="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/winclip/"
  [ -e "$old_bin" ] || [ -d "$HOME/.local/lib/winclip" ] || [ -d "$DATA_HOME/gnome-shell/extensions/$old_ext" ] || return 0
  echo "Removing the old WinClip install..."
  if [ -x "$old_bin" ]; then
    "$old_bin" --quit >/dev/null 2>&1 || true
    for _ in $(seq 30); do   # very old versions don't wait for the daemon to exit
      pgrep -f "lib/winclip|bin/winclip" >/dev/null || break
      sleep 0.1
    done
  fi
  rm -rf "$HOME/.local/lib/winclip" "$DATA_HOME/gnome-shell/extensions/$old_ext"
  rm -f "$old_bin" "$DATA_HOME/applications/winclip.desktop" "$CONFIG_HOME/autostart/winclip.desktop" \
        "$DATA_HOME/icons/hicolor/scalable/apps/winclip.svg"
  if command -v gsettings >/dev/null && gsettings list-schemas 2>/dev/null | grep -x org.gnome.shell >/dev/null; then
    gsettings_list_remove org.gnome.shell enabled-extensions "$old_ext"
    gsettings_list_remove org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$old_kb"
    local key
    for key in name command binding; do
      gsettings reset "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$old_kb" "$key"
    done
  fi
}

# ---------- 1. Required packages ----------
echo "Checking requirements..."
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "Copyshelf needs Python 3.10 or newer." >&2
  exit 1
fi
have_gtk() {
  python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("GdkPixbuf", "2.0"); from gi.repository import Gtk, GdkPixbuf' 2>/dev/null
}
if ! have_gtk; then
  if ! offer_install "Copyshelf needs GTK 3 and its Python bindings (PyGObject)." \
         python3-gi:python3-gobject:python-gobject:python3-gobject \
         gir1.2-gtk-3.0:gtk3:gtk3:typelib-1_0-Gtk-3_0 || ! have_gtk; then
    echo "Install those packages, then run the installer again." >&2
    exit 1
  fi
fi

read -r DESKTOP SESSION < <(PYTHONPATH=. python3 -c 'from copyshelf.desktop import detect
d = detect(); print(d.name, "wayland" if d.wayland else "x11")')
echo "Desktop: $DESKTOP ($SESSION)"

# Recommended extras for this desktop. Without them Copyshelf still works, but copy-only
# (you press Ctrl+V) and/or without a tray icon.
extras=()
if [ "$SESSION" = x11 ]; then
  command -v xdotool >/dev/null || extras+=(xdotool:xdotool:xdotool:xdotool)
elif [ "$DESKTOP" = kde ] || [ "$DESKTOP" = wlroots ]; then
  command -v wl-paste >/dev/null || extras+=(wl-clipboard:wl-clipboard:wl-clipboard:wl-clipboard)
fi
if [ "$DESKTOP" = wlroots ]; then
  command -v wtype >/dev/null || extras+=(wtype:wtype:wtype:wtype)
fi
# Tray icon outside GNOME (GNOME gets a top-bar icon from our extension instead).
if [ "$DESKTOP" != gnome ] && ! python3 -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1")' 2>/dev/null \
   && ! python3 -c 'import gi; gi.require_version("AppIndicator3", "0.1")' 2>/dev/null; then
  extras+=(gir1.2-ayatanaappindicator3-0.1:libayatana-appindicator-gtk3:libayatana-appindicator:typelib-1_0-AyatanaAppIndicator3-0_1)
fi
if [ ${#extras[@]} -gt 0 ]; then
  if ! offer_install "Recommended for your desktop (auto-paste, clipboard watching, tray icon):" "${extras[@]}"; then
    note "Some recommended packages aren't installed, so auto-paste or the tray icon may not work. Run the installer again to add them."
  fi
fi

# ---------- 2. Program files ----------
remove_old_winclip

echo "Installing Copyshelf to $LIB_DIR ..."
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR" "$(dirname "$BIN")"
cp -r copyshelf "$LIB_DIR/"
cp uninstall.sh "$LIB_DIR/"   # so `copyshelf --uninstall` works without the source folder
find "$LIB_DIR" -name __pycache__ -prune -exec rm -rf {} +

# The `copyshelf` command. Putting our folder first on sys.path means this installed copy
# is used even when you run `copyshelf` from inside the source folder.
cat > "$BIN" <<EOF
#!/bin/sh
exec python3 -c 'import sys; sys.path.insert(0, "$LIB_DIR"); from copyshelf.__main__ import main; sys.exit(main())' "\$@"
EOF
chmod 755 "$BIN"

mkdir -p "$DATA_HOME/applications" "$DATA_HOME/icons/hicolor/scalable/apps" "$CONFIG_HOME/autostart"
sed "s|@BIN@|$BIN|" data/copyshelf.desktop > "$DATA_HOME/applications/copyshelf.desktop"
sed "s|@BIN@|$BIN|" data/copyshelf-autostart.desktop > "$CONFIG_HOME/autostart/copyshelf.desktop"
cp data/copyshelf.svg "$DATA_HOME/icons/hicolor/scalable/apps/copyshelf.svg"

# ---------- 3. GNOME Shell extension (auto-paste on GNOME Wayland) ----------
if [ "$DESKTOP" = gnome ]; then
  shell_major=$(gnome-shell --version 2>/dev/null | grep -oE '[0-9]+' | head -1 || true)
  if [ -n "$shell_major" ] && [ "$shell_major" -ge 45 ]; then
    echo "Installing the GNOME Shell helper extension..."
    mkdir -p "$EXT_DIR"
    cp gnome-extension/metadata.json gnome-extension/extension.js "$EXT_DIR/"
    # Writing the setting directly works even before GNOME has noticed the new extension.
    gsettings_list_add org.gnome.shell enabled-extensions "$EXT_UUID"
    if [ "$(gsettings get org.gnome.shell disable-user-extensions)" = true ]; then
      note "Extensions are switched off in GNOME. Turn them on in the Extensions app for auto-paste."
    fi
    if ! gnome-extensions info "$EXT_UUID" 2>/dev/null | grep "State: ACTIVE" >/dev/null; then
      note "Log out and back in once, so GNOME loads the helper extension. Until then, pick an item and press Ctrl+V yourself."
    fi
  else
    note "Your GNOME (${shell_major:-unknown}) is older than 45, so auto-paste isn't available on Wayland. Copyshelf will copy, and you press Ctrl+V."
  fi
fi

# ---------- 4. Super+V shortcut ----------
case "${XDG_CURRENT_DESKTOP:-}" in
  *XFCE*) desktop_kind=xfce ;;
  *) desktop_kind=$DESKTOP ;;
esac
case $desktop_kind in
  gnome)
    echo "Setting up the Super+V shortcut..."
    # GNOME uses Super+V for the notification list too; keep that on Super+M only.
    gsettings set org.gnome.shell.keybindings toggle-message-tray "['<Super>m']"
    gsettings_list_add org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$KEYBINDING"
    schema="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KEYBINDING"
    gsettings set "$schema" name "Copyshelf clipboard history"
    gsettings set "$schema" command "$BIN --show"
    gsettings set "$schema" binding "<Super>v"
    ;;
  xfce)
    echo "Setting up the Super+V shortcut..."
    xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/<Super>v" -n -t string -s "$BIN --show"
    ;;
  kde)
    note "Add the shortcut: System Settings > Keyboard > Shortcuts > Add New > Command or Script, command: $BIN --show. Meta+V is Klipper's by default; remove it there first, or pick another key."
    ;;
  wlroots)
    note "Add the shortcut to your compositor config. Sway: bindsym \$mod+v exec $BIN --show    Hyprland: bind = SUPER, V, exec, $BIN --show"
    ;;
  *)
    note "Bind a keyboard shortcut (e.g. Super+V) in your desktop's settings to the command: $BIN --show"
    ;;
esac

# ---------- 5. (Re)start the daemon ----------
"$BIN" --quit >/dev/null 2>&1 || true   # waits until any old copy has really exited
nohup "$BIN" >/dev/null 2>&1 &

echo
echo "Done! Copy a few things, then press your shortcut (Super+V)."
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) note "$HOME/.local/bin is not on your PATH, so type the full path ($BIN) to run copyshelf from a terminal." ;;
esac
for n in "${notes[@]}"; do
  echo
  echo "NOTE: $n"
done
