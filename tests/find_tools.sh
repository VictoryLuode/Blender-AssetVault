#!/usr/bin/env bash
# Locate the tools this project drives.  Sourced by the scripts, not run.
#
#   source tests/find_tools.sh
#   BLENDER="$(find_blender)"
#
# Every function honours its explicit override first (BLENDER, BLENDER_ADDON_DIR,
# BLENDER_CONFIG_DIR), then searches the usual locations and returns the newest
# match.  Nothing here assumes a user name or a drive letter.
#
# Globs go through nullglob arrays on purpose: `compgen -G` returns only the
# first match under MSYS, which silently picks the wrong build.

# the filesystem a path lives on: ntfs for a local disk, smbfs for a mapped share
fs_type_of() {
    local drive
    drive="$(df -P "$1" 2>/dev/null | tail -1 | awk '{print $1}')"
    case "$drive" in
        [A-Za-z]:) mount 2>/dev/null | awk -v d="$drive" '$1 == d { print $5; exit }' ;;
        *) printf '%s\n' "" ;;
    esac
}

# newest Blender executable
find_blender() {
    if [ -n "${BLENDER:-}" ] && [ -f "$BLENDER" ]; then
        printf '%s\n' "$BLENDER"
        return 0
    fi
    local had_nullglob=0
    if shopt -q nullglob; then had_nullglob=1; fi
    shopt -s nullglob

    local -a all=()
    local drive

    # a normal installer
    all+=( "$HOME"/AppData/Local/Programs/Blender*/*/blender.exe )
    all+=( "/c/Program Files/Blender Foundation"/Blender*/*/blender.exe )
    all+=( "/d/Program Files/Blender Foundation"/Blender*/*/blender.exe )

    # Blender Launcher keeps its build library under Scoop's persist folder
    for drive in /c /d /e /f /g /h; do
        [ -d "$drive" ] || continue
        all+=( $drive/Scoop/persist/blender-launcher/BlenderBuilds/*/*/blender.exe )
        all+=( $drive/Scoop/apps/blender-launcher/current/BlenderBuilds/*/*/blender.exe )
    done

    # a build folder of its own, wherever the documents tree currently lives
    all+=( "$HOME"/BlenderBuilds/*/*/blender.exe )
    all+=( "$HOME"/Documents/Blender/BlenderBuilds/*/*/blender.exe )
    for drive in /c /d /e /f /g /h; do
        [ -d "$drive" ] || continue
        all+=( $drive/home/Documents/Blender/BlenderBuilds/*/*/blender.exe )
        all+=( $drive/Documents/Blender/BlenderBuilds/*/*/blender.exe )
    done

    if [ "$had_nullglob" -eq 0 ]; then shopt -u nullglob; fi
    if [ ${#all[@]} -eq 0 ]; then return 1; fi

    # A build on a mapped network drive cannot be started here at all - Windows
    # fails with "side-by-side configuration is incorrect" - so when both kinds
    # are present, the local ones win.
    local -a local=()
    local candidate
    for candidate in "${all[@]}"; do
        case "$(fs_type_of "$candidate")" in
            smbfs|nfs|cifs|net) continue ;;
        esac
        local+=( "$candidate" )
    done
    if [ ${#local[@]} -gt 0 ]; then
        all=( "${local[@]}" )
    fi

    printf '%s\n' "${all[@]}" | sort -V | tail -1
}

# newest Blender user "scripts/addons" folder - where the add-on gets installed
find_blender_addons() {
    if [ -n "${BLENDER_ADDON_DIR:-}" ]; then
        printf '%s\n' "$BLENDER_ADDON_DIR"
        return 0
    fi
    local had_nullglob=0
    if shopt -q nullglob; then had_nullglob=1; fi
    shopt -s nullglob
    local root="${BLENDER_CONFIG_DIR:-$HOME/AppData/Roaming/Blender Foundation/Blender}"
    local -a group=( "$root"/*/scripts/addons )
    if [ "$had_nullglob" -eq 0 ]; then shopt -u nullglob; fi
    if [ ${#group[@]} -eq 0 ]; then return 1; fi
    printf '%s\n' "${group[@]}" | sort -V | tail -1
}
