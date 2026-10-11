"""The settings window. Every change is saved and applied right away."""
from copyshelf import autostart, hotkey
from copyshelf._gi import Gdk, Gtk


class SettingsWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(title="Copyshelf Settings")
        self.app = app
        self.loading = False   # True while refresh() fills in values: don't save those back
        self.hotkey_kind = hotkey.kind(app.desktop)
        self.set_icon_name("copyshelf")
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        self.set_role("copyshelf-settings")
        self.connect("delete-event", lambda *a: self.hide() or True)

        grid = Gtk.Grid(column_spacing=32, row_spacing=16)
        grid.set_border_width(20)
        self.row = 0

        def add(title, subtitle, widget):
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            labels.pack_start(Gtk.Label(label=title, xalign=0), False, False, 0)
            if subtitle:
                sub = Gtk.Label(label=subtitle, xalign=0)
                sub.set_line_wrap(True)
                sub.set_width_chars(40)
                sub.set_max_width_chars(40)
                sub.get_style_context().add_class("dim-label")
                labels.pack_start(sub, False, False, 0)
            widget.set_valign(Gtk.Align.CENTER)
            widget.set_halign(Gtk.Align.END)
            grid.attach(labels, 0, self.row, 1, 1)
            grid.attach(widget, 1, self.row, 1, 1)
            self.row += 1

        self.size = Gtk.SpinButton.new_with_range(1, 500, 1)
        self.size.connect("value-changed", self.on_size)
        add("History size", "Unpinned items to keep. Pinned items are always kept.", self.size)

        self.switches = {}
        for key, title, subtitle in [
            ("auto_paste", "Paste automatically",
             "Paste into your app after you pick an item. Off: it's only copied."),
            ("popup_at_pointer", "Open at the mouse pointer",
             "Otherwise the list opens in the middle of the screen."),
            ("skip_sensitive", "Ignore copied passwords",
             "Don't save copies that password managers mark as secret."),
            ("show_tray_icon", "Show icon in the top bar" if app.desktop.name == "gnome"
             else "Show tray icon", None),
        ]:
            switch = Gtk.Switch()
            switch.connect("notify::active", self.on_switch, key)
            self.switches[key] = switch
            add(title, subtitle, switch)

        self.autostart = Gtk.Switch()
        self.autostart.connect("notify::active", self.on_autostart)
        add("Start at login", None, self.autostart)

        self.hotkey_label = Gtk.Label()
        if self.hotkey_kind:
            box = Gtk.Box(spacing=8)
            change = Gtk.Button(label="Change…")
            change.connect("clicked", self.on_change_hotkey)
            box.pack_start(self.hotkey_label, False, False, 0)
            box.pack_start(change, False, False, 0)
            add("Keyboard shortcut", None, box)
        else:
            self.hotkey_label.set_selectable(True)
            self.hotkey_label.set_line_wrap(True)
            self.hotkey_label.set_max_width_chars(30)
            self.hotkey_label.set_markup(
                "Set it in your desktop's keyboard settings, with the command:\n"
                f"<tt>{autostart.launcher_command()} --show</tt>")
            add("Keyboard shortcut", None, self.hotkey_label)

        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda b: self.hide())
        close.set_halign(Gtk.Align.END)
        grid.attach(close, 0, self.row, 2, 1)
        self.add(grid)

    def on_size(self, spin):
        if not self.loading:
            self.app.set_setting("max_items", int(spin.get_value()))

    def on_switch(self, switch, _param, key):
        if not self.loading:
            self.app.set_setting(key, switch.get_active())

    def on_autostart(self, switch, _param):
        if not self.loading:
            autostart.set_enabled(switch.get_active())

    def refresh(self):
        """Show the current values."""
        self.loading = True
        cfg = self.app.cfg
        self.size.set_value(cfg["max_items"])
        for key, switch in self.switches.items():
            switch.set_active(cfg[key])
        self.autostart.set_active(autostart.is_enabled())
        if self.hotkey_kind:
            self.hotkey_label.set_text(hotkey.label(hotkey.get_binding(self.hotkey_kind)))
        self.loading = False

    def present_settings(self):
        self.refresh()
        self.show_all()
        self.present()
        return False

    # ----- changing the shortcut -----
    def on_change_hotkey(self, _button):
        accel = capture_shortcut(self)
        if accel:
            hotkey.set_binding(self.hotkey_kind, accel, f"{autostart.launcher_command()} --show")
            self.hotkey_label.set_text(hotkey.label(accel))


def capture_shortcut(parent):
    """Show a small dialog that waits for a key combination. Returns it as an accelerator
    string like '<Super>v', or None if cancelled."""
    dialog = Gtk.Dialog(title="New shortcut", transient_for=parent, modal=True)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    label = Gtk.Label(label="Press the new shortcut, for example Super+V.\n"
                            "It needs Ctrl, Alt or Super. Esc cancels.")
    label.set_justify(Gtk.Justification.CENTER)
    label.set_margin_top(24)
    label.set_margin_bottom(24)
    label.set_margin_start(24)
    label.set_margin_end(24)
    dialog.get_content_area().add(label)
    result = {}

    def on_key(_widget, event):
        if event.is_modifier:
            return True   # wait for the real key
        if event.keyval == Gdk.KEY_Escape:
            dialog.response(Gtk.ResponseType.CANCEL)
            return True
        # Turn the raw modifier bits (e.g. Mod4) into named ones (Super) GTK understands.
        state = Gdk.Keymap.get_for_display(dialog.get_display()).add_virtual_modifiers(event.state)
        mods = state & Gtk.accelerator_get_default_mod_mask()
        if not mods & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK
                       | Gdk.ModifierType.SUPER_MASK):
            label.set_text("That needs Ctrl, Alt or Super too.\nTry again, or press Esc.")
            return True
        result["accel"] = Gtk.accelerator_name(Gdk.keyval_to_lower(event.keyval), mods)
        dialog.response(Gtk.ResponseType.OK)
        return True

    dialog.connect("key-press-event", on_key)
    dialog.show_all()
    response = dialog.run()
    dialog.destroy()
    return result.get("accel") if response == Gtk.ResponseType.OK else None
