#!/usr/bin/env bash
# Publishes a new Copyshelf release:   ./release.sh 0.3.0
#
# Before running it, describe the changes in CHANGELOG.md under a "## 0.3.0 - <date>"
# heading. The script then:
#   1. checks everything is ready (clean git, in sync with GitHub, changelog written),
#   2. runs the tests,
#   3. sets the version number in the code,
#   4. after you confirm: commits, tags v0.3.0, pushes, and creates the GitHub release
#      with that changelog section as its notes.
# Within a day, everyone's Copyshelf offers them the update.
set -euo pipefail
cd "$(dirname "$0")"

die() { echo "release: $*" >&2; exit 1; }

version=${1:-}
[[ $version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "usage: ./release.sh X.Y.Z   (for example ./release.sh 0.3.0)"
tag="v$version"

# ---------- 1. Ready? ----------
command -v gh >/dev/null || die "needs the GitHub CLI: sudo apt install gh, then gh auth login"
gh auth status >/dev/null 2>&1 || die "not logged in to GitHub. Run: gh auth login"
[ "$(git branch --show-current)" = main ] || die "switch to the main branch first (git checkout main)."
[ -z "$(git status --porcelain)" ] || die "you have uncommitted changes. Commit them first (see: git status)."
git fetch -q origin
git merge-base --is-ancestor origin/main HEAD || die "GitHub has commits you don't have. Run: git pull"
! git rev-parse -q --verify "refs/tags/$tag" >/dev/null || die "$tag already exists."

last_tag=$(git describe --tags --abbrev=0 2>/dev/null || true)
if [ -n "$last_tag" ]; then
  python3 -c 'import sys; v = lambda s: tuple(map(int, s.lstrip("v").split(".")))
sys.exit(v(sys.argv[1]) <= v(sys.argv[2]))' "$version" "$last_tag" \
    || die "$version must be newer than the last release, $last_tag."
fi

# The release notes: everything under "## <version>" up to the next "## " heading.
notes=$(awk -v v="$version" '/^## / { if (found) exit; if ($2 == v) { found = 1; next } } found' CHANGELOG.md)
[ -n "$(echo "$notes" | tr -d '[:space:]')" ] \
  || die "CHANGELOG.md has no notes for $version. Add a '## $version - $(date +%F)' section first."

# GNOME only loads extension code at login, so tell users when this release changes it.
if [ -z "$last_tag" ] || ! git diff --quiet "$last_tag" HEAD -- gnome-extension/; then
  extension_changed=true
else
  extension_changed=false
fi

# ---------- 2. Tests ----------
echo "Running the tests..."
python3 -m pytest -q || die "the tests failed, so nothing was released."

# ---------- 3. Version numbers ----------
python3 - "$version" "$extension_changed" <<'EOF'
import json, re, sys
version, extension_changed = sys.argv[1], sys.argv[2] == "true"

def set_line(path, pattern, line):
    text = open(path).read()
    new, count = re.subn(pattern, line, text, count=1, flags=re.M)
    if count != 1:
        sys.exit(f"release: couldn't find the version line in {path}")
    open(path, "w").write(new)

set_line("copyshelf/__init__.py", r'^__version__ = ".*"$', f'__version__ = "{version}"')
set_line("pyproject.toml", r'^version = ".*"$', f'version = "{version}"')
if extension_changed:   # the extension's own version only changes when its code does
    path = "gnome-extension/metadata.json"
    data = json.load(open(path))
    data["version-name"] = version
    open(path, "w").write(json.dumps(data, indent=2) + "\n")
EOF

# ---------- 4. Publish ----------
echo
echo "Ready to release Copyshelf $version ($tag)."
echo "Release notes:"
while IFS= read -r line; do echo "    $line"; done <<< "$notes"
$extension_changed && echo "(The GNOME extension changed: users will be told to log out and back in.)"
echo
read -r -p "Publish it now? This pushes to GitHub and notifies users. [y/N] " answer
if [[ ! $answer =~ ^[Yy] ]]; then
  git checkout -q -- copyshelf/__init__.py pyproject.toml gnome-extension/metadata.json
  die "cancelled; nothing was changed."
fi

git add copyshelf/__init__.py pyproject.toml gnome-extension/metadata.json
git diff --cached --quiet || git commit -q -m "Release $version"
git tag -a "$tag" -m "Copyshelf $version"
git push -q origin main "$tag"

notes_file=$(mktemp)
trap 'rm -f "$notes_file"' EXIT
{
  echo "$notes"
  if $extension_changed; then
    printf '\n<!-- copyshelf:needs-relogin -->\n'
  fi
} > "$notes_file"
gh release create "$tag" --title "Copyshelf $version" --notes-file "$notes_file" --verify-tag

echo
echo "Released! https://github.com/ashish12345bisht/copyshelf/releases/tag/$tag"
