"""Command line entry point.

    copyshelf            start the background daemon
    copyshelf --show     open/close the popup (bind this to Super+V)
    copyshelf --settings open the settings window
    copyshelf --clear    clear the history (pinned items are kept)
    copyshelf --check-updates  look for a new version on GitHub
    copyshelf --quit     stop the daemon
    copyshelf --uninstall  remove Copyshelf (add --purge to delete history and settings too)

GTK is slow to import, so --show and --quit talk to the running daemon first and only
load GTK if they have to start one. That keeps the hotkey feeling instant.
"""
import argparse
import logging
import os
import sys

from copyshelf import __version__, ipc


def parse_args(argv):
    p = argparse.ArgumentParser(prog="copyshelf", description="Clipboard history for Linux.")
    p.add_argument("--show", action="store_true", help="open or close the popup")
    p.add_argument("--settings", action="store_true", help="open the settings window")
    p.add_argument("--clear", action="store_true", help="clear the history (keeps pinned items)")
    p.add_argument("--check-updates", action="store_true", help="check GitHub for a new version")
    p.add_argument("--quit", action="store_true", help="stop the running daemon")
    p.add_argument("--uninstall", action="store_true", help="remove Copyshelf from this computer")
    p.add_argument("--purge", action="store_true", help="with --uninstall: also delete history and settings")
    p.add_argument("--debug", action="store_true", help="print detailed logs (or set COPYSHELF_DEBUG=1)")
    p.add_argument("--reset-paste-permission", action="store_true",
                   help="forget the saved RemoteDesktop portal permission (KDE)")
    p.add_argument("--version", action="version", version=f"copyshelf {__version__}")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    debug = args.debug or bool(os.environ.get("COPYSHELF_DEBUG"))
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO,
                        format="copyshelf: %(levelname)s: %(message)s")

    if args.uninstall:
        # install.sh puts uninstall.sh next to the installed package.
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "uninstall.sh")
        if not os.path.exists(script):
            print("Can't find uninstall.sh. Run it from the Copyshelf source folder instead.")
            return 1
        os.execvp("bash", ["bash", script] + (["--purge"] if args.purge else []))
    if args.quit:
        if not ipc.quit_daemon():
            print("Copyshelf is not running.")
        return 0
    if args.clear:
        if ipc.send("clear") != "ok":
            print("Copyshelf is not running.")
        return 0
    if args.show and ipc.send("show") == "ok":
        return 0   # the running daemon opened the popup
    if args.settings and ipc.send("settings") == "ok":
        return 0
    if args.check_updates and ipc.send("check-updates") == "ok":
        return 0
    if args.reset_paste_permission:
        from copyshelf.paste.portal import reset_permission
        print("Forgot the saved permission." if reset_permission() else "No saved permission.")
        return 0

    # No daemon running: become the daemon. Choose GTK's backend before GTK is imported.
    from copyshelf.desktop import gdk_backend
    os.environ.setdefault("GDK_BACKEND", gdk_backend())
    from copyshelf.app import run
    return run(show=args.show, settings=args.settings, check_updates=args.check_updates)


if __name__ == "__main__":
    sys.exit(main())
