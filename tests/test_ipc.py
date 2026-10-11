import os
import socket
import stat
import time

import pytest

from copyshelf import ipc


@pytest.fixture(autouse=True)
def private_runtime_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))


def test_send_without_daemon_returns_none():
    assert ipc.send("show") is None


def test_server_round_trip():
    received = []

    def handler(cmd):
        received.append(cmd)
        return "ok"

    srv = ipc.Server(handler)
    srv.start()
    try:
        assert ipc.send("show") == "ok"
        assert received == ["show"]
    finally:
        srv.close()
    assert ipc.send("show") is None   # closed server: no answer


def test_silent_client_does_not_block_server():
    srv = ipc.Server(lambda cmd: "ok")
    srv.start()
    try:
        silent = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        silent.connect(ipc.socket_path())   # connects but never sends anything
        start = time.monotonic()
        assert ipc.send("ping", timeout=3) == "ok"
        assert time.monotonic() - start < 2.5
        silent.close()
    finally:
        srv.close()


def test_socket_is_private():
    srv = ipc.Server(lambda cmd: "ok")
    srv.start()
    try:
        assert stat.S_IMODE(os.stat(ipc.socket_path()).st_mode) == 0o600
    finally:
        srv.close()


def test_instance_lock_is_exclusive():
    first = ipc.acquire_instance_lock()
    assert first is not None
    assert ipc.acquire_instance_lock() is None
    first.close()   # what happens when the daemon exits
    again = ipc.acquire_instance_lock()
    assert again is not None
    again.close()


def test_runtime_dir_fallback_is_private(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    path = ipc.socket_path()
    assert path.startswith(str(tmp_path / "cache"))
    assert stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) == 0o700
