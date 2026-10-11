import json
import os

import pytest

from copyshelf import migrate
from copyshelf.history import History


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path


def make_old_install(xdg):
    """Old WinClip data: settings, plus a history with an image stored by full path."""
    (xdg / "config" / "winclip").mkdir(parents=True)
    (xdg / "config" / "winclip" / "config.json").write_text('{"max_items": 7}')
    images = xdg / "data" / "winclip" / "images"
    images.mkdir(parents=True)
    (images / "abc.png").write_bytes(b"\x89PNG old image")
    items = [
        {"id": "1", "key": "t:1", "type": "text", "pinned": True, "ts": 1.0, "text": "old text"},
        {"id": "2", "key": "i:abc", "type": "image", "pinned": False, "ts": 2.0,
         "path": str(images / "abc.png")},
    ]
    (xdg / "data" / "winclip" / "history.json").write_text(json.dumps(items))


def test_old_folders_are_moved(xdg):
    make_old_install(xdg)
    migrate.move_old_data()
    assert not (xdg / "config" / "winclip").exists()
    assert json.loads((xdg / "config" / "copyshelf" / "config.json").read_text()) == {"max_items": 7}
    assert (xdg / "data" / "copyshelf" / "history.json").exists()


def test_history_survives_the_move_including_images(xdg):
    make_old_install(xdg)
    migrate.move_old_data()
    h = History(str(xdg / "data" / "copyshelf"))
    assert [i["id"] for i in h.items] == ["1", "2"]
    image = h.items[1]
    assert image["path"] == str(xdg / "data" / "copyshelf" / "images" / "abc.png")
    assert os.path.isfile(image["path"])


def test_existing_new_folders_are_never_overwritten(xdg):
    make_old_install(xdg)
    (xdg / "config" / "copyshelf").mkdir(parents=True)
    (xdg / "config" / "copyshelf" / "config.json").write_text('{"max_items": 99}')
    migrate.move_old_data()
    assert json.loads((xdg / "config" / "copyshelf" / "config.json").read_text()) == {"max_items": 99}
    assert (xdg / "config" / "winclip").exists()   # left alone


def test_nothing_to_migrate(xdg):
    migrate.move_old_data()   # must not fail or create anything
    assert not (xdg / "config").exists()


def test_repaired_image_path_is_saved(xdg):
    make_old_install(xdg)
    migrate.move_old_data()
    History(str(xdg / "data" / "copyshelf"))
    saved = json.loads((xdg / "data" / "copyshelf" / "history.json").read_text())
    assert saved[1]["path"] == str(xdg / "data" / "copyshelf" / "images" / "abc.png")
