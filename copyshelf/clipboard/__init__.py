"""Clipboard backends: watch for copies, and put a history item back on the clipboard.

Every backend has the same small interface:
    backend.start(on_text, on_image, on_failed)   # on_text(str), on_image(png_bytes), on_failed()
    backend.set_item(item) -> bool                 # item is a history dict
    backend.skip_sensitive                         # True: ignore copies marked as passwords
"""

# Clipboard formats that password managers (KeePassXC, KDE apps, ...) add to mark a copied
# secret. If one of these is present, the copy is not saved to history.
SENSITIVE_TYPES = {"x-kde-passwordManagerHint"}


def is_sensitive(types):
    return bool(SENSITIVE_TYPES & set(types))


def create_backend(method):
    """method: 'gtk' or 'wl-clipboard' (see copyshelf.desktop.clipboard_method)."""
    if method == "wl-clipboard":
        from copyshelf.clipboard.wl import WlClipboard
        return WlClipboard()
    from copyshelf.clipboard.gtk import GtkClipboard
    return GtkClipboard()
