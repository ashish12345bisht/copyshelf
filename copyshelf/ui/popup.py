"""The popup window: the list you see after pressing Super+V."""
from copyshelf._gi import Gdk, GdkPixbuf, GdkX11, GLib, Gtk, Pango

CSS = b"""
window.copyshelf { background-color: @theme_bg_color; border: 1px solid alpha(@theme_fg_color, 0.18); }
.copyshelf-title { font-weight: bold; font-size: 15px; }
list { background-color: transparent; }
row { border-radius: 8px; margin: 3px 2px; background-color: alpha(@theme_fg_color, 0.05); }
row:selected { background-color: alpha(@theme_selected_bg_color, 0.85); }
.pin-off { opacity: 0.35; }
row.pinned { border-left: 3px solid @theme_selected_bg_color; }
.icon-btn { padding: 2px 6px; min-height: 0; min-width: 0; }
"""


def install_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


# Our GNOME Shell extension moves windows with this role to the mouse pointer.
ROLE_AT_POINTER = "copyshelf-popup-at-pointer"
ROLE_DEFAULT = "copyshelf-popup"


class ClipWindow(Gtk.Window):
    """`on_pick(item)` is called when the user chooses an item (Enter or click).
    `on_settings()` is called when the user clicks the settings button."""

    def __init__(self, history, on_pick, on_settings):
        super().__init__(title="Clipboard")
        self.history = history
        self.on_pick = on_pick
        self.on_settings = on_settings
        self.had_focus = False
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_placement("center")
        self.set_default_size(380, 460)
        self.set_resizable(False)
        self.get_style_context().add_class("copyshelf")

        self.connect("delete-event", lambda *a: self.hide() or True)
        self.connect("key-press-event", self.on_key)
        self.connect("focus-in-event", self.on_focus_in)
        self.connect("focus-out-event", self.on_focus_out)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_border_width(12)

        header = Gtk.Box(spacing=8)
        title = Gtk.Label(label="Clipboard", xalign=0)
        title.get_style_context().add_class("copyshelf-title")
        clear_btn = Gtk.Button(label="Clear all")
        clear_btn.set_tooltip_text("Remove everything except pinned items")
        clear_btn.set_can_focus(False)
        clear_btn.connect("clicked", self.on_clear)
        settings_btn = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.BUTTON)
        settings_btn.set_tooltip_text("Settings")
        settings_btn.set_relief(Gtk.ReliefStyle.NONE)
        settings_btn.set_can_focus(False)
        settings_btn.connect("clicked", lambda b: (self.hide(), self.on_settings()))
        header.pack_start(title, True, True, 0)
        header.pack_end(settings_btn, False, False, 0)
        header.pack_end(clear_btn, False, False, 0)

        self.search = Gtk.SearchEntry(placeholder_text="Search history…")
        self.search.connect("search-changed", self.on_search_changed)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.listbox.set_filter_func(self.filter_row)
        self.listbox.connect("row-activated", lambda lb, row: self.paste_item(row.item_id))
        placeholder = Gtk.Label(label="Nothing here yet.\nCopy something and it will show up here.")
        placeholder.set_justify(Gtk.Justification.CENTER)
        placeholder.set_margin_top(40)
        placeholder.show()
        self.listbox.set_placeholder(placeholder)

        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.add(self.listbox)

        hint = Gtk.Label(label="Enter: paste   ↑↓: move   Del: remove   Esc: close", xalign=0)
        hint.set_opacity(0.55)

        outer.pack_start(header, False, False, 0)
        outer.pack_start(self.search, False, False, 0)
        outer.pack_start(self.scroller, True, True, 0)
        outer.pack_start(hint, False, False, 0)
        self.add(outer)

    def set_placement(self, mode):
        """mode: 'extension', 'gtk-mouse' or 'center' (see copyshelf.desktop.popup_placement).
        For 'extension', GTK still asks for the centre, and the extension then moves the
        window to the pointer before it's drawn; if the extension isn't running, you
        simply get the centre."""
        self.set_position(Gtk.WindowPosition.MOUSE if mode == "gtk-mouse"
                          else Gtk.WindowPosition.CENTER)
        self.set_role(ROLE_AT_POINTER if mode == "extension" else ROLE_DEFAULT)

    # ----- building rows -----
    def refresh(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        for item in self.history.items:
            self.listbox.add(self.build_row(item))
        self.listbox.show_all()
        self.select_first_visible()

    def build_row(self, item):
        row = Gtk.ListBoxRow()
        row.item_id = item["id"]
        if item["pinned"]:
            row.get_style_context().add_class("pinned")
        box = Gtk.Box(spacing=6)
        box.set_border_width(8)

        if item["type"] == "text":
            content = Gtk.Label(label=item["text"].strip()[:600], xalign=0)
            content.set_line_wrap(True)
            content.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            content.set_lines(3)
            content.set_ellipsize(Pango.EllipsizeMode.END)
            content.set_max_width_chars(36)
        else:
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(item["path"], 270, 140, True)
                content = Gtk.Image.new_from_pixbuf(pb)
                content.set_halign(Gtk.Align.START)
            except GLib.Error:
                content = Gtk.Label(label="[image unavailable]", xalign=0)
        box.pack_start(content, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pin = Gtk.Button(label="📌")
        pin.set_tooltip_text("Unpin" if item["pinned"] else "Pin (keeps it after Clear all)")
        delete = Gtk.Button(label="✕")
        delete.set_tooltip_text("Delete")
        for btn in (pin, delete):
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.set_can_focus(False)
            btn.get_style_context().add_class("icon-btn")
        if not item["pinned"]:
            pin.get_style_context().add_class("pin-off")
        pin.connect("clicked", lambda b: self.on_pin(item["id"]))
        delete.connect("clicked", lambda b: self.delete_item(item["id"]))
        actions.pack_start(pin, False, False, 0)
        actions.pack_start(delete, False, False, 0)
        box.pack_end(actions, False, False, 0)

        row.add(box)
        return row

    # ----- filtering / selection -----
    def filter_row(self, row):
        q = self.search.get_text().strip().lower()
        if not q:
            return True
        item = self.history.get(row.item_id)
        if not item:
            return False
        if item["type"] == "image":
            # Images have no text, so match them by what you'd call them.
            return any(word.startswith(q) for word in ("image", "picture", "screenshot", "photo"))
        return q in item["text"].lower()

    def on_search_changed(self, entry):
        self.listbox.invalidate_filter()
        self.select_first_visible()

    def visible_rows(self):
        return [r for r in self.listbox.get_children() if r.get_child_visible()]

    def select_first_visible(self):
        rows = self.visible_rows()
        if rows:
            self.listbox.select_row(rows[0])
            self.scroller.get_vadjustment().set_value(0)

    def move_selection(self, step):
        rows = self.visible_rows()
        if not rows:
            return
        current = self.listbox.get_selected_row()
        idx = rows.index(current) if current in rows else -1
        idx = max(0, min(len(rows) - 1, idx + step))
        row = rows[idx]
        self.listbox.select_row(row)
        alloc = row.get_allocation()
        self.scroller.get_vadjustment().clamp_page(alloc.y, alloc.y + alloc.height)

    # ----- actions -----
    def paste_item(self, item_id):
        item = self.history.get(item_id)
        if item:
            self.on_pick(item)

    def delete_item(self, item_id):
        self.history.delete(item_id)
        self.refresh()

    def on_pin(self, item_id):
        self.history.toggle_pin(item_id)
        self.refresh()

    def on_clear(self, *a):
        self.history.clear_unpinned()
        self.refresh()

    # ----- show / hide -----
    def toggle(self):
        if self.get_visible():
            self.hide()
        else:
            self.show_popup()
        return False

    def show_popup(self):
        self.search.set_text("")
        self.refresh()
        self.had_focus = False
        self.show_all()
        self.search.grab_focus()
        ts = Gtk.get_current_event_time()
        gdk_win = self.get_window()
        if GdkX11 and gdk_win is not None and isinstance(gdk_win, GdkX11.X11Window):
            ts = GdkX11.x11_get_server_time(gdk_win)
        self.present_with_time(ts)
        return False

    def on_focus_in(self, *a):
        self.had_focus = True
        return False

    def on_focus_out(self, *a):
        # Close when the user clicks elsewhere.
        if self.had_focus:
            GLib.timeout_add(120, lambda: (not self.is_active() and self.hide()) and False)
        return False

    def on_key(self, widget, event):
        k = event.keyval
        if k == Gdk.KEY_Escape:
            self.hide()
            return True
        if k in (Gdk.KEY_Down, Gdk.KEY_Up):
            self.move_selection(1 if k == Gdk.KEY_Down else -1)
            return True
        if k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            row = self.listbox.get_selected_row()
            if row:
                self.paste_item(row.item_id)
            return True
        if k == Gdk.KEY_Delete and not self.search.get_text():
            row = self.listbox.get_selected_row()
            if row:
                self.delete_item(row.item_id)
            return True
        return False
