#!/usr/bin/env bash
# One-line installer for Copyshelf:
#
#   curl -fsSL https://raw.githubusercontent.com/ashish12345bisht/copyshelf/main/get.sh | bash
#
# Downloads the latest release of Copyshelf and runs its install.sh. Arguments after `bash -s --` are passed
# on, e.g. `... | bash -s -- --yes` installs missing packages without asking.
#
# Everything is inside main(), which runs on the last line: if the download is cut off
# halfway, bash never runs a half-received script.
set -euo pipefail

# Prints the body of a URL (curl or wget, whichever exists).
fetch() {
  if command -v curl >/dev/null; then curl -fsSL "$1"
  elif command -v wget >/dev/null; then wget -qO- "$1"
  else
    echo "Copyshelf's installer needs 'curl' or 'wget'." >&2
    return 1
  fi
}

main() {
  local repo="${COPYSHELF_REPO:-ashish12345bisht/copyshelf}"
  local url="${COPYSHELF_TARBALL:-}"

  if [ "$(id -u)" = 0 ]; then
    echo "Please run this as your normal user, not with sudo or as root." >&2
    echo "Copyshelf installs into your home folder and asks for sudo itself if it needs packages." >&2
    exit 1
  fi
  command -v tar >/dev/null || { echo "Copyshelf's installer needs 'tar'." >&2; exit 1; }

  # Which version: COPYSHELF_REF (e.g. "main" for the development version), otherwise the
  # latest release, otherwise main if there are no releases yet.
  if [ -z "$url" ]; then
    local ref="${COPYSHELF_REF:-}" kind=heads
    if [ -z "$ref" ]; then
      ref=$(fetch "https://api.github.com/repos/$repo/releases/latest" 2>/dev/null \
            | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1 || true)
      kind=tags
    fi
    if [ -z "$ref" ]; then
      ref=main kind=heads
    fi
    if [ "$kind" = heads ] && [ -n "${COPYSHELF_REF:-}" ]; then
      echo "Using the '$ref' branch (development version)."
    fi
    url="https://github.com/$repo/archive/refs/$kind/$ref.tar.gz"
    echo "Downloading Copyshelf ${ref}..."
  else
    echo "Downloading Copyshelf..."
  fi

  # Not `local`: the cleanup below runs after main() has returned.
  COPYSHELF_TMP=$(mktemp -d)
  trap 'rm -rf "$COPYSHELF_TMP"' EXIT
  local tmp=$COPYSHELF_TMP

  fetch "$url" | tar -xz -C "$tmp" --strip-components=1
  bash "$tmp/install.sh" "$@"
}

main "$@"
