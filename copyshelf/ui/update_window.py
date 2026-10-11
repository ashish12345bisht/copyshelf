"""The "new version available" window: what's new, and Update now / Remind me later / Skip."""
import re
import threading

from copyshelf import __version__, updates
from copyshelf._gi import GLib, Gtk, Pango


def format_notes(buffer, notes):
    """Show Markdown-ish release notes nicely: '## Added' headings in bold, '- ' as bullets.
    (Only the bits a changelog uses; anything else is shown as plain text.)"""
    bold = buffer.create_tag("heading", weight=Pango.Weight.BOLD, pixels_above_lines=8)
    buffer.set_text("")
    lines = notes.strip().splitlines() or ["No release notes."]
    for i, line in enumerate(lines):
        end = buffer.get_end_iter()
        newline = "\n" if i < len(lines) - 1 else ""
        heading = re.match(r"^#+\s*(.*)", line)
        if heading:
            buffer.insert_with_tags(end, heading.group(1) + newline, bold)
            continue
        line = re.sub(r"^\s*[-*]\s+", "  •  ", line)
        line = re.sub(r"\*\*(.+?)\*\*|`(.+?)`", lambda m: m.group(1) or m.group(2), line)
        buffer.insert(end, line + newline)


class UpdateWindow(Gtk.Window):
    def __init__(self, release, checker):
        super().__init__(title="Copyshelf update")
        self.release = release
        self.checker = checker
        self.set_icon_name("copyshelf")
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(480, 440)
        self.set_role("copyshelf-update")
        self.set_keep_above(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(20)

        title = Gtk.Label(xalign=0)
        title.set_markup(f"<big><b>Copyshelf {release.version} is available</b></big>")
        current = Gtk.Label(label=f"You have version {__version__}.", xalign=0)
        current.get_style_context().add_class("dim-label")

        notes_title = Gtk.Label(xalign=0)
        notes_title.set_markup("<b>What's new</b>")
        notes = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD)
        notes.set_left_margin(10)
        notes.set_right_margin(10)
        notes.set_top_margin(6)
        notes.set_bottom_margin(10)
        format_notes(notes.get_buffer(), release.notes)
        scroller = Gtk.ScrolledWindow()
        scroller.set_shadow_type(Gtk.ShadowType.IN)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(notes)

        link = Gtk.LinkButton.new_with_label(release.page_url, "View this release on GitHub")
        link.set_halign(Gtk.Align.START)

        self.status = Gtk.Label(xalign=0)
        self.status.set_line_wrap(True)
        if release.needs_relogin:
            self.status.set_text("After updating, log out and back in once to finish.")
        self.spinner = Gtk.Spinner()
        status_row = Gtk.Box(spacing=8)
        status_row.pack_start(self.spinner, False, False, 0)
        status_row.pack_start(self.status, True, True, 0)

        buttons = Gtk.Box(spacing=8)
        self.skip_btn = Gtk.Button(label="Skip this version")
        self.later_btn = Gtk.Button(label="Remind me later")
        self.update_btn = Gtk.Button(label="Update now")
        self.update_btn.get_style_context().add_class("suggested-action")
        self.skip_btn.connect("clicked", self.on_skip)
        self.later_btn.connect("clicked", self.on_later)
        self.update_btn.connect("clicked", self.on_update)
        buttons.pack_start(self.skip_btn, False, False, 0)
        buttons.pack_end(self.update_btn, False, False, 0)
        buttons.pack_end(self.later_btn, False, False, 0)

        box.pack_start(title, False, False, 0)
        box.pack_start(current, False, False, 0)
        box.pack_start(notes_title, False, False, 6)
        box.pack_start(scroller, True, True, 0)
        box.pack_start(link, False, False, 0)
        box.pack_start(status_row, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        self.add(box)
        # Closing the window counts as "remind me later", so it doesn't nag again today.
        self.connect("delete-event", lambda *a: self.on_later())

    def on_skip(self, *_):
        self.checker.skip(self.release.version)
        self.destroy()

    def on_later(self, *_):
        self.checker.remind_later()
        self.destroy()
        return False

    def on_update(self, *_):
        for button in (self.skip_btn, self.later_btn, self.update_btn):
            button.set_sensitive(False)
        self.spinner.start()
        self.status.set_text("Downloading…")
        threading.Thread(target=self._download, daemon=True).start()

    def _download(self):   # runs on a background thread
        try:
            source = updates.download_release(self.release)
        except (OSError, ValueError) as e:
            GLib.idle_add(self._failed, str(e))
            return
        GLib.idle_add(self._install, source)

    def _install(self, source):
        try:
            updates.start_install(source)
        except OSError as e:
            return self._failed(str(e))
        # The installer stops this Copyshelf and starts the new one, which then says
        # "Updated to …". This window disappears along with this process.
        self.status.set_text("Installing… Copyshelf will restart in a moment.")
        return False

    def _failed(self, error):
        self.spinner.stop()
        self.status.set_text(f"The update didn't work: {error}\n"
                             "Check your internet connection and try again.")
        for button in (self.skip_btn, self.later_btn, self.update_btn):
            button.set_sensitive(True)
        return False


def show_message(title, body):
    """A small 'You're up to date' style message box."""
    dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
                               text=title)
    dialog.format_secondary_text(body)
    dialog.set_keep_above(True)
    dialog.connect("response", lambda d, _r: d.destroy())
    dialog.show()
