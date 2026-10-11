#!/usr/bin/env bash
# One-line installer for Copyshelf:
#
#   curl -fsSL https://raw.githubusercontent.com/ashish12345bisht/copyshelf/main/get.sh | bash
#
# Downloads Copyshelf's source and runs install.sh. Arguments after `bash -s --` are passed
# on, e.g. `... | bash -s -- --yes` installs missing packages without asking.
#
# Everything is inside main(), which runs on the last line: if the download is cut off
# halfway, bash never runs a half-received script.
set -euo pipefail

main() {
  local repo="${COPYSHELF_REPO:-ashish12345bisht/copyshelf}"
  local ref="${COPYSHELF_REF:-main}"
  local url="${COPYSHELF_TARBALL:-https://github.com/$repo/archive/refs/heads/$ref.tar.gz}"

  if [ "$(id -u)" = 0 ]; then
    echo "Please run this as your normal user, not with sudo or as root." >&2
    echo "Copyshelf installs into your home folder and asks for sudo itself if it needs packages." >&2
    exit 1
  fi
  command -v tar >/dev/null || { echo "Copyshelf's installer needs 'tar'." >&2; exit 1; }

  # Not `local`: the cleanup below runs after main() has returned.
  COPYSHELF_TMP=$(mktemp -d)
  trap 'rm -rf "$COPYSHELF_TMP"' EXIT
  local tmp=$COPYSHELF_TMP

  echo "Downloading Copyshelf..."
  if command -v curl >/dev/null; then
    curl -fsSL "$url" | tar -xz -C "$tmp" --strip-components=1
  elif command -v wget >/dev/null; then
    wget -qO- "$url" | tar -xz -C "$tmp" --strip-components=1
  else
    echo "Copyshelf's installer needs 'curl' or 'wget'." >&2
    exit 1
  fi

  bash "$tmp/install.sh" "$@"
}

main "$@"
