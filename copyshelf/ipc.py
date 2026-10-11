"""Talking to the running daemon over a Unix socket.

`copyshelf --show` is a separate, short-lived process (started by the hotkey). It sends
"show" to the daemon and exits. The protocol is one line in, one line ("ok") back.
"""
import fcntl
import logging
import os
import socket
import threading
import time

from copyshelf.config import runtime_dir

log = logging.getLogger(__name__)


def socket_path():
    return os.path.join(runtime_dir(), "copyshelf.sock")


def send(cmd, timeout=2.0):
    """Send a command to the daemon. Returns its reply, or None if no daemon answered."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(socket_path())
            s.sendall(cmd.encode() + b"\n")
            return s.recv(64).decode(errors="replace").strip()
    except OSError:
        return None


def quit_daemon(wait=5.0):
    """Ask the daemon to quit and wait until it has really gone. Returns True if one was running."""
    if send("quit") is None:
        return False
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and send("ping", timeout=0.5) is not None:
        time.sleep(0.1)
    return True


def acquire_instance_lock():
    """Make sure only one daemon runs. Returns an open lock file to keep, or None if
    another daemon already holds the lock. The OS releases it when the process exits,
    even after a crash, so a stale lock can't block startup."""
    f = open(os.path.join(runtime_dir(), "copyshelf.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.close()
        return None
    return f


class Server:
    """Accepts commands on the socket in a background thread.

    `handler(cmd)` is called on that background thread and returns the reply text.
    GTK may only be used from the main thread, so the handler must hand GTK work over
    with GLib.idle_add.
    """

    def __init__(self, handler):
        self.handler = handler
        self.path = socket_path()
        self.sock = None

    def start(self):
        try:
            os.unlink(self.path)   # left over from a crash; we hold the instance lock, so it's stale
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.sock.listen(5)
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return   # socket closed: we're shutting down
            with conn:
                # A client that connects and never sends anything can't block us for long.
                conn.settimeout(1.0)
                try:
                    cmd = conn.recv(256).decode(errors="replace").strip()
                    conn.sendall((self.handler(cmd) + "\n").encode())
                except OSError:
                    pass

    def close(self):
        if self.sock:
            self.sock.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass
