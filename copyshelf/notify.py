"""Desktop notifications, sent straight to the notification service over D-Bus.

Notifications can have buttons ("actions"). When the user clicks one, the service sends an
ActionInvoked signal with the notification's id and the action's key, and we call back.
"""
import logging

from copyshelf import APP_ID
from copyshelf._gi import Gio, GLib

log = logging.getLogger(__name__)

BUS_NAME = "org.freedesktop.Notifications"
OBJECT_PATH = "/org/freedesktop/Notifications"
INTERFACE = "org.freedesktop.Notifications"

_callbacks = {}         # notification id -> on_action(action_key)
_subscription = None


def _on_action_invoked(_bus, _sender, _path, _iface, _signal, params):
    notification_id, action_key = params.unpack()
    callback = _callbacks.pop(notification_id, None)
    if callback:
        callback(action_key)


def notify(summary, body="", icon="copyshelf", actions=None, on_action=None, timeout_ms=5000):
    """Show a notification. `actions` is a list of (key, label) buttons; clicking one calls
    on_action(key). "default" is the key for clicking the notification itself.
    Returns True if it was shown."""
    global _subscription
    flat_actions = [part for key, label in (actions or []) for part in (key, label)]
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        if on_action and _subscription is None:
            _subscription = bus.signal_subscribe(BUS_NAME, INTERFACE, "ActionInvoked", OBJECT_PATH,
                                                 None, Gio.DBusSignalFlags.NONE, _on_action_invoked)
        reply = bus.call_sync(
            BUS_NAME, OBJECT_PATH, INTERFACE, "Notify",
            GLib.Variant("(susssasa{sv}i)",
                         (APP_ID, 0, icon, summary, body, flat_actions, {}, timeout_ms)),
            GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error as e:
        log.warning("Could not show notification: %s", e.message)
        return False
    if on_action:
        _callbacks[reply.unpack()[0]] = on_action
    return True
