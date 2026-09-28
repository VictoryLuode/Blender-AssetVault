"""Where a saved group goes: the target library, its catalog file, its .blend file.

A node group is stored as one .blend file inside the library folder, holding
nothing but that group (plus whatever groups it nests).  Saving and updating are
the same write - that is what makes an update cheap and predictable: there is
exactly one copy in the library, and it is always the last one saved.

Nothing here touches the file the user is working in, and nothing here goes
through the Asset Browser's catalog service: the catalog definition file is
plain text, so the add-on appends its line directly.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import bpy

CATALOG_FILE = "blender_assets.cats.txt"
DEFAULT_CATALOG = "Group"

# Special entries in the Asset Browser's library enum - not libraries of ours.
_NON_LIBRARY_REFS = {"LOCAL", "CURRENT", "ESSENTIALS", "ALL"}

# Everything Windows refuses in a file name, plus the control characters.
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Long enough for real group names, short enough for any filesystem.
_MAX_FILENAME = 150

_CATALOG_HEADER = (
    b"# This is an Asset Catalog Definition file for Blender.\n"
    b"#\n"
    b"# Empty lines and lines starting with `#` will be ignored.\n"
    b"# The first non-ignored line should be the version indicator.\n"
    b'# Other lines are of the format "UUID:catalog/path/for/assets:simple catalog name"\n'
    b"\n"
    b"VERSION 1\n"
    b"\n"
)


def sanitize(name: str) -> str:
    """A node group name as a file name: recognisable, and always writable."""
    clean = _INVALID_FILENAME.sub("_", name or "").strip().rstrip(". ")
    return clean[:_MAX_FILENAME] or "Unnamed"


def user_libraries() -> list[tuple[str, str]]:
    """(name, absolute path) for every asset library Blender knows about."""
    out: list[tuple[str, str]] = []
    for lib in bpy.context.preferences.filepaths.asset_libraries:
        path = bpy.path.abspath(lib.path)
        if path:
            out.append((lib.name, path))
    return out


def library_path(name: str) -> str | None:
    """Absolute path of the library called `name`, or None."""
    for lib_name, path in user_libraries():
        if lib_name == name:
            return path
    return None


def active_library_name(context) -> str | None:
    """The library selected in an Asset Browser, if this window has one open."""
    screen = getattr(context, "screen", None)
    for area in getattr(screen, "areas", ()):
        if area.type != 'ASSET_BROWSER':
            continue
        params = getattr(area.spaces.active, "params", None)
        # 4.x renamed this one; read whichever this Blender has.
        ref = getattr(params, "asset_library_reference", None)
        if ref is None:
            ref = getattr(params, "asset_library_ref", None)
        if not ref or ref in _NON_LIBRARY_REFS:
            continue
        if library_path(ref):
            return ref
    return None


def target_library(context, prefs) -> tuple[str, str] | None:
    """Where the next save goes: the Asset Browser's library, else the preference.

    Deliberately no falling back to "whichever library happens to be first": a
    save that lands in a library nobody named is worse than a save that says it
    could not decide.  The preference defaults to the first configured library
    when it has never been set, so the out-of-the-box path still works.
    """
    if prefs is not None and getattr(prefs, "follow_asset_browser", False):
        name = active_library_name(context)
        if name:
            path = library_path(name)
            if path:
                return name, path

    name = getattr(prefs, "default_library", "") if prefs is not None else ""
    path = library_path(name) if name else None
    if path:
        return name, path
    return None


def read_catalogs(library_dir: str) -> list[tuple[str, str]]:
    """(uuid, catalog path) pairs from a library's catalog definition file."""
    filepath = Path(library_dir) / CATALOG_FILE
    rows: list[tuple[str, str]] = []
    if not filepath.is_file():
        return rows
    with filepath.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("VERSION"):
                continue
            parts = line.split(":", 2)
            if len(parts) >= 2 and parts[0] and parts[1]:
                rows.append((parts[0], parts[1]))
    return rows


def ensure_catalog(library_dir: str, catalog_path: str) -> str:
    """UUID of `catalog_path` in that library, adding the catalog when missing.

    The catalog file is appended to in binary mode, so every byte the Asset
    Browser wrote - CRLF endings, non-ASCII catalog names - survives untouched.
    Blender's catalog service reads the file when it next loads that library; if
    the user edits catalogs in the Asset Browser before that, its in-memory copy
    can overwrite this line, and the next save puts it back.
    """
    catalog_path = (catalog_path or DEFAULT_CATALOG).strip().strip("/") or DEFAULT_CATALOG

    for existing_uuid, path in read_catalogs(library_dir):
        if path == catalog_path:
            return existing_uuid

    new_uuid = str(uuid.uuid4())
    simple_name = catalog_path.replace("/", "-")
    line = "%s:%s:%s" % (new_uuid, catalog_path, simple_name)

    filepath = Path(library_dir) / CATALOG_FILE
    raw = filepath.read_bytes() if filepath.is_file() else b""
    head = b"" if raw else _CATALOG_HEADER
    if raw and not raw.endswith((b"\n", b"\r")):
        head = b"\n"  # never glue a new line onto a half-written one
    newline = b"\r\n" if b"\r\n" in raw else b"\n"

    with filepath.open("ab") as handle:
        handle.write(head + line.encode("utf-8") + newline)
    return new_uuid


def asset_path(library_dir: str, group_name: str) -> Path:
    """The library file this group is (or would be) stored in."""
    return Path(library_dir) / (sanitize(group_name) + ".blend")


def find_copy(library_dir: str, group_name: str) -> Path | None:
    """The group's file in that library, if it is already there."""
    filepath = asset_path(library_dir, group_name)
    return filepath if filepath.is_file() else None


def contains_group(filepath, group_name: str) -> bool:
    """Does that library file actually hold a node group of this name?

    Checked before any overwrite: a same-named file that this add-on did not
    write must never be replaced, so the decision is made on the file's
    contents, never on its name.
    """
    filepath = str(filepath)
    try:
        with bpy.data.libraries.load(filepath, link=False, assets_only=True) as (src, _dst):
            names = list(src.node_groups or [])
    except Exception:
        return False
    return group_name in names


def _nested_groups(node_tree, seen=None) -> list:
    """Every group this one uses, depth first.

    Collected explicitly rather than trusting the writer to follow pointers: the
    set that goes into the library file is then decided here, in one place.
    """
    seen = set() if seen is None else seen
    found = []
    for node in getattr(node_tree, "nodes", ()):
        inner = getattr(node, "node_tree", None)
        if inner is None or inner.name in seen:
            continue
        seen.add(inner.name)
        found.append(inner)
        found.extend(_nested_groups(inner, seen))
    return found


def write_group(library_dir: str, node_tree, catalog_uuid: str, filepath=None) -> Path:
    """Write the group into its own .blend inside the library, nested groups included.

    The asset mark and the catalog only exist for the duration of the write - the
    catalog id has to be on the datablock for Blender to store it, but a save must
    not change anything in the file the user is working in.
    """
    filepath = Path(filepath) if filepath is not None else asset_path(library_dir, node_tree.name)

    marked_here = not node_tree.asset_data
    if marked_here:
        node_tree.asset_mark()
    original_catalog = str(node_tree.asset_data.catalog_id)

    try:
        node_tree.asset_data.catalog_id = catalog_uuid
        datablocks = {node_tree, *_nested_groups(node_tree)}
        bpy.data.libraries.write(str(filepath), datablocks, fake_user=True)
    finally:
        if marked_here:
            node_tree.asset_clear()
        else:
            node_tree.asset_data.catalog_id = original_catalog

    return filepath


def refresh_libraries() -> str:
    """Ask Blender to re-read the asset libraries so the new file shows up now.

    Both of these operators want an Asset Browser in the context; when there is
    none the listing still catches up on its own, so a failure here is not fatal
    and is reported rather than raised.
    """
    for op_name in ("library_refresh", "library_reload_listing"):
        operator = getattr(bpy.ops.asset, op_name, None)
        if operator is None:
            continue
        try:
            if operator.poll():
                operator()
                return op_name
        except Exception:
            continue
    return ""
