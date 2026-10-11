import json

from copyshelf.config import DEFAULTS, load_config, save_config


def write(path, data):
    path.write_text(data if isinstance(data, str) else json.dumps(data))


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(str(tmp_path / "none.json")) == DEFAULTS


def test_valid_values_are_used(tmp_path):
    p = tmp_path / "c.json"
    write(p, {"max_items": 50, "auto_paste": False, "paste_method": "none"})
    cfg = load_config(str(p))
    assert cfg["max_items"] == 50
    assert cfg["auto_paste"] is False
    assert cfg["paste_method"] == "none"
    assert cfg["skip_sensitive"] is True   # not in file: default


def test_invalid_values_fall_back_to_defaults(tmp_path):
    p = tmp_path / "c.json"
    write(p, {"max_items": 0, "auto_paste": "yes", "paste_method": "magic", "max_items_typo": 5})
    assert load_config(str(p)) == DEFAULTS


def test_bool_is_not_accepted_as_number(tmp_path):
    p = tmp_path / "c.json"
    write(p, {"max_items": True})
    assert load_config(str(p))["max_items"] == DEFAULTS["max_items"]


def test_broken_json_gives_defaults(tmp_path):
    p = tmp_path / "c.json"
    write(p, "{oops")
    assert load_config(str(p)) == DEFAULTS


def test_non_object_gives_defaults(tmp_path):
    p = tmp_path / "c.json"
    write(p, "[1, 2]")
    assert load_config(str(p)) == DEFAULTS


def test_save_and_load_round_trip(tmp_path):
    p = str(tmp_path / "sub" / "c.json")
    cfg = dict(DEFAULTS, max_items=10, auto_paste=False)
    save_config(cfg, p)
    assert load_config(p) == cfg
