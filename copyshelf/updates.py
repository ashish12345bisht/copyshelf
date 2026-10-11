"""Checking GitHub for a newer Copyshelf, and installing it when the user says yes.

Privacy: the check downloads public information about the latest release (its version
number and release notes) from api.github.com. Nothing about the user or their clipboard
is sent. It can be turned off in Settings ("check_updates").

The flow:
  1. A few minutes after login, then about once a day, fetch the latest release.
  2. If it's newer, and the user hasn't skipped it or asked to be reminded later,
     show a notification; clicking it opens the update window (ui/update_window.py).
  3. "Update now" downloads that release and runs its install.sh as a separate process.
     The installer restarts Copyshelf, and the new version says "Updated to X".
"""
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request
from dataclasses import dataclass

from copyshelf import GITHUB_REPO, __version__, config
from copyshelf._gi import GLib

log = logging.getLogger(__name__)

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
FIRST_CHECK_DELAY_S = 3 * 60     # don't slow down login: wait a few minutes
CHECK_EVERY_S = 24 * 3600
REMIND_LATER_S = 24 * 3600
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
# release.sh adds this (invisible on GitHub) when a release changes the GNOME extension.
RELOGIN_MARKER = "<!-- copyshelf:needs-relogin -->"


@dataclass(frozen=True)
class Release:
    version: str        # "0.3.0"
    notes: str          # release notes as written in CHANGELOG.md
    page_url: str       # the release's page on GitHub
    tarball_url: str    # source code of exactly this release
    needs_relogin: bool


# ----- versions -----
def parse_version(text):
    """'v0.3.0' or '0.3.0' -> (0, 3, 0); None if it isn't a version."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", str(text).strip())
    return tuple(int(n) for n in match.groups()) if match else None


def is_newer(candidate, current):
    a, b = parse_version(candidate), parse_version(current)
    return a is not None and b is not None and a > b


# ----- asking GitHub -----
def parse_release(data):
    """Turn GitHub's JSON for a release into a Release, or None if it doesn't look right."""
    if not isinstance(data, dict) or not isinstance(data.get("tag_name"), str):
        return None
    tag = data["tag_name"]
    version = parse_version(tag)
    if version is None or data.get("draft") or data.get("prerelease"):
        return None
    body = data.get("body") if isinstance(data.get("body"), str) else ""
    return Release(
        version=".".join(map(str, version)),
        notes=body.replace(RELOGIN_MARKER, "").strip(),
        page_url=data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
        tarball_url=f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.tar.gz",
        needs_relogin=RELOGIN_MARKER in body,
    )


def fetch_latest(url=API_URL, timeout=10):
    """The latest release, or None if GitHub can't be reached or answers oddly.
    Blocks: call it from a background thread."""
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"copyshelf/{__version__}",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read(1_000_000).decode("utf-8"))
    except (OSError, ValueError) as e:   # offline, timeout, HTTP error, broken JSON...
        log.info("Update check failed: %s", e)
        return None
    return parse_release(data)


# ----- remembering the user's choices -----
def state_path():
    return os.path.join(config.state_dir(), "updates.json")


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    path = state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(path + ".tmp", path)
    except OSError as e:
        log.warning("Could not save update state: %s", e)


def check_due(state, now):
    last = state.get("last_check", 0)
    # `last > now` happens if the clock was wrong before: check rather than wait for ages.
    return not isinstance(last, (int, float)) or last > now or now - last >= CHECK_EVERY_S


def should_offer(release, state, now, current=__version__):
    """Should we tell the user about this release (automatic checks only)?"""
    if release is None or not is_newer(release.version, current):
        return False
    if state.get("skipped_version") == release.version:
        return False
    remind_after = state.get("remind_after", 0)
    return not (isinstance(remind_after, (int, float)) and now < remind_after)


def just_updated(state, current=__version__):
    """True on the first start after an update (not after a fresh install)."""
    previous = state.get("last_run_version")
    return previous is not None and is_newer(current, previous)


# ----- installing -----
def _check_member(member, dest):
    target = os.path.realpath(os.path.join(dest, member.name))
    if not target.startswith(os.path.realpath(dest) + os.sep):
        raise ValueError(f"unsafe path in archive: {member.name}")
    if not (member.isfile() or member.isdir()):
        raise ValueError(f"unexpected file type in archive: {member.name}")


def safe_extract(archive, dest):
    """Unpack a .tar.gz, refusing anything that would land outside `dest` (e.g. '../x')
    or isn't a plain file or folder. Returns the archive's single top-level folder."""
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            _check_member(member, dest)
        if hasattr(tarfile, "data_filter"):   # Python 3.12+ (and recent 3.10/3.11 updates)
            tar.extractall(dest, filter="data")
        else:
            tar.extractall(dest)
    tops = {m.name.split("/", 1)[0] for m in members}
    if len(tops) != 1:
        raise ValueError("archive should contain exactly one folder")
    return os.path.join(dest, tops.pop())


def download_release(release, timeout=60):
    """Download and unpack a release into ~/.cache/copyshelf/update. Returns the source
    folder. Blocks: call it from a background thread. Raises OSError/ValueError on failure."""
    work = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
                        "copyshelf", "update")
    shutil.rmtree(work, ignore_errors=True)   # leftovers from a previous update
    os.makedirs(work)
    archive = os.path.join(work, "release.tar.gz")
    request = urllib.request.Request(release.tarball_url,
                                     headers={"User-Agent": f"copyshelf/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response, open(archive, "wb") as out:
        size = 0
        while chunk := response.read(64 * 1024):
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                raise ValueError("download is unexpectedly large")
            out.write(chunk)
    source = safe_extract(archive, os.path.join(work, "src"))
    if not os.path.isfile(os.path.join(source, "install.sh")):
        raise ValueError("the download doesn't contain install.sh")
    return source


def start_install(source):
    """Run the release's installer as its own process, in its own session, so it keeps
    going when it stops this Copyshelf to start the new one. Output goes to a log file."""
    # source is ~/.cache/copyshelf/update/src/<folder>; the log goes in .../update/
    log_path = os.path.join(os.path.dirname(os.path.dirname(source)), "install.log")
    with open(log_path, "w") as log_file:
        subprocess.Popen(["bash", os.path.join(source, "install.sh")], cwd=source,
                         stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
                         start_new_session=True)
    log.info("Installer started; its output goes to %s", log_path)
    return log_path


# ----- the background checker -----
class UpdateChecker:
    """Checks a few minutes after start, then looks every hour whether a day has passed."""

    def __init__(self, enabled, on_found, fetch=fetch_latest):
        self.enabled = enabled          # function -> bool (reads the current setting)
        self.on_found = on_found        # on_found(release), on the GTK main thread
        self.fetch = fetch
        self.busy = False

    def start(self):
        GLib.timeout_add_seconds(FIRST_CHECK_DELAY_S, self._tick_once)
        GLib.timeout_add_seconds(3600, self._tick)

    def _tick_once(self):
        self._tick()
        return False

    def _tick(self):
        if self.enabled() and check_due(load_state(), time.time()):
            self.check()
        return True   # keep the hourly timer running

    def check(self, manual=False, on_done=None):
        """Fetch the latest release in the background. Automatic checks call on_found if the
        user should hear about it; manual checks always call on_done(release or None)."""
        if self.busy:
            return
        self.busy = True

        def work():
            release = self.fetch()
            GLib.idle_add(self._finish, release, manual, on_done)

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, release, manual, on_done):
        self.busy = False
        state = load_state()
        if release is not None:   # offline: try again at the next hourly tick
            state["last_check"] = time.time()
            save_state(state)
        if manual:
            if on_done:
                on_done(release)
        elif should_offer(release, state, time.time()):
            self.on_found(release)
        return False

    @staticmethod
    def skip(version):
        state = load_state()
        state["skipped_version"] = version
        save_state(state)

    @staticmethod
    def remind_later():
        state = load_state()
        state["remind_after"] = time.time() + REMIND_LATER_S
        save_state(state)
