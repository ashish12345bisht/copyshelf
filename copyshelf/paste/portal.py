"""Paste through the RemoteDesktop portal. Default on KDE Plasma (Wayland).

The portal is the official Wayland way for an app to send keys to other apps. The desktop
asks the user for permission the first time. We ask it to remember the answer
("persist_mode" 2) and save the "restore token" it gives back, so later sessions start
without asking again.

The portal answers asynchronously: each call returns a "request" object path, and the
answer arrives later as a Response signal on that path. The steps are:
    CreateSession -> SelectDevices (keyboard; restore token) -> Start (may ask the user)
After that, NotifyKeyboardKeysym presses keys directly. We keep the session open while
Copyshelf runs, so only the first paste after startup waits for the portal.
"""
import logging
import os
import uuid

from copyshelf._gi import Gio, GLib
from copyshelf.config import config_dir

log = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"

KEYBOARD = 1               # device type bit
PERSIST_UNTIL_REVOKED = 2  # persist_mode
RESPONSE_OK = 0
PRESSED, RELEASED = 1, 0
XK_CONTROL_L, XK_V = 0xFFE3, 0x0076   # keysyms (key names), so it's Ctrl+V on any layout


def token_path():
    return os.path.join(config_dir(), "portal_token")


def _load_token():
    try:
        with open(token_path(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _save_token(token):
    os.makedirs(config_dir(), exist_ok=True)
    # 0600: the token lets this user's apps skip the permission dialog, so keep it private.
    fd = os.open(token_path(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)


def reset_permission():
    """Forget the saved token, so the portal asks again next time."""
    try:
        os.remove(token_path())
        return True
    except FileNotFoundError:
        return False


class PortalPaster:
    name = "portal"

    def __init__(self, on_failed):
        self.on_failed = on_failed   # called if a queued paste can't happen (e.g. user said no)
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.session = None
        self.starting = False
        self.pending = False
        self.denied = False

    def available(self):
        try:
            self.bus.call_sync(BUS_NAME, OBJECT_PATH, "org.freedesktop.DBus.Properties", "Get",
                               GLib.Variant("(ss)", (REMOTE_DESKTOP, "version")),
                               None, Gio.DBusCallFlags.NONE, 1000, None)
            return True
        except GLib.Error:
            return False

    def paste(self):
        if self.denied:
            return False   # user said no this session: don't pop the dialog on every paste
        if self.session:
            self._press_ctrl_v()
            return True
        self.pending = True
        if not self.starting:
            self.starting = True
            self._create_session()
        return True   # the paste happens once the session is ready

    # ----- portal plumbing -----
    def _request(self, method, signature, args, options, on_ok):
        """Call a portal method and run on_ok(results) when its Response arrives."""
        token = "copyshelf_" + uuid.uuid4().hex[:8]
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        sub_id = None

        def on_response(_bus, _sender, _path, _iface, _signal, params):
            self.bus.signal_unsubscribe(sub_id)
            code, results = params.unpack()
            if code == RESPONSE_OK:
                on_ok(results)
            else:
                self._fail(f"{method} was cancelled or denied (code {code})", denied=code == 1)

        # Subscribe before calling, so we can't miss a fast answer.
        sub_id = self.bus.signal_subscribe(BUS_NAME, "org.freedesktop.portal.Request", "Response",
                                           request_path, None, Gio.DBusSignalFlags.NONE,
                                           on_response)
        options = dict(options, handle_token=GLib.Variant("s", token))

        def on_called(bus, result):
            try:
                bus.call_finish(result)
            except GLib.Error as e:
                self.bus.signal_unsubscribe(sub_id)
                self._fail(f"{method} failed: {e.message}")

        self.bus.call(BUS_NAME, OBJECT_PATH, REMOTE_DESKTOP, method,
                      GLib.Variant(signature, (*args, options)), None,
                      Gio.DBusCallFlags.NONE, -1, None, on_called)

    def _create_session(self):
        self._request("CreateSession", "(a{sv})", (),
                      {"session_handle_token": GLib.Variant("s", "copyshelf_" + uuid.uuid4().hex[:8])},
                      self._on_session_created)

    def _on_session_created(self, results):
        self.session_path = results["session_handle"]
        options = {"types": GLib.Variant("u", KEYBOARD),
                   "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED)}
        token = _load_token()
        if token:
            options["restore_token"] = GLib.Variant("s", token)
        self._request("SelectDevices", "(oa{sv})", (self.session_path,), options,
                      self._on_devices_selected)

    def _on_devices_selected(self, _results):
        self._request("Start", "(osa{sv})", (self.session_path, ""), {}, self._on_started)

    def _on_started(self, results):
        if "restore_token" in results:   # tokens are single-use: always save the new one
            _save_token(results["restore_token"])
        self.session = self.session_path
        self.starting = False
        # If the user (or desktop) ends the session, start a new one on the next paste.
        self.bus.signal_subscribe(BUS_NAME, "org.freedesktop.portal.Session", "Closed",
                                  self.session, None, Gio.DBusSignalFlags.NONE,
                                  lambda *a: setattr(self, "session", None))
        log.info("RemoteDesktop portal session ready")
        if self.pending:
            self.pending = False
            self._press_ctrl_v()

    def _fail(self, message, denied=False):
        log.warning("Portal paste: %s", message)
        self.starting = False
        self.denied = denied
        if self.pending:
            self.pending = False
            self.on_failed()

    def _press_ctrl_v(self):
        for keysym, state in ((XK_CONTROL_L, PRESSED), (XK_V, PRESSED),
                              (XK_V, RELEASED), (XK_CONTROL_L, RELEASED)):
            self.bus.call(BUS_NAME, OBJECT_PATH, REMOTE_DESKTOP, "NotifyKeyboardKeysym",
                          GLib.Variant("(oa{sv}iu)", (self.session, {}, keysym, state)),
                          None, Gio.DBusCallFlags.NONE, -1, None, None)
