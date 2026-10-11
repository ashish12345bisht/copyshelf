#!/usr/bin/env bash
# Removes Copyshelf for the current user. Your clipboard history and settings are kept
# unless you pass --purge.
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
LIB_DIR="$HOME/.local/lib/copyshelf"
BIN="$HOME/.local/bin/copyshelf"
EXT_UUID="copyshelf@ashish12345bisht.github.io"
KEYBINDING="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/copyshelf/"

purge=false
[ "${1:-}" = "--purge" ] && purge=true

# Removes $3 from the gsettings string-list key $1 $2.
gsettings_list_remove() {
  local cur new
  cur=$(gsettings get "$1" "$2")
  new=$(python3 -c "import ast,sys; l=ast.literal_eval(sys.argv[1].replace('@as ','')); print([x for x in l if x != sys.argv[2]])" "$cur" "$3")
  gsettings set "$1" "$2" "$new"
}

echo "Stopping Copyshelf..."
if [ -x "$BIN" ]; then
  "$BIN" --quit >/dev/null 2>&1 || true
fi

echo "Removing program files..."
rm -rf "$LIB_DIR"
rm -f "$BIN" \
      "$DATA_HOME/applications/copyshelf.desktop" \
      "$CONFIG_HOME/autostart/copyshelf.desktop" \
      "$DATA_HOME/icons/hicolor/scalable/apps/copyshelf.svg"

if command -v gsettings >/dev/null && gsettings list-schemas 2>/dev/null | grep -x org.gnome.shell >/dev/null; then
  echo "Removing the GNOME extension and shortcut..."
  gsettings_list_remove org.gnome.shell enabled-extensions "$EXT_UUID"
  rm -rf "$DATA_HOME/gnome-shell/extensions/$EXT_UUID"

  gsettings_list_remove org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$KEYBINDING"
  schema="org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$KEYBINDING"
  for key in name command binding; do
    gsettings reset "$schema" "$key"
  done
  # Give Super+V back to the notification list, if it's still how install.sh left it.
  if [ "$(gsettings get org.gnome.shell.keybindings toggle-message-tray)" = "['<Super>m']" ]; then
    gsettings reset org.gnome.shell.keybindings toggle-message-tray
  fi
fi

if command -v xfconf-query >/dev/null; then
  xfconf-query -c xfce4-keyboard-shortcuts -p "/commands/custom/<Super>v" -r 2>/dev/null || true
fi

if $purge; then
  echo "Deleting clipboard history and settings..."
  rm -rf "$DATA_HOME/copyshelf" "$CONFIG_HOME/copyshelf" "$STATE_HOME/copyshelf"
else
  echo "Kept your history ($DATA_HOME/copyshelf) and settings ($CONFIG_HOME/copyshelf)."
  echo "To delete them too:  rm -rf \"$DATA_HOME/copyshelf\" \"$CONFIG_HOME/copyshelf\""
fi
echo "Copyshelf has been removed."
