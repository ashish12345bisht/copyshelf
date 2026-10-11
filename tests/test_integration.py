"""End-to-end test: run the real daemon on a private X display and copy things to it.

Needs a separate X display so it can't touch your real clipboard. Set COPYSHELF_TEST_DISPLAY:
    Xwayland :87 -rootless &                     # inside a desktop session, no sudo
    COPYSHELF_TEST_DISPLAY=:87 python3 -m pytest
or on a server / CI:
    xvfb-run -a sh -c 'COPYSHELF_TEST_DISPLAY=$DISPLAY python3 -m pytest'
"""
import json
import os
import subprocess
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "tests", "helpers", "clip_owner.py")
DISPLAY = os.environ.get("COPYSHELF_TEST_DISPLAY")

pytestmark = pytest.mark.skipif(not DISPLAY, reason="set COPYSHELF_TEST_DISPLAY to run")


def wait_for(check, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    return None


def write_config(env, **settings):
    path = os.path.join(env["XDG_CONFIG_HOME"], "copyshelf", "config.json")
    with open(path, "w") as f:
        json.dump({"auto_paste": False, **settings}, f)


@pytest.fixture
def env(tmp_path):
    for d in ("run", "data", "config"):
        (tmp_path / d).mkdir(mode=0o700)
    e = dict(os.environ)
    for var in ("WAYLAND_DISPLAY", "COPYSHELF_DEBUG", "GDK_BACKEND"):
        e.pop(var, None)
    e.update(DISPLAY=DISPLAY, GDK_BACKEND="x11", XDG_SESSION_TYPE="x11", XDG_CURRENT_DESKTOP="",
             XDG_RUNTIME_DIR=str(tmp_path / "run"), XDG_DATA_HOME=str(tmp_path / "data"),
             XDG_CONFIG_HOME=str(tmp_path / "config"), PYTHONPATH=ROOT)
    # No auto-paste: there's nothing to paste into, and it would show a notification.
    (tmp_path / "config" / "copyshelf").mkdir()
    (tmp_path / "config" / "copyshelf" / "config.json").write_text('{"auto_paste": false}')
    return e


def copyshelf(env, *args, **kw):
    return subprocess.run([sys.executable, "-m", "copyshelf", *args], env=env, cwd=ROOT,
                          capture_output=True, text=True, timeout=10, **kw)


def ping(env):
    out = subprocess.run([sys.executable, "-c", "from copyshelf import ipc; print(ipc.send('ping'))"],
                         env=env, cwd=ROOT, capture_output=True, text=True, timeout=5)
    return out.stdout.strip() == "ok"


@pytest.fixture
def daemon(env):
    proc = subprocess.Popen([sys.executable, "-m", "copyshelf", "--debug"], env=env, cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert wait_for(lambda: ping(env)), "daemon did not start"
    yield proc
    if proc.poll() is None:
        proc.terminate()
    output = proc.communicate(timeout=5)[0]
    # Errors inside GTK callbacks don't stop the daemon, they're only printed. Fail on them.
    assert "Traceback" not in output, output


def history(env):
    path = os.path.join(env["XDG_DATA_HOME"], "copyshelf", "history.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def copy(env, kind, value=""):
    """Run the helper that owns the clipboard; returns the process (kill it when done)."""
    proc = subprocess.Popen([sys.executable, HELPER, kind, value], env=env,
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "ready"
    return proc


def test_records_text(env, daemon):
    owner = copy(env, "text", "hello from the test")
    try:
        assert wait_for(lambda: any(i.get("text") == "hello from the test" for i in history(env)))
    finally:
        owner.kill()


def test_records_image(env, daemon):
    owner = copy(env, "image")
    try:
        item = wait_for(lambda: next((i for i in history(env) if i["type"] == "image"), None))
        assert item and os.path.isfile(item["path"])
    finally:
        owner.kill()


def test_skips_password_manager_copies(env, daemon):
    secret = copy(env, "secret", "hunter2")
    time.sleep(1.5)
    secret.kill()
    marker = copy(env, "text", "after the secret")   # proves the daemon kept watching
    try:
        assert wait_for(lambda: any(i.get("text") == "after the secret" for i in history(env)))
        assert not any(i.get("text") == "hunter2" for i in history(env))
    finally:
        marker.kill()


def test_show_toggles_popup_without_crashing(env, daemon):
    assert copyshelf(env, "--show").returncode == 0
    assert copyshelf(env, "--show").returncode == 0
    assert ping(env) and daemon.poll() is None


def test_second_daemon_refuses_to_start(env, daemon):
    out = copyshelf(env)
    assert out.returncode == 1
    assert "already running" in out.stdout


def test_quit_waits_until_daemon_is_gone(env, daemon):
    assert copyshelf(env, "--quit").returncode == 0
    assert daemon.wait(5) == 0
    assert not os.path.exists(os.path.join(env["XDG_RUNTIME_DIR"], "copyshelf.sock"))
    assert copyshelf(env, "--quit").stdout.strip() == "Copyshelf is not running."


def test_loads_history_from_previous_version(env):
    """History written by the old single-file version must still load."""
    data = os.path.join(env["XDG_DATA_HOME"], "copyshelf")
    os.makedirs(data)
    old = [{"id": "abc", "key": "t:1", "pinned": True, "ts": 1.0, "type": "text", "text": "old item"}]
    with open(os.path.join(data, "history.json"), "w") as f:
        json.dump(old, f)
    proc = subprocess.Popen([sys.executable, "-m", "copyshelf"], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_for(lambda: ping(env))
        owner = copy(env, "text", "new item")
        assert wait_for(lambda: [i.get("text") for i in history(env)] == ["new item", "old item"])
        owner.kill()
    finally:
        proc.terminate()
        proc.wait(5)


def test_clear_keeps_pinned(env):
    data = os.path.join(env["XDG_DATA_HOME"], "copyshelf")
    os.makedirs(data)
    pinned = {"id": "p", "key": "t:p", "pinned": True, "ts": 1.0, "type": "text", "text": "pinned"}
    with open(os.path.join(data, "history.json"), "w") as f:
        json.dump([pinned], f)
    proc = subprocess.Popen([sys.executable, "-m", "copyshelf"], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_for(lambda: ping(env))
        owner = copy(env, "text", "not pinned")
        assert wait_for(lambda: len(history(env)) == 2)
        owner.kill()
        assert copyshelf(env, "--clear").returncode == 0
        assert wait_for(lambda: [i["text"] for i in history(env)] == ["pinned"])
    finally:
        proc.terminate()
        proc.wait(5)


def test_history_size_setting_is_used(env):
    write_config(env, max_items=2)
    proc = subprocess.Popen([sys.executable, "-m", "copyshelf"], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_for(lambda: ping(env))
        for text in ("one", "two", "three"):
            owner = copy(env, "text", text)
            assert wait_for(lambda: any(i.get("text") == text for i in history(env)))
            owner.kill()
        assert [i["text"] for i in history(env)] == ["three", "two"]
    finally:
        proc.terminate()
        proc.wait(5)


def test_settings_window_opens(env, daemon):
    assert copyshelf(env, "--settings").returncode == 0
    time.sleep(1)
    assert ping(env) and daemon.poll() is None
