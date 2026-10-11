"""Update checks: version logic, the user's choices, GitHub replies, and safe downloads."""
import io
import json
import os
import tarfile
import time
import urllib.request

import pytest

from copyshelf import updates
from copyshelf.updates import Release

NOW = 1_800_000_000.0


def release(version="0.3.0", notes="### Fixed\n- a bug", relogin=False):
    return Release(version, notes, "https://example/rel", "https://example/x.tar.gz", relogin)


@pytest.fixture(autouse=True)
def private_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


# ----- versions -----
@pytest.mark.parametrize("text, expected", [
    ("0.3.0", (0, 3, 0)), ("v1.10.2", (1, 10, 2)), ("v2.0.0-beta", (2, 0, 0)),
    ("latest", None), ("", None), ("1.2", None),
])
def test_parse_version(text, expected):
    assert updates.parse_version(text) == expected


def test_is_newer_compares_numbers_not_text():
    assert updates.is_newer("0.10.0", "0.9.0")   # as text, "0.10" < "0.9"
    assert not updates.is_newer("0.2.0", "0.2.0")
    assert not updates.is_newer("0.1.9", "0.2.0")
    assert not updates.is_newer("garbage", "0.2.0")


# ----- GitHub's reply -----
GOOD = {"tag_name": "v0.3.0", "body": "### Added\n- thing", "html_url": "https://gh/rel",
        "draft": False, "prerelease": False}


def test_parse_release():
    r = updates.parse_release(GOOD)
    assert (r.version, r.notes, r.page_url, r.needs_relogin) == ("0.3.0", "### Added\n- thing",
                                                                 "https://gh/rel", False)
    assert r.tarball_url.endswith("/archive/refs/tags/v0.3.0.tar.gz")


def test_relogin_marker_is_detected_and_hidden():
    r = updates.parse_release(dict(GOOD, body="- thing\n\n" + updates.RELOGIN_MARKER))
    assert r.needs_relogin
    assert "copyshelf:needs-relogin" not in r.notes


@pytest.mark.parametrize("data", [
    None, [], {"body": "no tag"}, dict(GOOD, tag_name="nightly"),
    dict(GOOD, draft=True), dict(GOOD, prerelease=True),
])
def test_bad_or_unsuitable_replies_are_ignored(data):
    assert updates.parse_release(data) is None


def test_missing_notes_are_fine():
    assert updates.parse_release(dict(GOOD, body=None)).notes == ""


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_latest_success(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout: FakeResponse(json.dumps(GOOD).encode()))
    assert updates.fetch_latest().version == "0.3.0"


@pytest.mark.parametrize("failure", [
    OSError("network is unreachable"),
    urllib.request.URLError("no route"),
    TimeoutError("timed out"),
])
def test_fetch_latest_network_errors_return_none(monkeypatch, failure):
    def fail(req, timeout):
        raise failure
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert updates.fetch_latest() is None


def test_fetch_latest_broken_json_returns_none(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: FakeResponse(b"<html>oops"))
    assert updates.fetch_latest() is None


def test_fetch_latest_sends_nothing_but_the_request(monkeypatch):
    seen = {}

    def capture(req, timeout):
        seen["url"], seen["data"], seen["headers"] = req.full_url, req.data, dict(req.headers)
        return FakeResponse(json.dumps(GOOD).encode())
    monkeypatch.setattr(urllib.request, "urlopen", capture)
    updates.fetch_latest()
    assert seen["url"] == updates.API_URL
    assert seen["data"] is None   # a plain GET: no body
    assert set(seen["headers"]) == {"Accept", "User-agent"}


# ----- when to check, when to offer -----
def test_check_due():
    assert updates.check_due({}, NOW)
    assert not updates.check_due({"last_check": NOW - 3600}, NOW)
    assert updates.check_due({"last_check": NOW - 25 * 3600}, NOW)
    assert updates.check_due({"last_check": NOW + 99999}, NOW)   # clock was wrong
    assert updates.check_due({"last_check": "garbage"}, NOW)


def test_should_offer():
    assert updates.should_offer(release("0.3.0"), {}, NOW, current="0.2.0")
    assert not updates.should_offer(release("0.2.0"), {}, NOW, current="0.2.0")
    assert not updates.should_offer(None, {}, NOW, current="0.2.0")


def test_skipped_version_is_not_offered_but_the_next_one_is():
    state = {"skipped_version": "0.3.0"}
    assert not updates.should_offer(release("0.3.0"), state, NOW, current="0.2.0")
    assert updates.should_offer(release("0.4.0"), state, NOW, current="0.2.0")


def test_remind_later_waits():
    state = {"remind_after": NOW + 60}
    assert not updates.should_offer(release("0.3.0"), state, NOW, current="0.2.0")
    assert updates.should_offer(release("0.3.0"), state, NOW + 61, current="0.2.0")


def test_skip_and_remind_are_remembered():
    updates.UpdateChecker.skip("0.3.0")
    updates.UpdateChecker.remind_later()
    state = updates.load_state()
    assert state["skipped_version"] == "0.3.0"
    assert state["remind_after"] > time.time() + 23 * 3600


def test_just_updated():
    assert updates.just_updated({"last_run_version": "0.2.0"}, current="0.3.0")
    assert not updates.just_updated({"last_run_version": "0.3.0"}, current="0.3.0")
    assert not updates.just_updated({}, current="0.3.0")   # fresh install, not an update


def test_broken_state_file_is_ignored():
    os.makedirs(os.path.dirname(updates.state_path()))
    with open(updates.state_path(), "w") as f:
        f.write("{not json")
    assert updates.load_state() == {}


# ----- the background checker -----
class SyncThread:
    """Stands in for threading.Thread: runs the work immediately."""

    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def sync_glib(monkeypatch):
    """Run UpdateChecker.check synchronously: no thread, no GTK main loop. monkeypatch puts
    the real GLib.idle_add and threading.Thread back after each test."""
    monkeypatch.setattr(updates.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.setattr(updates.threading, "Thread", SyncThread)


def run_check(checker, **kw):
    checker.check(**kw)


def test_automatic_check_offers_newer_release(sync_glib):
    found = []
    checker = updates.UpdateChecker(lambda: True, found.append, fetch=lambda: release("99.0.0"))
    run_check(checker)
    assert [r.version for r in found] == ["99.0.0"]
    assert updates.load_state()["last_check"] > 0


def test_automatic_check_stays_quiet_when_up_to_date(sync_glib):
    found = []
    checker = updates.UpdateChecker(lambda: True, found.append, fetch=lambda: release("0.0.1"))
    run_check(checker)
    assert found == []


def test_offline_check_is_silent_and_retried(sync_glib):
    found = []
    checker = updates.UpdateChecker(lambda: True, found.append, fetch=lambda: None)
    run_check(checker)
    assert found == []
    assert "last_check" not in updates.load_state()   # so the next hourly tick tries again


def test_manual_check_always_answers(sync_glib):
    answers = []
    checker = updates.UpdateChecker(lambda: True, lambda r: None, fetch=lambda: release("0.0.1"))
    run_check(checker, manual=True, on_done=answers.append)
    assert answers[0].version == "0.0.1"


# ----- downloading safely -----
def make_tarball(path, files):
    with tarfile.open(path, "w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_safe_extract(tmp_path):
    archive = tmp_path / "r.tar.gz"
    make_tarball(archive, {"copyshelf-0.3.0/install.sh": "echo hi", "copyshelf-0.3.0/a/b.py": "x"})
    top = updates.safe_extract(str(archive), str(tmp_path / "out"))
    assert os.path.isfile(os.path.join(top, "install.sh"))


@pytest.mark.parametrize("evil", ["../escape.sh", "/etc/evil", "top/../../escape.sh"])
def test_safe_extract_refuses_paths_outside(tmp_path, evil):
    archive = tmp_path / "r.tar.gz"
    make_tarball(archive, {"top/install.sh": "ok", evil: "bad"})
    with pytest.raises(ValueError):
        updates.safe_extract(str(archive), str(tmp_path / "out"))
    assert not (tmp_path / "escape.sh").exists()


def test_safe_extract_refuses_links(tmp_path):
    archive = tmp_path / "r.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        link = tarfile.TarInfo("top/passwd")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
    with pytest.raises(ValueError):
        updates.safe_extract(str(archive), str(tmp_path / "out"))


def test_download_release_from_local_file(tmp_path):
    archive = tmp_path / "copyshelf-9.9.9.tar.gz"
    make_tarball(archive, {"copyshelf-9.9.9/install.sh": "echo installing"})
    r = Release("9.9.9", "", "", archive.as_uri(), False)
    source = updates.download_release(r)
    assert open(os.path.join(source, "install.sh")).read() == "echo installing"


def test_download_without_installer_is_rejected(tmp_path):
    archive = tmp_path / "x.tar.gz"
    make_tarball(archive, {"top/README.md": "no installer here"})
    with pytest.raises(ValueError):
        updates.download_release(Release("9.9.9", "", "", archive.as_uri(), False))


def test_start_install_runs_detached(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(updates.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    source = tmp_path / "update" / "src" / "copyshelf-9.9.9"   # the layout download_release makes
    source.mkdir(parents=True)
    log_path = updates.start_install(str(source))
    assert log_path == str(tmp_path / "update" / "install.log")
    args, kw = calls[0]
    assert args == ["bash", str(source / "install.sh")]
    assert kw["start_new_session"] is True   # survives when the installer stops Copyshelf
    assert kw["stdin"] is updates.subprocess.DEVNULL   # never waits for keyboard input
