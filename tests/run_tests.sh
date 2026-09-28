#!/usr/bin/env bash
# Headless test run for Asset Vault.
#
#   tests/run_tests.sh [path/to/blender.exe]
#
# Blender gets throwaway script and config folders, so the add-on is enabled and
# driven without touching the real user configuration, the real add-on folder or
# any real asset library.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=tests/find_tools.sh
source "$REPO/tests/find_tools.sh"
BLENDER="${1:-$(find_blender || true)}"
if [ -z "$BLENDER" ]; then
    echo "no Blender found - pass one: tests/run_tests.sh /path/to/blender.exe" >&2
    exit 2
fi
WORK="$(mktemp -d "${LOCALAPPDATA:-/tmp}/assetvault_test.XXXXXX")"
WIN_WORK="$(cygpath -w "$WORK")"
WIN_REPO="$(cygpath -w "$REPO")"
SCRIPTS="$WORK/scripts"
CONFIG="$WORK/config"
REPORT="$WORK/report.json"

mkdir -p "$SCRIPTS/addons" "$CONFIG"
cp -r "$REPO/asset_vault" "$SCRIPTS/addons/"
rm -rf "$SCRIPTS/addons/asset_vault/__pycache__"

echo "blender : $BLENDER"
echo "scripts : $WIN_WORK\\scripts"
echo

failed=0

echo "──────────────── tests/test_version_sync.sh (version has one source) ────────────────"
set +e
bash "$REPO/tests/test_version_sync.sh"
version_status=$?
set -e
[ "$version_status" -eq 0 ] || failed=1
echo

echo "──────────────── tests/test_asset_vault.py ────────────────"
LOG="$WORK/blender.log"
set +e
BLENDER_USER_SCRIPTS="$WIN_WORK\\scripts" \
BLENDER_USER_CONFIG="$WIN_WORK\\config" \
    "$BLENDER" --background --factory-startup --python-exit-code 1 \
    --python "$WIN_REPO\\tests\\test_asset_vault.py" \
    -- --report "$WIN_WORK\\report.json" --work "$WIN_WORK\\files" 2>&1 | tee "$LOG"
status="${PIPESTATUS[0]}"
set -e
echo

# Blender prints tracebacks instead of raising for some paths - catch that noise.
if grep -q "Traceback" "$LOG"; then
    echo "FAIL  unexpected traceback in Blender output:" >&2
    grep -n -A 4 "Traceback" "$LOG" | head -30 >&2
    failed=1
else
    echo "PASS  no traceback noise in Blender output"
fi
echo

if [ ! -f "$REPORT" ]; then
    echo "report: MISSING - the suite did not run to completion" >&2
    failed=1
else
    echo "report: $WIN_WORK\\report.json"
    [ "$status" -eq 0 ] || failed=1
fi

if [ "$failed" -eq 0 ]; then
    echo "ALL TESTS PASSED"
else
    echo "SOME TESTS FAILED" >&2
fi
exit "$failed"
