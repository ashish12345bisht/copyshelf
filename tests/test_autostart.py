import os

import pytest

from copyshelf import autostart


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CONFIG_DIRS", str(tmp_path / "etc"))
    return tmp_path


def system_file(dirs):
    path = dirs / "etc" / "autostart" / "copyshelf.desktop"
    path.parent.mkdir(parents=True)
    path.write_text("[Desktop Entry]\nType=Application\nExec=copyshelf\n")
    return path


def test_off_by_default_without_any_file(dirs):
    assert not autostart.is_enabled()


def test_enable_writes_user_file(dirs):
    autostart.set_enabled(True)
    assert os.path.exists(autostart.user_file())
    assert autostart.is_enabled()


def test_disable_removes_user_file_when_no_system_file(dirs):
    autostart.set_enabled(True)
    autostart.set_enabled(False)
    assert not os.path.exists(autostart.user_file())
    assert not autostart.is_enabled()


def test_system_file_counts_as_enabled(dirs):
    system_file(dirs)
    assert autostart.is_enabled()


def test_disable_overrides_system_file(dirs):
    system_file(dirs)
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    assert "Hidden=true" in open(autostart.user_file()).read()
    autostart.set_enabled(True)
    assert autostart.is_enabled()


def test_file_written_by_install_sh_counts_as_enabled(dirs):
    path = autostart.user_file()
    os.makedirs(os.path.dirname(path))
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "copyshelf-autostart.desktop")) as f:
        open(path, "w").write(f.read().replace("@BIN@", "/x/copyshelf"))
    assert autostart.is_enabled()


def test_gnome_disabled_flag_is_respected(dirs):
    path = autostart.user_file()
    os.makedirs(os.path.dirname(path))
    open(path, "w").write("[Desktop Entry]\nExec=copyshelf\nX-GNOME-Autostart-enabled=false\n")
    assert not autostart.is_enabled()
