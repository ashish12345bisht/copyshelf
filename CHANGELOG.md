# Changelog

What changed in each version of Copyshelf. The section for a version is what users see
under "What's new" when Copyshelf offers them the update, so write it for them.

To release a new version: add a section at the top like the one below, then run
`./release.sh X.Y.Z`. Use `### Added`, `### Changed` and `### Fixed` headings, and one
`- ` line per change.

## 0.2.0 - 2026-10-11

The first public release.

### Added
- Clipboard history: press Super+V to see your last 25 copies (text and images) and paste one.
- Pin items to keep them when you clear the history.
- Search, and full keyboard control (↑ ↓ Enter, Del, Esc).
- Automatic pasting into the app you were using, including terminals.
- Opens at the mouse pointer on GNOME and X11.
- Settings window: history size, auto-paste, keyboard shortcut, start at login, and more.
- Top-bar icon on GNOME, tray icon on other desktops.
- Copies that password managers mark as secret are not saved.
- Works on GNOME, KDE Plasma, Sway, Hyprland and X11 desktops.
- Lets you know when a new version is available, and updates in one click.
