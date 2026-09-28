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

    The hidden tree-type field is what the node editor's Add menu filters on (see
    the note on MENU_TYPE_PROP), so it is set here rather than left to whichever
    marking path marked the group.  An asset the user hid on purpose stays hidden:
    a save is not the place to undo that.
    """
    filepath = Path(filepath) if filepath is not None else asset_path(library_dir, node_tree.name)

    marked_here = not node_tree.asset_data
    if marked_here:
        node_tree.asset_mark()
    asset = node_tree.asset_data
    original_catalog = str(asset.catalog_id)
    # asset_mark() writes the tree-type field itself, so a temporary mark still has
    # to have it taken out again when the library copy is meant to stay hidden.
    original_type = (
        None
        if marked_here
        else (asset[MENU_TYPE_PROP] if MENU_TYPE_PROP in asset else None)
    )
    stays_hidden = filepath.is_file() and menu_visibility(filepath, node_tree.name) is False

    try:
        asset.catalog_id = catalog_uuid
        tree_type = TREE_TYPE_VALUES.get(node_tree.bl_idname)
        if tree_type is not None:
            if stays_hidden:
                try:
                    del asset[MENU_TYPE_PROP]
                except (KeyError, TypeError):
                    pass
            else:
                asset[MENU_TYPE_PROP] = tree_type

        datablocks = {node_tree, *_nested_groups(node_tree)}
        bpy.data.libraries.write(str(filepath), datablocks, fake_user=True)
    finally:
        if marked_here:
            node_tree.asset_clear()
        else:
            asset.catalog_id = original_catalog
            if original_type is None:
                try:
                    del asset[MENU_TYPE_PROP]
                except (KeyError, TypeError):
                    pass
            else:
                asset[MENU_TYPE_PROP] = original_type
        _VISIBILITY_CACHE.clear()

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


# ------------------------------------------------------------------ Add menu visibility

#: Blender keeps a node group asset's tree type in a hidden field on the asset
#: metadata, and the node editor's Add menu skips every asset that does not carry
#: it (`build_catalog_tree()` in space_node/add_menu_assets.cc).  Taking the field
#: out is therefore the only way to keep an asset out of the Add menu while it
#: stays a normal asset in the Asset Browser.  The values are Blender's NTREE_*
#: enum; a test reads them back out of Blender so they cannot drift silently.
MENU_TYPE_PROP = "type"
TREE_TYPE_VALUES = {
    "ShaderNodeTree": 0,
    "CompositorNodeTree": 1,
    "TextureNodeTree": 2,
    "GeometryNodeTree": 3,
}

#: ID collections that make a library file "not ours" - a downloaded pack, or a
#: file saved by hand with more than node groups in it.  Never rewritten.
_FOREIGN_ID_COLLECTIONS = (
    "actions",
    "armatures",
    "collections",
    "curves",
    "images",
    "materials",
    "meshes",
    "objects",
    "scenes",
    "textures",
    "worlds",
)

#: (path, mtime, size) -> visibility, so a menu redraw does not re-read a file.
_VISIBILITY_CACHE: dict = {}


def load_library_groups(filepath) -> dict:
    """Node groups in a library file as {name in the file: datablock}.

    Keyed by the name the file gives them, not by the name they end up with:
    loading a group the session already has makes Blender rename the newcomer
    ("Scatter.001"), and matching on those names would silently miss.

    The list handed to `bpy.data.libraries.load` comes back holding the loaded
    datablocks instead of the names, so it is copied up front.  What comes back
    is owned by the caller and must be dropped again - see `release_groups()`.
    """
    with bpy.data.libraries.load(str(filepath), link=False) as (src, dst):
        names = [entry for entry in (src.node_groups or [])]
        dst.node_groups = list(names)
    loaded = [entry for entry in (dst.node_groups or []) if entry is not None]
    return dict(zip(names, loaded))


def release_groups(groups) -> None:
    """Drop datablocks that were loaded out of a library file.

    Without this the session would keep a second copy of every group in the file
    (and a save would then write those copies out again).
    """
    for entry in groups.values() if isinstance(groups, dict) else groups:
        try:
            bpy.data.node_groups.remove(entry)
        except Exception:
            pass


def holds_only_groups(filepath) -> bool:
    """True when that library file holds node groups and nothing else."""
    try:
        with bpy.data.libraries.load(str(filepath), link=False) as (src, _dst):
            for name in _FOREIGN_ID_COLLECTIONS:
                if list(getattr(src, name, None) or []):
                    return False
    except Exception:
        return False
    return True


def menu_visibility(filepath, group_name):
    """"Is this asset in the node Add menus?" - None when it is not ours.

    None covers both "no group of that name here" and "a group that is not an
    asset": nothing to switch either way.
    """
    filepath = Path(filepath)
    try:
        stat = filepath.stat()
        stamp = (str(filepath), group_name, stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None
    if stamp in _VISIBILITY_CACHE:
        return _VISIBILITY_CACHE[stamp]

    groups = load_library_groups(filepath)
    try:
        tree = groups.get(group_name)
        found = None if tree is None or tree.asset_data is None else MENU_TYPE_PROP in tree.asset_data
    finally:
        release_groups(groups)

    _VISIBILITY_CACHE[stamp] = found
    return found


def set_menu_visibility(filepath, group_name, visible: bool) -> tuple[bool, str]:
    """Put an asset into the node Add menus, or take it out of them.

    The file is rewritten only when it holds nothing but node groups, and the
    loaded copies are dropped again afterwards, so nothing accumulates in the
    session the user is working in.
    """
    filepath = Path(filepath)
    if not holds_only_groups(filepath):
        return False, "%s holds more than node groups - not rewriting it" % filepath.name

    groups = load_library_groups(filepath)
    parked = None
    try:
        tree = groups.get(group_name)
        if tree is None or tree.asset_data is None:
            return False, "No asset called '%s' in %s" % (group_name, filepath.name)

        # A group the session already holds forces Blender to rename the loaded copy
        # ("Name.001"), and libraries.write() stores the name a datablock carries -
        # which would rename the asset inside the library file.  Park the session's
        # own datablock for the duration and give its name back afterwards.
        if tree.name != group_name:
            occupied = bpy.data.node_groups.get(group_name)
            if occupied is not None:
                occupied.name = group_name + ".vault-parked"
                parked = occupied
            tree.name = group_name

        if visible:
            value = TREE_TYPE_VALUES.get(tree.bl_idname)
            if value is None:
                return False, "Unknown node tree type '%s'" % tree.bl_idname
            tree.asset_data[MENU_TYPE_PROP] = value
            message = "'%s' is back in the Add menu" % group_name
        else:
            try:
                del tree.asset_data[MENU_TYPE_PROP]
            except (KeyError, TypeError):
                pass
            message = "'%s' is hidden from the Add menu (still in the Asset Browser)" % group_name

        bpy.data.libraries.write(str(filepath), set(groups.values()), fake_user=True)
    finally:
        release_groups(groups)
        if parked is not None:
            try:
                parked.name = group_name
            except Exception:
                pass

    _VISIBILITY_CACHE.clear()
    return True, message

