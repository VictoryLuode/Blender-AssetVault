#!/usr/bin/env bash
# Copy the add-on into a Blender user "scripts/addons" folder.
#
#   ./install.sh                          # newest Blender found on this machine
#   ./install.sh "C:/Users/me/AppData/Roaming/Blender Foundation/Blender/4.5/scripts/addons"
#
# The folder is copied, not zipped: after this, enable "Asset Vault" in
# Edit > Preferences > Add-ons and it is loaded from there.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"

TARGET="${1:-$(find_blender_addons || true)}"
if [ -z "$TARGET" ]; then
    echo "no Blender 'scripts/addons' folder found - pass one: ./install.sh <dir>" >&2
    exit 2
fi
if [ ! -d "$TARGET" ]; then
    echo "not a folder: $TARGET" >&2
    exit 2
fi

rm -rf "$TARGET/asset_vault"
cp -r "$REPO/asset_vault" "$TARGET/asset_vault"
rm -rf "$TARGET/asset_vault/__pycache__"
echo "installed asset_vault -> $TARGET/asset_vault"
echo "now enable it: Edit > Preferences > Add-ons > search \"Asset Vault\""
