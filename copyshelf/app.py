"""The background daemon: wires history, clipboard backend, paster and popup together."""
import logging
import signal

from copyshelf import __version__, config, ipc, migrate, updates
from copyshelf._gi import Gdk, GLib, Gtk, unix_signal_add
from copyshelf.clipboard import create_backend
from copyshelf.clipboard import wl as wl_clipboard
from copyshelf.desktop import clipboard_method, detect, paste_methods, popup_placement
from copyshelf.history import History
from copyshelf.notify import notify
from copyshelf.paste import PasteManager
from copyshelf.ui.popup import ClipWindow, install_css
from copyshelf.ui.settings import SettingsWindow
from copyshelf.ui.tray import Tray
from copyshelf.ui.update_window import UpdateWindow, show_message

log = logging.getLogger(__name__)

PASTE_DELAY_MS = 200   # time for focus to return to the app before we press Ctrl+V


class App:
    def __init__(self):
        # Our windows' WM_CLASS / app id, so the desktop shows "Copyshelf" with our icon.
        GLib.set_prgname("copyshelf")
        Gdk.set_program_class("Copyshelf")
        self.cfg = config.load_config()
        self.desktop = detect()
        log.info("Desktop: %s", self.desktop)

        self.history = History(config.data_dir(), self.cfg["max_items"])
        self.paster = PasteManager(paste_methods(self.desktop, self.cfg["paste_method"]))

        install_css()
        Gtk.Window.set_default_icon_name("copyshelf")
        self.win = ClipWindow(self.history, self.on_pick, self.show_settings)
        self.settings_win = None   # created the first time it's opened

        # GNOME gets a top-bar icon from our extension instead, so don't show two.
        self.tray = None
        if self.desktop.name != "gnome":
            self.tray = Tray(on_show=self.win.show_popup, on_settings=self.show_settings,
                             on_clear=self.clear_history, on_check_updates=self.check_updates_now)

        method = clipboard_method(self.desktop, wl_clipboard.available())
        self.clipboard = None
        self.start_clipboard(method)
        self.apply_settings()

        self.updates = updates.UpdateChecker(enabled=lambda: self.cfg["check_updates"],
                                             on_found=self.offer_update)
        self.updates.start()
        self.update_win = None
        self.announce_if_updated()

    # ----- clipboard -----
    def start_clipboard(self, method):
        self.clipboard = create_backend(method)
        self.clipboard.skip_sensitive = self.cfg["skip_sensitive"]
        self.clipboard.start(self.on_text, self.on_image, self.on_clipboard_failed)
        log.info("Clipboard backend: %s", self.clipboard.name)

    def on_clipboard_failed(self):
        if self.clipboard.name != "gtk":
            log.warning("Falling back to the GTK clipboard backend")
            self.start_clipboard("gtk")
        return False

    def on_text(self, text):
        if self.history.add_text(text):
            self.refresh_if_visible()
        return False

    def on_image(self, png_bytes):
        if self.history.add_image(png_bytes):
            self.refresh_if_visible()
        return False

    def refresh_if_visible(self):
        if self.win.get_visible():
            self.win.refresh()

    # ----- settings -----
    def set_setting(self, key, value):
        """Called by the settings window: save, then apply right away."""
        self.cfg[key] = value
        config.save_config(self.cfg)
        self.apply_settings()

    def apply_settings(self):
        if self.history.max_items != self.cfg["max_items"]:
            self.history.set_max_items(self.cfg["max_items"])
        self.clipboard.skip_sensitive = self.cfg["skip_sensitive"]
        self.win.set_placement(popup_placement(self.desktop, self.cfg["popup_at_pointer"]))
        if self.tray:
            self.tray.set_visible(self.cfg["show_tray_icon"])
        # (auto_paste is read each time an item is picked.)

    def show_settings(self):
        if self.settings_win is None:
            self.settings_win = SettingsWindow(self)
        self.settings_win.present_settings()
        return False

    def clear_history(self):
        self.history.clear_unpinned()
        self.refresh_if_visible()
        return False

    # ----- updates -----
    def offer_update(self, release):
        """A newer version was found by the automatic check: tell the user, gently."""
        notify(f"Copyshelf {release.version} is available",
               "See what's new, and update if you like.",
               actions=[("default", "See what's new"), ("show", "See what's new")],
               on_action=lambda _key: self.show_update_window(release), timeout_ms=0)

    def show_update_window(self, release):
        if self.update_win:
            self.update_win.destroy()
        self.update_win = UpdateWindow(release, self.updates)
        self.update_win.show_all()
        self.update_win.present()
        return False

    def check_updates_now(self):
        """'Check for updates' from the menu or Settings: always answer, even if up to date."""
        def done(release):
            if release is None:
                show_message("Couldn't check for updates",
                             "GitHub couldn't be reached. Check your internet connection.")
            elif updates.is_newer(release.version, __version__):
                self.show_update_window(release)
            else:
                show_message("Copyshelf is up to date", f"You have the latest version, {__version__}.")
        self.updates.check(manual=True, on_done=done)
        return False

    def announce_if_updated(self):
        """First start after an update: say so, and whether a log out is still needed."""
        state = updates.load_state()
        if updates.just_updated(state):
            body = "Enjoy the new version."
            if self.desktop.name == "gnome" and self.desktop.wayland:
                from copyshelf.paste.gnome_extension import needs_relogin
                if needs_relogin():
                    body = "Log out and back in once to finish the update."
            notify(f"Copyshelf was updated to {__version__}", body)
        if state.get("last_run_version") != __version__:
            state["last_run_version"] = __version__
            updates.save_state(state)

    # ----- picking an item -----
    def on_pick(self, item):
        if not self.clipboard.set_item(item):
            return
        self.win.hide()
        if self.cfg["auto_paste"]:
            GLib.timeout_add(PASTE_DELAY_MS, self.paster.paste)

    # ----- commands from `copyshelf --show` etc. (called on the IPC thread) -----
    def handle_command(self, cmd):
        if cmd == "show":
            GLib.idle_add(self.win.toggle)
        elif cmd == "settings":
            GLib.idle_add(self.show_settings)
        elif cmd == "clear":
            GLib.idle_add(self.clear_history)
        elif cmd == "check-updates":
            GLib.idle_add(self.check_updates_now)
        elif cmd == "quit":
            GLib.idle_add(Gtk.main_quit)
        elif cmd != "ping":
            return "error: unknown command"
        return "ok"


def run(show=False, settings=False, check_updates=False):
    migrate.move_old_data()
    lock = ipc.acquire_instance_lock()
    if lock is None:
        print("Copyshelf is already running. Use `copyshelf --show` to open it.")
        return 1

    app = App()
    server = ipc.Server(app.handle_command)
    try:
        server.start()
    except OSError as e:   # e.g. "AF_UNIX path too long" with an unusual XDG_RUNTIME_DIR
        log.error("Cannot create the command socket %s: %s", server.path, e)
        return 1
    # Ctrl+C in a terminal, or `kill`, shuts down cleanly (removes the socket).
    for sig in (signal.SIGINT, signal.SIGTERM):
        unix_signal_add(GLib.PRIORITY_DEFAULT, sig, Gtk.main_quit)
    if show:
        GLib.idle_add(app.win.show_popup)
    if settings:
        GLib.idle_add(app.show_settings)
    if check_updates:
        GLib.idle_add(app.check_updates_now)

    log.info("Copyshelf running. History: %s", app.history.file)
    try:
        Gtk.main()
    finally:
        server.close()
        if hasattr(app.clipboard, "stop"):
            app.clipboard.stop()
        lock.close()
    return 0
