#!/usr/bin/env bash
# The version lives in three places and all three have to agree:
#   asset_vault/__init__.py  ->  __version__
#   asset_vault/__init__.py  ->  bl_info["version"]   (must stay a *literal*: Blender
#                               reads it with ast.literal_eval, so no tuple()
#                               built from __version__ - that hides the add-on)
#   CHANGELOG.md             ->  top "## vX.Y.Z" heading (what the user reads)

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INIT="$REPO/asset_vault/__init__.py"
code_version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$INIT")"
literal_version="$(grep -m1 -E '^ *"version": *\([0-9]+, *[0-9]+, *[0-9]+\)' "$INIT" \
    | sed -E 's/^ *"version": *\(([0-9]+), *([0-9]+), *([0-9]+)\).*/\1.\2.\3/')"
changelog_version="$(grep -m1 -E '^## ' "$REPO/CHANGELOG.md" | sed -E 's/^## +v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"

failed=0
if [ -z "$code_version" ]; then
    echo "FAIL  no __version__ in asset_vault/__init__.py" >&2
    failed=1
fi
if [ -z "$literal_version" ]; then
    echo "FAIL  no literal bl_info[\"version\"] tuple in asset_vault/__init__.py" >&2
    echo "      (Blender 5.x reads bl_info with ast.literal_eval - a computed value" >&2
    echo "       makes the add-on invisible in Preferences)" >&2
    failed=1
fi
if [ -n "$code_version" ] && [ "$code_version" != "$literal_version" ]; then
    echo "FAIL  __version__ is $code_version but bl_info[\"version\"] is ${literal_version:-missing}" >&2
    failed=1
fi
if [ -n "$code_version" ] && [ "$code_version" != "$changelog_version" ]; then
    echo "FAIL  asset_vault/__init__.py says $code_version, CHANGELOG.md top entry says '${changelog_version:-nothing}'" >&2
    failed=1
fi
[ "$failed" -eq 0 ] || exit 1

echo "PASS  version sync: $code_version (bl_info + CHANGELOG agree)"
