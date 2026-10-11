import json
import os
import stat

import pytest

from copyshelf.history import MAX_TEXT_LEN, History


@pytest.fixture
def hist(tmp_path):
    return History(str(tmp_path / "data"), max_items=3)


def texts(h):
    return [i.get("text") for i in h.items]


def test_add_text_puts_newest_first(hist):
    hist.add_text("a")
    hist.add_text("b")
    assert texts(hist) == ["b", "a"]


def test_blank_text_is_ignored(hist):
    assert not hist.add_text("")
    assert not hist.add_text("   \n\t")
    assert hist.items == []


def test_copying_same_text_twice_is_a_no_op(hist):
    assert hist.add_text("a")
    assert not hist.add_text("a")
    assert texts(hist) == ["a"]


def test_copying_older_item_moves_it_to_top(hist):
    hist.add_text("a")
    hist.add_text("b")
    first_id = hist.items[1]["id"]
    assert hist.add_text("a")
    assert texts(hist) == ["a", "b"]
    assert hist.items[0]["id"] == first_id   # same item, not a duplicate


def test_limit_drops_oldest_unpinned(hist):
    for t in "abcd":
        hist.add_text(t)
    assert texts(hist) == ["d", "c", "b"]


def test_pinned_items_do_not_count_toward_limit(hist):
    hist.add_text("keep")
    hist.toggle_pin(hist.items[0]["id"])
    for t in "abcd":
        hist.add_text(t)
    assert texts(hist) == ["d", "c", "b", "keep"]


def test_unpinning_does_not_delete_immediately(hist):
    hist.add_text("old")
    hist.toggle_pin(hist.items[0]["id"])
    for t in "abc":
        hist.add_text(t)
    old = next(i for i in hist.items if i["text"] == "old")
    hist.toggle_pin(old["id"])   # now 4 unpinned items with a limit of 3
    assert "old" in texts(hist)


def test_clear_keeps_pinned(hist):
    hist.add_text("a")
    hist.add_text("b")
    hist.toggle_pin(hist.items[1]["id"])   # pin "a"
    hist.clear_unpinned()
    assert texts(hist) == ["a"]


def test_delete(hist):
    hist.add_text("a")
    hist.add_text("b")
    hist.delete(hist.items[0]["id"])
    assert texts(hist) == ["a"]
    hist.delete("no-such-id")   # unknown ids are ignored
    assert texts(hist) == ["a"]


def test_long_text_is_truncated(hist):
    hist.add_text("x" * (MAX_TEXT_LEN + 10))
    assert len(hist.items[0]["text"]) == MAX_TEXT_LEN


def test_history_persists(tmp_path):
    d = str(tmp_path / "data")
    h = History(d)
    h.add_text("hello")
    h.toggle_pin(h.items[0]["id"])
    h2 = History(d)
    assert texts(h2) == ["hello"]
    assert h2.items[0]["pinned"] is True


def test_data_folder_is_private(tmp_path):
    d = tmp_path / "data"
    d.mkdir(mode=0o755)
    History(str(d))
    assert stat.S_IMODE(os.stat(d).st_mode) == 0o700


# ----- images -----
PNG_A = b"\x89PNG fake image A"
PNG_B = b"\x89PNG fake image B"


def test_add_image_saves_file(hist):
    assert hist.add_image(PNG_A)
    path = hist.items[0]["path"]
    with open(path, "rb") as f:
        assert f.read() == PNG_A


def test_same_image_twice_is_one_item(hist):
    hist.add_image(PNG_A)
    assert not hist.add_image(PNG_A)
    assert len(hist.items) == 1


def test_deleting_image_removes_file(hist):
    hist.add_image(PNG_A)
    path = hist.items[0]["path"]
    hist.delete(hist.items[0]["id"])
    assert not os.path.exists(path)


def test_trimmed_image_file_is_removed(hist):
    hist.add_image(PNG_A)
    path = hist.items[0]["path"]
    for t in "abc":
        hist.add_text(t)
    assert not os.path.exists(path)


def test_clear_removes_unpinned_image_files_only(hist):
    hist.add_image(PNG_A)
    hist.add_image(PNG_B)
    pinned = hist.items[0]
    hist.toggle_pin(pinned["id"])
    gone = hist.items[1]["path"]
    hist.clear_unpinned()
    assert os.path.exists(pinned["path"])
    assert not os.path.exists(gone)


def test_empty_image_is_ignored(hist):
    assert not hist.add_image(b"")


# ----- damaged or edited files -----
def write_history(d, content):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "history.json"), "w") as f:
        f.write(content)


def test_corrupt_file_starts_empty_and_is_kept_aside(tmp_path):
    d = str(tmp_path / "data")
    write_history(d, "{not json")
    h = History(d)
    assert h.items == []
    assert os.path.exists(os.path.join(d, "history.json.broken"))


def test_wrong_top_level_type_starts_empty(tmp_path):
    d = str(tmp_path / "data")
    write_history(d, json.dumps({"oops": 1}))
    assert History(d).items == []


def test_invalid_items_are_dropped(tmp_path):
    d = str(tmp_path / "data")
    good = {"id": "1", "key": "t:x", "type": "text", "pinned": False, "ts": 1.0, "text": "ok"}
    bad = [
        {"id": "2", "type": "text", "text": "missing key/pinned/ts"},
        {"id": "3", "key": "t:y", "type": "text", "pinned": "yes", "ts": 1.0, "text": "bad pinned"},
        {"id": "4", "key": "i:z", "type": "image", "pinned": False, "ts": 1.0, "path": "/nope.png"},
        {"id": "5", "key": "v:z", "type": "video", "pinned": False, "ts": 1.0},
        "just a string",
    ]
    write_history(d, json.dumps([good] + bad))
    assert [i["id"] for i in History(d).items] == ["1"]


def test_orphan_images_are_cleaned_up(tmp_path):
    d = str(tmp_path / "data")
    h = History(d)
    orphan = os.path.join(h.img_dir, "deadbeef.png")
    with open(orphan, "wb") as f:
        f.write(b"x")
    History(d)
    assert not os.path.exists(orphan)


def test_save_failure_does_not_crash(hist, monkeypatch):
    def fail(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("builtins.open", fail)
    hist.add_text("still works in memory")   # must not raise
    assert texts(hist) == ["still works in memory"]


def test_set_max_items_trims(hist):
    for t in "abc":
        hist.add_text(t)
    hist.set_max_items(1)
    assert texts(hist) == ["c"]
