"""Clipboard history: a list of items saved as JSON, with images saved as PNG files.

This module is plain Python (no GTK), so it can be unit-tested anywhere.

Each item is a dict:
    {"id": "...", "key": "t:<sha1>" or "i:<sha1>", "type": "text" or "image",
     "pinned": False, "ts": 1700000000.0, "text": "..."}   # or "path": "/.../images/<sha1>.png"
"key" is a hash of the content, used to spot duplicates.
"""
import hashlib
import json
import logging
import os
import time
import uuid

log = logging.getLogger(__name__)

MAX_TEXT_LEN = 200_000   # characters stored per text item


def _valid_item(item):
    """True if a loaded item has every field we rely on (protects against hand-edited files)."""
    if not isinstance(item, dict):
        return False
    common = (isinstance(item.get("id"), str) and isinstance(item.get("key"), str)
              and isinstance(item.get("pinned"), bool) and isinstance(item.get("ts"), (int, float)))
    if not common:
        return False
    if item.get("type") == "text":
        return isinstance(item.get("text"), str)
    if item.get("type") == "image":
        return isinstance(item.get("path"), str) and os.path.isfile(item["path"])
    return False


class History:
    def __init__(self, data_dir, max_items=25):
        self.data_dir = data_dir
        self.img_dir = os.path.join(data_dir, "images")
        self.file = os.path.join(data_dir, "history.json")
        self.max_items = max_items
        os.makedirs(self.img_dir, exist_ok=True)
        # History can contain private data, so only this user may open the folder.
        os.chmod(data_dir, 0o700)
        self.items = []
        self.load()

    # ----- loading / saving -----
    def load(self):
        try:
            with open(self.file, encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            raw = []
        except (OSError, ValueError) as e:
            log.warning("History file is damaged (%s); keeping a copy and starting fresh", e)
            self._set_aside_broken_file()
            raw = []
        if not isinstance(raw, list):
            raw = []
        repaired = [item for item in raw if self._fix_image_path(item)]
        self.items = [i for i in raw if _valid_item(i)]
        if repaired:
            self.save()   # store the corrected paths, so this only happens once
        self._delete_orphan_images()

    def save(self):
        """Write atomically (temp file + rename), so a crash never leaves half a file."""
        tmp = self.file + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.items, f)
            os.replace(tmp, self.file)
        except OSError as e:   # e.g. disk full: keep running with the in-memory history
            log.error("Could not save history: %s", e)

    def _fix_image_path(self, item):
        """Image items store a full path. If the data folder was moved or renamed, look for
        the same file name in the current images folder. Returns True if it fixed the path."""
        if isinstance(item, dict) and item.get("type") == "image" and isinstance(item.get("path"), str):
            if not os.path.isfile(item["path"]):
                moved = os.path.join(self.img_dir, os.path.basename(item["path"]))
                if os.path.isfile(moved):
                    item["path"] = moved
                    return True
        return False

    def _set_aside_broken_file(self):
        try:
            os.replace(self.file, self.file + ".broken")
        except OSError:
            pass

    def _delete_orphan_images(self):
        """Remove image files no item points to (left behind by a crash or a manual edit)."""
        used = {i["path"] for i in self.items if i["type"] == "image"}
        for name in os.listdir(self.img_dir):
            path = os.path.join(self.img_dir, name)
            if name.endswith(".png") and path not in used:
                try:
                    os.remove(path)
                except OSError:
                    pass

    # ----- queries -----
    def get(self, item_id):
        return next((i for i in self.items if i["id"] == item_id), None)

    # ----- adding -----
    def add_text(self, text):
        """Add copied text. Returns True if the history changed."""
        if not text or not text.strip():
            return False
        text = text[:MAX_TEXT_LEN]
        key = "t:" + hashlib.sha1(text.encode("utf-8", "replace"), usedforsecurity=False).hexdigest()
        return self._add(key, {"type": "text", "text": text})

    def add_image(self, png_bytes):
        """Add a copied image (PNG bytes). Returns True if the history changed."""
        if not png_bytes:
            return False
        digest = hashlib.sha1(png_bytes, usedforsecurity=False).hexdigest()  # for spotting duplicates only
        path = os.path.join(self.img_dir, digest + ".png")
        if not os.path.exists(path):
            try:
                with open(path, "wb") as f:
                    f.write(png_bytes)
            except OSError as e:
                log.error("Could not save image: %s", e)
                return False
        return self._add("i:" + digest, {"type": "image", "path": path})

    def _add(self, key, data):
        existing = next((i for i in self.items if i["key"] == key), None)
        if existing:
            if self.items[0] is existing:
                return False            # copied the same thing again: nothing to do
            self.items.remove(existing)  # copied an older item again: move it to the top
            existing["ts"] = time.time()
            self.items.insert(0, existing)
        else:
            self.items.insert(0, {"id": uuid.uuid4().hex, "key": key, "pinned": False,
                                  "ts": time.time(), **data})
        self._trim()
        self.save()
        return True

    def _trim(self):
        """Keep at most max_items unpinned items (pinned items don't count)."""
        unpinned = [i for i in self.items if not i["pinned"]]
        for old in unpinned[self.max_items:]:
            self._remove(old)

    # ----- changing -----
    def set_max_items(self, n):
        self.max_items = n
        self._trim()
        self.save()

    def _remove(self, item):
        self.items.remove(item)
        if item["type"] == "image":
            try:
                os.remove(item["path"])
            except OSError:
                pass

    def delete(self, item_id):
        item = self.get(item_id)
        if item:
            self._remove(item)
            self.save()

    def toggle_pin(self, item_id):
        item = self.get(item_id)
        if item:
            # No trimming here: an item you just unpinned shouldn't vanish in front of you.
            # The limit is applied again on the next copy.
            item["pinned"] = not item["pinned"]
            self.save()

    def clear_unpinned(self):
        for item in [i for i in self.items if not i["pinned"]]:
            self._remove(item)
        self.save()
