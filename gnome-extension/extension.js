// Copyshelf helper: runs inside GNOME Shell and does the things a normal app isn't allowed
// to do on Wayland:
//   1. Paste: press Ctrl+V in the focused app (no "Remote Interaction" dialog).
//   2. Move Copyshelf's popup to the mouse pointer (apps can't see or set positions on Wayland).
//   3. Show a top-bar icon with a menu (GNOME has no tray of its own).
//
// Pasting is a D-Bus method on GNOME Shell's own bus name:
//   bus name:  org.gnome.Shell
//   path:      /io/github/Copyshelf
//   method:    io.github.Copyshelf.Paste()
// Paste() can only press Ctrl+V (Ctrl+Shift+V in terminals), so other programs can't use it to type arbitrary keys.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

const IFACE_XML = `
<node>
  <interface name="io.github.Copyshelf">
    <method name="Paste"/>
    <method name="GetVersion">
      <arg type="s" direction="out" name="version"/>
    </method>
  </interface>
</node>`;

const OBJECT_PATH = '/io/github/Copyshelf';

// Copyshelf gives its popup this window role when it should open at the mouse pointer.
const POPUP_ROLE = 'copyshelf-popup-at-pointer';

// Terminals paste with Ctrl+Shift+V (plain Ctrl+V is a control character there).
// Main check: the app's .desktop file lists "TerminalEmulator" in Categories.
// Backup: known window class names (lowercased), for apps without a proper .desktop file.
const TERMINALS = [
    'org.gnome.ptyxis', 'org.gnome.terminal', 'gnome-terminal', 'gnome-terminal-server',
    'org.gnome.console', 'kgx', 'kitty', 'alacritty', 'com.mitchellh.ghostty',
    'org.wezfurlong.wezterm', 'foot', 'tilix', 'com.gexperts.tilix', 'terminator',
    'org.kde.konsole', 'konsole',
];

function focusedAppIsTerminal() {
    const win = global.display.focus_window;
    const wmClass = win?.get_wm_class()?.toLowerCase() ?? '';
    const app = win ? Shell.WindowTracker.get_default().get_window_app(win) : null;
    const categories = app?.get_app_info()?.get_categories() ?? '';
    const isTerminal = categories.split(';').includes('TerminalEmulator') ||
        TERMINALS.includes(wmClass);
    // One line per paste, for troubleshooting:
    //   journalctl --user -b -o cat /usr/bin/gnome-shell | grep Copyshelf
    console.log(`Copyshelf: pasting into "${wmClass}" app=${app?.get_id()} (terminal: ${isTerminal})`);
    return isTerminal;
}

// The `copyshelf` command, for the top-bar menu.
function copyshelfCommand() {
    const local = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'copyshelf']);
    if (GLib.file_test(local, GLib.FileTest.IS_EXECUTABLE))
        return local;
    return GLib.find_program_in_path('copyshelf');
}

function runCopyshelf(arg) {
    const cmd = copyshelfCommand();
    if (!cmd) {
        Main.notify('Copyshelf', 'The copyshelf command was not found. Is Copyshelf installed?');
        return;
    }
    try {
        Gio.Subprocess.new([cmd, arg], Gio.SubprocessFlags.NONE);
    } catch (e) {
        console.error(`Copyshelf: could not run ${cmd} ${arg}: ${e.message}`);
    }
}

// Reads "show_tray_icon" from Copyshelf's settings file (shown unless set to false).
function iconWanted(configFile) {
    try {
        const [, bytes] = configFile.load_contents(null);
        return JSON.parse(new TextDecoder().decode(bytes)).show_tray_icon !== false;
    } catch {
        return true;   // no settings file yet, or unreadable: use the default
    }
}

export default class CopyshelfExtension extends Extension {
    enable() {
        // 1. A virtual keyboard owned by GNOME itself. Its key presses look like real ones to apps.
        const backend = global.stage.context?.get_backend?.() ?? Clutter.get_default_backend();
        this._keyboard = backend.get_default_seat()
            .create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);

        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this._dbus.export(Gio.DBus.session, OBJECT_PATH);

        // 2. Each time Copyshelf shows its popup, GNOME creates a new window object for it.
        this._windowCreatedId = global.display.connect('window-created',
            (_display, win) => this._onWindowCreated(win));

        // 3. Top-bar icon, shown or hidden live when the setting changes.
        this._configFile = Gio.File.new_for_path(
            GLib.build_filenamev([GLib.get_user_config_dir(), 'copyshelf', 'config.json']));
        this._configMonitor = this._configFile.monitor_file(Gio.FileMonitorFlags.NONE, null);
        this._configMonitor.connect('changed', () => this._syncIndicator());
        this._indicator = null;
        this._syncIndicator();
    }

    disable() {
        this._dbus?.unexport();
        this._dbus = null;
        this._keyboard = null;
        if (this._windowCreatedId) {
            global.display.disconnect(this._windowCreatedId);
            this._windowCreatedId = 0;
        }
        this._configMonitor?.cancel();
        this._configMonitor = null;
        this._indicator?.destroy();
        this._indicator = null;
    }

    // ----- popup at the pointer -----
    _onWindowCreated(win) {
        if (win.get_role() !== POPUP_ROLE)
            return;
        // Run once GNOME has sized and placed the window, but before it's drawn: no jump.
        global.compositor.get_laters().add(Meta.LaterType.BEFORE_REDRAW, () => {
            this._moveToPointer(win);
            return GLib.SOURCE_REMOVE;
        });
    }

    _moveToPointer(win) {
        if (!win.get_compositor_private())
            return;   // already closed again
        const [px, py] = global.get_pointer();
        const area = Main.layoutManager.getWorkAreaForMonitor(global.display.get_current_monitor());
        const frame = win.get_frame_rect();
        // Top-left corner at the pointer, but keep the whole popup on screen.
        const x = Math.max(area.x, Math.min(px, area.x + area.width - frame.width));
        const y = Math.max(area.y, Math.min(py, area.y + area.height - frame.height));
        win.move_frame(true, x, y);
    }

    // ----- top-bar icon -----
    _syncIndicator() {
        const wanted = iconWanted(this._configFile);
        if (wanted && !this._indicator) {
            this._indicator = new PanelMenu.Button(0.0, 'Copyshelf', false);
            this._indicator.add_child(new St.Icon({
                icon_name: 'edit-paste-symbolic',
                style_class: 'system-status-icon',
            }));
            const menu = this._indicator.menu;
            menu.addAction('Show clipboard history', () => runCopyshelf('--show'));
            menu.addAction('Settings', () => runCopyshelf('--settings'));
            menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            menu.addAction('Clear history', () => runCopyshelf('--clear'));
            menu.addAction('Check for updates', () => runCopyshelf('--check-updates'));
            Main.panel.addToStatusArea(this.uuid, this._indicator);
        } else if (!wanted && this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }
    }

    // Which extension version GNOME is running. Copyshelf compares it with the installed
    // files to tell whether a log out is needed to finish an update.
    GetVersion() {
        return String(this.metadata['version-name'] ?? '');
    }

    // Called over D-Bus by Copyshelf after it has put the chosen item on the clipboard.
    Paste() {
        // Keyvals (key names) rather than raw keycodes, so this is Ctrl+V on any keyboard layout.
        const now = GLib.get_monotonic_time();  // microseconds, as notify_keyval expects
        const press = Clutter.KeyState.PRESSED;
        const release = Clutter.KeyState.RELEASED;
        const modifiers = focusedAppIsTerminal()
            ? [Clutter.KEY_Control_L, Clutter.KEY_Shift_L]
            : [Clutter.KEY_Control_L];

        for (const key of modifiers)
            this._keyboard.notify_keyval(now, key, press);
        this._keyboard.notify_keyval(now, Clutter.KEY_v, press);
        this._keyboard.notify_keyval(now, Clutter.KEY_v, release);
        for (const key of modifiers.reverse())
            this._keyboard.notify_keyval(now, key, release);
    }
}
